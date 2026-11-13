"""AI箱庭: 掟を切り替えた直後の住民の反応(定型文)。"""

from __future__ import annotations

import random

from gateway.services import hakoniwa_logic as logic
from gateway.services.hakoniwa_reactions import rule_reactions


def _world(ids=("aoi", "ren")):
    return logic.new_world_state([logic.preset_resident(pid) for pid in ids])


def _toggle(state, card_id, active, language="ja", area_id=None, seed=0):
    after = logic.set_rule(state, card_id, active, random.Random(seed))
    return after, rule_reactions(
        state, after, card_id, active, language, area_id, random.Random(seed)
    )


def test_swap_start_lets_the_man_in_a_womans_body_speak_first():
    after, reaction = _toggle(_world(), "swap", True)
    assert reaction is not None
    speakers = [line["resident_id"] for line in reaction["lines"]]
    assert speakers == ["ren", "aoi"]
    ren_line, aoi_line = (line["text"] for line in reaction["lines"])
    # 台詞ではフルネームでなく、ふだんの呼び方(蓮は苗字を呼び捨て、葵は下の名前＋くん)
    assert "高瀬" in ren_line and "高瀬 葵" not in ren_line and "俺" in ren_line
    assert "蓮くん" in aoi_line and "苑田 蓮" not in aoi_line and "私" in aoi_line


def test_swap_end_returns_both_to_their_bodies():
    swapped, _ = _toggle(_world(), "swap", True)
    _after, reaction = _toggle(swapped, "swap", False)
    texts = {line["resident_id"]: line["text"] for line in reaction["lines"]}
    assert texts["ren"].startswith("やっと")
    assert texts["aoi"].startswith("戻った")


def test_dress_start_has_a_male_and_a_female_reaction():
    _after, reaction = _toggle(_world(), "dress", True)
    texts = {line["resident_id"]: line["text"] for line in reaction["lines"]}
    assert "ドレスなのか" in texts["ren"]
    assert "華やか" in texts["aoi"]


def test_speaker_is_picked_from_the_area_being_viewed():
    state = _world(("aoi", "shiori", "ren"))
    garden = logic.find_resident(state, "ren")["current_area"]
    _after, reaction = _toggle(state, "ojousama", True, area_id=garden)
    assert [line["resident_id"] for line in reaction["lines"]] == ["ren"]
    assert reaction["area"] == garden
    assert "お嬢様言葉" in reaction["lines"][0]["text"]


def test_custom_rule_reaction_mentions_the_rule_and_its_look():
    state = logic.add_custom_rule(
        _world(), "猫の日", "全員が猫耳を付けて過ごす", appearance_tags="cat ears"
    )
    rule_id = state["custom_rules"][0]["id"]
    _after, reaction = _toggle(state, rule_id, True)
    assert "『猫の日』" in reaction["lines"][0]["text"]
    # 掟は世界の常識の書き換えなので、照れではなく当たり前として受け止め、かすかな違和感だけ出す
    assert "当たり前" in reaction["lines"][0]["text"]
    assert "恥ずかしい" not in reaction["lines"][0]["text"]


def test_turning_a_rule_off_and_english_text():
    on, _ = _toggle(_world(), "confession", True)
    _after, reaction = _toggle(on, "confession", False, language="en")
    text = reaction["lines"][0]["text"]
    assert text == "Phew, it feels like everyday life is back."
    _after, swap = _toggle(_world(), "swap", True, language="en")
    assert all("{" not in line["text"] for line in swap["lines"])
    assert "Takase" in swap["lines"][0]["text"]
    assert "Aoi Takase" not in swap["lines"][0]["text"]


def test_no_reaction_when_nothing_changed():
    on, _ = _toggle(_world(), "dress", True)
    _after, reaction = _toggle(on, "dress", True)
    assert reaction is None
