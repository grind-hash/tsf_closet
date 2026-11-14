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
        ("ニット帽と手編みのマフラーを装備して", "transform"),
        ("冬らしくマフラーを巻いて", "transform"),
        ("元に戻して", "clear"),
        ("Change back, please", "clear"),
        ("メイド服を着てるの？", "none"),
        ("ニット帽を被ってるんだね", "none"),
        ("その服にしてるんだね、似合ってる", "none"),
        ("You wear that well", "none"),
        ("おはよう、今日もいい天気だね", "none"),
    ],
)
def test_detect_chat_alteration(message, action):
    assert play.detect_chat_alteration(message)["action"] == action


def test_alteration_candidate_only_for_look_related_statements():
    assert play.alteration_candidate("その服、もっと派手なのがいいな")
    # 命令形でない書き方(〜を装備する)も分類に回す
    assert play.alteration_candidate(
        "冬にぴったりのニット帽と手編みのマフラーを装備する"
    )
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


# --- プレイヤーへの好感度 ---


def test_player_affinity_defaults_clamps_and_tiers():
    state = _world()
    assert all(resident["player_affinity"] == 0 for resident in state["residents"])

    raw = {**state, "residents": [dict(r) for r in state["residents"]]}
    raw["residents"][0]["player_affinity"] = 99
    raw["residents"][1]["player_affinity"] = "x"
    normalized = logic.normalize_state(raw)
    assert [r["player_affinity"] for r in normalized["residents"]] == [50, 0]
    old = {**state, "residents": [dict(r) for r in state["residents"]]}
    del old["residents"][0]["player_affinity"]
    assert logic.normalize_state(old)["residents"][0]["player_affinity"] == 0

    moved = play.adjust_player_affinity(state, "aoi", -80)
    assert logic.find_resident(moved, "aoi")["player_affinity"] == -50
    assert logic.find_resident(state, "aoi")["player_affinity"] == 0

    tiers = {
        -25: "hostile",
        -24: "wary",
        -6: "wary",
        -5: "neutral",
        10: "neutral",
        11: "friendly",
        29: "friendly",
        30: "close",
    }
    for value, tier in tiers.items():
        assert play.player_affinity_tier({"player_affinity": value}) == tier
    assert play.clamp_talk_affinity_delta(7) == 3
    assert play.clamp_talk_affinity_delta("-9") == -3
    assert play.clamp_talk_affinity_delta(None) == 0


def test_touch_follows_player_affinity():
    state = _world()
    aoi = {**logic.find_resident(state, "aoi"), "mood": 50}
    fond = {**aoi, "player_affinity": 30}
    averse = {**aoi, "player_affinity": -30}

    assert touch_tone(state, fond, "chest") == "fond"
    assert touch_tone(state, fond, "head") == "fond"
    assert touch_tone(state, averse, "lower") == "averse"
    assert touch_tone(state, averse, "head") == "averse"
    assert touch_tone(state, aoi, "chest") == "standard"
    # 好きな相手なら気分がふつうでも受け入れ側、嫌いなら頭でも上がらない
    assert play.touch_mood_delta(fond, "chest") == 1
    assert play.touch_mood_delta(fond, "lower") == 0
    assert play.touch_mood_delta(averse, "head") == 0
    assert play.touch_mood_delta(averse, "chest") == -2

    close_state = {
        **state,
        "residents": [fond if r["id"] == "aoi" else r for r in state["residents"]],
    }
    _, user = touch_prompts(close_state, fond, "chest", "ja", nsfw=False)
    assert "Do not show disgust" in user
    assert "Your feelings toward the player: you are very fond of them" in user
    _, user = touch_prompts(state, averse, "chest", "ja", nsfw=False)
    assert "open disgust" in user

    # 元男性の戸惑いは好感度より先(この姿で触られる戸惑いを残す)
    dressed = logic.set_rule(state, "dress", True, random.Random(0))
    ren = {**logic.find_resident(dressed, "ren"), "player_affinity": 40}
    assert touch_tone(dressed, ren, "chest") == "confused"


