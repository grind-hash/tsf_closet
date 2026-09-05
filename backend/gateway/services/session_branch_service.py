"""Branch a new game session from an existing history image.

Creates a new session that continues from a selected history snapshot,
with an LLM-generated situation summary instead of the default "初期状態".
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from ..databases.base import async_session_factory
from ..databases.character_repo import (
    fetch_session_characters,
    insert_session_character,
)
from ..schemas.session import BranchSessionResponse
from ..settings.config import settings
from .session import session_store
from .summary_service import summary_service

logger = logging.getLogger(__name__)


class SessionBranchError(Exception):
    """Raised when branching cannot proceed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _copy_custom_session_metadata(source_session_id: str, new_session_id: str) -> None:
    src = settings.history_images_dir / "custom" / f"session_{source_session_id}.json"
    if not src.exists():
        return
    dest = settings.history_images_dir / "custom" / f"session_{new_session_id}.json"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    except OSError as exc:
        logger.warning(
            "Failed to copy custom session metadata %s -> %s: %s",
            src,
            dest,
            exc,
        )


def _copy_surroundings_image(
    source_path: str | None,
    new_history_id: str,
) -> str | None:
    if not source_path:
        return None
    raw = Path(source_path)
    candidates = [
        raw,
        settings.history_images_dir.parent / source_path,
        settings.history_images_dir / raw.name,
    ]
    src_file: Path | None = None
    for path in candidates:
        try:
            if path.is_file():
                src_file = path
                break
        except OSError:
            continue
    if src_file is None:
        return None

    surroundings_dir = settings.history_images_dir / "surroundings"
    surroundings_dir.mkdir(parents=True, exist_ok=True)
    dest_file = surroundings_dir / f"{new_history_id}.png"
    try:
        shutil.copy2(src_file, dest_file)
    except OSError as exc:
        logger.warning("Failed to copy surroundings image: %s", exc)
        return None
    return str(dest_file.relative_to(settings.history_images_dir.parent))


async def _copy_session_characters(source_session_id: str, new_session_id: str) -> None:
    """Best-effort copy of current session_characters (no historical snapshot)."""
    async with async_session_factory() as db_session:
        records = list(await fetch_session_characters(db_session, source_session_id))
        for rec in records:
            await insert_session_character(
                db_session,
                session_id=new_session_id,
                name=rec.name,
                slot_index=rec.slot_index,
                appearance_natural=rec.appearance_natural or "",
                appearance_tags=rec.appearance_tags or "",
                position=rec.position or "center",
                source_preset_id=rec.source_preset_id,
                is_protagonist=bool(rec.is_protagonist),
                appearance_lock=bool(getattr(rec, "appearance_lock", False)),
                exclude_from_effects=bool(getattr(rec, "exclude_from_effects", False)),
            )
        await db_session.commit()


