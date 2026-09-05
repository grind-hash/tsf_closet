"""Unit tests for SessionCharacterService (spec 005, T013)."""

from __future__ import annotations

import pytest

from gateway.databases.models import Session as SessionORM
from gateway.databases.models import User
from gateway.services.character_service import (
    CHARACTER_LIMIT,
    CharacterLimitExceededError,
    SessionCharacterService,
)


async def _setup(factory):
    async with factory() as db:
        db.add(User(id="user-1"))
        db.add(
            SessionORM(
                id="sess-1",
                user_id="user-1",
                current_image_path="img/start.png",
                character_id="char-1",
            )
        )
        await db.commit()
    return factory


@pytest.mark.asyncio
async def test_create_in_session_assigns_sequential_slots(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        a = await SessionCharacterService.create_in_session(db, "sess-1", name="Alice")
        b = await SessionCharacterService.create_in_session(db, "sess-1", name="Bob")
        await db.commit()

    assert a.slot_index == 0
    assert b.slot_index == 1


@pytest.mark.asyncio
async def test_character_limit_exceeded_at_fifth(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        for i in range(CHARACTER_LIMIT):
            await SessionCharacterService.create_in_session(
                db, "sess-1", name=f"Char{i}"
            )
        await db.commit()

    async with factory() as db:
        with pytest.raises(CharacterLimitExceededError):
            await SessionCharacterService.create_in_session(
                db, "sess-1", name="Overflow"
            )


@pytest.mark.asyncio
async def test_delete_repacks_slot_indices(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        a = await SessionCharacterService.create_in_session(db, "sess-1", name="A")
        b = await SessionCharacterService.create_in_session(db, "sess-1", name="B")
        c = await SessionCharacterService.create_in_session(db, "sess-1", name="C")
        await db.commit()
        a_id = a.id
        c_id = c.id

    async with factory() as db:
        ok = await SessionCharacterService.delete(db, b.id)
        assert ok is True
        await db.commit()

    async with factory() as db:
        records = list(await SessionCharacterService.list_for_session(db, "sess-1"))

    assert len(records) == 2
    ids_in_order = [r.id for r in records]
    assert ids_in_order == [a_id, c_id]
    assert [r.slot_index for r in records] == [0, 1]


@pytest.mark.asyncio
async def test_invalid_position_raises(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        with pytest.raises(ValueError):
            await SessionCharacterService.create_in_session(
                db, "sess-1", name="X", position="behind"
            )


@pytest.mark.asyncio
async def test_update_position_change(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        rec = await SessionCharacterService.create_in_session(
            db, "sess-1", name="A", position="left"
        )
        await db.commit()

    async with factory() as db:
        updated = await SessionCharacterService.update(db, rec.id, position="right")
        await db.commit()
    assert updated is not None
    assert updated.position == "right"
