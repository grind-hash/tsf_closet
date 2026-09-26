"""登場ロスター（登場順・上限・人物別ネガティブ・性格行）のテスト。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from gateway.databases.models import Session as SessionORM
from gateway.databases.models import User
from gateway.services.character_service import (
    SessionCharacterService,
    apply_character_prompt_tags,
    attach_stage_negatives,
    build_novelai_characters_section,
    build_session_characters_prompt_section,
    build_stage_roster,
    upsert_protagonist_session_character,
)
from gateway.services.game_service import _parse_novelai_prompt_json


def _rec(
    slot_index: int,
    name: str,
    *,
    tags: str = "",
    is_protagonist: bool = False,
    on_stage: bool = True,
    negative: str = "",
    profile: dict | None = None,
    record_id: str | None = None,
):
    return SimpleNamespace(
        id=record_id or f"id-{name}",
        slot_index=slot_index,
        name=name,
        position="center",
        appearance_tags=tags,
        appearance_natural="",
        is_protagonist=is_protagonist,
        on_stage=on_stage,
        negative_tags=negative,
        profile_json=json.dumps(profile, ensure_ascii=False) if profile else None,
        appearance_lock=False,
        exclude_from_effects=False,
    )


# ---------------------------------------------------------------------------
# build_stage_roster
# ---------------------------------------------------------------------------


def test_roster_drops_off_stage_and_puts_protagonist_first() -> None:
    records = [
        _rec(2, "Mio", tags="1girl, twintails"),
        _rec(1, "Sakura", tags="1girl", on_stage=False),
        _rec(0, "Hero", tags="1boy", is_protagonist=True, on_stage=False),
    ]
    roster = build_stage_roster(records)
    assert [c.name for c in roster] == ["Hero", "Mio"]
    assert roster[0].is_protagonist


def test_roster_inserts_fallback_protagonist_when_not_persisted() -> None:
    roster = build_stage_roster(
        [_rec(0, "Sakura", tags="1girl")],
        protagonist_name="Hero",
        protagonist_tags="1boy, short hair",
    )
    assert [c.name for c in roster] == ["Hero", "Sakura"]
    assert roster[0].record_id is None
    assert roster[0].appearance_tags == "1boy, short hair"


@pytest.mark.parametrize("limit", [6, 22])
def test_roster_truncates_to_model_limit(limit: int) -> None:
    records = [_rec(0, "Hero", tags="1boy", is_protagonist=True)] + [
        _rec(i, f"P{i}", tags="1girl") for i in range(1, 30)
    ]
    roster = build_stage_roster(records, limit=limit)
    assert len(roster) == limit
    assert roster[0].name == "Hero"
    assert roster[-1].name == f"P{limit - 1}"


# ---------------------------------------------------------------------------
# attach_stage_negatives
# ---------------------------------------------------------------------------


def test_attach_negatives_maps_by_stage_index_and_truncates() -> None:
    stage = build_stage_roster(
        [
            _rec(0, "Hero", tags="1boy", is_protagonist=True),
            _rec(1, "Sakura", tags="1girl", negative="glasses"),
            _rec(2, "Mio", tags="1girl", negative="hat"),
        ]
    )
    characters = [
        {"prompt": "1boy", "stage_index": 0},
        # Sakura の要素が空で飛ばされても、Mio は stage_index で正しく対応する
        {"prompt": "1girl, twintails", "stage_index": 2},
        {"prompt": "1girl, extra person", "stage_index": 3},
    ]
    result = attach_stage_negatives(characters, stage, limit=6)
    assert "negative_prompt" not in result[0]
    assert result[1]["negative_prompt"] == "hat"
    assert "negative_prompt" not in result[2]

    truncated = attach_stage_negatives(characters, stage, limit=2)
    assert len(truncated) == 2


def test_attach_negatives_without_stage_only_truncates() -> None:
    characters = [{"prompt": f"p{i}"} for i in range(8)]
    result = attach_stage_negatives(characters, (), limit=6)
    assert len(result) == 6
    assert all("negative_prompt" not in c for c in result)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def test_novelai_section_numbers_on_stage_only_and_states_order() -> None:
    records = [
        _rec(0, "Hero", tags="1boy", is_protagonist=True),
        _rec(1, "Sakura", tags="1girl", on_stage=False),
        _rec(2, "Mio", tags="1girl, twintails"),
    ]
    result = build_novelai_characters_section(records)
    assert "Character 1 (Hero" in result
    assert "Character 2 (Mio" in result
    assert "Sakura" not in result
    assert "EXACTLY this order" in result


def test_novelai_section_adds_gender_token_from_profile() -> None:
    records = [
        _rec(0, "Hero", tags="short hair", is_protagonist=True),
        _rec(
            1, "Sakura", tags="long hair, school uniform", profile={"gender": "woman"}
        ),
        _rec(2, "Ren", tags="1boy, glasses", profile={"gender": "woman"}),
    ]
    result = build_novelai_characters_section(records)
    # 主人公のタグは履歴由来のため補わない
    assert "tags: short hair" in result
    assert "tags: 1girl, long hair, school uniform" in result
    # 既に性別トークンがあれば足さない
    assert "tags: 1boy, glasses" in result


def test_text_section_includes_profile_for_non_protagonists() -> None:
    records = [
        _rec(
            0,
            "Hero",
            tags="1boy",
            is_protagonist=True,
            profile={"personality": "主人公の性格"},
        ),
        _rec(
            1,
            "Sakura",
            tags="1girl",
            profile={
                "gender": "woman",
                "pronoun": "わたし",
                "personality": "面倒見がよい",
                "reaction_style": "cheerful",
                "interests": ["料理", "手芸", "読書", "映画"],
                "tsf_attitude": "興味津々",
            },
        ),
    ]
    text = build_session_characters_prompt_section(records)
    assert "[主人公]" in text
    assert "主人公の性格" not in text
    assert "人物設定: 性別=女性 / 一人称=わたし / 性格=面倒見がよい" in text
    assert "反応=明るい" in text
    assert "趣味=料理、手芸、読書" in text
    assert "映画" not in text
    assert "TSFへの態度=興味津々" in text
    assert "一人称・性格・反応スタイルを厳守" in text

    without = build_session_characters_prompt_section(records, include_profile=False)
    assert "人物設定" not in without


def test_text_section_empty_when_everyone_off_stage() -> None:
    records = [_rec(1, "Sakura", tags="1girl", on_stage=False)]
    assert build_session_characters_prompt_section(records) == ""
    assert build_novelai_characters_section(records) == ""


# ---------------------------------------------------------------------------
# LLM output parsing and write-back
# ---------------------------------------------------------------------------


def test_parse_keeps_original_index_when_entry_is_empty() -> None:
    raw = json.dumps(
        {
            "characters": [
                {"tags": "1boy", "position": "center"},
                {"tags": "", "position": "left"},
                {"tags": "1girl", "position": "right"},
            ],
            "scene": "park",
        }
    )
    parsed = _parse_novelai_prompt_json(raw)
    assert parsed is not None
    _scene, characters = parsed
    assert [c["stage_index"] for c in characters] == [0, 2]


async def _setup_session(factory) -> None:
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


@pytest.mark.asyncio
async def test_apply_prompt_tags_skips_off_stage_character(isolated_db):
    factory = isolated_db.async_factory
    await _setup_session(factory)
    async with factory() as db:
        await upsert_protagonist_session_character(
            db, "sess-1", name="Hero", appearance_tags="1boy, old"
        )
        await SessionCharacterService.create_in_session(
            db, "sess-1", name="Sakura", appearance_tags="1girl, old", on_stage=False
        )
        await SessionCharacterService.create_in_session(
            db, "sess-1", name="Mio", appearance_tags="1girl, old mio"
        )
        await db.commit()

    async with factory() as db:
        records = await SessionCharacterService.list_for_session(db, "sess-1")
        stage_ids = [c.record_id for c in build_stage_roster(records)]
        written = await apply_character_prompt_tags(
            db,
            "sess-1",
            [
                {"prompt": "1boy, new", "stage_index": 0},
                {"prompt": "1girl, new mio", "stage_index": 1},
            ],
            stage_ids=stage_ids,
        )
        await db.commit()
    assert written == 2

    async with factory() as db:
        by_name = {
            r.name: r
            for r in await SessionCharacterService.list_for_session(db, "sess-1")
        }
    assert by_name["Hero"].appearance_tags == "1boy, new"
    assert by_name["Mio"].appearance_tags == "1girl, new mio"
    # 登場 OFF の Sakura は、slot 順では 2 番目でも書き換えない
    assert by_name["Sakura"].appearance_tags == "1girl, old"
