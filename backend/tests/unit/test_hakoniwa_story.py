"""AI箱庭の物語の厚み: 違和感と対面・適応と名残・記憶・物語の弧・まとめ・プロンプト。"""

from __future__ import annotations

import random

from gateway.services import hakoniwa_logic as logic
from gateway.services import hakoniwa_story as story
from gateway.services import hakoniwa_story_text as story_text
from gateway.services.hakoniwa_digest import build_day_digest
from gateway.services.hakoniwa_prompts import event_user_prompt


def _world(preset_ids=("aoi", "shiori", "tamako", "ren", "ritsu"), **kwargs):
    return logic.new_world_state(
        [logic.preset_resident(pid) for pid in preset_ids], **kwargs
    )


def _resident(state, resident_id):
    return logic.find_resident(state, resident_id)


def _transform(state, resident_id, description="メイド服", image="tf.png"):
    return logic.set_transformation(
        state,
        resident_id,
        {
            "description": description,
            "tags": "1girl, maid",
            "image": image,
            "day": state["day"],
        },
    )


def _swap(state, pair=("aoi", "ren")):
    """入れ替わりの朝を、決まった二人で始めた状態(set_rule の乱数を避ける)。"""
    residents = []
    for resident in state["residents"]:
        entry = dict(resident)
        if entry["id"] in pair:
            story.start_adaptation(entry, "swap", state["day"])
        residents.append(entry)
    return {
        **state,
        "active_rules": [*state["active_rules"], "swap"],
        "swap_pair": list(pair),
        "residents": residents,
    }


# --- 世界の違和感と対面 ---


def test_dissonance_gain_decay_and_confrontation():
    state = _world()
    assert state["dissonance_enabled"] is True

    state = story.add_dissonance(state, 8)
    assert story.dissonance_value(state) == 8
    # 書き換えのあった日は静まらず、無い日は3下がる
    assert story.decay_dissonance(state) == state
    assert story.dissonance_value(story.decay_dissonance({**state, "day": 2})) == 5

    state = story.add_dissonance({**state, "dissonance": 75}, 8)
    assert story.confrontation_pending(state)
    resolved = story.resolve_confrontation(state)
    assert story.dissonance_value(resolved) == 40
    assert resolved["dissonance_acknowledged"] is True
    assert not story.confrontation_pending(story.add_dissonance(resolved, 100))


def test_disabled_dissonance_is_frozen():
    state = _world(dissonance_enabled=False)

    assert story.add_dissonance(state, 50) == state
    assert not story.confrontation_pending({**state, "dissonance": 90})
    assert not story.investigation_active({**state, "dissonance": 60})


def test_world_adaptation_softens_dissonance_gain():
    state = _transform(_world(), "aoi")
    key = story.form_key(state, _resident(state, "aoi"))
    state["world_adaptation"] = {key: {"kind": "transform", "stage": 2}}

    assert story.dissonance_value(story.add_dissonance(state, 10)) == 5
    state["world_adaptation"][key]["stage"] = 3
    assert story.dissonance_value(story.add_dissonance(state, 3)) == 1


def test_investigator_preference_and_group_replacement():
    assert story.investigator(_world())["id"] == "ritsu"
    assert story.investigator(_world(("aoi", "shiori", "ren")))["id"] == "shiori"
    assert story.investigator(_world(("aoi", "ren")))["id"] == "aoi"

    state = {**_world(), "dissonance": 55}
    by_id = {r["id"]: r for r in state["residents"]}
    groups = [(by_id["aoi"], by_id["ren"]), (by_id["shiori"], by_id["tamako"])]
    replaced = story.ensure_investigator(state, groups)
    assert {r["id"] for r in replaced[-1]} >= {"ritsu"}
    assert story.ensure_investigator({**state, "dissonance": 30}, groups) == groups


# --- 適応と名残 ---


