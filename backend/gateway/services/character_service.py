"""SessionCharacter / CharacterPreset business logic (spec 005).

Distinct from existing ``services/characters.py`` which handles single-person
mode profiles. This module manages persisted multi-character state.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from ..databases.character_repo import (
    delete_character_preset,
    delete_session_character,
    fetch_character_preset,
    fetch_character_presets,
    fetch_protagonist_session_character,
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
        appearance_lock: bool = False,
        exclude_from_effects: bool = False,
    ) -> SessionCharacter:
        existing = list(await fetch_session_characters(db, session_id))
        non_protagonist_count = sum(1 for r in existing if not r.is_protagonist)
        if non_protagonist_count >= CHARACTER_LIMIT:
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
            appearance_lock=appearance_lock,
            exclude_from_effects=exclude_from_effects,
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
        Protagonist (is_protagonist=True) is always placed at slot 0;
        non-protagonist records follow in their existing relative order.
        """
        records = list(await fetch_session_characters(db, session_id))
        # protagonist first, then others by current slot_index
        protagonist = [r for r in records if r.is_protagonist]
        others = [r for r in records if not r.is_protagonist]
        ordered = protagonist + others
        for new_index, record in enumerate(ordered):
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
        markers: list[str] = []
        if getattr(rec, "exclude_from_effects", False):
            markers.append("[指示対象外・外見を変更しない]")
        if getattr(rec, "appearance_lock", False):
            markers.append("[外見ロック中]")
        marker_str = (" " + " ".join(markers)) if markers else ""
        lines.append(f"- {rec.name}（{', '.join(descriptor_bits)}）{marker_str}")
    lines.append("上記の登場人物が同じ場面に共存している前提で描写してください。")
    lines.append(
        "「指示対象外」とマークされた人物にはユーザー指示の効果（着替え・行動・現実改変等）を適用せず、"
        "現在の外見をそのまま保ってください。"
    )
    return "\n".join(lines)


async def load_session_characters_for_prompt(
    db: AsyncSession,
    session_id: str,
) -> list[SessionCharacter]:
    """Single-query loader for prompt assembly (FR-011)."""
    return await fetch_session_characters(db, session_id)


async def upsert_protagonist_session_character(
    db: AsyncSession,
    session_id: str,
    *,
    name: str,
    appearance_tags: str,
) -> SessionCharacter:
    """Create or update the protagonist session_character for a session.

    Called on every play turn when multi-person mode is active so the
    CharacterPanel always reflects the current protagonist identity (FR-010).
    The record is always placed at slot_index=0, position=center.
    """
    existing = await fetch_protagonist_session_character(db, session_id)
    if existing is None:
        record = await insert_session_character(
            db,
            session_id=session_id,
            slot_index=0,
            name=name,
            appearance_natural="",
            appearance_tags=appearance_tags,
            position="center",
            is_protagonist=True,
        )
        # Shift non-protagonist records to start at slot 1
        await SessionCharacterService.reassign_positions(db, session_id)
        return record
    # Update only when values have changed to avoid unnecessary writes.
    # appearance_lock / exclude_from_effects が True の場合は外見タグを上書きしない
    # (名前はメタ情報のため例外的に更新可能)
    appearance_locked = bool(
        getattr(existing, "appearance_lock", False)
        or getattr(existing, "exclude_from_effects", False)
    )
    patch: dict = {}
    if existing.name != name:
        patch["name"] = name
    if not appearance_locked and existing.appearance_tags != appearance_tags:
        patch["appearance_tags"] = appearance_tags
    if patch:
        await update_session_character(db, existing.id, **patch)
        await db.refresh(existing)
    return existing


_POSITION_LABEL_EN = {
    "left": "left",
    "center-left": "center-left",
    "center": "center",
    "center-right": "center-right",
    "right": "right",
}


def build_novelai_characters_section(
    records: Sequence[SessionCharacter],
    *,
    protagonist_name: str | None = None,
    protagonist_tags: str | None = None,
) -> str:
    """Build an English NovelAI-image prompt section from session-character records.

    Returns an empty string when there are no records with useful tag/name data
    so callers can append the result unconditionally (FR-010 / FR-012).

    Records with ``is_protagonist=True`` are rendered first with a [protagonist]
    marker. ``protagonist_name`` / ``protagonist_tags`` kwargs act as a fallback
    for callers that resolve the identity before the DB record is created
    (i.e. the very first upsert turn). When both a DB protagonist record and
    kwargs are supplied, the DB record takes precedence.
    """
    # Sort: protagonist first (slot_index=0), then others by slot_index.
    sorted_records = sorted(
        records, key=lambda r: (0 if r.is_protagonist else 1, r.slot_index)
    )

    # Check whether we have a protagonist via DB record or kwargs fallback.
    db_has_protagonist = any(r.is_protagonist for r in sorted_records)
    kwarg_tags = (protagonist_tags or "").strip()
    has_protagonist = db_has_protagonist or bool(kwarg_tags)

    if not sorted_records and not has_protagonist:
        return ""

    lines: list[str] = [
        "",
        "## Registered Characters (MUST appear in image, MUST use these tags as-is)",
    ]

    counter = 1
    protagonist_emitted = False
    for rec in sorted_records:
        position = _POSITION_LABEL_EN.get(rec.position, rec.position)
        tags = (rec.appearance_tags or "").strip()
        natural = (rec.appearance_natural or "").strip()
        descriptor: list[str] = [f"position: {position}"]
        if tags:
            descriptor.append(f"tags: {tags}")
        elif natural:
            descriptor.append(f"appearance: {natural}")
        marker_parts: list[str] = []
        if rec.is_protagonist:
            marker_parts.append("[protagonist]")
        if getattr(rec, "exclude_from_effects", False):
            marker_parts.append(
                "[bystander, do NOT apply user instruction effects, keep tags exactly]"
            )
        if getattr(rec, "appearance_lock", False):
            marker_parts.append("[appearance locked, keep tags exactly]")
        marker = (" " + " ".join(marker_parts)) if marker_parts else ""
        lines.append(
            f"- Character {counter} ({rec.name}, {', '.join(descriptor)}){marker}"
        )
        if rec.is_protagonist:
            protagonist_emitted = True
        counter += 1

    # Fallback: kwargs-only protagonist (first play turn before upsert is committed)
    if not protagonist_emitted and kwarg_tags:
        name = (protagonist_name or "Protagonist").strip() or "Protagonist"
        descriptor = ["position: center", f"tags: {kwarg_tags}"]
        lines.insert(
            2,  # after the header line
            f"- Character 1 ({name}, {', '.join(descriptor)}) [protagonist]",
        )
        # renumber the rest
        renumbered: list[str] = [lines[0], lines[1], lines[2]]
        for i, line in enumerate(lines[3:], start=2):
            if line.startswith("- Character "):
                renumbered.append(
                    line.replace(f"Character {i - 1} ", f"Character {i} ", 1)
                )
            else:
                renumbered.append(line)
        lines = renumbered

    lines.append(
        "All listed characters MUST be present in the image alongside the main "
        "subject; preserve their tags exactly."
    )
    return "\n".join(lines)


