"""Prompt Expander の定数・上限のテスト。"""

from __future__ import annotations

from gateway.consts.novelai_text_models import (
    DEFAULT_NOVELAI_TEXT_MODEL,
    NOVELAI_TEXT_MODEL_OPTIONS,
    is_novelai_text_model,
)
from gateway.consts.prompt_expander import (
    MAX_CHARACTER_PROMPTS_V5,
    MAX_CHARACTER_PROMPTS_V45,
    PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS,
    is_prompt_expander_image_model,
    max_character_prompts,
    max_character_prompts_map,
)


def test_character_limits_by_model():
    assert (
        max_character_prompts("nai-diffusion-5-full") == MAX_CHARACTER_PROMPTS_V5 == 22
    )
    assert max_character_prompts("nai-diffusion-5-curated") == 22
    assert (
        max_character_prompts("nai-diffusion-4-5-full")
        == MAX_CHARACTER_PROMPTS_V45
        == 6
    )
    assert max_character_prompts("nai-diffusion-4-5-curated") == 6
    # 未知名・None は V4.5 相当に倒す
    assert max_character_prompts(None) == 6
    assert max_character_prompts("unknown") == 6


def test_character_limit_map_covers_all_options():
    mapping = max_character_prompts_map()
    assert set(mapping) == set(PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS)
    assert mapping["nai-diffusion-5-full"] == 22
    assert mapping["nai-diffusion-4-5-curated"] == 6


def test_image_model_options():
    assert is_prompt_expander_image_model("nai-diffusion-5-curated")
    assert not is_prompt_expander_image_model("nai-diffusion-3")
    assert not is_prompt_expander_image_model(None)


def test_text_model_options():
    assert NOVELAI_TEXT_MODEL_OPTIONS == ("glm-4-6", "xialong-v1")
    assert DEFAULT_NOVELAI_TEXT_MODEL == "glm-4-6"
    assert is_novelai_text_model("xialong-v1")
    assert not is_novelai_text_model("gpt-4")
    assert not is_novelai_text_model(None)