def test_swap_rule_starts_adaptation_and_leaves_remnant():
    state = logic.set_rule(_world(), "swap", True, random.Random(1))
    pair = state["swap_pair"]
    assert all(_resident(state, rid)["adaptation"]["kind"] == "swap" for rid in pair)

    for _ in range(3):
        state, _progress = story.advance_adaptations(state)
    ended = logic.set_rule(state, "swap", False, random.Random(1))

    for rid in pair:
        resident = _resident(ended, rid)
        assert resident["adaptation"] is None
        assert resident["remnant"]["kind"] == "swap"
        assert resident["remnant"]["days_left"] >= 2


def test_adaptation_speed_follows_personality():
    state = _swap(_transform(_world(), "ritsu"), ("aoi", "shiori"))

    state, progressions = story.advance_adaptations(state)

    stages = {
        r["id"]: r["adaptation"]["stage"] for r in state["residents"] if r["adaptation"]
    }
    # 薫(好奇心)は1日で1段、葵(明るく)は 0.75、栞(内気)は 0.4
    assert stages == {"ritsu": 1, "aoi": 0, "shiori": 0}
    assert progressions == [{"id": "ritsu", "kind": "transform", "stage": 1}]


def test_clearing_transform_leaves_fading_remnant():
    state = _transform(_world(), "aoi")
    for _ in range(4):
        state, _ = story.advance_adaptations(state)
    assert _resident(state, "aoi")["adaptation"]["stage"] == 3

    cleared = logic.clear_transformation(state, "aoi")
    remnant = _resident(cleared, "aoi")["remnant"]
    assert remnant["variant"] in ("gesture", "posture", "speech", "nostalgia")
    assert remnant["days_left"] == 5
    text = story_text.remnant_view(cleared, _resident(cleared, "aoi"), "ja")["text"]
    assert text

    for _ in range(5):
        cleared = story.decay_remnants(cleared)
    assert _resident(cleared, "aoi")["remnant"] is None


def test_world_adaptation_advances_and_forgets_gone_looks():
    state = _transform(_world(), "aoi")

    state, first = story.advance_world_adaptations(state)
    state, second = story.advance_world_adaptations(state)

    assert first == []
    assert second == [{"ids": ["aoi"], "kind": "transform", "stage": 1}]
    cleared = logic.clear_transformation(state, "aoi")
    cleared, _ = story.advance_world_adaptations(cleared)
    assert cleared["world_adaptation"] == {}


# --- 記憶 ---


def test_transform_event_is_remembered_by_target_and_witnesses():
    state = _world()
    event = {
        "title": "葵の変身",
        "narration": "n",
        "lines": [],
        "participants": ["aoi", "tamako"],
        "kind": "transform",
        "change_text": "メイド服",
    }

    state = logic.apply_event(state, event, random.Random(0))

    assert story.resident_memories(state, "aoi")[0]["kind"] == "transform_self"
    witness = story.resident_memories(state, "tamako")[0]
    assert witness["kind"] == "transform_witness"
    assert witness["partner_id"] == "aoi"
    assert story_text.memory_text(state, witness, "ja") == (
        "高瀬 葵の姿が変わる場面に居合わせた: 「メイド服」"
    )
    assert "Aoi Takase" in story_text.memory_text(state, witness, "en")


def test_big_affinity_moves_become_bonds_and_small_ones_do_not():
    state = _world()
    base = {"title": "t", "narration": "n", "lines": [], "participants": ["aoi", "ren"]}

    small = logic.apply_event(state, {**base, "affinity_delta": 5}, random.Random(0))
    big = logic.apply_event(state, {**base, "affinity_delta": -9}, random.Random(0))

    assert story.resident_memories(small, "aoi") == []
    memory = story.resident_memories(big, "ren")[0]
    assert (memory["kind"], memory["partner_id"], memory["delta"]) == (
        "bond",
        "aoi",
        -9,
    )


