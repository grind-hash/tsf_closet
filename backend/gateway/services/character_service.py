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
from ..consts.character_limits import (
    APPEARANCE_NATURAL_MAX_LEN,
    APPEARANCE_TAGS_MAX_LEN,
)

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


async def apply_character_prompt_tags(
    db: AsyncSession,
    session_id: str,
    character_prompts: Sequence[dict[str, Any]],
) -> int:
    """Write confirmed image-generation character prompts into session rows.

    ``character_prompts`` is the Opus-split list of
    ``{"prompt": "<tags>", "position": ...}`` (index 0 = protagonist).
    Rows with ``appearance_lock`` / ``exclude_from_effects`` are skipped.
    Non-protagonist rows are matched by ``slot_index`` (0-based).

    Returns the number of rows updated.
    """
    if not character_prompts:
        return 0
    records = await fetch_session_characters(db, session_id)
    if not records:
        return 0
    by_slot = {r.slot_index: r for r in records}
    protagonist = next((r for r in records if r.is_protagonist), None)
    written = 0

    for idx, entry in enumerate(character_prompts):
        if not isinstance(entry, dict):
            continue
        tags = entry.get("prompt")
        if not isinstance(tags, str):
            continue
        tags_stripped = tags.strip()
        if not tags_stripped:
            continue

        target: SessionCharacter | None = None
        if idx == 0 and protagonist is not None:
            target = protagonist
        else:
            target = by_slot.get(idx)

        if target is None:
            continue
        if getattr(target, "appearance_lock", False) or getattr(
            target, "exclude_from_effects", False
        ):
            continue
        if (target.appearance_tags or "") == tags_stripped:
            continue
        await update_session_character(db, target.id, appearance_tags=tags_stripped)
        written += 1
    return written


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
        record = by_id[cid]
        # 保護フラグが立っているキャラはサーバ側で無視する（LLM 指示違反への安全網）
        if getattr(record, "appearance_lock", False) or getattr(
            record, "exclude_from_effects", False
        ):
            logger.info(
                "apply_appearance_updates: skip protected character "
                "(id=%s, lock=%s, exclude=%s)",
                cid,
                getattr(record, "appearance_lock", False),
                getattr(record, "exclude_from_effects", False),
            )
            continue
        patch: dict[str, Any] = {}
        nat = entry.get("appearance_natural")
        tags = entry.get("appearance_tags")
        if isinstance(nat, str) and nat != "":
            if len(nat) > APPEARANCE_NATURAL_MAX_LEN:
                logger.info(
                    "apply_appearance_updates: truncate appearance_natural "
                    "(id=%s, %d -> %d chars)",
                    cid,
                    len(nat),
                    APPEARANCE_NATURAL_MAX_LEN,
                )
                nat = nat[:APPEARANCE_NATURAL_MAX_LEN].rstrip()
            patch["appearance_natural"] = nat
        if isinstance(tags, str) and tags != "":
            if len(tags) > APPEARANCE_TAGS_MAX_LEN:
                logger.info(
                    "apply_appearance_updates: truncate appearance_tags "
                    "(id=%s, %d -> %d chars)",
                    cid,
                    len(tags),
                    APPEARANCE_TAGS_MAX_LEN,
                )
                tags = tags[:APPEARANCE_TAGS_MAX_LEN].rstrip().rstrip(",")
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


def _parse_history_after_description_json(
    after_description: str | None,
) -> dict | None:
    """Parse the JSON payload from a stored ``after_description`` string.

    Strips optional ``\u0060\u0060\u0060json`` fences and recovers from trailing prose by
    extracting the first ``{...}`` block. Returns ``None`` for legacy plain-text
    descriptions or any malformed payload.
    """
    if not after_description:
        return None
    text = after_description.strip()
    if text.startswith("```"):
        rest = text[3:]
        idx = 0
        while idx < len(rest) and not rest[idx].isspace():
            idx += 1
        text = rest[idx:].lstrip()
        if text.endswith("```"):
            text = text[: -len("```")].rstrip()
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
    return data


def extract_characters_from_history(
    after_description: str | None,
) -> list[dict] | None:
    """Return the ``characters`` array from a multi-character history entry.

    Returns ``None`` for single-character format ``{"character": "..."}`` or
    any other shape. Used to restore non-protagonist appearance after a
    history delete/edit.
    """
    data = _parse_history_after_description_json(after_description)
    if data is None:
        return None
    characters = data.get("characters")
    if not isinstance(characters, list) or not characters:
        return None
    return [c for c in characters if isinstance(c, dict)]


def _looks_like_novelai_tag_list(text: str) -> bool:
    """Heuristic: treat comma-separated NovelAI-style prompts as tag lists.

    Used when ``after_description`` stores the character prompt string directly
    (Opus JSON-split success path) rather than a JSON envelope.
    """
    stripped = text.strip()
    if not stripped or len(stripped) < 8:
        return False
    # Japanese free-text history (non-Opus dress-up) is not tags.
    narrative_markers = (
        "に変身した姿",
        "という現実改変",
        "により変化した姿",
        "transformed appearance",
        "after transforming",
    )
    if any(marker in stripped for marker in narrative_markers):
        return False
    # Narrative Japanese sentences without tag separators are not tags.
    if "。" in stripped or "、" in stripped:
        return False
    lower = stripped.lower()
    has_subject = any(
        token in lower
        for token in (
            "1girl",
            "1boy",
            "1other",
            "2girls",
            "2boys",
            "solo",
            "multiple girls",
            "multiple boys",
        )
    )
    comma_count = stripped.count(",")
    if has_subject and comma_count >= 1:
        return True
    # Quality-tag heavy prompts without explicit 1girl/1boy still count.
    if comma_count >= 2 and any(
        token in lower
        for token in (
            "masterpiece",
            "best quality",
            "amazing quality",
            "very aesthetic",
        )
    ):
        return True
    return False


