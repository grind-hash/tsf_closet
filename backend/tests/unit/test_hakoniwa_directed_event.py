"""AI箱庭の「指示した出来事」: 参加者の決め方・プロンプト・生成の失敗。

ルーターを通す確認は test_hakoniwa_router.py にある。
"""

from __future__ import annotations

import json
import random

import pytest

from gateway.services import hakoniwa_generation as gen
from gateway.services import hakoniwa_logic as logic
from gateway.services.hakoniwa_errors import HakoniwaError
from gateway.services.hakoniwa_prompts import (
    DIALOGUE_CRAFT_GUIDANCE,
    DIRECTED_DIALOGUE_CRAFT_GUIDANCE,
    DIRECTED_EVENT_RETRY_NOTE,
    event_system_prompt,
    event_user_prompt,
)

INSTRUCTION = "二人で一緒にお風呂に入る"


def _state():
    # aoi(女性・living) / ren(男性・garden) / ritsu(男性・living) / tamako(女性・living)
    return logic.new_world_state(
        [logic.preset_resident(pid) for pid in ("aoi", "ren", "ritsu", "tamako")]
    )


def _ids(group) -> list[str]:
    return [resident["id"] for resident in group]


def _transformed_female(state, resident_id: str):
    return logic.set_transformation(
        state,
        resident_id,
        {
            "description": "女の子にして",
            "tags": "1girl, long hair, sundress",
            "image": "tf.png",
            "day": 1,
        },
    )


