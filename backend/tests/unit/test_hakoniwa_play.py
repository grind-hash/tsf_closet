"""AI箱庭の関わり方: 世界のメモ・掟の相性・介入・会話の変身指示の判定・タッチ。"""

from __future__ import annotations

import random

import pytest

from gateway.services import hakoniwa_logic as logic
from gateway.services import hakoniwa_play as play
from gateway.services import hakoniwa_story as story
from gateway.services.hakoniwa_errors import HakoniwaError
from gateway.services.hakoniwa_generation import touch_tone
from gateway.services.hakoniwa_prompts import active_rules_text, event_user_prompt


def _world(ids=("aoi", "ren")):
    return logic.new_world_state([logic.preset_resident(pid) for pid in ids])


def test_world_memo_is_added_only_when_written():
    state = _world()
    group = tuple(state["residents"])
    assert "Highest-priority" not in event_user_prompt(state, group, "ja", nsfw=False)

    state = {**state, "world_memo": play.validate_world_memo(" 全員が敬語で話す ")}
    text = event_user_prompt(state, group, "ja", nsfw=False)
    assert text.endswith("全員が敬語で話す")
    with pytest.raises(HakoniwaError):
        play.validate_world_memo("あ" * 1001)


def test_synergy_text_and_card_view():
    state = logic.set_rule(_world(), "dress", True, random.Random(0))
    assert "Rule combinations" not in active_rules_text(state, "ja")
    cards = play.card_synergies(state, "dress", "ja")
    assert {card["with_id"] for card in cards} == {"swap", "ojousama"}
    assert not any(card["active"] for card in cards)

    state = logic.set_rule(state, "ojousama", True, random.Random(0))
    assert "compete in graceful manners" in active_rules_text(state, "ja")
    active = [c for c in play.card_synergies(state, "dress", "ja") if c["active"]]
    assert active[0]["label"] == "お嬢様のドレスパーティ"


def test_intervention_choices_follow_the_world():
    state = _world()
    assert play.available_interventions(state) == ["watch", "nudge", "rewrite"]

    transformed = logic.set_transformation(
        state, "aoi", {"description": "d", "tags": "t", "image": "i.png", "day": 1}
    )
    assert play.available_interventions(transformed)[1] == "adaptation_care"
    stirring = {**transformed, "dissonance": 25}
    assert play.available_interventions(stirring)[2] == "dissonance_push"
    assert (
        play.available_interventions({**stirring, "dissonance_enabled": False})[2]
        == "rewrite"
    )

    with pytest.raises(HakoniwaError):
        play.set_intervention(state, "dissonance_push")
    chosen = play.set_intervention(transformed, "adaptation_care")
    assert play.pending_intervention(chosen) == "adaptation_care"
    # 状況が変わって選べなくなった介入は効かせない
    assert play.pending_intervention(logic.clear_transformation(chosen, "aoi")) is None
    assert play.pending_intervention(play.set_intervention(state, "watch")) is None


def test_arc_boost_raises_affinity_between_arc_members():
    state = _world(("aoi", "tamako", "ren"))
    for resident in state["residents"]:
        if resident["id"] in ("aoi", "tamako"):
            other = "tamako" if resident["id"] == "aoi" else "aoi"
            resident["affinities"][other] = 25
    state = story.refresh_story_arcs(state)
    assert play.available_interventions(state)[1] == "arc_boost"

    boosted = play.boost_arc_relationships(state)

    assert logic.find_resident(boosted, "aoi")["affinities"]["tamako"] == 28
    assert (
        logic.find_resident(boosted, "aoi")["affinities"]["ren"]
        == (logic.find_resident(state, "aoi")["affinities"]["ren"])
    )


@pytest.mark.parametrize(
    ("message", "action"),
    [
        ("メイド服に着替えて", "transform"),
        ("髪を銀色のロングにして", "transform"),
        ("Please put on a maid outfit", "transform"),
        ("Transform into a magical girl", "transform"),
        ("元に戻して", "clear"),
        ("Change back, please", "clear"),
        ("メイド服を着てるの？", "none"),
        ("その服にしてるんだね、似合ってる", "none"),
        ("You wear that well", "none"),
        ("おはよう、今日もいい天気だね", "none"),
    ],
)
def test_detect_chat_alteration(message, action):
    assert play.detect_chat_alteration(message)["action"] == action


def test_alteration_candidate_only_for_look_related_statements():
    assert play.alteration_candidate("その服、もっと派手なのがいいな")
    assert not play.alteration_candidate("その服、どこで買ったの？")
    assert not play.alteration_candidate("おはよう")


def test_touch_mood_and_tone():
    state = _world()
    aoi = logic.find_resident(state, "aoi")
    assert play.touch_mood_delta({**aoi, "mood": 50}, "head") == 2
    assert play.touch_mood_delta({**aoi, "mood": 50}, "lower") == -3
    assert play.touch_mood_delta({**aoi, "mood": 80}, "chest") == 1
    with pytest.raises(HakoniwaError):
        play.validate_touch_part("feet")

    dressed = logic.set_rule(state, "dress", True, random.Random(0))
    assert touch_tone(dressed, logic.find_resident(dressed, "ren"), "chest") == (
        "confused"
    )
    assert touch_tone(dressed, {**aoi, "mood": 80}, "chest") == "tolerant"


def test_chat_history_is_trimmed_and_forgotten_with_the_resident():
    state = _world(("aoi", "ren", "tamako"))
    for index in range(45):
        state = play.append_chat(state, "aoi", [{"role": "player", "text": str(index)}])

    history = play.chat_history(state, "aoi")
    assert len(history) == 40
    assert history[0]["text"] == "5"
    assert "aoi" not in logic.remove_resident(state, "aoi")["chat_histories"]
    assert logic.normalize_state(state)["chat_histories"]["aoi"] == history


def test_japanese_output_drops_simplified_characters_only():
    from gateway.services.hakoniwa_text import normalize_output

    text = "违和感があって、全然违う。镜に映る颜を见た。机の上の叶わない夢"
    assert normalize_output(text, "ja") == (
        "違和感があって、全然違う。鏡に映る顔を見た。机の上の叶わない夢"
    )
    assert normalize_output("违", "en") == "违"


def test_swap_note_names_the_pronoun_to_keep():
    from gateway.services.hakoniwa_prompts import residents_text

    state = logic.set_rule(_world(), "swap", True, random.Random(0))
    text = residents_text(state, "ja")
    assert "Still says their own first person '私', never 苑田 蓮's '俺'." in text
