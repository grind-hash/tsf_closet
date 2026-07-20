"""gender_congruence モジュールのユニットテスト。"""

from __future__ import annotations

from gateway.services.gender_congruence import (
    evaluate_gender_congruence_rule,
    parse_congruence_llm_response,
)


def test_man_suit_is_congruent() -> None:
    result = evaluate_gender_congruence_rule("メンズスーツに着替えさせる", "man")
    assert result.fit == "congruent"
    assert result.should_feel_gender_discomfort is False


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


def test_woman_suit_is_incongruent() -> None:
    result = evaluate_gender_congruence_rule("メンズスーツを着せる", "woman")
    assert result.fit == "incongruent"
    assert result.should_feel_gender_discomfort is True


def test_woman_dress_is_congruent() -> None:
    result = evaluate_gender_congruence_rule("ドレスに着替える", "woman")
    assert result.fit == "congruent"
    assert result.should_feel_gender_discomfort is False


def test_ambiguous_defaults_to_discomfort() -> None:
    result = evaluate_gender_congruence_rule("不思議な光に包まれる", "man")
    assert result.fit == "ambiguous"
    assert result.should_feel_gender_discomfort is True


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