def test_memories_keep_heavy_and_recent_entries():
    state = _world()
    for day in range(1, 10):
        state = story.add_memory(
            state,
            "aoi",
            {"day": day, "kind": "rule_start", "weight": 1, "rule_id": "dress"},
        )
    state = story.add_memory(
        state, "aoi", {"day": 2, "kind": "confrontation", "weight": 3}
    )

    memories = story.resident_memories(state, "aoi")
    assert len(memories) == 8
    assert any(item["kind"] == "confrontation" for item in memories)
    assert [item["day"] for item in memories if item["kind"] == "rule_start"][0] == 3


def test_rule_toggle_memories_and_forgetting():
    state = logic.set_rule(_world(), "swap", True, random.Random(2))
    pair = state["swap_pair"]

    state = story.record_rule_toggle_memories(state, "swap", True, None)

    kinds = {item["kind"] for item in story.resident_memories(state, pair[0])}
    assert kinds == {"rule_start", "swap_start"}
    other = next(r["id"] for r in state["residents"] if r["id"] not in pair)
    assert story_text.memories_view(state, other, "ja")[0]["text"] == (
        "掟『入れ替わりの朝』が始まった"
    )
    removed = logic.remove_resident(state, pair[0])
    assert pair[0] not in removed["memories"]


# --- 物語の弧 ---


def test_arcs_start_from_existing_situations():
    state = {**_world(), "dissonance": 55, "day": 3}
    state = _transform(state, "aoi")
    state["residents"][0]["transformation"]["day"] = 1

    state = story.refresh_story_arcs(state)

    kinds = [arc["kind"] for arc in story.active_arcs(state)]
    assert kinds == ["investigation", "transform"]
    assert story.active_arcs(state)[0]["resident_ids"][0] == "ritsu"


def test_bond_arc_and_climax_flow():
    state = _world(("aoi", "tamako", "ren"))
    for resident in state["residents"]:
        if resident["id"] in ("aoi", "tamako"):
            other = "tamako" if resident["id"] == "aoi" else "aoi"
            resident["affinities"][other] = 25
    state = story.refresh_story_arcs(state)
    arc = story.active_arcs(state)[0]
    assert (arc["kind"], set(arc["resident_ids"])) == ("bond", {"aoi", "tamako"})

    by_id = {r["id"]: r for r in state["residents"]}
    groups = [(by_id["ren"],), (by_id["tamako"], by_id["aoi"])]
    for expected_climax in (False, False, True):
        assignment = story.arc_focus_assignments(state, groups)
        assert assignment == {1: {"arc_id": arc["id"], "climax": expected_climax}}
        state = story.record_arc_event(
            state, arc["id"], {"id": "e", "day": 1, "title": "t"}, expected_climax
        )
    closed = story.arc_by_id(state, arc["id"])
    assert (closed["status"], closed["close_reason"], closed["progress"]) == (
        "closed",
        "climax",
        3,
    )
    # 閉じた直後は同じ弧を立て直さない
    assert story.active_arcs(story.refresh_story_arcs(state)) == []


def test_arc_closes_when_its_premise_is_gone():
    state = {**_world(), "day": 3}
    state = _transform(state, "aoi")
    state["residents"][0]["transformation"]["day"] = 1
    state = story.refresh_story_arcs(state)
    assert story.active_arcs(state)[0]["kind"] == "transform"

    cleared = logic.clear_transformation(state, "aoi")
    refreshed = story.refresh_story_arcs(cleared)

    arc = refreshed["story_arcs"][0]
    assert (arc["status"], arc["close_reason"]) == ("closed", "resolved")


# --- 1日のまとめ ---


