"""Unit tests for prompt utilities (US1-US3).

Covers pronoun substitution, personality classification, opening selection,
and opening deduplication logic.
"""

import pytest

from gateway.services.prompts import (
    build_feeling_prompt,
    classify_personality_type,
    select_opening,
    build_enhanced_feeling_prompt,
)


# ── classify_personality_type ──


@pytest.mark.parametrize(
    ("personality", "description", "expected"),
    [
        ("気が強い", "", "bold"),
        ("穏やかで優しい性格", "", "gentle"),
        ("明るい元気な女の子", "", "cheerful"),
        ("恥ずかしがりで内気な子", "", "shy"),
        ("冷静でクールな性格", "", "calm"),
        ("情熱的で熱い心の持ち主", "", "passionate"),
        ("普通の性格", "", "default"),
        ("", "", "default"),
        ("", "おっとりした少女", "gentle"),
        ("元気で活発", "陽気な性格", "cheerful"),
    ],
)
def test_classify_personality_type(
    personality: str, description: str, expected: str
) -> None:
    result = classify_personality_type(personality, description)
    assert result == expected


def test_classify_personality_type_empty_returns_default() -> None:
    assert classify_personality_type("", "") == "default"


# ── select_opening ──


def test_select_opening_flat_list_returns_element() -> None:
    openings = ["えっ…{pronoun}の姿が…", "これは…{pronoun}が…"]
    result = select_opening(openings, pronoun="俺")
    assert "俺" in result
    assert "{pronoun}" not in result


def test_select_opening_dict_returns_formatted() -> None:
    openings = {
        "default": ["えっ…{pronoun}が…"],
        "bold": ["ふん、見せてやる！{pronoun}の姿を！"],
    }
    result = select_opening(openings, personality_type="bold", pronoun="私")
    assert "私" in result
    assert "{pronoun}" not in result


def test_select_opening_dedup_avoids_used() -> None:
    openings = {
        "default": ["A{pronoun}", "B{pronoun}", "C{pronoun}"],
    }
    used = ["A僕", "B僕"]
    results = set()
    for _ in range(50):
        r = select_opening(openings, pronoun="僕", used_openings=used)
        results.add(r)
    # Should almost always choose "C僕" since A and B are used
    assert "C僕" in results


def test_select_opening_dedup_all_used_still_returns() -> None:
    openings = ["A{pronoun}"]
    used = ["A僕"]
    result = select_opening(openings, pronoun="僕", used_openings=used)
    assert result == "A僕"


def test_select_opening_empty_pool_fallback() -> None:
    result = select_opening([], pronoun="あたし")
    assert "あたし" in result


# ── build_feeling_prompt (basic pronoun substitution) ──


def test_build_feeling_prompt_uses_custom_pronoun() -> None:
    result = build_feeling_prompt(
        before_desc="plain clothes",
        after_desc="maid outfit",
        instruction="maid costume",
        pronoun="俺",
        opening="えっ…俺の姿が…",
    )
    assert "俺" in result


def test_build_feeling_prompt_default_pronoun() -> None:
    result = build_feeling_prompt(
        before_desc="casual",
        after_desc="dress",
        instruction="dress",
        opening="えっ…{pronoun}の姿が…",
    )
    assert "僕" in result


# ── build_enhanced_feeling_prompt (personality + pronoun + opening) ──


def test_enhanced_prompt_injects_personality() -> None:
    system, user = build_enhanced_feeling_prompt(
        before_desc="casual",
        after_desc="uniform",
        instruction="school uniform",
        bloom=20,
        pronoun="私",
        personality="穏やかで優しい",
    )
    assert "穏やかで優しい" in system
    assert "私" in user


def test_enhanced_prompt_nsfw_mode() -> None:
    system, user = build_enhanced_feeling_prompt(
        before_desc="casual",
        after_desc="bikini",
        instruction="swimsuit",
        bloom=50,
        nsfw_mode=True,
        pronoun="僕",
        transformation_count=1,
    )
    assert "官能" in system


def test_enhanced_prompt_first_transformation() -> None:
    system, user = build_enhanced_feeling_prompt(
        before_desc="normal",
        after_desc="dress",
        instruction="dress",
        bloom=0,
        transformation_count=0,
    )
    # First transformation should use special stage
    assert system is not None
    assert user is not None


def test_enhanced_prompt_gender_congruent_skips_discomfort() -> None:
    from gateway.services.gender_congruence import GenderCongruenceResult

    congruence = GenderCongruenceResult(
        fit="congruent",
        should_feel_gender_discomfort=False,
        reason="test",
        source="rule",
    )
    system, user = build_enhanced_feeling_prompt(
        before_desc="casual",
        after_desc="suit",
        instruction="メンズスーツ",
        bloom=10,
        pronoun="僕",
        transformation_count=1,
        gender_congruence=congruence,
    )
    assert "元の性別として自然" in system
    assert "抵抗と理屈" not in user
    assert "着心地" in user or "第一印象" in user
    # 禁止指示としての言及は可。強制構成の「抵抗と理屈」は使わない
