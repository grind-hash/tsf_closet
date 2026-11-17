"""AI箱庭のテキスト生成: 出来事の検証、名前から id への対応、定型へのフォールバック。"""

from __future__ import annotations

import json
import random

import pytest

from gateway.services import hakoniwa_generation as gen
from gateway.services import hakoniwa_logic as logic
from gateway.services.hakoniwa_prompts import (
    event_system_prompt,
    event_user_prompt,
    greeting_prompts,
    transform_reaction_prompts,
)


def _state():
    return logic.new_world_state(
        [logic.preset_resident("aoi"), logic.preset_resident("ren")]
    )


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


def _event_json(**overrides):
    data = {
        "title": "庭の朝",
        "narration": "朝の庭で、二人は芽吹いたばかりの苗を眺めていた。",
        "lines": [
            {"speaker": "高瀬葵", "text": "ほら、芽が出てるよ"},
            {"speaker": "苑田 蓮", "text": "……ああ、よく育っている"},
        ],
        "participants": ["高瀬 葵", "苑田 蓮"],
        "mood_delta": {"高瀬 葵": 5, "苑田 蓮": 99},
        "affinity_delta": 4,
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


@pytest.mark.asyncio
async def test_generated_event_maps_names_to_ids(monkeypatch):
    _stub(monkeypatch, [_event_json()])
    state = _state()
    group = tuple(state["residents"])

    event = await gen.generate_event(
        state, group, "ja", random.Random(0), novelai_model=None, nsfw=False
    )

    assert event["source"] == "llm"
    assert [line["speaker"] for line in event["lines"]] == ["aoi", "ren"]
    assert event["mood_delta"] == {"aoi": 5, "ren": 20}
    assert event["affinity_delta"] == 4


@pytest.mark.asyncio
async def test_event_bgm_is_chosen_from_scene_tracks_and_kept(monkeypatch):
    calls = _stub(monkeypatch, [_event_json(bgm="Night")])
    state = _state()
    group = tuple(state["residents"])

    event = await gen.generate_event(
        state, group, "ja", random.Random(0), novelai_model=None, nsfw=False
    )

    assert event["bgm"] == "night"
    system, _user = calls[0]
    # 選べるのは TSF シナリオの曲から結末の曲を除いたもの。重要度は物語の進み具合で測る
    assert '"bgm": "' in system
    assert "ending_success" not in system
    assert "climax of a story arc" in system
    # 年代記に残り、画面へ返す
    saved = logic.apply_event(state, event, random.Random(0))
    assert saved["events"][-1]["bgm"] == "night"


@pytest.mark.asyncio
async def test_unknown_or_ending_bgm_is_dropped_without_a_repair(monkeypatch):
    for value in ("ending_success", "scene07_important_event.ogg", 3):
        calls = _stub(monkeypatch, [_event_json(bgm=value)])
        state = _state()

        event = await gen.generate_event(
            state,
            tuple(state["residents"]),
            "ja",
            random.Random(0),
            novelai_model=None,
            nsfw=False,
        )

        assert event["source"] == "llm"
        assert "bgm" not in event
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_unknown_speaker_falls_back_to_template(monkeypatch):
    bad = _event_json(lines=[{"speaker": "知らない人", "text": "やあ"}])
    calls = _stub(monkeypatch, [bad, bad])
    state = _state()

    event = await gen.generate_event(
        state,
        tuple(state["residents"]),
        "ja",
        random.Random(0),
        novelai_model=None,
        nsfw=False,
    )

    assert event["source"] == "template"
    assert len(calls) == 2  # 1回目と修復の依頼
    assert set(event["participants"]) == {"aoi", "ren"}


@pytest.mark.asyncio
async def test_rule_focus_event_retries_once_more(monkeypatch):
    state = logic.add_custom_rule(_state(), "掟", "全員メイド服で過ごす")
    rule_id = state["custom_rules"][0]["id"]
    state = logic.set_rule(state, rule_id, True, random.Random(0))
    calls = _stub(monkeypatch, [RuntimeError("x"), _event_json()])

    event = await gen.generate_event(
        state,
        tuple(state["residents"]),
        "ja",
        random.Random(0),
        novelai_model=None,
        nsfw=False,
        rule_focus_rule_id=rule_id,
    )

    assert event["source"] == "llm"
    assert "Repeated, mandatory" in calls[1][1]


@pytest.mark.asyncio
async def test_greeting_falls_back_to_preset_lines(monkeypatch):
    _stub(monkeypatch, [RuntimeError("down")])
    state = _state()

    greeting = await gen.generate_greeting(
        state,
        logic.find_resident(state, "aoi"),
        "en",
        random.Random(0),
        novelai_model=None,
        nsfw=False,
    )

    assert greeting["source"] == "template"
    assert (
        greeting["text"]
        in logic.resident_text(logic.find_resident(state, "aoi"), "en")["greetings"]
    )


@pytest.mark.asyncio
async def test_convert_change_to_tags_retries_until_english(monkeypatch):
    _stub(monkeypatch, ["メイド服の女の子", "```", "1girl, maid, long hair"])

    tags = await gen.convert_change_to_tags("メイド服", "1boy", novelai_model=None)

    assert tags == "1girl, maid, long hair"


def test_template_event_prefers_swap_templates_for_swap_pair():
    state = logic.set_rule(_state(), "swap", True, random.Random(0))
    group = tuple(state["residents"])
    swap_titles = {t["title"] for t in gen.HAKONIWA_TEMPLATES["en"]["swap"]}

    titles = {
        gen.template_event(state, group, "en", random.Random(seed))["title"]
        for seed in range(30)
    }

    assert titles & swap_titles


def test_prompts_carry_rules_language_and_male_guidance():
    state = logic.set_rule(_state(), "dress", True, random.Random(0))
    group = tuple(state["residents"])

    system = event_system_prompt(group, state, "en", nsfw=False)
    user = event_user_prompt(state, group, "en", nsfw=False, others_today=[["Ritsu"]])

    assert "in English" in system
    assert "male bodies" in system
    assert "non-explicit" in system
    assert "Rule of Dresses" not in user  # 掟は表示名ではなく指示文を渡す
    assert "wear a dress" in user
    assert "Ren Sonoda is a man wearing feminine clothes" in user
    assert "Ritsu" in user
    assert "くん" not in system
    assert "くん" in event_system_prompt(group, state, "ja", nsfw=False)


def test_clean_tags_rejects_japanese_and_caps_length_at_tag_boundary():
    assert gen.clean_tags("メイド服") is None
    many = ", ".join(f"tag{i}" for i in range(40))
    assert len(gen.clean_tags(many).split(", ")) == 40
    long = ", ".join(f"longtag{i:04d}" for i in range(300))
    cleaned = gen.clean_tags(long)
    assert len(cleaned) <= gen.HAKONIWA_TAGS_MAX_LENGTH
    assert all(
        tag.startswith("longtag") and len(tag) == 11 for tag in cleaned.split(", ")
    )
    assert gen.needs_tag_expansion("茶髪のポニーテール")
    assert not gen.needs_tag_expansion("1girl, brown hair")


def test_prompts_keep_each_mind_pronoun_and_forbid_simplified_chinese():
    state = logic.set_rule(_state(), "swap", True, random.Random(0))
    group = tuple(state["residents"])

    system = event_system_prompt(group, state, "ja", nsfw=False)
    user = event_user_prompt(state, group, "ja", nsfw=False)

    assert "keeps their own first-person pronoun" in system
    assert "simplified Chinese" in system
    assert "First-person pronoun: 俺" in user
    assert "First-person pronoun: 私" in user
    assert "simplified Chinese" not in event_system_prompt(
        group, state, "en", nsfw=False
    )


def test_male_guidance_depends_on_body_or_outfit():
    dressed = logic.set_rule(_state(), "dress", True, random.Random(0))
    group = tuple(dressed["residents"])
    outfit_prompt = event_user_prompt(dressed, group, "en", nsfw=False)
    assert "his own body stays male" in outfit_prompt
    assert "different center of gravity" not in outfit_prompt

    transformed = logic.set_transformation(
        _state(),
        "ren",
        {
            "description": "女の子に",
            "tags": "1girl, long hair",
            "image": "x.png",
            "day": 1,
        },
    )
    group = tuple(transformed["residents"])
    body_prompt = event_user_prompt(transformed, group, "en", nsfw=False)
    assert "different center of gravity" in body_prompt


@pytest.mark.parametrize("language", ["ja", "en"])
@pytest.mark.parametrize("look", ["dress", "outfit", "body", "swap"])
def test_greeting_and_reaction_distinguish_body_from_outfit(language, look):
    state = _state()
    if look in ("dress", "swap"):
        state = logic.set_rule(state, look, True, random.Random(0))
    else:
        state = logic.set_transformation(
            state,
            "ren",
            {
                "description": "姿を変更",
                "tags": "1girl, dress" if look == "body" else "1boy, dress",
                "image": "x.png",
                "day": 1,
            },
        )
    target = logic.find_resident(state, "ren")
    _, greeting = greeting_prompts(state, target, language, nsfw=False)
    _, reaction = transform_reaction_prompts(
        state, target, "姿を変更", [], language, nsfw=False
    )

    if look in ("body", "swap"):
        assert "strangeness of the body" in greeting
        assert "different center of gravity" in reaction
    else:
        assert "body stays male" in greeting
        assert "strangeness of the body" not in greeting
        if look == "outfit":
            assert "his own body stays male" in reaction
        assert "different center of gravity" not in reaction
    assert f"First-person pronoun: {'俺' if language == 'ja' else 'I'}" in reaction