def _event_json(names: list[str], **overrides) -> str:
    data = {
        "title": "湯けむり",
        "narration": "湯気の立つ浴室で、二人は肩を並べて湯船に浸かった。",
        "lines": [{"speaker": name, "text": "……あったかいね"} for name in names],
        "participants": names,
        "mood_delta": {name: 6 for name in names},
        "affinity_delta": 5,
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


# --- 参加者の決め方 ---


def test_cast_solo_is_only_the_target():
    state = _state()

    group = logic.directed_event_cast(state, "aoi", "solo", ["ren"], random.Random(0))

    assert _ids(group) == ["aoi"]


def test_cast_selected_dedupes_and_skips_the_target():
    state = _state()

    group = logic.directed_event_cast(
        state, "aoi", "selected", ["ren", "aoi", "ren"], random.Random(0)
    )

    assert _ids(group) == ["aoi", "ren"]


@pytest.mark.parametrize(
    ("partner_ids", "code"),
    [
        ([], "event_partners_required"),
        (["aoi"], "event_partners_required"),
        (["nobody"], "resident_not_found"),
        (["ren", "ritsu", "tamako"], "event_too_many_partners"),
    ],
)
def test_cast_selected_errors(partner_ids, code):
    with pytest.raises(HakoniwaError) as error:
        logic.directed_event_cast(
            _state(), "aoi", "selected", partner_ids, random.Random(0)
        )

    assert error.value.code == code


def test_cast_room_takes_up_to_two_from_the_same_room():
    state = _state()

    group = logic.directed_event_cast(state, "aoi", "room", None, random.Random(0))

    assert _ids(group)[0] == "aoi"
    assert set(_ids(group)[1:]) == {"ritsu", "tamako"}
    # ren は garden にいるので巻き込まれない
    assert "ren" not in _ids(group)


def test_cast_room_without_others_is_an_error():
    with pytest.raises(HakoniwaError) as error:
        logic.directed_event_cast(_state(), "ren", "room", None, random.Random(0))

    assert error.value.code == "event_room_empty"


def test_cast_rejects_unknown_scope():
    with pytest.raises(HakoniwaError) as error:
        logic.directed_event_cast(_state(), "aoi", "everyone", None, random.Random(0))

    assert error.value.code == "invalid_event_scope"


def test_male_body_pairs_follow_the_current_body():
    state = _state()
    group = tuple(logic.find_resident(state, pid) for pid in ("aoi", "ren", "ritsu"))

    assert [_ids(pair) for pair in logic.male_body_pairs(state, group)] == [
        ["ren", "ritsu"]
    ]

    changed = _transformed_female(state, "ritsu")
    group = tuple(logic.find_resident(changed, pid) for pid in ("aoi", "ren", "ritsu"))
    assert logic.male_body_pairs(changed, group) == []


# --- プロンプト ---


def _prompt(state, ids, *, nsfw: bool, instruction: str = INSTRUCTION) -> str:
    group = tuple(logic.find_resident(state, pid) for pid in ids)
    return event_user_prompt(
        state,
        group,
        "ja",
        nsfw=nsfw,
        area_id="living",
        include_theme=False,
        directed_instruction=instruction,
    )


def test_directed_prompt_puts_the_instruction_first_and_keeps_current_looks():
    prompt = _prompt(_state(), ["aoi", "tamako"], nsfw=False)

    assert "[Most important: the scene the player has ordered]" in prompt
    assert f'"{INSTRUCTION}"' in prompt
    assert "never revert anyone to their original look" in prompt
    # 指示に従うのは本人たちの意思で、押し切る・強いる場面にはしない
    assert "goes along with it willingly" in prompt
    assert "never depict anyone being forced" in prompt
    assert "Do not spend the scene on build-up" in prompt
    assert "Keep it non-explicit even if the instruction" in prompt
    # 指示した場面は最近の出来事と似ていてもよい
    assert "Avoid topics and developments similar" not in prompt


def test_directed_prompt_depicts_adult_acts_when_nsfw_is_on():
    prompt = _prompt(_state(), ["aoi", "tamako"], nsfw=True)

    assert "the scene opens in the middle of that act" in prompt
    assert "every line is spoken while doing it" in prompt
    assert "skips to afterwards" in prompt
    assert "Keep it non-explicit even if the instruction" not in prompt


def test_directed_prompt_names_male_body_pairs():
    state = _state()

    prompt = _prompt(state, ["aoi", "ren", "ritsu"], nsfw=True)

    assert "苑田 蓮 and 九条 薫 both currently have male bodies" in prompt
    assert "高瀬 葵 and" not in prompt


def test_directed_prompt_allows_a_man_with_a_transformed_former_man():
    state = _transformed_female(_state(), "ritsu")

    prompt = _prompt(state, ["ren", "ritsu"], nsfw=True)

    assert "both currently have male bodies" not in prompt


def _investigating_state():
    """九条 薫(調べ役)が妖艶な女性の姿に変身し、違和感が探り合いの段階にある世界。"""
    state = logic.set_transformation(
        _state(),
        "ritsu",
        {
            "description": "妖艶な美女にして",
            "tags": "1girl, long black hair, seductive smile, black dress, cleavage",
            "image": "tf.png",
            "day": 1,
        },
    )
    return {**state, "dissonance": 62}


def test_directed_prompt_drops_the_daily_focus_sections():
    state = _investigating_state()

    daily = event_user_prompt(
        state,
        (logic.find_resident(state, "ritsu"), logic.find_resident(state, "ren")),
        "ja",
        nsfw=True,
    )
    directed = _prompt(state, ["ritsu", "ren"], nsfw=True)

    # 日常の出来事では調査・姿への反応・適応を主題にする
    assert "make this an event about investigating" in daily
    assert "[Important: always include reactions to the current look]" in daily
    # 指示した出来事では、それらが場面を乗っ取るため載せず、色付けだけにする
    for section in (
        "make this an event about investigating",
        "[Important: always include reactions to the current look]",
        "[Important: follow each adaptation stage]",
        "[Important: follow how the world is adapting]",
        "[Important: thicken the reactions to the daring look]",
    ):
        assert section not in directed
    assert "[Their current bodies: color only]" in directed
    assert "九条 薫 is originally a man, now in a woman's body" in directed


def test_directed_prompt_keeps_the_swap_as_color_only():
    state = logic.new_world_state(
        [logic.preset_resident("aoi"), logic.preset_resident("ren")]
    )
    state = {**state, "active_rules": ["swap"], "swap_pair": ["aoi", "ren"]}

    prompt = _prompt(state, ["aoi", "ren"], nsfw=True)

    assert "make the reaction to the body swap the theme" not in prompt
    assert "高瀬 葵 and 苑田 蓮 have swapped bodies." in prompt


def test_directed_prompt_tells_the_residents_never_hear_the_order():
    prompt = _prompt(_state(), ["aoi", "tamako"], nsfw=True)

    assert "a stage direction that the residents never hear" in prompt
    assert "never quote or restate it" in prompt


def test_masked_words_are_read_as_plain_words():
    masked = _prompt(
        _state(), ["aoi", "tamako"], nsfw=True, instruction="セッ〇スをする"
    )
    plain = _prompt(_state(), ["aoi", "tamako"], nsfw=True)

    assert "hidden with symbols" in masked
    assert "hidden with symbols" not in plain


def test_directed_system_prompt_decides_the_place_first():
    state = _state()
    group = (logic.find_resident(state, "aoi"), logic.find_resident(state, "tamako"))

    directed = event_system_prompt(group, state, "ja", nsfw=True, directed=True)
    daily = event_system_prompt(group, state, "ja", nsfw=True)

    assert '{"location": ' in directed
    assert "at the boarding house" not in directed
    assert DIRECTED_DIALOGUE_CRAFT_GUIDANCE in directed
    assert DIALOGUE_CRAFT_GUIDANCE not in directed
    # 日常の出来事の形は変えない
    assert '{"title": ' in daily
    assert "at the boarding house" in daily
    assert DIALOGUE_CRAFT_GUIDANCE in daily


def test_regular_event_prompt_is_unchanged_without_instruction():
    state = _state()
    group = (logic.find_resident(state, "aoi"), logic.find_resident(state, "tamako"))

    prompt = event_user_prompt(state, group, "ja", nsfw=False)

    assert "the scene the player has ordered" not in prompt
    assert "Avoid topics and developments similar" in prompt


# --- 生成 ---


def _stub(monkeypatch, outputs):
    calls: list[tuple[str, str]] = []
    queue = list(outputs)

    async def fake(system, user, *, novelai_model, max_tokens=1400):
        calls.append((system, user))
        item = queue.pop(0) if queue else ""
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(gen, "_generate_text", fake)
    return calls


@pytest.mark.asyncio
async def test_generate_directed_event_maps_names(monkeypatch):
    calls = _stub(monkeypatch, [_event_json(["高瀬 葵", "大島 珠子"])])
    state = _state()
    group = (logic.find_resident(state, "aoi"), logic.find_resident(state, "tamako"))

    event = await gen.generate_directed_event(
        state,
        group,
        INSTRUCTION,
        "ja",
        novelai_model=None,
        nsfw=True,
        area_id="living",
    )

    assert event["participants"] == ["aoi", "tamako"]
    assert [line["speaker"] for line in event["lines"]] == ["aoi", "tamako"]
    assert event["area"] == "living"
    assert INSTRUCTION in calls[0][1]


@pytest.mark.asyncio
async def test_generate_directed_event_retries_then_fails(monkeypatch):
    bad = _event_json(["知らない人"])
    calls = _stub(monkeypatch, [bad] * 10)
    state = _state()
    group = (logic.find_resident(state, "aoi"),)

    with pytest.raises(HakoniwaError) as error:
        await gen.generate_directed_event(
            state,
            group,
            INSTRUCTION,
            "ja",
            novelai_model=None,
            nsfw=False,
            area_id="living",
        )

    assert error.value.code == "event_generation_failed"
    # 指示した出来事は、既定の穏やかな雰囲気より指示を優先させる
    assert "ordered directly by the player" in calls[0][0]
    # 1回目は指示だけ、2回目は指示を再掲して生成する(各回に JSON の修復依頼が挟まる)
    assert DIRECTED_EVENT_RETRY_NOTE not in calls[0][1]
    assert any(DIRECTED_EVENT_RETRY_NOTE in user for _, user in calls[1:])


# --- 続きを指示 ---

PREVIOUS = {
    "id": "ev1",
    "day": 1,
    "title": "初めての夜",
    "narration": "薄暗いホテルの部屋で、二人はベッドに並んで腰を下ろした。",
    "lines": [
        {"speaker": "aoi", "text": "ねえ、もう少しそばに来て"},
        {"speaker": "tamako", "text": "あら、甘えん坊ね"},
    ],
    "participants": ["aoi", "tamako"],
    "area": "living",
    "location": "hotel",
    "kind": "directed",
    "instruction": "ホテルで二人きりになる",
}
CONTINUE = "そのまま抱き合う"


def _with_previous(state):
    return {**state, "events": [dict(PREVIOUS)]}


def test_continuation_source_must_be_from_today():
    state = _with_previous(_state())

    assert logic.continuation_source(state, "ev1")["title"] == "初めての夜"
    with pytest.raises(HakoniwaError) as missing:
        logic.continuation_source(state, "nope")
    with pytest.raises(HakoniwaError) as old:
        logic.continuation_source({**state, "day": 2}, "ev1")

    assert missing.value.code == "event_not_found"
    assert old.value.code == "event_not_today"


def test_continuation_cast_keeps_the_residents_who_still_live_here():
    state = _state()

    group = logic.continuation_cast(state, PREVIOUS)
    partly = logic.continuation_cast(
        state, {**PREVIOUS, "participants": ["gone", "tamako"]}
    )

    assert _ids(group) == ["aoi", "tamako"]
    assert _ids(partly) == ["tamako"]
    with pytest.raises(HakoniwaError) as error:
        logic.continuation_cast(state, {**PREVIOUS, "participants": ["gone"]})
    assert error.value.code == "event_cast_gone"


def test_continuation_prompt_carries_the_previous_scene():
    state = _with_previous(_state())
    group = (logic.find_resident(state, "aoi"), logic.find_resident(state, "tamako"))

    prompt = event_user_prompt(
        state,
        group,
        "ja",
        nsfw=True,
        area_id="living",
        include_theme=False,
        directed_instruction=CONTINUE,
        continues_event=state["events"][0],
    )

    assert f'how the previous scene continues: "{CONTINUE}"' in prompt
    assert "[The previous scene: this event continues directly from it]" in prompt
    assert 'The order it followed: "ホテルで二人きりになる"' in prompt
    assert PREVIOUS["narration"] in prompt
    # 台詞は話し手の名前つきの全文を、出力と同じ JSON の形で渡す
    # (「」で囲むと、生成が JSON の text にも「」を書き写して壊れる)
    assert '{"speaker": "高瀬 葵", "text": "ねえ、もう少しそばに来て"}' in prompt
    assert "「ねえ、もう少しそばに来て」" not in prompt
    assert "Do not restart or re-introduce the situation" in prompt
    # 場所は前の場面の場所(エリアの外でも)に留まるのが既定
    assert 'the previous scene took place at "hotel"' in prompt
    assert "(where the previous scene took place)" in prompt
    assert "Place: not fixed." not in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("generated", "expected"),
    [(None, "hotel"), ("the moon", "hotel"), ("bathroom", "bathroom")],
)
async def test_continued_event_stays_unless_the_scene_moves(
    monkeypatch, generated, expected
):
    overrides = {"location": generated} if generated else {}
    _stub(monkeypatch, [_event_json(["高瀬 葵", "大島 珠子"], **overrides)])
    state = _with_previous(_state())
    group = (logic.find_resident(state, "aoi"), logic.find_resident(state, "tamako"))

    event = await gen.generate_directed_event(
        state,
        group,
        CONTINUE,
        "ja",
        novelai_model=None,
        nsfw=True,
        area_id="living",
        previous_event=state["events"][0],
    )

    assert event["area"] == "living"
    assert event["location"] == expected