def extract_protagonist_tags_from_history(
    after_description: str | None,
) -> str | None:
    """Extract the protagonist appearance tags from a prior history entry.

    When multi-character mode is active, ``after_description`` is stored as a
    JSON document of the form ``{"characters": [{"tags": "...", ...}, ...],
    "scene": "..."}``. The first entry in ``characters`` is conventionally the
    protagonist; we return its ``tags`` field. Returns ``None`` for legacy
    plain-text descriptions or any malformed payload (FR-010 protect existing
    sessions).
    """
    if not after_description:
        return None
    text = after_description.strip()
    # Strip optional ```json ... ``` code fences (single-line or multi-line).
    if text.startswith("```"):
        # Remove leading fence with optional language tag.
        # Handles both ``` followed by newline and ```json followed by space/newline.
        rest = text[3:]
        # Drop optional language tag (e.g. "json") up to the first whitespace.
        idx = 0
        while idx < len(rest) and not rest[idx].isspace():
            idx += 1
        text = rest[idx:].lstrip()
        if text.endswith("```"):
            text = text[: -len("```")].rstrip()
    # JSON object may be embedded with trailing prose; take the first {...} block.
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    # Multi-character format: {"characters": [{"tags": "...", ...}, ...]}
    characters = data.get("characters")
    if isinstance(characters, list) and characters:
        first = characters[0]
        if isinstance(first, dict):
            tags = first.get("tags")
            if isinstance(tags, str):
                tags_stripped = tags.strip()
                if tags_stripped:
                    return tags_stripped
    # Single-character format: {"character": "...", "scene": "..."}
    # 単一キャラ format でも主人公タグとして扱う (FR-010 dress-up bug fix)
    single = data.get("character")
    if isinstance(single, str):
        single_stripped = single.strip()
        if single_stripped:
            return single_stripped
    return None


def resolve_protagonist_image_identity(
    *,
    last_after_description: str | None,
    character: Any | None,
    self_profile: dict | None,
    custom_metadata: dict | None,
) -> tuple[str | None, str | None]:
    """Resolve the protagonist's display name and appearance tags for the
    NovelAI image prompt's Registered Characters section (FR-010).

    Priority for tags:
        1. JSON-parsed ``characters[0].tags`` from the previous turn's
           ``after_description`` (preserves continuity across turns).
        2. ``custom_metadata.base_tags`` -> ``self_profile.appearance_tags``
           -> ``character.base_tags``. Used both for new sessions and for
           legacy plain-text histories: without protagonist tags the LLM
           tends to merge supporting-character traits into the main subject,
           so a base-tag fallback is safer than skipping the entry entirely.

    The display name is taken from custom metadata, the self-profile, or the
    template character in that order, defaulting to ``"Protagonist"``.
    """
    custom_metadata = custom_metadata or {}

    extracted = extract_protagonist_tags_from_history(last_after_description)
    if extracted:
        tags: str | None = extracted
    else:
        candidates = (
            (custom_metadata.get("base_tags") or "").strip(),
            ((self_profile or {}).get("appearance_tags") or "").strip(),
            ((getattr(character, "base_tags", "") if character else "") or "").strip(),
        )
        tags = next((c for c in candidates if c), None)

    if not tags:
        return (None, None)

    name_candidates = (
        (custom_metadata.get("name") or "").strip(),
        ((self_profile or {}).get("name") or "").strip(),
        ((getattr(character, "name", "") if character else "") or "").strip(),
    )
    name = next((c for c in name_candidates if c), "Protagonist")
    return (name, tags)


__all__ = [
    "ALLOWED_POSITIONS",
    "CHARACTER_LIMIT",
    "CharacterLimitExceededError",
    "CharacterPresetService",
    "SessionCharacterService",
    "apply_appearance_updates",
    "build_novelai_characters_section",
    "build_session_characters_prompt_section",
    "extract_protagonist_tags_from_history",
    "load_session_characters_for_prompt",
    "resolve_protagonist_image_identity",
    "upsert_protagonist_session_character",
]
