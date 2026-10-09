"""ORM helpers for session_character and character_preset tables (spec 005).

Low-level helpers; callers are responsible for committing the transaction.
All session-scoped reads return ordered by ``slot_index`` ASC to make
prompt-construction deterministic. See data-model.md and FR-011.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CharacterGroupPreset, CharacterPreset, History, SessionCharacter

# ---------------------------------------------------------------------------
# SessionCharacter helpers
# ---------------------------------------------------------------------------


async def fetch_session_characters(
    db: AsyncSession, session_id: str
) -> Sequence[SessionCharacter]:
    """Return all characters of ``session_id`` ordered by slot_index ASC."""
    stmt = (
        select(SessionCharacter)
        .where(SessionCharacter.session_id == session_id)
        .order_by(SessionCharacter.slot_index.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def fetch_session_character(
    db: AsyncSession, character_id: str
) -> SessionCharacter | None:
    """Return one SessionCharacter or None."""
    stmt = select(SessionCharacter).where(SessionCharacter.id == character_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def fetch_protagonist_session_character(
    db: AsyncSession, session_id: str
) -> SessionCharacter | None:
    """Return the is_protagonist record for a session, or None."""
    stmt = (
        select(SessionCharacter)
        .where(
            SessionCharacter.session_id == session_id,
            SessionCharacter.is_protagonist.is_(True),
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def insert_session_character(
    db: AsyncSession,
    *,
    session_id: str,
    name: str,
    slot_index: int = 0,
    appearance_natural: str = "",
    appearance_tags: str = "",
    position: str = "center",
    source_preset_id: str | None = None,
    is_protagonist: bool = False,
    appearance_lock: bool = False,
    exclude_from_effects: bool = False,
    negative_tags: str = "",
    profile_json: str | None = None,
    on_stage: bool = True,
    thumbnail_url: str | None = None,
    appearance_spec_rev: int = 0,
) -> SessionCharacter:
    """Insert one SessionCharacter and return the persisted instance."""
    record = SessionCharacter(
        id=uuid.uuid4().hex,
        session_id=session_id,
        slot_index=slot_index,
        name=name,
        appearance_natural=appearance_natural,
        appearance_tags=appearance_tags,
        position=position,
        source_preset_id=source_preset_id,
        is_protagonist=is_protagonist,
        appearance_lock=appearance_lock,
        exclude_from_effects=exclude_from_effects,
        negative_tags=negative_tags,
        profile_json=profile_json,
        on_stage=on_stage,
        thumbnail_url=thumbnail_url,
        appearance_spec_rev=appearance_spec_rev,
    )
    db.add(record)
    await db.flush()
    return record


async def update_session_character(
    db: AsyncSession,
    character_id: str,
    **patch: Any,
) -> SessionCharacter | None:
    """Apply partial update to one SessionCharacter; returns updated row or None."""
    record = await fetch_session_character(db, character_id)
    if record is None:
        return None
    allowed = {
        "name",
        "appearance_natural",
        "appearance_tags",
        "position",
        "slot_index",
        "source_preset_id",
        "is_protagonist",
        "appearance_lock",
        "exclude_from_effects",
        "negative_tags",
        "profile_json",
        "on_stage",
        "thumbnail_url",
        "appearance_spec_rev",
    }
    for key, value in patch.items():
        if key in allowed and value is not None:
            setattr(record, key, value)
    await db.flush()
    return record


async def fetch_latest_character_states(
    db: AsyncSession,
    session_id: str,
    *,
    until: datetime | None = None,
) -> str | None:
    """Return the newest non-NULL ``history.character_states_json`` of a session.

    Turns without per-character tags store NULL, so skipping them keeps the
    last drawn look instead of falling back to the settings. ``until`` limits
    the search to histories created at or before that time (session branch).
    """
    stmt = select(History.character_states_json).where(
        History.session_id == session_id,
        History.character_states_json.is_not(None),
    )
    if until is not None:
        stmt = stmt.where(History.created_at <= until)
    stmt = stmt.order_by(History.created_at.desc(), History.id.desc()).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_session_character(db: AsyncSession, character_id: str) -> int:
    """Delete one SessionCharacter; returns number of rows removed."""
    stmt = sa_delete(SessionCharacter).where(SessionCharacter.id == character_id)
    result = await db.execute(stmt)
    return result.rowcount or 0


async def delete_non_protagonist_session_characters(
    db: AsyncSession, session_id: str
) -> int:
    """Delete every non-protagonist character of a session; returns rows removed."""
    stmt = sa_delete(SessionCharacter).where(
        SessionCharacter.session_id == session_id,
        SessionCharacter.is_protagonist.is_(False),
    )
    result = await db.execute(stmt)
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# CharacterPreset helpers
# ---------------------------------------------------------------------------


async def fetch_character_presets(
    db: AsyncSession,
) -> Sequence[CharacterPreset]:
    """Return all presets ordered by name ASC."""
    stmt = select(CharacterPreset).order_by(CharacterPreset.name.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


async def fetch_character_preset(
    db: AsyncSession, preset_id: str
) -> CharacterPreset | None:
    """Return one CharacterPreset or None."""
    stmt = select(CharacterPreset).where(CharacterPreset.id == preset_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def insert_character_preset(
    db: AsyncSession,
    *,
    name: str,
    appearance_natural: str = "",
    appearance_tags: str = "",
    default_position: str = "center",
    tags_meta: str | None = None,
    negative_tags: str = "",
    profile_json: str | None = None,
    thumbnail_url: str | None = None,
) -> CharacterPreset:
    """Insert a new preset; returns the persisted instance."""
    record = CharacterPreset(
        id=uuid.uuid4().hex,
        name=name,
        appearance_natural=appearance_natural,
        appearance_tags=appearance_tags,
        default_position=default_position,
        tags_meta=tags_meta,
        negative_tags=negative_tags,
        profile_json=profile_json,
        thumbnail_url=thumbnail_url,
    )
    db.add(record)
    await db.flush()
    return record


async def update_character_preset(
    db: AsyncSession,
    preset_id: str,
    **patch: Any,
) -> CharacterPreset | None:
    """Partial update of a preset. Returns the updated row or None."""
    record = await fetch_character_preset(db, preset_id)
    if record is None:
        return None
    allowed = {
        "name",
        "appearance_natural",
        "appearance_tags",
        "default_position",
        "tags_meta",
        "negative_tags",
        "profile_json",
        "thumbnail_url",
    }
    for key, value in patch.items():
        if key in allowed and value is not None:
            setattr(record, key, value)
    await db.flush()
    return record


async def delete_character_preset(db: AsyncSession, preset_id: str) -> int:
    """Delete a preset; returns rows removed."""
    stmt = sa_delete(CharacterPreset).where(CharacterPreset.id == preset_id)
    result = await db.execute(stmt)
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# CharacterGroupPreset helpers
# ---------------------------------------------------------------------------


async def fetch_character_group_presets(
    db: AsyncSession,
) -> Sequence[CharacterGroupPreset]:
    """Return all group presets ordered by name ASC."""
    stmt = select(CharacterGroupPreset).order_by(CharacterGroupPreset.name.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


async def fetch_character_group_preset(
    db: AsyncSession, group_id: str
) -> CharacterGroupPreset | None:
    """Return one CharacterGroupPreset or None."""
    stmt = select(CharacterGroupPreset).where(CharacterGroupPreset.id == group_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def insert_character_group_preset(
    db: AsyncSession, *, name: str, members_json: str
) -> CharacterGroupPreset:
    """Insert a new group preset; returns the persisted instance."""
    record = CharacterGroupPreset(
        id=uuid.uuid4().hex,
        name=name,
        members_json=members_json,
    )
    db.add(record)
    await db.flush()
    return record


async def update_character_group_preset(
    db: AsyncSession,
    group_id: str,
    **patch: Any,
) -> CharacterGroupPreset | None:
    """Partial update of a group preset. Returns the updated row or None."""
    record = await fetch_character_group_preset(db, group_id)
    if record is None:
        return None
    allowed = {"name", "members_json"}
    for key, value in patch.items():
        if key in allowed and value is not None:
            setattr(record, key, value)
    await db.flush()
    return record


async def delete_character_group_preset(db: AsyncSession, group_id: str) -> int:
    """Delete a group preset; returns rows removed."""
    stmt = sa_delete(CharacterGroupPreset).where(CharacterGroupPreset.id == group_id)
    result = await db.execute(stmt)
    return result.rowcount or 0


__all__ = [
    "fetch_session_characters",
    "fetch_session_character",
    "insert_session_character",
    "update_session_character",
    "delete_session_character",
    "delete_non_protagonist_session_characters",
    "fetch_latest_character_states",
    "fetch_character_presets",
    "fetch_character_preset",
    "insert_character_preset",
    "update_character_preset",
    "delete_character_preset",
    "fetch_character_group_presets",
    "fetch_character_group_preset",
    "insert_character_group_preset",
    "update_character_group_preset",
    "delete_character_group_preset",
]