# --- 出来事で変わった姿 ---


def _look_event():
    return {
        "id": "ev1",
        "title": "とりかえっこ",
        "narration": "二人は笑いながら、着ているものをそっくり取り替えた。",
        "lines": [
            {"speaker": "aoi", "text": "珠子さんのブラウス、意外と着やすいね"},
            {"speaker": "tamako", "text": "そのジャケット、私にも似合うかしら"},
        ],
        "participants": ["aoi", "tamako"],
        "instruction": "葵と珠子が服を交換する",
    }


NAMES = {"aoi": "高瀬 葵", "tamako": "大島 珠子"}
LOOKS = {
    "aoi": "1girl, brown hair, ponytail, denim jacket, leggings",
    "tamako": "1girl, silver hair, white blouse, pencil skirt",
}


@pytest.mark.asyncio
async def test_event_look_plan_gets_every_look_before_the_event(monkeypatch):
    output = json.dumps(
        {
            "changes": [
                {
                    "name": "高瀬葵",
                    "tags": ["1girl", "brown hair", "white blouse", "pencil skirt"],
                    "description": " 珠子のブラウスと\nスカートを着ている ",
                },
                # 前と同じ姿・知らない名前・タグにならない出力・2回目の同じ住民は載せない
                {"name": "大島 珠子", "tags": LOOKS["tamako"], "description": "同じ"},
                {"name": "だれか", "tags": "1girl, dress", "description": "x"},
                {"name": "大島 珠子", "tags": "ドレス姿", "description": "x"},
                {"name": "高瀬 葵", "tags": "1girl, dress", "description": "x"},
            ]
        },
        ensure_ascii=False,
    )
    calls = _stub(monkeypatch, [output])

    plan = await gen.plan_event_looks(
        _look_event(), NAMES, LOOKS, "ja", novelai_model=None
    )

    assert plan == [
        {
            "resident_id": "aoi",
            "tags": "1girl, brown hair, white blouse, pencil skirt",
            "description": "珠子のブラウスと スカートを着ている",
        }
    ]
    system, user = calls[0]
    # 服の交換は相手の出来事の前の姿が要るので、全員ぶんの姿と指示を1回で渡す
    assert f"- 高瀬 葵: {LOOKS['aoi']}" in user
    assert f"- 大島 珠子: {LOOKS['tamako']}" in user
    assert "葵と珠子が服を交換する" in user
    assert "高瀬 葵: 珠子さんのブラウス、意外と着やすいね" in user
    assert "「" not in user
    assert "the other one had before the event" in system


