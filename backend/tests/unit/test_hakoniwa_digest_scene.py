"""AI箱庭の1日のまとめと場面絵の組み立て。"""

from __future__ import annotations

import random

from gateway.services import hakoniwa_logic as logic
from gateway.services.hakoniwa_digest import build_day_digest
from gateway.services.hakoniwa_scene import scene_request, scene_suggestion


def _world(preset_ids=("aoi", "shiori", "ren")):
    return logic.new_world_state([logic.preset_resident(pid) for pid in preset_ids])


def _event(**fields):
    return {
        "id": fields.pop("id", "e1"),
        "title": "t",
        "narration": "n",
        "lines": [],
        "participants": ["aoi", "ren"],
        "mood_delta": {},
        "affinity_delta": 0,
        **fields,
    }


def test_highlight_prefers_transform_then_movement():
    before = _world()
    events = [
        _event(id="a", affinity_delta=2, mood_delta={"aoi": 3}),
        _event(id="b", affinity_delta=-9),
        _event(id="c", kind="transform", participants=["ren"]),
    ]

    digest = build_day_digest(before, before, events)
    assert digest["highlight"]["event_id"] == "c"
    assert digest["highlight"]["reason"] == "transform"

    digest = build_day_digest(before, before, events[:2])
    assert digest["highlight"] == {
        "event_id": "b",
        "title": "t",
        "reason": "movement",
        "participants": ["aoi", "ren"],
    }
    assert digest["day"] == 1


def test_changes_list_affinity_and_big_mood_swings():
    before = _world()
    after = logic.apply_event(
        before,
        _event(affinity_delta=-9, mood_delta={"shiori": 12}),
        random.Random(0),
    )

    changes = build_day_digest(before, after, [after["events"][-1]])["changes"]

    assert changes[0]["type"] == "affinity"
    assert changes[0]["delta"] == -9
    assert changes[1]["type"] == "mood"
    assert changes[1]["id"] == "shiori"


def test_tomorrow_hint_order():
    state = _world()
    assert build_day_digest(state, state, [])["hint"] == {"type": "no_rules"}

    state = logic.set_rule(state, "dress", True, random.Random(0))
    assert build_day_digest(state, state, [])["hint"] == {
        "type": "more_rules",
        "remaining": 2,
    }

    near = logic.update_resident(state, "aoi", {})
    near["residents"][0]["affinities"]["ren"] = 25
    hint = build_day_digest(near, near, [])["hint"]
    assert hint == {
        "type": "near_close",
        "ids": ["aoi", "ren"],
        "value": 25,
        "remaining": 5,
    }

    swapped = logic.set_rule(near, "swap", True, random.Random(0))
    assert build_day_digest(swapped, swapped, [])["hint"]["type"] == "swap"


def test_scene_suggestion_for_contact_words_in_ja_and_en():
    hug_ja = _event(narration="二人はそっと抱き合った。")
    hug_en = _event(lines=[{"speaker": "aoi", "text": "Let me hug you."}])

    assert scene_suggestion(hug_ja, "ja")["level"] == "normal"
    assert scene_suggestion(hug_en, "en")["reason"].startswith("Residents touch")
    assert scene_suggestion(_event(), "ja") is None
    assert scene_suggestion({**hug_ja, "participants": ["aoi"]}, "ja") is None
    assert scene_suggestion({**hug_ja, "scene_image": "x.png"}, "ja") is None


def test_scene_request_places_characters_and_uses_current_looks():
    state = logic.set_rule(_world(), "dress", True, random.Random(0))
    event = _event(area="garden", participants=["aoi", "ren"])

    request = scene_request(state, event, "hugging, smiling")

    assert request["prompt"].startswith("1girl, 1boy, sparse japanese garden")
    assert "hugging, smiling" in request["prompt"]
    left, right = request["characters"]
    assert left["position"] == (0.3, 0.5)
    assert right["position"] == (0.7, 0.5)
    assert left["fixed_position"] and right["fixed_position"]
    assert "coral sundress" in left["prompt"]
    assert "solo" not in left["prompt"].split(", ")
    assert "dark green hair" in left["negative_prompt"]


def test_scene_request_follows_body_swap_and_single_participant():
    state = logic.set_rule(_world(("aoi", "ren")), "swap", True, random.Random(0))

    request = scene_request(state, _event(participants=["aoi"]), "")

    only = request["characters"][0]
    assert only["position"] == (0.5, 0.5)
    assert "fixed_position" not in only
    assert "dark green hair" in only["prompt"]
    assert request["prompt"].startswith("1boy")
    assert "cinematic scene" in request["prompt"]
