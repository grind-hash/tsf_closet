"""Unit tests for action prompt generation (US4).

Covers build_action_prompt with various bloom levels, NSFW mode,
personality injection, and recent actions handling.
"""

import pytest

from gateway.services.action_prompts import build_action_prompt


def test_basic_action_prompt_returns_tuple() -> None:
    system, user = build_action_prompt(
        instruction="go to the cafe",
        current_description="wearing a maid outfit",
    )
    assert isinstance(system, str)
    assert isinstance(user, str)
    assert len(system) > 0
    assert len(user) > 0


def test_action_prompt_includes_instruction() -> None:
    _, user = build_action_prompt(
        instruction="go shopping",
        current_description="casual dress",
    )
    assert "go shopping" in user


def test_action_prompt_includes_pronoun() -> None:
    _, user = build_action_prompt(
        instruction="walk",
        current_description="uniform",
        pronoun="あたし",
    )
    assert "あたし" in user


@pytest.mark.parametrize(
    ("bloom", "expected_fragment"),
    [
        (10, "confused"),
        (30, "wavering"),
        (60, "accepted"),
        (80, "embraces"),
    ],
)
def test_action_prompt_bloom_stages(bloom: int, expected_fragment: str) -> None:
    system, _ = build_action_prompt(
        instruction="go out",
        current_description="dress",
        bloom=bloom,
        transformation_count=1,
    )
    assert expected_fragment in system


def test_action_prompt_nsfw_mode() -> None:
    system, _ = build_action_prompt(
        instruction="go to beach",
        current_description="bikini",
        nsfw_mode=True,
        transformation_count=1,
    )
    assert "官能" in system
    assert "変身した姿" in system


def test_action_prompt_personality_injection() -> None:
    system, user = build_action_prompt(
        instruction="cafe",
        current_description="maid outfit",
        personality="明るくて元気",
        transformation_count=1,
    )
    assert "明るくて元気" in system
    assert "明るくて元気" in user


def test_action_prompt_description_in_system() -> None:
    system, _ = build_action_prompt(
        instruction="walk",
        current_description="dress",
        personality="cold and calm",
        description="A silver-haired elf",
        transformation_count=1,
    )
    assert "A silver-haired elf" in system


def test_action_prompt_recent_actions() -> None:
    _, user = build_action_prompt(
        instruction="go to park",
        current_description="dress",
        recent_actions=["went to cafe", "visited store"],
        transformation_count=1,
    )
    assert "went to cafe" in user
    assert "visited store" in user


def test_action_prompt_recent_actions_truncated_to_five() -> None:
    actions = [f"action_{i}" for i in range(10)]
    _, user = build_action_prompt(
        instruction="next",
        current_description="outfit",
        recent_actions=actions,
        transformation_count=1,
    )
    # Should only include last 5
    assert "action_5" in user
    assert "action_9" in user
    assert "action_0" not in user


def test_action_prompt_empty_description_fallback() -> None:
    _, user = build_action_prompt(
        instruction="walk",
        current_description="",
        transformation_count=1,
    )
    # Fallback to "不明"
    assert "不明" in user


# ── Pre-transformation (transformation_count == 0) tests ──


def test_pre_transform_action_no_transformation_reference() -> None:
    """transformation_count==0 should produce a daily-life prompt with no TSF."""
    system, user = build_action_prompt(
        instruction="カフェに行く",
        current_description="",
        transformation_count=0,
    )
    assert "まだ変身していない" in system or "まだ変身して" in system
    assert "変身した姿" not in system
    assert "普段の姿" in user or "何の変身も起きて" in user
    # The bloom-based stage description should NOT appear
    assert "confused" not in system
    assert "wavering" not in system


def test_pre_transform_action_nsfw_mode() -> None:
    system, _ = build_action_prompt(
        instruction="カフェに行く",
        current_description="",
        nsfw_mode=True,
        transformation_count=0,
    )
    assert "官能" in system
    assert "まだ変身して" in system


def test_pre_transform_action_user_prompt_no_outfit() -> None:
    """Pre-transform user prompt should not include outfit/description section."""
    _, user = build_action_prompt(
        instruction="散歩する",
        current_description="maid outfit",
        transformation_count=0,
    )
    # current_description should NOT appear in pre-transform user prompt
    assert "maid outfit" not in user
    assert "散歩する" in user


def test_post_transform_action_includes_description() -> None:
    """transformation_count>=1 should include outfit description as before."""
    system, user = build_action_prompt(
        instruction="カフェに行く",
        current_description="メイド服を着た少女",
        bloom=10,
        transformation_count=1,
    )
    assert "メイド服を着た少女" in user
    assert "confused" in system  # bloom < 25


def test_pre_transform_with_personality() -> None:
    system, user = build_action_prompt(
        instruction="カフェに行く",
        current_description="",
        personality="明るくて元気",
        transformation_count=0,
    )
    assert "明るくて元気" in system
    assert "明るくて元気" in user