@pytest.mark.asyncio
async def test_event_look_plan_without_description_and_failure(monkeypatch):
    _stub(
        monkeypatch,
        [json.dumps({"changes": [{"name": "高瀬 葵", "tags": "1girl, yukata"}]})],
    )
    plan = await gen.plan_event_looks(
        _look_event(), NAMES, LOOKS, "ja", novelai_model=None
    )
    # 説明が無ければ、出来事の指示を説明にする
    assert plan[0]["description"] == "葵と珠子が服を交換する"

    _stub(monkeypatch, ["not json", "still not json"])
    with pytest.raises(HakoniwaError) as caught:
        await gen.plan_event_looks(
            _look_event(), NAMES, LOOKS, "ja", novelai_model=None
        )
    assert caught.value.code == "event_look_failed"


def test_event_look_plan_is_kept_on_the_event():
    state = logic.apply_event(
        _state(),
        {
            "title": "とりかえっこ",
            "narration": "二人は服を取り替えた。",
            "lines": [],
            "participants": ["aoi", "tamako"],
            "mood_delta": {},
            "affinity_delta": 0,
            "source": "player",
        },
        random.Random(0),
    )
    event_id = state["events"][-1]["id"]
    plan = [{"resident_id": "aoi", "tags": "1girl, yukata", "description": "浴衣姿"}]

    planned = logic.set_event_look_plan(state, event_id, plan)

    assert logic.event_look_entry(planned, event_id, "aoi") == plan[0]
    # 保存した状態を読み込み直しても残る
    reloaded = logic.normalize_state(planned)
    assert logic.event_look_entry(reloaded, event_id, "aoi") == plan[0]
    assert "look_plan" not in state["events"][-1]
    with pytest.raises(HakoniwaError) as caught:
        logic.event_look_entry(planned, event_id, "tamako")
    assert caught.value.code == "event_look_not_planned"
    with pytest.raises(HakoniwaError) as caught:
        logic.set_event_look_plan(state, "nope", plan)
    assert caught.value.code == "event_not_found"
