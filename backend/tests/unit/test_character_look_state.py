"""登場人物の「設定」と「現在の姿（履歴に残した姿）」を分ける処理のテスト。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from gateway.databases.character_repo import fetch_latest_character_states
from gateway.databases.models import History, User
from gateway.databases.models import Session as SessionORM
from gateway.services.character_service import (
    CharacterLook,
    SessionCharacterService,
    attach_stage_negatives,
    build_character_states,
    build_novelai_characters_section,
    build_session_characters_prompt_section,
    build_stage_roster,
    ref_to_stage_index,
    remove_avoided_tags,
    resolve_character_look,
    upsert_protagonist_session_character,
)
from gateway.services.game_service import (
    GameService,
    _MultiCharacterSections,
    _parse_novelai_prompt_json,
)
from gateway.services.session_branch_service import _branch_character_states


def _rec(
    record_id: str,
    slot_index: int,
    *,
    name: str | None = None,
    tags: str = "",
    natural: str = "",
    is_protagonist: bool = False,
    on_stage: bool = True,
    lock: bool = False,
    exclude: bool = False,
    spec_rev: int = 0,
    negative: str = "",
):
    return SimpleNamespace(
        id=record_id,
        slot_index=slot_index,
        name=name or record_id,
        position="center",
        appearance_tags=tags,
        appearance_natural=natural,
        is_protagonist=is_protagonist,
        on_stage=on_stage,
        negative_tags=negative,
        profile_json=None,
        appearance_lock=lock,
        exclude_from_effects=exclude,
        appearance_spec_rev=spec_rev,
    )


# ---------------------------------------------------------------------------
# resolve_character_look
# ---------------------------------------------------------------------------


def test_look_uses_history_while_setting_is_unchanged() -> None:
    record = _rec("emma", 1, tags="1girl, red hair, hostess dress", spec_rev=2)
    looks = {"emma": CharacterLook(tags="1girl, red hair, bikini", spec_rev=2)}
    assert resolve_character_look(record, looks) == (
        "1girl, red hair, bikini",
        "history",
        "1girl, red hair, bikini",
    )


def test_look_uses_setting_after_user_changed_it() -> None:
    record = _rec("emma", 1, tags="1girl, red hair, hostess dress", spec_rev=3)
    looks = {"emma": CharacterLook(tags="1girl, red hair, bikini", spec_rev=2)}
    look_tags, source, current = resolve_character_look(record, looks)
    assert (look_tags, source) == ("1girl, red hair, hostess dress", "spec")
    # 画面には直前に描いた姿も出せる
    assert current == "1girl, red hair, bikini"


def test_fixed_look_always_uses_setting() -> None:
    record = _rec("nao", 0, tags="1girl, milky beige hair", lock=True)
    looks = {"nao": CharacterLook(tags="1boy, short black hair", spec_rev=0)}
    assert resolve_character_look(record, looks)[:2] == (
        "1girl, milky beige hair",
        "fixed",
    )


def test_look_without_history_uses_setting() -> None:
    record = _rec("mio", 2, natural="ツインテールの女の子")
    assert resolve_character_look(record, {}) == ("", "spec", None)


# ---------------------------------------------------------------------------
# refs and parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ref", "expected"),
    [("C2", 1), ("c1", 0), ("Character 3", 2), (2, 1), ("C0", None), ("x", None)],
)
def test_ref_to_stage_index(ref, expected) -> None:
    assert ref_to_stage_index(ref) == expected


def test_parse_maps_entries_by_ref_even_when_reordered() -> None:
    raw = json.dumps(
        {
            "characters": [
                {"ref": "C2", "tags": "1girl, red hair", "position": "left"},
                {"tags": "1boy, bartender", "position": "right"},
                {"ref": "C1", "tags": "1girl, milky beige hair", "position": "center"},
                {"ref": "C1", "tags": "duplicate", "position": "center"},
            ],
            "scene": "bar",
        }
    )
    parsed = _parse_novelai_prompt_json(raw)
    assert parsed is not None
    _scene, characters = parsed
    # 一覧の順に並び、一覧外・重複した ref は None で後ろに回る
    assert [(c["stage_index"], c["prompt"]) for c in characters] == [
        (0, "1girl, milky beige hair"),
        (1, "1girl, red hair"),
        (None, "1boy, bartender"),
        (None, "duplicate"),
    ]


def test_parse_without_refs_keeps_array_order() -> None:
    raw = json.dumps(
        {
            "characters": [
                {"tags": "1boy", "position": "center"},
                {"tags": "1girl", "position": "left"},
            ],
            "scene": "park",
        }
    )
    parsed = _parse_novelai_prompt_json(raw)
    assert parsed is not None
    assert [c["stage_index"] for c in parsed[1]] == [0, 1]


def test_protagonist_prompt_is_found_by_stage_index() -> None:
    stage = build_stage_roster(
        [_rec("nao", 0, tags="1boy", is_protagonist=True), _rec("emma", 1)]
    )
    characters = [
        {"prompt": "1girl, red hair", "stage_index": 1},
        {"prompt": "1girl, milky beige hair", "stage_index": 0},
    ]
    assert (
        GameService._protagonist_prompt(characters, stage) == "1girl, milky beige hair"
    )
    # 一覧が無い（パネル OFF）ときは従来どおり先頭
    assert GameService._protagonist_prompt(characters) == "1girl, red hair"


# ---------------------------------------------------------------------------
# build_character_states
# ---------------------------------------------------------------------------


def test_states_carry_over_and_update_by_character_id() -> None:
    records = [
        _rec("nao", 0, tags="1boy", is_protagonist=True),
        _rec("nagisa", 1, on_stage=False),
        _rec("emma", 2, tags="1girl, red hair", spec_rev=1),
        _rec("ren", 3, tags="1boy, suit", lock=True),
    ]
    stage = build_stage_roster(records)
    previous = [
        {"character_id": "nagisa", "tags": "1boy, blue hair", "spec_rev": 0},
        {"character_id": "ren", "tags": "1boy, suit", "spec_rev": 0},
        {"character_id": "deleted", "tags": "1girl", "spec_rev": 0},
    ]
    states = build_character_states(
        previous,
        stage,
        [
            {"prompt": "1girl, milky beige hair", "stage_index": 0},
            {"prompt": "1girl, red hair, casting spell", "stage_index": 1},
            {"prompt": "1boy, changed", "stage_index": 2},
            {"prompt": "unlisted", "stage_index": None},
        ],
        [r.id for r in records],
    )
    assert states is not None
    by_id = {s["character_id"]: s for s in states}
    assert set(by_id) == {"nao", "nagisa", "emma", "ren"}
    assert by_id["nao"]["tags"] == "1girl, milky beige hair"
    assert by_id["emma"] == {
        "character_id": "emma",
        "tags": "1girl, red hair, casting spell",
        "spec_rev": 1,
    }
    # 登場 OFF は前回のまま、固定は上書きしない
    assert by_id["nagisa"]["tags"] == "1boy, blue hair"
    assert by_id["ren"]["tags"] == "1boy, suit"


def test_states_none_without_per_character_output() -> None:
    stage = build_stage_roster([_rec("nao", 0, tags="1boy", is_protagonist=True)])
    assert build_character_states([], stage, None, ["nao"]) is None


def test_states_record_protagonist_created_during_the_turn() -> None:
    stage = build_stage_roster([], protagonist_name="Nao", protagonist_tags="1boy")
    states = build_character_states(
        [],
        stage,
        [{"prompt": "1girl", "stage_index": 0}],
        [],
        protagonist_id="nao-new",
    )
    assert states == [{"character_id": "nao-new", "tags": "1girl", "spec_rev": 0}]


# ---------------------------------------------------------------------------
# Prompt sections
# ---------------------------------------------------------------------------


def test_image_section_lists_refs_rules_and_avoid() -> None:
    records = [
        _rec("nao", 0, name="ナオ", tags="1boy", is_protagonist=True, negative="hat"),
        _rec("emma", 1, name="エマ", natural="ホステスドレスの女性。赤い髪"),
    ]
    looks = {"nao": CharacterLook(tags="1girl, milky beige hair", spec_rev=0)}
    section = build_novelai_characters_section(records, looks=looks)
    assert "- C1 (ナオ, position: center, tags: 1girl, milky beige hair)" in section
    assert "avoid: hat" in section
    assert (
        "- C2 (エマ, position: center, appearance: ホステスドレスの女性。赤い髪)"
        in (section)
    )
    assert "refer to C1 (the protagonist)" in section
    # 服を指定しない変身（「美少女になった」）で服が消えないよう、服の引き継ぎを明示する
    assert "Clothing carries over" in section
    assert "describes THAT character" in section
    assert "Never move a change onto a different character" in section


def test_text_section_hides_outdated_natural_when_look_is_carried_over() -> None:
    records = [
        _rec(
            "emma",
            1,
            name="エマ",
            tags="1girl, red hair",
            natural="ホステスドレスの女性",
        )
    ]
    looks = {"emma": CharacterLook(tags="1girl, red hair, bikini", spec_rev=0)}
    text = build_session_characters_prompt_section(records, looks=looks)
    assert "タグ: 1girl, red hair, bikini" in text
    assert "ホステスドレス" not in text
    # 設定の姿を使う間は自然文も出す
    assert "ホステスドレス" in build_session_characters_prompt_section(records)


def test_protagonist_spec_look_only_after_user_change_or_fixed() -> None:
    def sections(**kwargs) -> _MultiCharacterSections:
        record = _rec("nao", 0, is_protagonist=True, **kwargs)
        return _MultiCharacterSections(stage=tuple(build_stage_roster([record])))

    # システムが作った行（rev 0）・履歴なし: 直前の履歴の姿を引き継ぐ
    assert sections(tags="1boy").protagonist_spec_look() is None
    # ユーザーが設定を変えた
    assert sections(tags="1girl", spec_rev=1).protagonist_spec_look() == "1girl"
    # タグが空なら自然文
    assert (
        sections(natural="ミルキーベージュの美少女", spec_rev=1).protagonist_spec_look()
        == "ミルキーベージュの美少女"
    )
    # 姿を固定
    assert sections(tags="1girl", lock=True).protagonist_spec_look() == "1girl"


# ---------------------------------------------------------------------------
# DB: spec revision, protagonist upsert, latest states, branch
# ---------------------------------------------------------------------------


async def _setup_session(factory, session_id: str = "sess-1") -> None:
    async with factory() as db:
        if await db.get(User, "user-1") is None:
            db.add(User(id="user-1"))
        db.add(
            SessionORM(
                id=session_id,
                user_id="user-1",
                current_image_path="img/start.png",
                character_id="char-1",
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_spec_revision_moves_only_when_the_drawn_setting_changes(isolated_db):
    factory = isolated_db.async_factory
    await _setup_session(factory)
    async with factory() as db:
        emma = await SessionCharacterService.create_in_session(
            db, "sess-1", name="エマ", appearance_tags="1girl, red hair"
        )
        mio = await SessionCharacterService.create_in_session(
            db, "sess-1", name="ミオ", appearance_natural="ツインテール"
        )
        await db.commit()

    async def rev_after(character_id: str, **patch) -> int:
        async with factory() as db:
            record = await SessionCharacterService.update(db, character_id, **patch)
            await db.commit()
            assert record is not None
            return record.appearance_spec_rev

    # タグがある人物の自然文だけを直しても描く姿は変わらない
    assert await rev_after(emma.id, appearance_natural="赤い髪の女性") == 0
    assert await rev_after(emma.id, on_stage=False) == 0
    assert await rev_after(emma.id, appearance_tags="1girl, red hair, dress") == 1
    # タグが空の人物は自然文が描く姿になる
    assert await rev_after(mio.id, appearance_natural="ツインテールの女の子") == 1
    assert await rev_after(mio.id, reset_look=True) == 2


@pytest.mark.asyncio
async def test_protagonist_upsert_keeps_setting_and_syncs_name(isolated_db):
    factory = isolated_db.async_factory
    await _setup_session(factory)
    async with factory() as db:
        created = await upsert_protagonist_session_character(
            db, "sess-1", name="ナオ", appearance_tags="1boy, short black hair"
        )
        await db.commit()
    async with factory() as db:
        updated = await upsert_protagonist_session_character(
            db, "sess-1", name="ナオ改", appearance_tags="1girl, hostess dress"
        )
        await db.commit()
    assert updated.id == created.id
    assert updated.name == "ナオ改"
    assert updated.appearance_tags == "1boy, short black hair"


@pytest.mark.asyncio
async def test_latest_states_skip_turns_without_character_output(isolated_db):
    factory = isolated_db.async_factory
    await _setup_session(factory)
    base = datetime(2026, 9, 26, 10, 0, 0)
    async with factory() as db:
        for index, states in enumerate(
            [
                [{"character_id": "emma", "tags": "first", "spec_rev": 0}],
                [{"character_id": "emma", "tags": "second", "spec_rev": 0}],
                None,
            ]
        ):
            db.add(
                History(
                    id=f"hist-{index}",
                    session_id="sess-1",
                    instruction=f"turn {index}",
                    image_path=f"img/{index}.png",
                    character_states_json=(
                        json.dumps(states) if states is not None else None
                    ),
                    created_at=base + timedelta(minutes=index),
                )
            )
        await db.commit()
    async with factory() as db:
        latest = await fetch_latest_character_states(db, "sess-1")
        until_first = await fetch_latest_character_states(
            db, "sess-1", until=base + timedelta(seconds=30)
        )
    assert json.loads(latest)[0]["tags"] == "second"
    assert json.loads(until_first)[0]["tags"] == "first"


@pytest.mark.asyncio
async def test_branch_remaps_states_to_new_character_ids(isolated_db):
    factory = isolated_db.async_factory
    await _setup_session(factory)
    created_at = datetime(2026, 9, 26, 10, 0, 0)
    async with factory() as db:
        db.add(
            History(
                id="hist-src",
                session_id="sess-1",
                instruction="turn",
                image_path="img/src.png",
                character_states_json=json.dumps(
                    [
                        {"character_id": "old-emma", "tags": "1girl", "spec_rev": 1},
                        {"character_id": "gone", "tags": "1boy", "spec_rev": 0},
                    ]
                ),
                created_at=created_at,
            )
        )
        await db.commit()
    states = await _branch_character_states(
        "sess-1", created_at, {"old-emma": "new-emma"}
    )
    assert states == [{"character_id": "new-emma", "tags": "1girl", "spec_rev": 1}]


# ---------------------------------------------------------------------------
# Avoided tags
# ---------------------------------------------------------------------------


def test_remove_avoided_tags_ignores_case_underscores_and_emphasis() -> None:
    prompt = "1girl, E-cup breasts, pubic hair, {Pubic_Hair}, surprised"
    assert (
        remove_avoided_tags(prompt, "pubic hair, silver sequin")
        == "1girl, E-cup breasts, surprised"
    )
    assert remove_avoided_tags(prompt, "") == prompt


def test_avoided_tags_are_removed_only_from_that_character() -> None:
    stage = build_stage_roster(
        [
            _rec("nao", 0, tags="1girl", is_protagonist=True, negative="pubic hair"),
            _rec("emma", 1, tags="1girl, red hair"),
        ]
    )
    result = attach_stage_negatives(
        [
            {"prompt": "1girl, milky beige hair, pubic hair", "stage_index": 0},
            {"prompt": "1girl, red hair, pubic hair", "stage_index": 1},
        ],
        stage,
        limit=6,
    )
    assert result[0]["prompt"] == "1girl, milky beige hair"
    assert result[0]["negative_prompt"] == "pubic hair"
    assert result[1]["prompt"] == "1girl, red hair, pubic hair"
