"""Tests for apply_appearance_updates and prompt section builder (spec 005, T026)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gateway.consts.character_limits import (
    APPEARANCE_NATURAL_MAX_LEN,
    APPEARANCE_TAGS_MAX_LEN,
)
from gateway.databases.base import Base
from gateway.databases.models import Session as SessionORM
from gateway.databases.models import User
from gateway.services.character_service import (
    SessionCharacterService,
    apply_appearance_updates,
    apply_character_prompt_tags,
    build_session_characters_prompt_section,
    upsert_protagonist_session_character,
)
from gateway.services.llm_service import LLMService


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


@pytest.mark.asyncio
async def test_apply_character_prompt_tags_updates_protagonist_and_support(
    tmp_path: Path,
):
    factory = await _setup(tmp_path)
    async with factory() as db:
        await upsert_protagonist_session_character(
            db,
            "sess-1",
            name="Protagonist",
            appearance_tags="1boy, old tags",
        )
        await SessionCharacterService.create_in_session(
            db,
            "sess-1",
            name="Support",
            appearance_tags="1girl, old support",
            position="left",
        )
        await db.commit()

    async with factory() as db:
        n = await apply_character_prompt_tags(
            db,
            "sess-1",
            [
                {"prompt": "1girl, school uniform, blonde hair"},
                {"prompt": "1boy, suit, black hair"},
            ],
        )
        await db.commit()
    assert n == 2

    async with factory() as db:
        records = {
            r.name: r
            for r in await SessionCharacterService.list_for_session(db, "sess-1")
        }
    assert (
        records["Protagonist"].appearance_tags == "1girl, school uniform, blonde hair"
    )
    assert records["Support"].appearance_tags == "1boy, suit, black hair"


@pytest.mark.asyncio
async def test_apply_character_prompt_tags_respects_appearance_lock(tmp_path: Path):
    factory = await _setup(tmp_path)
    async with factory() as db:
        await upsert_protagonist_session_character(
            db,
            "sess-1",
            name="Protagonist",
            appearance_tags="1boy, locked",
        )
        # lock after create (upsert helper does not accept lock kwargs)
        records = list(await SessionCharacterService.list_for_session(db, "sess-1"))
        await SessionCharacterService.update(db, records[0].id, appearance_lock=True)
        await db.commit()

    async with factory() as db:
        n = await apply_character_prompt_tags(
            db,
            "sess-1",
            [{"prompt": "1girl, should not apply"}],
        )
        await db.commit()
    assert n == 0

    async with factory() as db:
        records = list(await SessionCharacterService.list_for_session(db, "sess-1"))
    assert records[0].appearance_tags == "1boy, locked"


@pytest.mark.asyncio
async def test_apply_appearance_updates_respects_appearance_lock(tmp_path: Path):
    factory = await _setup(tmp_path)
    async with factory() as db:
        a = await SessionCharacterService.create_in_session(
            db,
            "sess-1",
            name="Alice",
            appearance_tags="locked_original",
            appearance_lock=True,
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
                    "appearance_tags": "should_not_apply",
                    "appearance_natural": "ignored",
                }
            ],
        )
        await db.commit()
    assert n == 0

    async with factory() as db:
        records = list(await SessionCharacterService.list_for_session(db, "sess-1"))
    assert records[0].appearance_tags == "locked_original"


@pytest.mark.asyncio
async def test_apply_appearance_updates_respects_exclude_from_effects(tmp_path: Path):
    factory = await _setup(tmp_path)
    async with factory() as db:
        a = await SessionCharacterService.create_in_session(
            db,
            "sess-1",
            name="Alice",
            appearance_tags="excluded_original",
            exclude_from_effects=True,
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
                    "appearance_tags": "should_not_apply",
                }
            ],
        )
        await db.commit()
    assert n == 0

    async with factory() as db:
        records = list(await SessionCharacterService.list_for_session(db, "sess-1"))
    assert records[0].appearance_tags == "excluded_original"


@pytest.mark.asyncio
async def test_apply_appearance_updates_truncates_long_natural(tmp_path: Path):
    factory = await _setup(tmp_path)
    async with factory() as db:
        a = await SessionCharacterService.create_in_session(db, "sess-1", name="Alice")
        await db.commit()

    long_text = "あ" * (APPEARANCE_NATURAL_MAX_LEN + 200)
    async with factory() as db:
        n = await apply_appearance_updates(
            db,
            "sess-1",
            [
                {
                    "character_id": a.id,
                    "changed": True,
                    "appearance_natural": long_text,
                }
            ],
        )
        await db.commit()
    assert n == 1

    async with factory() as db:
        records = list(await SessionCharacterService.list_for_session(db, "sess-1"))
    assert len(records[0].appearance_natural) <= APPEARANCE_NATURAL_MAX_LEN


@pytest.mark.asyncio
async def test_apply_appearance_updates_truncates_long_tags(tmp_path: Path):
    factory = await _setup(tmp_path)
    async with factory() as db:
        a = await SessionCharacterService.create_in_session(db, "sess-1", name="Alice")
        await db.commit()

    long_tags = ("tag_x, " * 200).strip(", ")
    assert len(long_tags) > APPEARANCE_TAGS_MAX_LEN
    async with factory() as db:
        n = await apply_appearance_updates(
            db,
            "sess-1",
            [
                {
                    "character_id": a.id,
                    "changed": True,
                    "appearance_tags": long_tags,
                }
            ],
        )
        await db.commit()
    assert n == 1

    async with factory() as db:
        records = list(await SessionCharacterService.list_for_session(db, "sess-1"))
    assert len(records[0].appearance_tags) <= APPEARANCE_TAGS_MAX_LEN


class _FakeFeelingResult:
    def __init__(self, content: str) -> None:
        self.content = content


async def _run_infer_with_capture(
    language: str, characters: list[dict]
) -> dict[str, str]:
    svc = LLMService()
    captured: dict[str, str] = {}

    async def _fake(system_prompt: str, user_prompt: str, **kw):
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return _FakeFeelingResult(
            '{"updates": [{"character_id": "c1", "changed": false}]}'
        )

    fake = AsyncMock(side_effect=_fake)
    with patch.object(svc, "generate_feeling", fake):
        await svc.infer_appearance_updates(characters, "wave hands", language=language)
    return captured


@pytest.mark.asyncio
async def test_infer_appearance_updates_system_prompt_contains_language_rule_ja():
    captured = await _run_infer_with_capture(
        "ja",
        [
            {
                "id": "c1",
                "name": "Alice",
                "appearance_natural": "",
                "appearance_tags": "",
            }
        ],
    )
    assert "日本語" in captured["system"]
    assert "英" in captured["system"]
    assert "replacement" in captured["system"].lower()
    assert "appearance_lock" in captured["system"]
    assert "exclude_from_effects" in captured["system"]


@pytest.mark.asyncio
async def test_infer_appearance_updates_system_prompt_contains_language_rule_en():
    captured = await _run_infer_with_capture(
        "en",
        [
            {
                "id": "c1",
                "name": "Alice",
                "appearance_natural": "",
                "appearance_tags": "",
            }
        ],
    )
    assert "English" in captured["system"]


@pytest.mark.asyncio
async def test_infer_appearance_updates_payload_includes_protection_flags():
    captured = await _run_infer_with_capture(
        "ja",
        [
            {
                "id": "c1",
                "name": "Alice",
                "appearance_natural": "",
                "appearance_tags": "",
                "appearance_lock": True,
                "exclude_from_effects": False,
            }
        ],
    )
    assert "appearance_lock" in captured["user"]
    assert "exclude_from_effects" in captured["user"]