def test_chat_reply_is_longer_and_cut_at_a_sentence_end():
    from gateway.consts.hakoniwa_play import HAKONIWA_CHAT_REPLY_MAX
    from gateway.services.hakoniwa_generation import _clean_chat_reply

    state = _world()
    aoi = logic.find_resident(state, "aoi")
    system, _ = chat_reply_prompts(state, aoi, [], "やあ", "ja", nsfw=False)
    assert "usually three to six sentences" in system
    assert f"at most {HAKONIWA_CHAT_REPLY_MAX // 2} characters" in system

    sentence = "今日はいい天気だね。"
    long_reply = sentence * (HAKONIWA_CHAT_REPLY_MAX // len(sentence) + 5)
    cut = _clean_chat_reply(long_reply)
    assert cut is not None
    assert len(cut) <= HAKONIWA_CHAT_REPLY_MAX
    assert cut.endswith("。")
    assert _clean_chat_reply("「" + "あ" * 700 + "」") == "あ" * HAKONIWA_CHAT_REPLY_MAX
    assert _clean_chat_reply('{"reply": "x"}') is None


def test_player_impression_is_read_and_clamped():
    from gateway.services.hakoniwa_generation import _parse_impression
    from gateway.services.hakoniwa_prompts import player_impression_prompts

    assert _parse_impression('{"delta": 2}') == 2
    assert _parse_impression('考えた結果 {"delta": -8}') == -3
    assert _parse_impression("great") == 0
    assert _parse_impression('{"delta": "a lot"}') == 0

    state = _world()
    aoi = logic.find_resident(state, "aoi")
    history = [{"role": "resident", "text": "おはよう"}]
    system, user = player_impression_prompts(state, aoi, history, "かわいいね", "ja")
    assert '{"delta": an integer from -3 to 3}' in system
    assert "The player's latest message: かわいいね" in user
    assert "高瀬 葵: おはよう" in user


def test_chat_entries_keep_the_day_and_events_read_only_recent_talks():
    state = {**_world(), "day": 1}
    state = play.append_chat(state, "aoi", [{"role": "player", "text": "1日目"}])
    state = {**state, "day": 3}
    state = play.append_chat(
        state,
        "aoi",
        [
            {"role": "player", "text": "ニットに着替える"},
            {"role": "resident", "text": "すごく気に入ったよ"},
        ],
    )
    assert [entry["day"] for entry in play.chat_history(state, "aoi")] == [1, 3, 3]
    # 2日前の会話は渡さない。日の無い古い履歴は直近として扱う
    assert [e["text"] for e in play.recent_chat_for_events(state, "aoi")] == [
        "ニットに着替える",
        "すごく気に入ったよ",
    ]
    legacy = {
        **state,
        "chat_histories": {"aoi": [{"role": "player", "text": "昔の会話"}]},
    }
    assert play.recent_chat_for_events(legacy, "aoi") == [
        {"role": "player", "text": "昔の会話"}
    ]
    for index in range(10):
        state = play.append_chat(state, "aoi", [{"role": "player", "text": str(index)}])
    assert len(play.recent_chat_for_events(state, "aoi")) == 6


def test_event_prompt_keeps_feelings_from_talks_and_speech_style():
    state = {**_world(("aoi", "tamako")), "player_name": "はっしゅ"}
    group = tuple(state["residents"])
    plain = event_user_prompt(state, group, "ja", nsfw=False)
    assert "Recent talks with the player" not in plain
    # プリセットの一言を口調の手本として JSON の文字列で渡す
    assert (
        'Speech style sample (match this tone; do not reuse the line): "あらあら'
        in (plain)
    )

    state = play.append_chat(
        state,
        "tamako",
        [
            {"role": "player", "text": "ワンピースに着替える"},
            {"role": "resident", "text": "嫌じゃないわ。気に入ったの"},
        ],
    )
    text = event_user_prompt(state, group, "ja", nsfw=False)
    assert "大島 珠子 talking with the player:" in text
    assert '{"speaker": "はっしゅ", "text": "ワンピースに着替える"}' in text
    assert '{"speaker": "大島 珠子", "text": "嫌じゃないわ。気に入ったの"}' in text
    assert "do not make them complain about it or want to change back" in text


def test_chat_reply_does_not_pretend_and_classifier_reads_plain_forms():
    from gateway.services.hakoniwa_prompts import alteration_prompts

    state = _world()
    aoi = logic.find_resident(state, "aoi")
    system, _ = chat_reply_prompts(
        state, aoi, [], "マフラーを装備する", "ja", nsfw=False
    )
    assert "do not act as if you are already wearing or have become it" in system
    system, _ = alteration_prompts("マフラーを装備する", "高瀬 葵", "the usual look")
    assert "「〜を装備する」" in system
    assert "hats, scarves" in system
