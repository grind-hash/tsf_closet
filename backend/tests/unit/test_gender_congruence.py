"""gender_congruence モジュールのユニットテスト。"""

from __future__ import annotations

from gateway.services.gender_congruence import (
    evaluate_gender_congruence_rule,
    is_gender_aware_feeling_mode,
    normalize_feeling_mode,
    parse_congruence_llm_response,
    should_use_congruence_llm,
)


def test_man_suit_is_congruent() -> None:
    result = evaluate_gender_congruence_rule("メンズスーツに着替えさせる", "man")
    assert result.fit == "congruent"
    assert result.should_feel_gender_discomfort is False


def test_man_plain_suit_is_congruent() -> None:
    result = evaluate_gender_congruence_rule("スーツを着せる", "man")
    assert result.fit == "congruent"
    assert result.should_feel_gender_discomfort is False


def test_man_ladies_suit_is_incongruent() -> None:
    """レディーススーツはスーツ部分一致でも女装扱い。"""
    result = evaluate_gender_congruence_rule("レディーススーツを着せる", "man")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True
    assert "女性向け" in result.reason or "レディース" in result.reason


def test_man_ladies_pajamas_is_incongruent() -> None:
    result = evaluate_gender_congruence_rule("レディースパジャマ", "man")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True


def test_man_pajamas_is_congruent() -> None:
    result = evaluate_gender_congruence_rule("パジャマを着せる", "man")
    assert result.fit == "congruent"
    assert result.should_feel_gender_discomfort is False


def test_man_skirt_is_incongruent() -> None:
    result = evaluate_gender_congruence_rule("スカートを履かせる", "man")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True


def test_man_maid_is_incongruent() -> None:
    result = evaluate_gender_congruence_rule("メイド服に変身", "man")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True


def test_woman_mens_suit_is_incongruent() -> None:
    result = evaluate_gender_congruence_rule("メンズスーツを着せる", "woman")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True


def test_woman_ladies_suit_is_congruent() -> None:
    result = evaluate_gender_congruence_rule("レディーススーツ", "woman")
    assert result.fit == "congruent"
    assert result.should_feel_gender_discomfort is False


def test_woman_dress_is_congruent() -> None:
    result = evaluate_gender_congruence_rule("ドレスに着替える", "woman")
    assert result.fit == "congruent"
    assert result.should_feel_gender_discomfort is False


def test_ambiguous_defaults_to_discomfort() -> None:
    result = evaluate_gender_congruence_rule("不思議な光に包まれる", "man")
    assert result.fit == "ambiguous"
    assert result.should_feel_gender_discomfort is True


def test_normalize_feeling_mode() -> None:
    assert normalize_feeling_mode("legacy") == "legacy"
    assert normalize_feeling_mode("gender_aware") == "gender_aware"
    # 誤保存互換
    assert normalize_feeling_mode("new") == "gender_aware"
    assert normalize_feeling_mode("experimental") == "gender_aware"
    assert normalize_feeling_mode(None) == "legacy"
    assert normalize_feeling_mode("unknown") == "legacy"


def test_is_gender_aware_feeling_mode() -> None:
    assert is_gender_aware_feeling_mode("legacy") is False
    assert is_gender_aware_feeling_mode("gender_aware") is True
    assert is_gender_aware_feeling_mode("new") is True
    assert is_gender_aware_feeling_mode("experimental") is True


def test_should_use_congruence_llm() -> None:
    assert should_use_congruence_llm("legacy", True) is False
    assert should_use_congruence_llm("gender_aware", False) is False
    assert should_use_congruence_llm("gender_aware", True) is True
    assert should_use_congruence_llm("new", True) is True


def test_parse_llm_json() -> None:
    raw = (
        '{"fit":"congruent","discomfort":false,'
        '"body":"original","social":"original","reason":"スーツで自然"}'
    )
    parsed = parse_congruence_llm_response(raw)
    assert parsed is not None
    assert parsed.fit == "congruent"
    assert parsed.should_feel_gender_discomfort is False
    assert parsed.source == "llm"


def test_parse_llm_json_in_code_fence() -> None:
    raw = """```json
{"fit":"incongruent","discomfort":true,"body":"altered","social":"opposite","reason":"女体化残存"}
```"""
    parsed = parse_congruence_llm_response(raw)
    assert parsed is not None
    assert parsed.fit == "incongruent"
    assert parsed.body_state == "altered"
    assert parsed.should_feel_gender_discomfort is True
