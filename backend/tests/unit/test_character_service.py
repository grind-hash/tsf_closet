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


@pytest.mark.asyncio
async def test_protagonist_cannot_be_taken_off_stage(isolated_db):
    from gateway.services.character_service import (
        upsert_protagonist_session_character,
    )

    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        hero = await upsert_protagonist_session_character(
            db, "sess-1", name="Hero", appearance_tags="1boy"
        )
        await db.commit()

    async with factory() as db:
        updated = await SessionCharacterService.update(
            db, hero.id, on_stage=False, negative_tags="hat"
        )
        await db.commit()
    assert updated is not None
    assert updated.on_stage is True
    assert updated.negative_tags == "hat"


@pytest.mark.asyncio
async def test_branch_copy_keeps_cast_fields(isolated_db):
    from gateway.services.session_branch_service import _copy_session_characters

    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        db.add(
            SessionORM(
                id="sess-2",
                user_id="user-1",
                current_image_path="img/start.png",
                character_id="char-1",
            )
        )
        await SessionCharacterService.create_in_session(
            db,
            "sess-1",
            name="Sakura",
            negative_tags="glasses",
            profile={"pronoun": "わたし"},
            on_stage=False,
            thumbnail_url="/prompt-expander/images/abc",
        )
        await db.commit()

    await _copy_session_characters("sess-1", "sess-2")

    async with factory() as db:
        copied = list(await SessionCharacterService.list_for_session(db, "sess-2"))
    assert len(copied) == 1
    assert copied[0].negative_tags == "glasses"
    assert copied[0].on_stage is False
    assert copied[0].thumbnail_url == "/prompt-expander/images/abc"
    assert "わたし" in (copied[0].profile_json or "")
