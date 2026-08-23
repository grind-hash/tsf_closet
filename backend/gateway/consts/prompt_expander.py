"""Prompt Expander の境界値・選択肢（唯一の情報源）。

フロントエンドは frontend/src/constants/promptExpander.ts に同値をミラーする。
"""

from __future__ import annotations

from typing import Final

from .novelai_models import is_v5_image_model

# 画像モデル（NovelAI のみ。NSFW は family から導出する）
PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS: Final[tuple[str, ...]] = (
    "nai-diffusion-5-full",
    "nai-diffusion-5-curated",
    "nai-diffusion-4-5-full",
    "nai-diffusion-4-5-curated",
)
DEFAULT_PROMPT_EXPANDER_IMAGE_MODEL: Final[str] = "nai-diffusion-4-5-full"

# キャラクタープロンプトの上限（V5 は公式発表の 22 人、V4.5 は従来どおり 6 人）
MAX_CHARACTER_PROMPTS_V5: Final[int] = 22
MAX_CHARACTER_PROMPTS_V45: Final[int] = 6

# 無料枠で生成できるサイズのみ（large 系は Anlas を消費するため対象外）
PROMPT_EXPANDER_IMAGE_SIZES: Final[tuple[str, ...]] = (
    "portrait",
    "landscape",
    "square",
)
DEFAULT_PROMPT_EXPANDER_IMAGE_SIZE: Final[str] = "portrait"

PROMPT_EXPANDER_EXPAND_MODES: Final[tuple[str, ...]] = ("off", "japanese", "tags")
PROMPT_EXPANDER_SOURCE_KINDS: Final[tuple[str, ...]] = (
    "none",
    "history",
    "entry",
    "upload",
)

PROMPT_EXPANDER_SUGGESTION_COUNT_DEFAULT: Final[int] = 3
PROMPT_EXPANDER_SUGGESTION_COUNT_MIN: Final[int] = 1
PROMPT_EXPANDER_SUGGESTION_COUNT_MAX: Final[int] = 5

PROMPT_EXPANDER_TITLE_MAX_LEN: Final[int] = 120
PROMPT_EXPANDER_INSTRUCTION_MAX_LEN: Final[int] = 4000
PROMPT_EXPANDER_PROMPT_MAX_LEN: Final[int] = 8000
PROMPT_EXPANDER_NEGATIVE_MAX_LEN: Final[int] = 4000
PROMPT_EXPANDER_CHARACTER_PROMPT_MAX_LEN: Final[int] = 2000
PROMPT_EXPANDER_MEMORY_MAX_LEN: Final[int] = 10000
# base64 文字列としての上限（約 12MB の画像に相当）
PROMPT_EXPANDER_UPLOAD_MAX_BASE64_LEN: Final[int] = 16 * 1024 * 1024

DEFAULT_PROMPT_EXPANDER_I2I_STRENGTH: Final[float] = 0.7
DEFAULT_PROMPT_EXPANDER_I2I_NOISE: Final[float] = 0.0


def max_character_prompts(image_model: str | None) -> int:
    """画像モデルに応じたキャラクタープロンプト上限を返す。"""
    return (
        MAX_CHARACTER_PROMPTS_V5
        if is_v5_image_model(image_model)
        else MAX_CHARACTER_PROMPTS_V45
    )


def max_character_prompts_map() -> dict[str, int]:
    """選択可能モデルごとの上限（設定応答に同梱する）。"""
    return {
        model: max_character_prompts(model)
        for model in PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS
    }


def is_prompt_expander_image_model(name: str | None) -> bool:
    return bool(name) and name in PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS
