"""キャラクター(CharacterPreset)の立ち絵の保存・取り込み・生成。

立ち絵は data/character_images/{preset_id}/ に置き、portrait_path に data 相対パスを、
thumbnail_url に配信 URL(API 相対)を持つ。素材(セッション・お気に入り・
Prompt Expander)の画像を取り込むか、外見タグから描く。生成はキャラチャットの
立ち絵と同じ generate_portrait_bytes を使う。
"""

from __future__ import annotations

import logging
import shutil
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from ..consts.novelai_models import resolve_user_image_model
from ..databases.base import async_session_factory
from ..databases.character_repo import fetch_character_preset
from ..databases.models import CharacterPreset
from ..settings.config import settings
from .character_profile import CharacterSourceNotFoundError, resolve_character_source
from .character_service import record_profile, with_gender_token
from .cost_tracker import begin_cost_tracking
from .image_paths import resolve_stored_image_path
from .portrait_generation import PortraitGenerationError, generate_portrait_bytes
from .providers import Provider, resolve_image_provider
from .session import session_store
from .source_snapshot import SourceSnapshotError, build_source_snapshot

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_SOURCE_PREFIX = "source-"
_GENERATED_PREFIX = "portrait-"


class CharacterPresetPortraitError(RuntimeError):
    """立ち絵の取り込み・生成に失敗した。code は API のエラーコード。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def preset_images_dir() -> Path:
    return settings.history_images_dir.parent / "character_images"


def _preset_dir(preset_id: str) -> Path:
    return preset_images_dir() / preset_id


def _stored_path(preset_id: str, filename: str) -> str:
    """DB に保存する data 相対パス(resolve_stored_image_path で解決できる形)。"""
    return f"character_images/{preset_id}/{filename}"


def preset_image_url(preset_id: str, filename: str) -> str:
    return f"/game/character-presets/{preset_id}/images/{filename}"


def preset_portrait_file(preset: CharacterPreset) -> Path | None:
    if not preset.portrait_path:
        return None
    local = _preset_dir(preset.id) / Path(preset.portrait_path).name
    if local.is_file():
        return local
    resolved = resolve_stored_image_path(preset.portrait_path)
    return resolved if resolved is not None and resolved.is_file() else None


def preset_portrait_url(preset: CharacterPreset) -> str | None:
    path = preset_portrait_file(preset)
    return preset_image_url(preset.id, path.name) if path is not None else None


def preset_image_file(preset_id: str, filename: str) -> Path:
    """配信する画像の実ファイル。パス区切りは name だけに落として無害化する。"""
    name = Path(filename).name
    if not name or Path(preset_id).name != preset_id:
        raise CharacterPresetPortraitError("image_not_found", "画像が見つかりません")
    candidate = _preset_dir(preset_id) / name
    if not candidate.is_file():
        raise CharacterPresetPortraitError("image_not_found", "画像が見つかりません")
    return candidate


def remove_preset_images(preset_id: str) -> None:
    if Path(preset_id).name != preset_id:
        return
    shutil.rmtree(_preset_dir(preset_id), ignore_errors=True)


def _set_portrait(preset: CharacterPreset, filename: str) -> None:
    """立ち絵を差し替え、前の画像ファイルを消す(サムネイルも同じ画像にする)。"""
    previous = Path(preset.portrait_path).name if preset.portrait_path else ""
    preset.portrait_path = _stored_path(preset.id, filename)
    preset.thumbnail_url = preset_image_url(preset.id, filename)
    if previous and previous != filename:
        (_preset_dir(preset.id) / previous).unlink(missing_ok=True)


def attach_preset_portrait(
    preset: CharacterPreset, source: Path, *, generated: bool
) -> None:
    """既存の画像ファイルをキャラクターの立ち絵として写す(呼び出し側が commit する)。

    generated は外見タグから描いた立ち絵(白抜きして表示する)かどうか。
    """
    suffix = source.suffix.lower()
    if suffix not in _IMAGE_SUFFIXES:
        suffix = ".png"
    directory = _preset_dir(preset.id)
    directory.mkdir(parents=True, exist_ok=True)
    prefix = _GENERATED_PREFIX if generated else _SOURCE_PREFIX
    filename = f"{prefix}{uuid.uuid4().hex[:8]}{suffix}"
    shutil.copyfile(source, directory / filename)
    _set_portrait(preset, filename)


def preset_portrait_is_generated(preset: CharacterPreset) -> bool:
    """立ち絵が外見タグから描いたものか(素材から取り込んだ画像は False)。"""
    return Path(str(preset.portrait_path or "")).name.startswith(_GENERATED_PREFIX)


async def import_preset_portrait(
    preset_id: str,
    *,
    session_id: str | None,
    history_id: str | None,
    prompt_expander_entry_id: str | None,
) -> tuple[CharacterPreset, dict[str, Any]]:
    """素材の画像を立ち絵として取り込み、(更新後のプリセット, 取り出した名前と外見) を返す。

    外見タグが空のキャラクターには、素材の外見を入れる(名前は変えない)。
    """
    try:
        _snapshot, image_path, _tags, _nsfw = await build_source_snapshot(
            session_id,
            history_id,
            source_prompt_expander_entry_id=prompt_expander_entry_id,
        )
        resolved = await resolve_character_source(
            session_id=session_id,
            history_id=history_id,
            prompt_expander_entry_id=prompt_expander_entry_id,
        )
    except SourceSnapshotError as exc:
        raise CharacterPresetPortraitError(exc.code, str(exc)) from exc
    except CharacterSourceNotFoundError as exc:
        raise CharacterPresetPortraitError("source_not_found", str(exc)) from exc
    async with async_session_factory() as db:
        preset = await fetch_character_preset(db, preset_id)
        if preset is None:
            raise CharacterPresetPortraitError(
                "preset_not_found", "キャラクターが見つかりません"
            )
        attach_preset_portrait(preset, Path(image_path), generated=False)
        if not preset.appearance_tags.strip() and not preset.appearance_natural.strip():
            preset.appearance_tags = str(resolved.get("appearance_tags") or "")
            preset.appearance_natural = str(resolved.get("appearance_natural") or "")
        await db.commit()
        await db.refresh(preset)
        return preset, resolved


async def stream_preset_portrait(
    preset_id: str, *, use_precise_reference: bool = False
) -> AsyncGenerator[dict[str, Any], None]:
    """外見タグから立ち絵を描く。いまの立ち絵があれば参照画像にする。

    use_precise_reference は NovelAI の精密参照(Anlas 消費)で、FE が確認済みの前提。

    Yields:
        status{phase: portrait} / portrait_image{preset} の素(dict) / cost{cost_usd} /
        complete{}
    """
    tracker = begin_cost_tracking()
    async with async_session_factory() as db:
        preset = await fetch_character_preset(db, preset_id)
        if preset is None:
            raise CharacterPresetPortraitError(
                "preset_not_found", "キャラクターが見つかりません"
            )
        tags = with_gender_token(preset.appearance_tags.strip(), record_profile(preset))
        reference = preset_portrait_file(preset)
    if not tags:
        raise CharacterPresetPortraitError(
            "portrait_unavailable", "外見タグがありません"
        )
    user_settings = await session_store.get_user_settings()
    nsfw_mode = bool(user_settings.get("nsfw_mode"))
    provider = resolve_image_provider()
    image_model = (
        resolve_user_image_model(user_settings, nsfw_mode)
        if provider == Provider.NOVELAI
        else None
    )
    yield {"event": "status", "data": {"phase": "portrait"}}
    try:
        data = await generate_portrait_bytes(
            tags=tags,
            nsfw_mode=nsfw_mode,
            provider=provider,
            image_model=image_model,
            reference_bytes=reference.read_bytes() if reference is not None else None,
            use_character_reference=use_precise_reference,
        )
    except PortraitGenerationError as exc:
        raise CharacterPresetPortraitError(exc.code, str(exc)) from exc
    except Exception as exc:
        logger.warning(
            "character preset portrait generation failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        detail = str(exc) or type(exc).__name__
        raise CharacterPresetPortraitError(
            "image_generation_failed", f"立ち絵の生成に失敗しました({detail})"
        ) from exc
    async with async_session_factory() as db:
        preset = await fetch_character_preset(db, preset_id)
        if preset is None:
            raise CharacterPresetPortraitError(
                "preset_not_found", "キャラクターが見つかりません"
            )
        directory = _preset_dir(preset.id)
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{_GENERATED_PREFIX}{uuid.uuid4().hex[:8]}.png"
        (directory / filename).write_bytes(data)
        _set_portrait(preset, filename)
        await db.commit()
        await db.refresh(preset)
        yield {"event": "portrait_image", "data": {"preset": preset}}
    if tracker.total_usd > 0:
        yield {"event": "cost", "data": {"cost_usd": tracker.total_usd}}
    yield {"event": "complete", "data": {}}


__all__ = [
    "CharacterPresetPortraitError",
    "attach_preset_portrait",
    "import_preset_portrait",
    "preset_image_file",
    "preset_image_url",
    "preset_images_dir",
    "preset_portrait_file",
    "preset_portrait_is_generated",
    "preset_portrait_url",
    "remove_preset_images",
    "stream_preset_portrait",
]
