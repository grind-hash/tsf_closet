"""AI箱庭のエリアと家具: 場所の決め方、家具の置き方、出来事の場所、プロンプトの場所の文。"""

from __future__ import annotations

import random

import pytest

from gateway.consts.hakoniwa import HAKONIWA_AREA_MAP
from gateway.services import hakoniwa_logic as logic
from gateway.services.hakoniwa_logic import HakoniwaError
from gateway.services.hakoniwa_prompts import place_text


def _world(preset_ids=("aoi", "shiori", "tamako", "ren", "ritsu")):
    return logic.new_world_state([logic.preset_resident(pid) for pid in preset_ids])


def test_presets_start_in_their_areas_and_layout_is_empty():
    state = _world()

    areas = {r["id"]: r["current_area"] for r in state["residents"]}
    assert areas == {
        "aoi": "living",
        "shiori": "study",
        "tamako": "living",
        "ren": "garden",
        "ritsu": "living",
    }
    assert state["furniture_layout"] == {
        "living": [None] * 4,
        "garden": [None] * 4,
        "study": [None] * 4,
    }


def test_placing_furniture_moves_the_single_item():
    state = logic.place_furniture(_world(), "living", 0, "lamp")
    moved = logic.place_furniture(state, "garden", 2, "lamp")

    assert moved["furniture_layout"]["living"][0] is None
    assert moved["furniture_layout"]["garden"][2] == "lamp"
    assert logic.placed_furniture(moved, "garden") == ["lamp"]
    cleared = logic.place_furniture(moved, "garden", 2, None)
    assert logic.placed_furniture(cleared, "garden") == []


@pytest.mark.parametrize(
    ("area", "slot", "item", "code"),
    [
        ("kitchen", 0, "lamp", "area_not_found"),
        ("living", 4, "lamp", "invalid_slot"),
        ("living", 0, "sofa", "furniture_not_found"),
    ],
)
def test_placing_furniture_validates_input(area, slot, item, code):
    with pytest.raises(HakoniwaError) as error:
        logic.place_furniture(_world(), area, slot, item)
    assert error.value.code == code


def test_normalize_drops_unknown_and_duplicate_furniture():
    state = _world()
    state["furniture_layout"] = {
        "living": ["lamp", "sofa", "lamp"],
        "garden": ["plush"],
    }

    normalized = logic.normalize_state(state)

    assert normalized["furniture_layout"]["living"] == ["lamp", None, None, None]
    assert normalized["furniture_layout"]["garden"] == ["plush", None, None, None]
    assert normalized["furniture_layout"]["study"] == [None] * 4


def test_events_gather_participants_in_their_area():
    state = _world(("aoi", "ren"))
    event = {
        "title": "t",
        "narration": "n",
        "lines": [],
        "participants": ["aoi", "ren"],
        "area": "study",
    }

    state = logic.apply_event(state, event, random.Random(0))

    assert state["events"][-1]["area"] == "study"
    assert {r["current_area"] for r in state["residents"]} == {"study"}
    unknown = logic.apply_event(state, {**event, "area": "moon"}, random.Random(0))
    assert unknown["events"][-1]["area"] == "living"


def test_event_area_is_usually_where_participants_are():
    state = _world(("shiori", "ren"))
    group = tuple(state["residents"])
    picked = [
        logic.pick_event_area(state, group, random.Random(seed)) for seed in range(200)
    ]

    assert set(picked) <= set(HAKONIWA_AREA_MAP)
    at_home = sum(1 for area in picked if area in {"study", "garden"})
    assert at_home > 140


def test_finish_day_sometimes_moves_residents():
    state = _world()
    moved = 0
    for seed in range(40):
        after = logic.finish_day(state, random.Random(seed))
        moved += sum(
            1
            for before, now in zip(state["residents"], after["residents"], strict=True)
            if before["current_area"] != now["current_area"]
        )
    assert 0 < moved < 40 * 5
    assert logic.finish_day(state)["residents"] == state["residents"]


def test_bystanders_are_in_the_same_area():
    state = _world()

    others = logic.bystanders(state, "aoi", random.Random(0))

    assert {r["id"] for r in others} <= {"tamako", "ritsu"}
    assert logic.bystanders(state, "ren", random.Random(0)) == []


def test_place_text_mentions_scene_and_furniture():
    state = logic.place_furniture(_world(), "garden", 1, "aquarium")

    text = place_text(state, "garden")

    assert "garden of Stardust House" in text
    assert "aquarium" in text
    assert "Placed here" not in place_text(state, "study")
