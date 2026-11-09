"""AI箱庭の世界の状態遷移(純粋関数)のテスト。"""

from __future__ import annotations

import random

import pytest

from gateway.consts.hakoniwa import (
    HAKONIWA_EVENT_LOG_MAX,
    HAKONIWA_MAX_ACTIVE_RULES,
    HAKONIWA_TRANSFORMATION_HISTORY_MAX,
)
from gateway.services import hakoniwa_logic as logic
from gateway.services.hakoniwa_logic import HakoniwaError

PRESETS = ["aoi", "shiori", "tamako", "ren", "ritsu"]


def _world(preset_ids=PRESETS):
    return logic.new_world_state([logic.preset_resident(pid) for pid in preset_ids])


def _male(name: str) -> dict:
    return logic.custom_resident(
        name=name,
        personality="穏やか",
        gender="male",
        appearance_text="",
        base_tags="1boy, short hair",
    )


def test_new_world_uses_preset_affinities_and_zero_for_others():
    custom = _male("ユウ")
    state = logic.new_world_state([logic.preset_resident("aoi"), custom])
    aoi = logic.find_resident(state, "aoi")

    assert state["day"] == 1
    assert aoi["affinities"] == {custom["id"]: 0}
    full = _world()
    assert logic.find_resident(full, "aoi")["affinities"]["tamako"] == 15


def test_new_world_requires_two_residents():
    with pytest.raises(HakoniwaError) as error:
        logic.new_world_state([logic.preset_resident("aoi")])
    assert error.value.code == "too_few_residents"


def test_preset_text_follows_language_unless_edited():
    state = _world()
    aoi = logic.find_resident(state, "aoi")

    assert logic.resident_name(aoi, "ja") == "高瀬 葵"
    assert logic.resident_name(aoi, "en") == "Aoi Takase"
    edited = logic.update_resident(state, "aoi", {"name": "あおい"})
    assert logic.resident_name(logic.find_resident(edited, "aoi"), "en") == "あおい"


def test_swap_rule_picks_a_pair_and_limits_active_rules():
    rng = random.Random(1)
    state = logic.set_rule(_world(), "swap", True, rng)

    assert len(state["swap_pair"]) == 2
    for card_id in ["dress", "ojousama"]:
        state = logic.set_rule(state, card_id, True, rng)
    assert len(state["active_rules"]) == HAKONIWA_MAX_ACTIVE_RULES
    with pytest.raises(HakoniwaError) as error:
        logic.set_rule(state, "confession", True, rng)
    assert error.value.code == "too_many_rules"
    cleared = logic.set_rule(state, "swap", False, rng)
    assert cleared["swap_pair"] is None


def test_choose_groups_always_includes_swap_pair():
    state = logic.set_rule(_world(), "swap", True, random.Random(2))
    pair = set(state["swap_pair"])

    for seed in range(20):
        groups = logic.choose_groups(state, random.Random(seed))
        assert len(groups) == 3
        assert {r["id"] for r in groups[0]} == pair


def test_romance_rules_never_pick_male_bodies_together():
    residents = [logic.preset_resident("aoi"), _male("ユウ"), _male("ケン")]
    residents.append(logic.preset_resident("ren"))
    state = logic.new_world_state(residents)
    state = logic.set_rule(state, "confession", True, random.Random(0))

    for seed in range(60):
        for group in logic.choose_groups(state, random.Random(seed)):
            if len(group) >= 2:
                genders = {logic.body_gender(state, r) for r in group}
                assert genders != {"male"}


def test_body_gender_follows_transformation_and_swap():
    state = _world(["aoi", "ren"])
    state = logic.set_transformation(
        state,
        "ren",
        {
            "description": "女の子に",
            "tags": "1girl, long hair",
            "image": "tf.png",
            "day": 1,
        },
    )
    ren = logic.find_resident(state, "ren")
    assert logic.body_gender(state, ren) == "female"
    assert logic.is_male_in_feminine_form(state, ren)

    cleared = logic.clear_transformation(state, "ren")
    swapped = logic.set_rule(cleared, "swap", True, random.Random(0))
    ren = logic.find_resident(swapped, "ren")
    assert logic.body_gender(swapped, ren) == "female"


def test_display_look_priority_transform_dress_base_and_swap():
    state = logic.set_rule(_world(["aoi", "ren"]), "dress", True, random.Random(0))
    aoi = logic.find_resident(state, "aoi")
    assert logic.display_look(state, aoi) == {
        "kind": "dress",
        "file": None,
        "bundled": True,
        "owner": "aoi",
    }

    state = logic.set_transformation(
        state,
        "aoi",
        {
            "description": "メイド服",
            "tags": "1girl, maid",
            "image": "tf_a.png",
            "day": 1,
        },
    )
    aoi = logic.find_resident(state, "aoi")
    assert logic.display_look(state, aoi)["file"] == "tf_a.png"

    state = logic.set_rule(state, "swap", True, random.Random(0))
    ren = logic.find_resident(state, "ren")
    look = logic.display_look(state, ren)
    assert look["owner"] == "aoi"
    assert look["file"] == "tf_a.png"


