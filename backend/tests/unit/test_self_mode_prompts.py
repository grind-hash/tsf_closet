"""Unit tests for self-mode prompt generation (US5/US6).

Covers build_self_mode_feeling_prompt, _build_self_profile_section,
and build_self_profile_generation_prompt.
"""

from gateway.services.self_mode_prompts import (
    build_self_mode_feeling_prompt,
    build_self_profile_generation_prompt,
    _build_self_profile_section,
)


# ── _build_self_profile_section ──


def test_profile_section_with_full_data() -> None:
    profile = {
        "personality": "cheerful and optimistic",
        "reaction_style": "bold",
        "tsf_attitude": "excited about it",
    }
    result = _build_self_profile_section(profile)
    assert "cheerful and optimistic" in result
    assert "大胆" in result
    assert "excited about it" in result


def test_profile_section_default_reaction_style_omitted() -> None:
    profile = {
        "personality": "calm",
        "reaction_style": "default",
    }
    result = _build_self_profile_section(profile)
    assert "性格: calm" in result
    assert "反応スタイル" not in result


def test_profile_section_empty_returns_fallback() -> None:
    result = _build_self_profile_section({})
    assert "プロフィール未設定" in result


def test_profile_section_truncates_long_personality() -> None:
    profile = {"personality": "x" * 300}
    result = _build_self_profile_section(profile)
    # Should truncate to 200
    assert len(result.split("性格: ")[1]) <= 200


# ── build_self_mode_feeling_prompt ──


def test_self_mode_feeling_prompt_returns_tuple() -> None:
    profile = {
        "personality": "quiet",
        "reaction_style": "shy",
        "pronoun": "私",
        "interests": ["reading"],
        "tsf_attitude": "curious",
    }
    system, user = build_self_mode_feeling_prompt(
        before_desc="casual",
        after_desc="dress",
        instruction="wear dress",
        self_profile=profile,
    )
    assert isinstance(system, str)
    assert isinstance(user, str)


def test_self_mode_feeling_prompt_uses_pronoun() -> None:
    profile = {
        "personality": "energetic",
        "pronoun": "俺",
        "interests": [],
        "reaction_style": "bold",
        "tsf_attitude": "",
    }
    _, user = build_self_mode_feeling_prompt(
        before_desc="casual",
        after_desc="maid",
        instruction="transform",
        self_profile=profile,
    )
    assert "俺" in user


def test_self_mode_feeling_prompt_includes_interests() -> None:
    profile = {
        "personality": "curious",
        "pronoun": "僕",
        "interests": ["anime", "games"],
        "reaction_style": "cheerful",
        "tsf_attitude": "",
    }
    _, user = build_self_mode_feeling_prompt(
        before_desc="plain",
        after_desc="uniform",
        instruction="uniform",
        self_profile=profile,
    )
    assert "anime" in user
    assert "games" in user


def test_self_mode_feeling_prompt_nsfw_mode() -> None:
    profile = {
        "personality": "shy",
        "pronoun": "僕",
        "interests": [],
        "reaction_style": "default",
        "tsf_attitude": "",
    }
    system, _ = build_self_mode_feeling_prompt(
        before_desc="casual",
        after_desc="bikini",
        instruction="swimsuit",
        self_profile=profile,
        nsfw_mode=True,
    )
    assert "官能" in system


def test_self_mode_feeling_prompt_normal_mode() -> None:
    profile = {
        "personality": "calm",
        "pronoun": "僕",
        "interests": [],
        "reaction_style": "default",
        "tsf_attitude": "",
    }
    system, _ = build_self_mode_feeling_prompt(
        before_desc="casual",
        after_desc="dress",
        instruction="dress",
        self_profile=profile,
        nsfw_mode=False,
    )
    assert "官能" not in system
    assert "物語の主人公" in system


def test_self_mode_feeling_prompt_empty_desc_fallback() -> None:
    profile = {"personality": "x", "pronoun": "僕", "interests": []}
    _, user = build_self_mode_feeling_prompt(
        before_desc="",
        after_desc="",
        instruction="test",
        self_profile=profile,
    )
    assert "不明" in user


# ── build_self_profile_generation_prompt ──


def test_self_profile_generation_prompt_returns_tuple() -> None:
    system, user = build_self_profile_generation_prompt(
        "20代の大学生、アニメ好き"
    )
    assert isinstance(system, str)
    assert isinstance(user, str)


def test_self_profile_generation_prompt_includes_input() -> None:
    _, user = build_self_profile_generation_prompt(
        "I'm a college student who likes reading"
    )
    assert "college student" in user


def test_self_profile_generation_prompt_truncates_long_input() -> None:
    long_text = "x" * 2000
    _, user = build_self_profile_generation_prompt(long_text)
    # Input should be truncated to 1000 chars
    x_count = user.count("x")
    assert x_count <= 1000


def test_self_profile_generation_system_contains_json_schema() -> None:
    system, _ = build_self_profile_generation_prompt("test")
    assert "personality" in system
    assert "reaction_style" in system
    assert "pronoun" in system
    assert "interests" in system
    assert "tsf_attitude" in system
