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


def test_manga_constants_and_helpers():
    from gateway.consts.prompt_expander import (
        PROMPT_EXPANDER_MANGA_LAYOUTS,
        PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO,
        PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX,
        PROMPT_EXPANDER_MANGA_TEXT_LANGUAGES,
        normalize_manga_panel_count,
        supports_manga_mode,
    )

    assert PROMPT_EXPANDER_MANGA_LAYOUTS == ("auto", "vertical", "horizontal", "grid")
    assert PROMPT_EXPANDER_MANGA_TEXT_LANGUAGES == ("auto", "ja", "en")
    assert supports_manga_mode("nai-diffusion-5-full")
    assert supports_manga_mode("nai-diffusion-5-curated")
    assert not supports_manga_mode("nai-diffusion-4-5-full")
    assert not supports_manga_mode(None)
    assert normalize_manga_panel_count(None) == PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO
    assert normalize_manga_panel_count("3") == PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO
    assert normalize_manga_panel_count(True) == PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO
    assert normalize_manga_panel_count(-1) == PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO
    assert normalize_manga_panel_count(3) == 3
    assert normalize_manga_panel_count(99) == PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX


def test_precise_reference_and_transparency_helpers():
    from gateway.consts.prompt_expander import (
        DEFAULT_PROMPT_EXPANDER_REFERENCE_TYPE,
        PROMPT_EXPANDER_ANLAS_PER_REFERENCE,
        PROMPT_EXPANDER_REFERENCE_TYPES,
        TRANSPARENT_BACKGROUND_NEGATIVE_TAGS,
        TRANSPARENT_BACKGROUND_TAGS_V5,
        TRANSPARENT_BACKGROUND_TAGS_V45,
        normalize_reference_type,
        supports_precise_reference,
        transparent_background_tags,
    )

    # 精密参照は V4.5 系だけ（V5 は API 非対応、未知名・None も不可）
    assert supports_precise_reference("nai-diffusion-4-5-full")
    assert supports_precise_reference("nai-diffusion-4-5-curated")
    assert not supports_precise_reference("nai-diffusion-5-full")
    assert not supports_precise_reference("nai-diffusion-5-curated")
    assert not supports_precise_reference(None)
    assert not supports_precise_reference("nai-diffusion-3")
    assert PROMPT_EXPANDER_REFERENCE_TYPES == ("character", "style", "character&style")
    assert normalize_reference_type("style") == "style"
    assert normalize_reference_type("vibe") == DEFAULT_PROMPT_EXPANDER_REFERENCE_TYPE
    assert normalize_reference_type(None) == "character"
    assert PROMPT_EXPANDER_ANLAS_PER_REFERENCE == 5

    # 背景透過タグは世代で分岐し、negative は複数人を禁じる語を含まない
    assert (
        transparent_background_tags("nai-diffusion-5-full")
        == TRANSPARENT_BACKGROUND_TAGS_V5
    )
    assert transparent_background_tags("nai-diffusion-5-curated") == (
        "transparent background",
        "no shadow",
    )
    assert (
        transparent_background_tags("nai-diffusion-4-5-full")
        == TRANSPARENT_BACKGROUND_TAGS_V45
    )
    assert "white background" in transparent_background_tags(
        "nai-diffusion-4-5-curated"
    )
    assert "transparent background" not in transparent_background_tags(None)
    assert "multiple views" in TRANSPARENT_BACKGROUND_NEGATIVE_TAGS
    assert not any(
        "girls" in tag or "people" in tag
        for tag in TRANSPARENT_BACKGROUND_NEGATIVE_TAGS
    )
