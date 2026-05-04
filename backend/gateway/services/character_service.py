"""SessionCharacter / CharacterPreset business logic (spec 005).

Distinct from existing ``services/characters.py`` which handles single-person
mode profiles. This module manages persisted multi-character state.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from ..databases.character_repo import (
    delete_character_preset,
    delete_session_character,
    fetch_character_preset,
    fetch_character_presets,
    fetch_session_character,
    fetch_session_characters,
    insert_character_preset,
    insert_session_character,
    update_character_preset,
    update_session_character,
)
from ..databases.models import CharacterPreset, SessionCharacter

logger = logging.getLogger(__name__)


CHARACTER_LIMIT = 4
ALLOWED_POSITIONS = (
    "left",
    "center-left",
    "center",
    "center-right",
    "right",
)


class CharacterLimitExceededError(ValueError):
    """Raised when adding would exceed CHARACTER_LIMIT for the session."""

    def __init__(self) -> None:
        super().__init__("character_limit_exceeded")


# ---------------------------------------------------------------------------
# SessionCharacterService
# ---------------------------------------------------------------------------


class SessionCharacterService:
    """Application service for SessionCharacter rows."""

    @staticmethod
    async def list_for_session(
        db: AsyncSession, session_id: str
    ) -> Sequence[SessionCharacter]:
        return await fetch_session_characters(db, session_id)

    @staticmethod
    async def create_in_session(
        db: AsyncSession,
        session_id: str,
        *,
        name: str,
        appearance_natural: str = "",
        appearance_tags: str = "",
        position: str = "center",
        slot_index: Optional[int] = None,
        source_preset_id: Optional[str] = None,
    ) -> SessionCharacter:
        existing = list(await fetch_session_characters(db, session_id))
        if len(existing) >= CHARACTER_LIMIT:
            raise CharacterLimitExceededError()
        if position not in ALLOWED_POSITIONS:
            raise ValueError(f"invalid_position:{position}")
        if slot_index is None:
            slot_index = len(existing)
        record = await insert_session_character(
            db,
            session_id=session_id,
            slot_index=slot_index,
            name=name,
            appearance_natural=appearance_natural,
            appearance_tags=appearance_tags,
            position=position,
            source_preset_id=source_preset_id,
        )
        await SessionCharacterService.reassign_positions(db, session_id)
        return record

    @staticmethod
    async def update(
        db: AsyncSession,
        character_id: str,
        **patch: Any,
    ) -> Optional[SessionCharacter]:
        if "position" in patch and patch["position"] is not None:
            if patch["position"] not in ALLOWED_POSITIONS:
                raise ValueError(f"invalid_position:{patch['position']}")
        record = await update_session_character(db, character_id, **patch)
        if record is not None and "slot_index" in patch:
            await SessionCharacterService.reassign_positions(db, record.session_id)
        return record

    @staticmethod
    async def delete(db: AsyncSession, character_id: str) -> bool:
        record = await fetch_session_character(db, character_id)
        if record is None:
            return False
        session_id = record.session_id
        await delete_session_character(db, character_id)
        await SessionCharacterService.reassign_positions(db, session_id)
        return True

    @staticmethod
    async def reassign_positions(db: AsyncSession, session_id: str) -> None:
        """Re-pack ``slot_index`` to be 0..N-1 ordered by current slot_index ASC.

        Implements R-005 last-write-wins re-numbering.
        """
        records = list(await fetch_session_characters(db, session_id))
        for new_index, record in enumerate(records):
            if record.slot_index != new_index:
                record.slot_index = new_index
        await db.flush()

    @staticmethod
    async def apply_preset_to_session(
        db: AsyncSession,
        session_id: str,
        preset_id: str,
    ) -> SessionCharacter:
        preset = await fetch_character_preset(db, preset_id)
        if preset is None:
            raise LookupError("preset_not_found")
        return await SessionCharacterService.create_in_session(
            db,
            session_id,
            name=preset.name,
            appearance_natural=preset.appearance_natural,
            appearance_tags=preset.appearance_tags,
            position=preset.default_position,
            source_preset_id=preset.id,
        )


# ---------------------------------------------------------------------------
# CharacterPresetService
# ---------------------------------------------------------------------------


class CharacterPresetService:
    """Application service for CharacterPreset rows (global)."""

    @staticmethod
    async def list_presets(
        db: AsyncSession,
    ) -> Sequence[CharacterPreset]:
        return await fetch_character_presets(db)

    @staticmethod
    async def create_preset_raw(
        db: AsyncSession,
        *,
        name: str,
        appearance_natural: str = "",
        appearance_tags: str = "",
        default_position: str = "center",
    ) -> CharacterPreset:
        if default_position not in ALLOWED_POSITIONS:
            raise ValueError(f"invalid_position:{default_position}")
        return await insert_character_preset(
            db,
            name=name,
            appearance_natural=appearance_natural,
            appearance_tags=appearance_tags,
            default_position=default_position,
        )

    @staticmethod
    async def create_preset_from_character(
        db: AsyncSession,
        *,
        from_character_id: str,
        name: str,
    ) -> CharacterPreset:
        source = await fetch_session_character(db, from_character_id)
        if source is None:
            raise LookupError("session_character_not_found")
        return await insert_character_preset(
            db,
            name=name,
            appearance_natural=source.appearance_natural,
            appearance_tags=source.appearance_tags,
            default_position=source.position,
        )

    @staticmethod
    async def update_preset(
        db: AsyncSession,
        preset_id: str,
        **patch: Any,
    ) -> Optional[CharacterPreset]:
        if (
            "default_position" in patch
            and patch["default_position"] is not None
            and patch["default_position"] not in ALLOWED_POSITIONS
        ):
            raise ValueError(f"invalid_position:{patch['default_position']}")
        return await update_character_preset(db, preset_id, **patch)

    @staticmethod
    async def delete_preset(db: AsyncSession, preset_id: str) -> bool:
        existing = await fetch_character_preset(db, preset_id)
        if existing is None:
            return False
        await delete_character_preset(db, preset_id)
        return True


# ---------------------------------------------------------------------------
# Appearance-update bridge (filled by US2 in T030)
# ---------------------------------------------------------------------------


async def apply_appearance_updates(
    db: AsyncSession,
    session_id: str,
    updates: list[dict[str, Any]],
) -> int:
    """Apply LLM-inferred appearance updates to SessionCharacter rows.

    Args:
        db: Active AsyncSession (caller commits).
        session_id: Owning session id.
        updates: List of dicts conforming to research R-002 schema:
            ``{character_id, changed, appearance_natural?, appearance_tags?}``.

    Returns:
        Number of rows updated.
    """
    if not updates:
        return 0
    by_id = {c.id: c for c in await fetch_session_characters(db, session_id)}
    written = 0
    for entry in updates:
        if not isinstance(entry, dict):
            continue
        if not entry.get("changed"):
            continue
        cid = entry.get("character_id")
        if not cid or cid not in by_id:
            continue
        patch: dict[str, Any] = {}
        nat = entry.get("appearance_natural")
        tags = entry.get("appearance_tags")
        if isinstance(nat, str) and nat != "":
            patch["appearance_natural"] = nat
        if isinstance(tags, str) and tags != "":
            patch["appearance_tags"] = tags
        if not patch:
            continue
        await update_session_character(db, cid, **patch)
        written += 1
    return written


_POSITION_LABEL_JA = {
    "left": "左",
    "center-left": "中央左",
    "center": "中央",
    "center-right": "中央右",
    "right": "右",
}


def build_session_characters_prompt_section(
    records: Sequence[SessionCharacter],
) -> str:
    """Build a Japanese prompt fragment from session-character records.

    Returns an empty string when there are no records, so callers can append
    the result unconditionally and fall back to existing single-character
    behavior automatically (FR-011 / SC-003).
    """
    if not records:
        return ""

    sorted_records = sorted(records, key=lambda r: r.slot_index)
    lines: list[str] = ["", "[同シーンの登場キャラクター一覧]"]
    for rec in sorted_records:
        position_label = _POSITION_LABEL_JA.get(rec.position, rec.position)
        natural = (rec.appearance_natural or "").strip()
        tags = (rec.appearance_tags or "").strip()
        descriptor_bits: list[str] = [f"位置={position_label}"]
        if natural:
            descriptor_bits.append(f"外見: {natural}")
        if tags:
            descriptor_bits.append(f"タグ: {tags}")
        lines.append(f"- {rec.name}（{', '.join(descriptor_bits)}）")
    lines.append("上記の登場人物が同じ場面に共存している前提で描写してください。")
    return "\n".join(lines)


async def load_session_characters_for_prompt(
    db: AsyncSession,
    session_id: str,
) -> list[SessionCharacter]:
    """Single-query loader for prompt assembly (FR-011)."""
    return await fetch_session_characters(db, session_id)


_POSITION_LABEL_EN = {
    "left": "left",
    "center-left": "center-left",
    "center": "center",
    "center-right": "center-right",
    "right": "right",
}


def build_novelai_characters_section(
    records: Sequence[SessionCharacter],
) -> str:
    """Build an English NovelAI-image prompt section from session-character records.

    Returns an empty string when there are no records so callers can append
    the result unconditionally (FR-010 / FR-012).
    """
    if not records:
        return ""

    sorted_records = sorted(records, key=lambda r: r.slot_index)
    lines: list[str] = [
        "",
        "## Registered Characters (MUST appear in image, MUST use these tags as-is)",
    ]
    for idx, rec in enumerate(sorted_records, start=1):
        position = _POSITION_LABEL_EN.get(rec.position, rec.position)
        tags = (rec.appearance_tags or "").strip()
        natural = (rec.appearance_natural or "").strip()
        descriptor: list[str] = [f"position: {position}"]
        if tags:
            descriptor.append(f"tags: {tags}")
        elif natural:
            descriptor.append(f"appearance: {natural}")
        lines.append(f"- Character {idx} ({rec.name}, {', '.join(descriptor)})")
    lines.append(
        "All listed characters MUST be present in the image alongside the main "
        "subject; preserve their tags exactly."
    )
    return "\n".join(lines)


__all__ = [
    "ALLOWED_POSITIONS",
    "CHARACTER_LIMIT",
    "CharacterLimitExceededError",
    "CharacterPresetService",
    "SessionCharacterService",
    "apply_appearance_updates",
    "build_novelai_characters_section",
    "build_session_characters_prompt_section",
    "load_session_characters_for_prompt",
]
