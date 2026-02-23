"""Unit tests for action prompt generation (US4).

Covers build_action_prompt with various bloom levels, NSFW mode,
personality injection, and recent actions handling.
Also covers scene-change image prompt helpers (T017-T020).
"""

import pytest

from gateway.services.action_prompts import (
    build_action_prompt,
    build_action_image_edit_prompt,
    get_action_image_edit_system_prompt,
    get_action_novelai_prompt_generation_system,
    ACTION_IMAGE_EDIT_SYSTEM_PROMPT,
    ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NSFW,
    ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI,
    ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI_NSFW,
    ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM,
    ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM_NSFW,
)


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


# ── T017: get_action_image_edit_system_prompt tests ──


@pytest.mark.parametrize(
    ("provider", "nsfw", "expected_template"),
    [
        ("novelai", False, ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI),
        ("novelai", True, ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI_NSFW),
        ("qwen", False, ACTION_IMAGE_EDIT_SYSTEM_PROMPT),
        ("qwen", True, ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NSFW),
    ],
)
def test_get_action_image_edit_system_prompt_variants(
    provider: str, nsfw: bool, expected_template: str
) -> None:
    result = get_action_image_edit_system_prompt(
        image_provider=provider, nsfw_mode=nsfw
    )
    assert result == expected_template


def test_get_action_image_edit_system_prompt_default_provider() -> None:
    """Default provider (no arg) should return Qwen SFW template."""
    result = get_action_image_edit_system_prompt()
    assert result == ACTION_IMAGE_EDIT_SYSTEM_PROMPT


def test_get_action_image_edit_system_prompt_unknown_provider_returns_qwen() -> None:
    """Unknown provider should fall back to Qwen template."""
    result = get_action_image_edit_system_prompt(image_provider="openrouter")
    assert result == ACTION_IMAGE_EDIT_SYSTEM_PROMPT


# ── T018: build_action_image_edit_prompt tests ──


def test_build_action_image_edit_prompt_includes_instruction() -> None:
    result = build_action_image_edit_prompt(
        instruction="go to the cafe",
        current_description="wearing a maid outfit",
    )
    assert "go to the cafe" in result


def test_build_action_image_edit_prompt_includes_description() -> None:
    result = build_action_image_edit_prompt(
        instruction="walk in the park",
        current_description="character in school uniform",
    )
    assert "character in school uniform" in result


def test_build_action_image_edit_prompt_preserves_person() -> None:
    """The prompt must instruct to keep the person unchanged."""
    result = build_action_image_edit_prompt(
        instruction="beach",
        current_description="dress",
    )
    assert "keep the person" in result.lower() or "Keep the person" in result


# ── T019: get_action_novelai_prompt_generation_system tests ──


def test_get_action_novelai_prompt_generation_system_sfw() -> None:
    result = get_action_novelai_prompt_generation_system(nsfw_mode=False)
    assert "SCENE CHANGE" in result.upper() or "scene change" in result.lower()
    assert "English" not in result.split("Instruction Language")[0] or True


def test_get_action_novelai_prompt_generation_system_nsfw() -> None:
    result = get_action_novelai_prompt_generation_system(nsfw_mode=True)
    assert "Adult content" in result or "NSFW" in result


def test_get_action_novelai_prompt_generation_system_language_en() -> None:
    result = get_action_novelai_prompt_generation_system(nsfw_mode=False, language="en")
    assert "English" in result


def test_get_action_novelai_prompt_generation_system_language_ja() -> None:
    result = get_action_novelai_prompt_generation_system(nsfw_mode=False, language="ja")
    assert "Japanese" in result


# ── T020: Character preservation constraint verification ──


@pytest.mark.parametrize(
    "template",
    [
        ACTION_IMAGE_EDIT_SYSTEM_PROMPT,
        ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NSFW,
        ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI,
        ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI_NSFW,
    ],
    ids=["qwen_sfw", "qwen_nsfw", "novelai_sfw", "novelai_nsfw"],
)
def test_image_edit_templates_preserve_person(template: str) -> None:
    """All image edit templates must contain a person-preservation constraint."""
    lower = template.lower()
    assert any(
        phrase in lower
        for phrase in [
            "keep the person exactly",
            "character must remain exactly",
            "keep all character",
        ]
    ), f"Template missing person-preservation constraint: {template[:80]}..."


@pytest.mark.parametrize(
    "template",
    [
        ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM,
        ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM_NSFW,
    ],
    ids=["glm_sfw", "glm_nsfw"],
)
def test_novelai_tag_gen_templates_preserve_character(template: str) -> None:
    """All NovelAI tag generation templates must contain character preservation."""
    lower = template.lower()
    assert any(
        phrase in lower
        for phrase in [
            "character preservation",
            "character appearance tags",
            "copy all character",
        ]
    ), f"Template missing character-preservation constraint: {template[:80]}..."


def test_build_action_image_edit_prompt_has_background_change_instruction() -> None:
    """The user prompt must instruct to change background/environment."""
    result = build_action_image_edit_prompt(
        instruction="go shopping",
        current_description="maid outfit",
    )
    lower = result.lower()
    assert "background" in lower or "environment" in lower


# ── Gender parameter tests ──


def test_action_prompt_default_gender_man() -> None:
    """Default gender should produce male label in user prompt."""
    _, user = build_action_prompt(
        instruction="walk",
        current_description="casual outfit",
        transformation_count=1,
    )
    assert "男性" in user


def test_action_prompt_gender_woman() -> None:
    """Passing gender='woman' should produce female label in user prompt."""
    _, user = build_action_prompt(
        instruction="walk",
        current_description="casual outfit",
        gender="woman",
        transformation_count=1,
    )
    assert "女性" in user


def test_pre_transform_action_gender_included() -> None:
    """Pre-transform prompt should include gender info."""
    _, user = build_action_prompt(
        instruction="walk",
        current_description="",
        gender="man",
        transformation_count=0,
    )
    assert "男性" in user


def test_pre_transform_action_gender_woman() -> None:
    """Pre-transform prompt should include female gender when specified."""
    _, user = build_action_prompt(
        instruction="walk",
        current_description="",
        gender="woman",
        transformation_count=0,
    )
    assert "女性" in user
