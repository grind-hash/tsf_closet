"""AI箱庭の出来事の場所: エリアの外の場所(浴室・商店街など)の選び方と場面の絵の背景。"""

from __future__ import annotations

import json
import random

import pytest

from gateway.consts.hakoniwa import HAKONIWA_LOCATION_MAP, event_location
from gateway.services import hakoniwa_generation as gen
from gateway.services import hakoniwa_logic as logic
from gateway.services.hakoniwa_errors import HakoniwaError
from gateway.services.hakoniwa_prompts import event_user_prompt
from gateway.services.hakoniwa_scene import scene_request


def _state():
    return logic.new_world_state(
        [logic.preset_resident("aoi"), logic.preset_resident("tamako")]
    )


def _group(state):
    return tuple(state["residents"])


def _event_json(**overrides) -> str:
    data = {
        "title": "湯けむり",
        "narration": "湯気の立つ浴室で、二人は肩を並べて湯船に浸かった。",
        "lines": [
            {"speaker": "高瀬 葵", "text": "あったかいね"},
            {"speaker": "大島 珠子", "text": "ほんとにねえ"},
        ],
        "participants": ["高瀬 葵", "大島 珠子"],
        "mood_delta": {"高瀬 葵": 3},
        "affinity_delta": 2,
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def _stub(monkeypatch, outputs):
    calls: list[tuple[str, str]] = []
    queue = list(outputs)

    async def fake(system, user, *, novelai_model, max_tokens=1400):
        calls.append((system, user))
        return queue.pop(0) if queue else ""

    monkeypatch.setattr(gen, "_generate_text", fake)
    return calls


# --- 場所の決め方 ---


def test_settle_keeps_an_outside_place_and_the_area():
    event = logic.settle_event_location({"title": "x"}, "living", "bathroom")

    assert event["area"] == "living"
    assert event["location"] == "bathroom"


def test_settle_moves_to_an_area_location():
    event = logic.settle_event_location({"title": "x"}, "living", "garden")

    assert event["area"] == "garden"
    assert "location" not in event


@pytest.mark.parametrize("location", [None, "", "moon"])
def test_settle_ignores_unknown_places(location):
    event = logic.settle_event_location({"location": "stale"}, "study", location)

    assert event["area"] == "study"
    assert "location" not in event


def test_validate_event_location():
    assert logic.validate_event_location("") is None
    assert logic.validate_event_location(" beach ") == "beach"
    with pytest.raises(HakoniwaError) as error:
        logic.validate_event_location("moon")
    assert error.value.code == "invalid_location"


def test_event_location_falls_back_to_the_area():
    assert event_location({"area": "garden"})["id"] == "garden"
    assert event_location({"area": "garden", "location": "cafe"})["id"] == "cafe"
    assert event_location({})["id"] == "living"


# --- プロンプト ---


def test_daily_prompt_offers_other_places_but_prefers_the_area():
    state = _state()

    prompt = event_user_prompt(state, _group(state), "ja", nsfw=False, area_id="garden")

    assert 'Usually set "location" to "garden"' in prompt
    assert "bathroom:" in prompt
    assert "shopping_street:" in prompt
    assert "garden:" not in prompt


def test_directed_auto_place_follows_the_order():
    state = _state()

    prompt = event_user_prompt(
        state,
        _group(state),
        "ja",
        nsfw=False,
        area_id="living",
        directed_instruction="商店街へ買い物に出かける",
    )

    assert "takes place at the destination" in prompt
    assert "Usually set" not in prompt


def test_fixed_place_uses_its_scene_and_no_choice():
    state = _state()

    prompt = event_user_prompt(
        state,
        _group(state),
        "ja",
        nsfw=False,
        area_id="living",
        directed_instruction="一緒にシャワーを浴びる",
        location_id="bathroom",
    )

    assert HAKONIWA_LOCATION_MAP["bathroom"]["scene"] in prompt
    assert 'Set "location" to "bathroom".' in prompt
    assert "Usually set" not in prompt


# --- 生成 ---


@pytest.mark.asyncio
async def test_generated_event_can_move_outside(monkeypatch):
    _stub(monkeypatch, [_event_json(location="bathroom")])
    state = _state()

    event = await gen.generate_event(
        state,
        _group(state),
        "ja",
        random.Random(0),
        novelai_model=None,
        nsfw=False,
        area_id="living",
    )

    assert event["area"] == "living"
    assert event["location"] == "bathroom"


@pytest.mark.asyncio
async def test_generated_event_with_unknown_place_stays_in_the_area(monkeypatch):
    _stub(monkeypatch, [_event_json(location="the moon")])
    state = _state()

    event = await gen.generate_event(
        state,
        _group(state),
        "ja",
        random.Random(0),
        novelai_model=None,
        nsfw=False,
        area_id="study",
    )

    assert event["area"] == "study"
    assert "location" not in event


@pytest.mark.asyncio
async def test_player_place_wins_over_the_generated_one(monkeypatch):
    _stub(monkeypatch, [_event_json(location="park")])
    state = _state()

    event = await gen.generate_directed_event(
        state,
        _group(state),
        "一緒にシャワーを浴びる",
        "ja",
        novelai_model=None,
        nsfw=False,
        area_id="living",
        location_id="bathroom",
    )

    assert event["location"] == "bathroom"


# --- 場面の絵 ---


def test_scene_image_uses_the_place_background():
    state = _state()
    event = {"participants": ["aoi", "tamako"], "area": "living", "location": "beach"}

    request = scene_request(state, event, "smile")

    assert HAKONIWA_LOCATION_MAP["beach"]["scene_tags"] in request["prompt"]
    assert "living room" not in request["prompt"]
