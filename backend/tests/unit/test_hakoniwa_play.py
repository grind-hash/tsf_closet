"""AI箱庭の関わり方: 世界のメモ・掟の相性・介入・会話の変身指示の判定・タッチ。"""

from __future__ import annotations

import random

import pytest

from gateway.services import hakoniwa_logic as logic
from gateway.services import hakoniwa_play as play
from gateway.services import hakoniwa_story as story
from gateway.services.hakoniwa_errors import HakoniwaError
from gateway.services.hakoniwa_generation import touch_tone
from gateway.services.hakoniwa_prompts import (
    active_rules_text,
    chat_reply_prompts,
    confrontation_prompts,
    event_user_prompt,
    greeting_prompts,
    touch_prompts,
)


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


def test_player_name_is_one_line_and_limited():
    assert play.validate_player_name("  ユウ \n 太郎 ") == "ユウ 太郎"
    assert play.validate_player_name("") == ""
    with pytest.raises(HakoniwaError) as caught:
        play.validate_player_name("あ" * 21)
    assert caught.value.code == "invalid_player_name"

    state = logic.normalize_state({**_world(), "player_name": " ユウ\n" + "あ" * 40})
    assert len(state["player_name"]) == 20
    assert state["player_name"].startswith("ユウ あ")
    assert play.player_name(logic.normalize_state(_world())) == ""


def _direct_prompts(state):
    resident = state["residents"][0]
    return [
        greeting_prompts(state, resident, "ja", nsfw=False)[0],
        touch_prompts(state, resident, "head", "ja", nsfw=False)[0],
        chat_reply_prompts(state, resident, [], "こんにちは", "ja", nsfw=False)[0],
    ]


def test_direct_talk_addresses_the_player_not_a_housemate():
    # 一言・タッチ・会話: 相手はプレイヤーで、同居人へ挨拶しない。名前が無ければ「あなた」
    for prompt in _direct_prompts(_world()):
        assert "is the player, not a housemate" in prompt
        assert "do not greet or call out to a housemate" in prompt
        assert "the player has no name in this world" in prompt
        assert "「あなた」" in prompt
        assert "「書き手」 or 「書き手さん」" in prompt

    named = {**_world(), "player_name": "ユウ"}
    for prompt in _direct_prompts(named):
        assert 'the residents know the player as "ユウ"' in prompt
        assert "「ユウさん」" in prompt
        assert "has no name in this world" not in prompt


def test_player_address_in_events_only_after_acknowledgement():
    # 出来事: 住民がプレイヤーの存在を知ったあと(公認)だけ、呼び方を添える
    state = {**_world(), "player_name": "ユウ"}
    group = tuple(state["residents"])
    assert "How to call the player" not in event_user_prompt(
        state, group, "ja", nsfw=False
    )

    acknowledged = {**state, "dissonance_acknowledged": True}
    text = event_user_prompt(acknowledged, group, "ja", nsfw=False)
    assert 'the residents know the player as "ユウ"' in text
    assert "is the player, not a housemate" not in text

    off = {**acknowledged, "dissonance_enabled": False}
    assert "How to call the player" not in event_user_prompt(
        off, group, "ja", nsfw=False
    )

    # 対面の出来事は、公認の前でもプレイヤーへ呼びかけるので必ず添える
    system, _ = confrontation_prompts(state, (group[0], group[1]), "ja", nsfw=False)
    assert 'the residents know the player as "ユウ"' in system
    assert "the writer" not in system


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