def test_custom_resident_without_avatar_has_no_bundled_look():
    state = logic.add_resident(_world(["aoi", "ren"]), _male("ユウ"))
    custom = state["residents"][-1]

    assert logic.own_look(state, custom) == {
        "kind": "base",
        "file": None,
        "bundled": False,
    }
    assert custom["affinities"] == {"aoi": 0, "ren": 0}
    assert logic.find_resident(state, "aoi")["affinities"][custom["id"]] == 0


def test_transformation_history_is_capped_and_reapplicable():
    state = _world(["aoi", "ren"])
    for index in range(HAKONIWA_TRANSFORMATION_HISTORY_MAX + 3):
        state = logic.set_transformation(
            state,
            "aoi",
            {
                "description": f"姿{index}",
                "tags": "1girl",
                "image": f"tf_{index}.png",
                "day": 1,
            },
        )
    aoi = logic.find_resident(state, "aoi")
    assert len(aoi["transformation_history"]) == HAKONIWA_TRANSFORMATION_HISTORY_MAX

    state = logic.reapply_transformation(state, "aoi", "tf_5.png")
    assert logic.find_resident(state, "aoi")["transformation"]["description"] == "姿5"
    with pytest.raises(HakoniwaError):
        logic.reapply_transformation(state, "aoi", "tf_0.png")


def test_remove_resident_clears_swap_and_affinities():
    state = logic.set_rule(
        _world(["aoi", "ren", "ritsu"]), "swap", True, random.Random(0)
    )
    target = state["swap_pair"][0]

    removed = logic.remove_resident(state, target)

    assert removed["swap_pair"] is None
    assert "swap" not in removed["active_rules"]
    assert all(target not in r["affinities"] for r in removed["residents"])
    with pytest.raises(HakoniwaError):
        logic.remove_resident(
            logic.remove_resident(removed, removed["residents"][0]["id"]), "x"
        )


def test_apply_event_clamps_and_records():
    state = _world(["aoi", "ren"])
    event = {
        "title": "t",
        "narration": "n",
        "lines": [{"speaker": "aoi", "text": "hi"}],
        "participants": ["aoi", "ren"],
        "mood_delta": {"aoi": 500},
        "affinity_delta": 100,
        "source": "llm",
    }

    state = logic.apply_event(state, event, random.Random(0))

    aoi = logic.find_resident(state, "aoi")
    assert 98 <= aoi["mood"] <= 100
    assert aoi["affinities"]["ren"] == 50
    assert state["last_pair"] == ["aoi", "ren"]
    assert state["events"][-1]["lines"] == [{"speaker": "aoi", "text": "hi"}]


def test_trim_events_keeps_favorites():
    events = [
        {"id": str(i), "favorite": i == 0} for i in range(HAKONIWA_EVENT_LOG_MAX + 5)
    ]

    trimmed = logic.trim_events(events)

    assert len(trimmed) == HAKONIWA_EVENT_LOG_MAX
    assert trimmed[0]["id"] == "0"


def test_custom_rule_focus_skips_male_only_groups():
    state = logic.new_world_state(
        [logic.preset_resident("aoi"), _male("ユウ"), logic.preset_resident("ren")]
    )
    state = logic.add_custom_rule(state, "掟", "全員メイド服")
    rule_id = state["custom_rules"][0]["id"]
    state = logic.set_rule(state, rule_id, True, random.Random(0))
    by_id = {r["id"]: r for r in state["residents"]}
    male_ids = [r["id"] for r in state["residents"] if r["gender"] == "male"]
    groups = [
        (by_id[male_ids[0]], by_id[male_ids[1]]),
        (by_id["aoi"], by_id["ren"]),
    ]

    assert logic.custom_rule_focus_assignments(state, groups) == {1: rule_id}


def test_gender_token_helpers():
    assert logic.tags_gender("1boy, short hair") == "male"
    assert logic.tags_gender("solo, mature female") == "female"
    assert logic.tags_gender("tomboy, long hair") is None
    assert logic.ensure_gender_token("long hair", "male") == "1boy, long hair"
    assert logic.ensure_gender_token("1girl, long hair", "male") == "1girl, long hair"
    assert logic.ensure_gender_token("", "female").startswith("1girl")
