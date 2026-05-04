"""Tests for apply_appearance_updates and prompt section builder (spec 005, T026)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gateway.databases.base import Base
from gateway.databases.models import Session as SessionORM, User
from gateway.services.character_service import (
    SessionCharacterService,
    apply_appearance_updates,
    build_session_characters_prompt_section,
)


async def _setup(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'app.db'}", future=True
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
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
async def test_apply_appearance_updates_only_changed_entries(tmp_path: Path):
    factory = await _setup(tmp_path)
    async with factory() as db:
        a = await SessionCharacterService.create_in_session(
            db, "sess-1", name="Alice", appearance_tags="old_tag_a"
        )
        b = await SessionCharacterService.create_in_session(
            db, "sess-1", name="Bob", appearance_tags="old_tag_b"
        )
        await db.commit()

    async with factory() as db:
        n = await apply_appearance_updates(
            db,
            "sess-1",
            [
                {
                    "character_id": a.id,
                    "changed": True,
                    "appearance_tags": "new_tag_a",
                },
                {"character_id": b.id, "changed": False},
            ],
        )
        await db.commit()

    assert n == 1

    async with factory() as db:
        records = list(await SessionCharacterService.list_for_session(db, "sess-1"))
    by_id = {r.id: r for r in records}
    assert by_id[a.id].appearance_tags == "new_tag_a"
    assert by_id[b.id].appearance_tags == "old_tag_b"


@pytest.mark.asyncio
async def test_apply_appearance_updates_skips_empty_strings(tmp_path: Path):
    factory = await _setup(tmp_path)
    async with factory() as db:
        a = await SessionCharacterService.create_in_session(
            db, "sess-1", name="Alice", appearance_tags="keep_me"
        )
        await db.commit()

    async with factory() as db:
        n = await apply_appearance_updates(
            db,
            "sess-1",
            [
                {
                    "character_id": a.id,
                    "changed": True,
                    "appearance_natural": "",
                    "appearance_tags": "",
                }
            ],
        )
        await db.commit()
    assert n == 0

    async with factory() as db:
        records = list(await SessionCharacterService.list_for_session(db, "sess-1"))
    assert records[0].appearance_tags == "keep_me"


def test_build_prompt_section_empty_returns_empty():
    assert build_session_characters_prompt_section([]) == ""


def test_build_prompt_section_includes_position_and_appearance():
    class _Stub:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    chars = [
        _Stub(
            name="Alice",
            position="left",
            appearance_natural="金髪のお嬢様",
            appearance_tags="blonde, gown",
            slot_index=0,
        ),
        _Stub(
            name="Bob",
            position="right",
            appearance_natural="",
            appearance_tags="",
            slot_index=1,
        ),
    ]
    text = build_session_characters_prompt_section(chars)
    assert "Alice" in text
    assert "Bob" in text
    assert "blonde, gown" in text
    assert "金髪" in text
