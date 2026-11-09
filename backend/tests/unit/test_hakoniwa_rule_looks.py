"""AI箱庭の掟の姿と複合の姿: 表示の優先順位・生成状況・プロンプトの姿の説明。"""

from __future__ import annotations

import random

from gateway.services import hakoniwa_logic as logic
from gateway.services.hakoniwa_generation import clean_look_tags
from gateway.services.hakoniwa_prompts import (
    appearance_focus_text,
    current_appearance_summary,
)
from gateway.services.hakoniwa_scene import look_tags


def _world():
    return logic.new_world_state([logic.preset_resident(pid) for pid in ("aoi", "ren")])


def _with_rule(state, name="メイドの日", tags="maid outfit, apron"):
    state = logic.add_custom_rule(state, name, "全員がメイド服で過ごす", "", tags)
    rule_id = state["custom_rules"][-1]["id"]
    return logic.set_rule(state, rule_id, True, random.Random(0)), rule_id


def _look(state, resident_id, kind, key, tags="maid outfit", source="maid outfit"):
    return logic.set_look_image(
        state,
        resident_id,
        kind=kind,
        key=key,
        entry={
            "image": f"{kind}_{resident_id}.png",
            "tags": tags,
            "source_tags": source,
        },
    )


def test_clean_look_tags_drops_person_tags():
    assert clean_look_tags("1girl, maid outfit, solo, cat ears, 2boys") == (
        "maid outfit, cat ears"
    )
    assert clean_look_tags("メイド服") is None


def test_display_priority_transform_combo_rule_dress_base():
    state, rule_id = _with_rule(_world(), tags="maid outfit")
    aoi = logic.find_resident(state, "aoi")
    assert logic.own_look(state, aoi)["kind"] == "base"
    assert logic.appearance_kind(state, aoi) == "rule"

    state = _look(state, "aoi", "rule", rule_id)
    assert logic.own_look(state, logic.find_resident(state, "aoi"))["kind"] == "rule"

    state = logic.set_rule(state, "dress", True, random.Random(0))
    combo = logic.active_combo(state)
    assert combo["includes_dress"] is True
    # 複合の姿がまだ無ければ、掟の姿のまま
    assert logic.own_look(state, logic.find_resident(state, "aoi"))["kind"] == "rule"
    state = _look(state, "aoi", "combo", combo["digest"], source="maid outfit")
    look = logic.own_look(state, logic.find_resident(state, "aoi"))
    assert (look["kind"], look["tags"]) == ("combo", "maid outfit")

    state = logic.set_transformation(
        state,
        "aoi",
        {
            "description": "魔法少女",
            "tags": "1girl, magical girl",
            "image": "tf.png",
            "day": 1,
        },
    )
    assert (
        logic.own_look(state, logic.find_resident(state, "aoi"))["kind"] == "transform"
    )
    # 掟を外すと、ドレス姿へ戻る
    plain = logic.set_rule(
        logic.clear_transformation(state, "aoi"), rule_id, False, random.Random(0)
    )
    assert logic.own_look(plain, logic.find_resident(plain, "aoi"))["kind"] == "dress"


def test_later_rule_wins_and_swap_shows_partner_look():
    state, first = _with_rule(_world(), "メイドの日", "maid outfit")
    state, second = _with_rule(state, "猫の日", "cat ears")
    state = _look(state, "ren", "rule", first, tags="1boy, maid outfit")
    state = _look(state, "ren", "rule", second, tags="1boy, cat ears")

    assert logic.own_look(state, logic.find_resident(state, "ren"))["rule_id"] == second
    state = {
        **state,
        "active_rules": [*state["active_rules"], "swap"],
        "swap_pair": ["aoi", "ren"],
    }
    shown = logic.display_look(state, logic.find_resident(state, "aoi"))
    assert (shown["owner"], shown["kind"]) == ("ren", "rule")
    assert look_tags(state, logic.find_resident(state, "aoi")) == "1boy, cat ears"


def test_combo_needs_a_custom_rule_and_two_components():
    state, first = _with_rule(_world())
    assert logic.active_combo(state) is None
    dress_only = logic.set_rule(_world(), "dress", True, random.Random(0))
    assert logic.active_combo(dress_only) is None

    state, second = _with_rule(state, "猫の日", "cat ears")
    combo = logic.active_combo(state)
    assert combo["rule_ids"] == [first, second]
    assert logic.combo_tags(state, combo["rule_ids"]) == "maid outfit, apron, cat ears"
    reordered = logic.combo_digest([second, first], False)
    assert reordered == combo["digest"]


def test_look_status_tracks_stale_images_and_rule_deletion():
    state, rule_id = _with_rule(_world(), tags="maid outfit")
    state = _look(state, "aoi", "rule", rule_id, source="maid outfit")
    state = _look(state, "ren", "rule", rule_id, source="old outfit")

    assert logic.rule_look_status(state, rule_id) == {
        "ready": 1,
        "stale": 1,
        "total": 2,
    }
    deleted = logic.delete_custom_rule(state, rule_id)
    assert all(not r["rule_images"] for r in deleted["residents"])


def test_prompt_links_rule_look_to_rule_text_and_feminine_form():
    state, _ = _with_rule(_world(), tags="maid outfit, frilled apron")
    ren = logic.find_resident(state, "ren")

    summary = current_appearance_summary(state, ren)
    assert summary.startswith("a look set by the rule 'メイドの日'")
    assert logic.is_male_in_feminine_form(state, ren)
    text = appearance_focus_text(state, (logic.find_resident(state, "aoi"), ren), "ja")
    assert "set by the world rules ('メイドの日': 全員がメイド服で過ごす)" in text


def test_normalize_keeps_looks_and_old_rules_get_empty_appearance():
    state, rule_id = _with_rule(_world())
    state = _look(state, "aoi", "rule", rule_id)
    legacy = {**state, "custom_rules": [{"id": rule_id, "name": "n", "text": "t"}]}

    normalized = logic.normalize_state(legacy)

    assert normalized["custom_rules"][0]["appearance_tags"] == ""
    assert logic.find_resident(normalized, "aoi")["rule_images"][rule_id]["image"]