async def branch_session_from_history(
    history_id: str,
    *,
    inherit_stats: bool = True,
    self_mode: bool | None = None,
    language: str | None = None,
) -> BranchSessionResponse:
    """Create a new session branched from the given history entry."""
    source_history = await session_store.get_history_by_id(history_id)
    if source_history is None:
        raise SessionBranchError("history_not_found", "履歴が見つかりません")

    source_session = await session_store.get_session_by_id(source_history.session_id)
    if source_session is None:
        raise SessionBranchError("session_not_found", "セッションが見つかりません")

    image_path = session_store.resolve_history_image_file(source_history)
    if image_path is None:
        raise SessionBranchError(
            "image_not_found",
            "分岐元の画像ファイルが見つかりません",
        )
    image_bytes = image_path.read_bytes()

    source_stats = await session_store.get_session_stats(source_session.id)
    difficulty = source_stats.difficulty if source_stats else "normal"
    nsfw_mode = source_stats.nsfw_mode if source_stats else False
    # 未指定時は分岐元を引き継ぐ。明示指定で自分自身モードのON/OFF切替が可能
    effective_self_mode = (
        bool(source_session.self_mode) if self_mode is None else bool(self_mode)
    )

    user_settings = await session_store.get_user_settings()
    effective_language = language or user_settings.get("language") or "ja"

    timeline = await session_store.get_session_timeline_until(
        source_session.id,
        until_created_at=source_history.created_at,
        limit=30,
    )
    appearance = (
        source_history.after_description or source_history.before_description or ""
    )
    branch_summary = await summary_service.generate_branch_situation_summary(
        timeline,
        appearance_description=appearance,
        language=effective_language,
        fallback_instruction=source_history.instruction,
    )

    # Deactivate current active session, then create the branch session
    await session_store.reset_session()

    new_session = await session_store.create_session(
        image_path=source_history.image_path,
        character_id=source_session.character_id,
        self_mode=effective_self_mode,
    )
    _copy_custom_session_metadata(source_session.id, new_session.id)

    # 自動メモ・ユーザーメモ（本文と有効フラグ）を引き継ぐ
    try:
        await session_store.copy_play_memory(source_session.id, new_session.id)
    except Exception as exc:
        logger.warning("Failed to copy play memory: %s", exc)

    transform_count = await session_store.count_transformations_until(
        source_session.id,
        history_id,
    )
    # Avoid daily-life first-turn prompts when branching from a non-initial image
    if transform_count == 0 and source_history.instruction not in (
        "初期状態",
        "(初期状態)",
    ):
        transform_count = 1
    if transform_count > 0:
        await session_store.update_session(
            new_session.id,
            transformation_count=transform_count,
        )

    if inherit_stats:
        reconstructed = await session_store.reconstruct_stats_at_history(
            source_session.id,
            history_id,
            difficulty=difficulty,
            nsfw_mode=nsfw_mode,
        )
        stats = await session_store.create_session_stats(
            new_session.id, difficulty, nsfw_mode
        )
        stats.bloom = reconstructed.bloom
        stats.shame = reconstructed.shame
        stats.adaptation = reconstructed.adaptation
        stats.passed_critical_points = list(reconstructed.passed_critical_points)
        await session_store.update_session_stats(stats)
    else:
        await session_store.create_session_stats(new_session.id, difficulty, nsfw_mode)

    # Attributes created at or before the branch point
    for attr in await session_store.get_session_attributes(source_session.id):
        created_raw = attr.get("created_at")
        include = True
        if created_raw:
            try:
                created_at = datetime.fromisoformat(str(created_raw))
                include = created_at <= source_history.created_at
            except (TypeError, ValueError):
                include = True
        if include:
            await session_store.add_session_attribute(
                new_session.id,
                attr["attribute_text"],
            )

    try:
        await _copy_session_characters(source_session.id, new_session.id)
    except Exception as exc:
        logger.warning("Failed to copy session characters: %s", exc)

    # Temporary history id for surroundings naming; add_history generates its own id
    # so we copy surroundings after knowing the real history id if needed.
    # add_history accepts surroundings_image_path string; prepare after first write.
    desc = appearance or None
    new_history = await session_store.add_history(
        session_id=new_session.id,
        instruction=branch_summary,
        image_data=image_bytes,
        feeling_text=branch_summary,
        before_description=desc,
        after_description=desc,
        instruction_type="session_branch",
    )

    if source_history.surroundings_image_path:
        new_surroundings = _copy_surroundings_image(
            source_history.surroundings_image_path,
            new_history.id,
        )
        if new_surroundings:
            await session_store.update_history_surroundings(
                new_history.id,
                new_surroundings,
            )

    # Ensure current_image_path points at the newly written history image
    await session_store.update_session(
        new_session.id,
        current_image_path=new_history.image_path,
        transformation_count=transform_count,
    )

    response = await session_store.get_full_session_response(new_session.id)
    if response is None:
        raise SessionBranchError(
            "branch_failed",
            "新規セッションの構築に失敗しました",
        )

    return BranchSessionResponse(
        **response.model_dump(),
        branch_summary=branch_summary,
        source_session_id=source_session.id,
        source_history_id=history_id,
        inherit_stats=inherit_stats,
    )