def test_digest_prefers_confrontation_and_reports_story():
    before = _world()
    after = {**before, "dissonance": 12}
    after = story.refresh_story_arcs(after)
    events = [
        {"id": "a", "title": "a", "participants": ["aoi", "ren"], "affinity_delta": 9},
        {"id": "b", "title": "b", "participants": ["aoi", "ren"], "arc_climax": True},
        {
            "id": "c",
            "title": "c",
            "participants": ["ritsu", "aoi"],
            "kind": "confrontation",
        },
    ]

    digest = build_day_digest(
        before,
        after,
        events,
        adaptations=[{"id": "aoi", "kind": "swap", "stage": 1}],
    )

    assert digest["highlight"]["reason"] == "confrontation"
    assert digest["hint"] == {"type": "acknowledged"}
    assert digest["adaptations"] == [{"id": "aoi", "kind": "swap", "stage": 1}]
    assert digest["dissonance"]["to_stage"] == "stillness"
    assert digest["dissonance"]["remaining"] == 8
    no_confrontation = build_day_digest(before, after, events[:2])
    assert no_confrontation["highlight"]["reason"] == "arc_climax"
    assert no_confrontation["hint"] == {
        "type": "dissonance_near",
        "stage": "stirring",
        "remaining": 8,
    }
    disabled = {**after, "dissonance_enabled": False}
    assert build_day_digest(before, disabled, [])["dissonance"] is None


# --- プロンプト ---


def test_event_prompt_includes_story_blocks_only_when_present():
    plain = _world()
    by_id = {r["id"]: r for r in plain["residents"]}
    group = (by_id["aoi"], by_id["ren"])

    text = event_user_prompt(plain, group, "ja", nsfw=False)
    assert "remembers" not in text
    assert "Ongoing stories" not in text
    assert "Premise" not in text

    state = {**_swap(plain), "dissonance": 55, "day": 3}
    state = story.record_rule_toggle_memories(state, "swap", True, None)
    state = story.refresh_story_arcs(state)
    by_id = {r["id"]: r for r in state["residents"]}
    group = (by_id["aoi"], by_id["ritsu"])
    arc = story.active_arcs(state)[0]

    text = event_user_prompt(
        state, group, "ja", nsfw=False, arc_focus_id=arc["id"], arc_climax=True
    )
    assert "高瀬 葵 remembers" in text
    assert "Swapped bodies with 苑田 蓮" in text
    assert "adaptation stage 'bewildered'" in text
    assert "investigating the world's changes" in text
    assert "Today is the climax of this story" in text
    assert "seriously discuss whether someone is rewriting" in text
    # 調査は好奇心で進め、怖がらせない
    assert "they are not frightened" in text
    assert "like amateur detectives, not fearful" in text


def test_adaptation_guidance_separates_outfit_from_body():
    state = _transform(_world(), "aoi", description="ニットに着替える")
    by_id = {r["id"]: r for r in state["residents"]}
    text = event_user_prompt(state, (by_id["aoi"], by_id["ren"]), "ja", nsfw=False)
    assert "adaptation stage 'bewildered'" in text
    assert "If only their clothes, accessories or hairstyle changed" in text
    assert "do not make them complain about it or want to change back" in text


def test_male_guidance_softens_after_adaptation():
    from gateway.services.hakoniwa_prompts import male_confusion_guidance

    state = _swap(_world(), ("aoi", "ren"))
    ren = _resident(state, "ren")
    assert "strongly bewildered" in male_confusion_guidance(state, ren, "蓮")

    for _ in range(4):
        state, _ = story.advance_adaptations(state)
    ren = _resident(state, "ren")
    assert ren["adaptation"]["stage"] >= 2
    assert "bewilderment is easing" in male_confusion_guidance(state, ren, "蓮")


def test_normalize_keeps_story_state():
    state = _transform({**_world(), "dissonance": 33}, "aoi")
    state = story.add_memory(state, "aoi", {"kind": "confrontation", "weight": 3})
    state = story.refresh_story_arcs({**state, "day": 4})

    normalized = logic.normalize_state(state)

    assert normalized["dissonance"] == 33
    assert normalized["memories"] == state["memories"]
    assert normalized["story_arcs"] == state["story_arcs"]
    assert _resident(normalized, "aoi")["adaptation"]["kind"] == "transform"
    legacy = logic.normalize_state({"residents": state["residents"], "day": 2})
    assert legacy["dissonance_enabled"] is True
    assert legacy["memories"] == {}
