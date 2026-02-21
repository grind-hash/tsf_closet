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
    )
    assert expected_fragment in system


def test_action_prompt_nsfw_mode() -> None:
    system, _ = build_action_prompt(
        instruction="go to beach",
        current_description="bikini",
        nsfw_mode=True,
    )
    assert "官能" in system


def test_action_prompt_personality_injection() -> None:
    system, user = build_action_prompt(
        instruction="cafe",
        current_description="maid outfit",
        personality="明るくて元気",
    )
    assert "明るくて元気" in system
    assert "明るくて元気" in user


def test_action_prompt_description_in_system() -> None:
    system, _ = build_action_prompt(
        instruction="walk",
        current_description="dress",
        personality="cold and calm",
        description="A silver-haired elf",
    )
    assert "A silver-haired elf" in system


def test_action_prompt_recent_actions() -> None:
    _, user = build_action_prompt(
        instruction="go to park",
        current_description="dress",
        recent_actions=["went to cafe", "visited store"],
    )
    assert "went to cafe" in user
    assert "visited store" in user


def test_action_prompt_recent_actions_truncated_to_five() -> None:
    actions = [f"action_{i}" for i in range(10)]
    _, user = build_action_prompt(
        instruction="next",
        current_description="outfit",
        recent_actions=actions,
    )
    # Should only include last 5
    assert "action_5" in user
    assert "action_9" in user
    assert "action_0" not in user


def test_action_prompt_empty_description_fallback() -> None:
    _, user = build_action_prompt(
        instruction="walk",
        current_description="",
    )
    # Fallback to "不明"
    assert "不明" in user
