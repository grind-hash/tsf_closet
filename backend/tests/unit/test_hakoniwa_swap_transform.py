"""AI箱庭: 入れ替わり中の変身。変身は体に付き、その体にいる人が体験する。"""

from __future__ import annotations

import random

import pytest

from gateway.services import hakoniwa_logic as logic
from gateway.services import hakoniwa_story as story
from gateway.services.hakoniwa_errors import HakoniwaError
from gateway.services.hakoniwa_prompts import current_appearance_summary
from gateway.services.hakoniwa_service import _resident_view


def _swapped_world():
    """葵と蓮が入れ替わった世界(葵は蓮の体、蓮は葵の体にいる)。"""
    state = logic.new_world_state(
        [logic.preset_resident(pid) for pid in ("aoi", "shiori", "ren")]
    )
    residents = []
    for resident in state["residents"]:
        entry = dict(resident)
        if entry["id"] in ("aoi", "ren"):
            story.start_adaptation(entry, "swap", state["day"])
        residents.append(entry)
    return {
        **state,
        "active_rules": ["swap"],
        "swap_pair": ["aoi", "ren"],
        "residents": residents,
    }


def _transform(state, resident_id, image="tf_ren_1.png"):
    return logic.set_transformation(
        state,
        resident_id,
        {
            "description": "メイド服に着替えて",
            "tags": "1boy, maid",
            "image": image,
            "day": state["day"],
        },
    )


def test_transform_during_swap_changes_the_body_the_person_is_in():
    state = _transform(_swapped_world(), "aoi")
    aoi = logic.find_resident(state, "aoi")
    ren = logic.find_resident(state, "ren")

    # 葵がいる蓮の体に変身が付く
    assert ren["transformation"]["image"] == "tf_ren_1.png"
    assert aoi["transformation"] is None
    # 表示: 葵の名札の姿(蓮の体)が変わり、蓮の名札の姿(葵の体)は変わらない
    assert logic.display_look(state, aoi)["kind"] == "transform"
    assert logic.display_look(state, aoi)["file"] == "tf_ren_1.png"
    assert logic.display_look(state, ren)["kind"] != "transform"
    # 文章: 変身したのは葵として扱う
    assert logic.appearance_kind(state, aoi) == "transform"
    assert logic.appearance_kind(state, ren) != "transform"
    assert "メイド服" in (current_appearance_summary(state, aoi) or "")
    assert "メイド服" not in (current_appearance_summary(state, ren) or "")
    # 適応は体験している葵に付く
    assert aoi["adaptation"]["kind"] == "transform"
    assert story.resident_adaptation(state, aoi) is not None


def test_resident_view_shows_the_inhabited_body_transformation():
    state = _transform(_swapped_world(), "aoi")
    aoi_view = _resident_view("w1", state, logic.find_resident(state, "aoi"), "ja")
    ren_view = _resident_view("w1", state, logic.find_resident(state, "ren"), "ja")
    assert aoi_view["transformation"] is not None
    assert [item["image"] for item in aoi_view["transformation_history"]] == [
        "tf_ren_1.png"
    ]
    assert ren_view["transformation"] is None
    assert ren_view["transformation_history"] == []


def test_clear_and_reapply_act_on_the_inhabited_body():
    state = _transform(_swapped_world(), "aoi")
    # 蓮がいる葵の体は変身していない
    with pytest.raises(HakoniwaError):
        logic.clear_transformation(state, "ren")

    cleared = logic.clear_transformation(state, "aoi")
    assert logic.find_resident(cleared, "ren")["transformation"] is None
    assert (
        logic.current_transformation(cleared, logic.find_resident(cleared, "aoi"))
        is None
    )

    again = logic.reapply_transformation(cleared, "aoi", "tf_ren_1.png")
    assert logic.find_resident(again, "ren")["transformation"]["image"] == (
        "tf_ren_1.png"
    )


def test_swap_end_returns_the_transformed_body_to_its_owner():
    state = _transform(_swapped_world(), "aoi")
    ended = logic.set_rule(state, "swap", False, random.Random(0))
    aoi = logic.find_resident(ended, "aoi")
    ren = logic.find_resident(ended, "ren")

    # 変身した体は蓮のもの。戻った蓮の姿が変身後になり、葵は元の姿に戻る
    assert logic.display_look(ended, ren)["kind"] == "transform"
    assert logic.display_look(ended, aoi)["kind"] != "transform"
    assert logic.appearance_kind(ended, ren) == "transform"
    assert logic.appearance_kind(ended, aoi) != "transform"
    # 蓮は変身した体への適応を始め、入れ替わりの名残も残る
    assert ren["adaptation"]["kind"] == "transform"
    assert ren["remnant"] is not None
    # 葵の変身への適応は、変身した体を出たので続かない
    assert story.resident_adaptation(ended, aoi) is None


def test_removing_a_swapped_resident_returns_the_partner_to_their_body():
    state = _transform(_swapped_world(), "aoi")
    removed = logic.remove_resident(state, "aoi")
    ren = logic.find_resident(removed, "ren")
    assert removed["swap_pair"] is None
    assert logic.display_look(removed, ren)["kind"] == "transform"
    assert ren["adaptation"]["kind"] == "transform"
