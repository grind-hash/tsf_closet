"""ORM helpers for session_character and character_preset tables (spec 005).

Low-level helpers; callers are responsible for committing the transaction.
All session-scoped reads return ordered by ``slot_index`` ASC to make
prompt-construction deterministic. See data-model.md and FR-011.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional, Sequence

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CharacterPreset, SessionCharacter


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
) -> Optional[SessionCharacter]:
    """Return one SessionCharacter or None."""
    stmt = select(SessionCharacter).where(SessionCharacter.id == character_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def fetch_protagonist_session_character(
    db: AsyncSession, session_id: str
) -> Optional[SessionCharacter]:
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
    source_preset_id: Optional[str] = None,
    is_protagonist: bool = False,
    appearance_lock: bool = False,
    exclude_from_effects: bool = False,
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
    )
    db.add(record)
    await db.flush()
    return record


async def update_session_character(
    db: AsyncSession,
    character_id: str,
    **patch: Any,
) -> Optional[SessionCharacter]:
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
    }
    for key, value in patch.items():
        if key in allowed and value is not None:
            setattr(record, key, value)
    await db.flush()
    return record


async def delete_session_character(db: AsyncSession, character_id: str) -> int:
    """Delete one SessionCharacter; returns number of rows removed."""
    stmt = sa_delete(SessionCharacter).where(SessionCharacter.id == character_id)
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
) -> Optional[CharacterPreset]:
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
    tags_meta: Optional[str] = None,
) -> CharacterPreset:
    """Insert a new preset; returns the persisted instance."""
    record = CharacterPreset(
        id=uuid.uuid4().hex,
        name=name,
        appearance_natural=appearance_natural,
        appearance_tags=appearance_tags,
        default_position=default_position,
        tags_meta=tags_meta,
    )
    db.add(record)
    await db.flush()
    return record


async def update_character_preset(
    db: AsyncSession,
    preset_id: str,
    **patch: Any,
) -> Optional[CharacterPreset]:
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


__all__ = [
    "fetch_session_characters",
    "fetch_session_character",
    "insert_session_character",
    "update_session_character",
    "delete_session_character",
    "fetch_character_presets",
    "fetch_character_preset",
    "insert_character_preset",
    "update_character_preset",
    "delete_character_preset",
]