def extract_protagonist_tags_from_history(
    after_description: str | None,
) -> str | None:
    """Extract the protagonist appearance tags from a prior history entry.

    Supported shapes:
    1. Multi-character JSON:
       ``{"characters": [{"tags": "...", ...}, ...], "scene": "..."}``
    2. Single-character JSON:
       ``{"character": "...", "scene": "..."}``
    3. Plain NovelAI tag list (character prompt stored as ``after_description``
       after a successful Opus JSON split).

    Returns ``None`` for Japanese narrative descriptions or malformed payloads.
    """
    if not after_description:
        return None
    data = _parse_history_after_description_json(after_description)
    if data is not None:
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

    # Opus success path stores character prompt as a plain tag string.
    plain = after_description.strip()
    if _looks_like_novelai_tag_list(plain):
        return plain
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
        ((self_profile or {}).get("display_name") or "").strip(),
        ((getattr(character, "name", "") if character else "") or "").strip(),
    )
    name = next((c for c in name_candidates if c), "Protagonist")
    return (name, tags)


async def restore_session_characters_appearance_from_history(
    session_id: str,
) -> int:
    """Reset SessionCharacter rows so they reflect the latest remaining
    history after a delete/edit.

    Protagonist (slot_index=0):
        Resolution priority is delegated to
        :func:`resolve_protagonist_image_identity`, which prefers
        ``characters[0].tags`` extracted from the previous history's
        ``after_description`` and falls back to base/self-profile tags when no
        history JSON remains. Both ``name`` and ``appearance_tags`` may be
        updated.

    Non-protagonist rows (slot_index >= 1):
        Restored only when the latest remaining history is a multi-character
        JSON payload. ``slot_index`` is matched against the array index in
        ``characters[i].tags``. If the payload is single-character format,
        absent, or the index is missing, the row is left untouched (no
        fallback exists for non-protagonist tags). Only ``appearance_tags``
        is updated.

    Per-row skip conditions (both protagonist and others):
        - ``appearance_lock`` is True
        - ``exclude_from_effects`` is True

    Returns the number of rows actually mutated.
    """
    # Lazy imports to avoid circular dependencies (services -> routes etc.)
    from ..databases.base import async_session_factory
    from .characters import character_manager
    from .game_service import game_service
    from .session import session_store

    async with async_session_factory() as db:
        records = await fetch_session_characters(db, session_id)
        if not records:
            return 0

    session = await session_store.get_session_by_id(session_id)
    if session is None:
        return 0

    character = None
    if getattr(session, "character_id", None):
        character = character_manager.get_by_id(session.character_id)

    self_profile: dict | None = None
    if getattr(session, "self_mode", False):
        self_profile = await session_store.get_self_profile()

    custom_metadata = game_service._load_custom_session_metadata(session_id)
    last_history = await session_store.get_latest_history(session_id)
    last_after_description = last_history.after_description if last_history else None

    history_characters = extract_characters_from_history(last_after_description)

    # Resolve protagonist identity (with fallback) up-front.
    protagonist_name, protagonist_tags = resolve_protagonist_image_identity(
        last_after_description=last_after_description,
        character=character,
        self_profile=self_profile,
        custom_metadata=custom_metadata,
    )

    updated_count = 0
    async with async_session_factory() as db:
        records = await fetch_session_characters(db, session_id)
        for rec in sorted(records, key=lambda r: r.slot_index):
            if getattr(rec, "appearance_lock", False) or getattr(
                rec, "exclude_from_effects", False
            ):
                continue

            patch: dict = {}
            if rec.is_protagonist:
                if not protagonist_tags:
                    continue
                if protagonist_name and rec.name != protagonist_name:
                    patch["name"] = protagonist_name
                if rec.appearance_tags != protagonist_tags:
                    patch["appearance_tags"] = protagonist_tags
            else:
                # Non-protagonist: only restore when multi-char JSON history
                # provides an entry at the matching slot index.
                if history_characters is None:
                    continue
                idx = rec.slot_index
                if idx < 0 or idx >= len(history_characters):
                    continue
                entry = history_characters[idx]
                tags = entry.get("tags") if isinstance(entry, dict) else None
                if not isinstance(tags, str):
                    continue
                tags_stripped = tags.strip()
                if not tags_stripped:
                    continue
                if rec.appearance_tags != tags_stripped:
                    patch["appearance_tags"] = tags_stripped

            if not patch:
                continue
            await update_session_character(db, rec.id, **patch)
            updated_count += 1

        if updated_count:
            await db.commit()
            logger.info(
                "Restored session characters appearance after history change "
                "(session=%s, updated=%d)",
                session_id,
                updated_count,
            )
    return updated_count


__all__ = [
    "ALLOWED_POSITIONS",
    "CHARACTER_LIMIT",
    "CharacterLimitExceededError",
    "CharacterPresetService",
    "SessionCharacterService",
    "apply_appearance_updates",
    "apply_character_prompt_tags",
    "build_novelai_characters_section",
    "build_session_characters_prompt_section",
    "extract_characters_from_history",
    "extract_protagonist_tags_from_history",
    "load_session_characters_for_prompt",
    "resolve_protagonist_image_identity",
    "restore_session_characters_appearance_from_history",
    "upsert_protagonist_session_character",
]
