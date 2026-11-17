"""AI箱庭: 住民どうしの呼び方(話す側のくせから作る)。"""

from __future__ import annotations

import random

from gateway.consts.hakoniwa import (
    HAKONIWA_ADDRESS_STYLE_DEFAULT,
    HAKONIWA_ADDRESS_STYLES,
)
from gateway.services import hakoniwa_logic as logic
from gateway.services.hakoniwa_generation import clean_profile
from gateway.services.hakoniwa_prompts import (
    gender_address_rules,
    resident_profile_text,
    residents_text,
)
from gateway.services.hakoniwa_random import template_residents
from gateway.services.hakoniwa_service import _resident_view


def _world(ids=("aoi", "shiori", "tamako", "ren", "ritsu")):
    return logic.new_world_state([logic.preset_resident(pid) for pid in ids])


def _by_id(state):
    return {resident["id"]: resident for resident in state["residents"]}


def test_presets_call_housemates_by_their_usual_names():
    residents = _by_id(_world())

    def call(speaker, listener, language="ja"):
        return logic.address_name(residents[speaker], residents[listener], language)

    assert call("tamako", "aoi") == "葵ちゃん"
    assert call("tamako", "ren") == "蓮くん"
    assert call("shiori", "aoi") == "葵さん"
    assert call("ren", "aoi") == "高瀬"
    # 新入りの薫は苗字＋さん
    assert call("ritsu", "aoi") == "高瀬さん"
    assert call("ritsu", "ren", "en") == "Mr. Sonoda"
    assert call("tamako", "aoi", "en") == "Aoi"


def test_much_older_housemates_get_an_honorific():
    residents = _by_id(_world())
    # 葵(20代後半)は ちゃん付けのくせでも、50代の珠子には さん を付ける
    assert logic.address_name(residents["aoi"], residents["tamako"], "ja") == "珠子さん"
    assert logic.address_name(residents["ren"], residents["tamako"], "ja") == "大島さん"
    assert logic.address_name(residents["aoi"], residents["ren"], "ja") == "蓮くん"


def test_reads_rough_ages():
    assert logic.age_years("20代後半") == 28
    assert logic.age_years("30代前半") == 32
    assert logic.age_years("27歳") == 27
    assert logic.age_years("late 20s") == 28
    assert logic.age_years("年齢不詳") is None


def test_own_style_overrides_the_preset_and_bad_values_fall_back():
    state = _world(("aoi", "ren"))
    state = logic.update_resident(state, "ren", {"address_style": "given_chan"})
    residents = _by_id(state)
    assert logic.address_name(residents["ren"], residents["aoi"], "ja") == "葵ちゃん"
    residents["ren"]["address_style"] = "nickname"
    assert logic.resident_address_style(residents["ren"]) == "family"
    custom = logic.custom_resident(
        name="サクラ",
        personality="穏やか",
        gender="female",
        appearance_text="",
        base_tags="1girl",
    )
    assert logic.resident_address_style(custom) == HAKONIWA_ADDRESS_STYLE_DEFAULT
    # 区切りの無い名前は、名前全体に敬称を付ける
    assert logic.address_name(residents["aoi"], custom, "ja") == "サクラちゃん"


def test_validated_fields_drop_unknown_styles():
    fields = logic.validate_resident_fields(
        name="サクラ",
        personality="穏やか",
        gender="female",
        appearance_text="",
        dress_text="",
        address_style="nickname",
    )
    assert fields["address_style"] == ""


def test_prompts_list_how_each_resident_calls_the_others():
    state = _world(("aoi", "tamako", "ren"))
    text = residents_text(state, "ja")
    assert "Calls housemates" in text
    assert "大島 珠子 -> 「珠子さん」" in text
    assert "高瀬 葵 -> 「葵ちゃん」" in text
    profile = resident_profile_text(state, _by_id(state)["ren"], "ja")
    assert "高瀬 葵 -> 「高瀬」" in profile
    assert "never call a housemate by their full name" in gender_address_rules("ja")


def test_resident_view_shows_the_style_and_each_address():
    state = _world(("aoi", "tamako"))
    view = _resident_view("w1", state, _by_id(state)["tamako"], "ja")
    assert view["address_style"] == "given_chan"
    assert view["addresses"] == {"aoi": "葵ちゃん"}


def test_random_residents_always_have_a_known_style():
    for resident in template_residents(4, "ja", random.Random(3)):
        assert resident["address_style"] in HAKONIWA_ADDRESS_STYLES
    raw = {"name": "佐倉 美咲", "gender": "female", "personality": "明るい"}
    picked = clean_profile({**raw, "address_style": "given"}, "ja")
    assert picked["address_style"] == "given"
    assert (
        clean_profile({**raw, "address_style": "nickname"}, "ja")["address_style"]
        == HAKONIWA_ADDRESS_STYLE_DEFAULT
    )
