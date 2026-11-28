"""Prompt Expander の境界値・選択肢（唯一の情報源）。

フロントエンドは frontend/src/constants/promptExpander.ts に同値をミラーする。
"""

from __future__ import annotations

from typing import Final

from .novelai_models import (
    PRECISE_REFERENCE_STRENGTH_MAX,
    PRECISE_REFERENCE_TYPES,
    is_v5_image_model,
    precise_reference_format,
)

# 画像モデル（NovelAI のみ。NSFW は family から導出する）
PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS: Final[tuple[str, ...]] = (
    "nai-diffusion-5-full",
    "nai-diffusion-5-full-medium",
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
# 精密参照の参照元。character はキャラクタープリセットの立ち絵（ID で送り再生成でも使える）
PROMPT_EXPANDER_REFERENCE_KINDS: Final[tuple[str, ...]] = (
    "history",
    "entry",
    "upload",
    "character",
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

# インペイント（部分修正）。i2i 元をベース画像に使い、マスクで塗った領域だけを描き直す。
# 強度・ノイズは i2i の値をそのまま inpaintImg2ImgStrength / noise として使う。
# NovelAI はマスクを 1/8 解像度で扱うため、書き出し・正規化のグリッドもそれに合わせる。
PROMPT_EXPANDER_MASK_GRID_DIVISOR: Final[int] = 8
PROMPT_EXPANDER_BRUSH_SIZE_MIN: Final[int] = 4
PROMPT_EXPANDER_BRUSH_SIZE_MAX: Final[int] = 96
DEFAULT_PROMPT_EXPANDER_BRUSH_SIZE: Final[int] = 32

# 精密参照（NovelAI character reference）。V4.5 系と V5 Full / Curated で使え、
# 1 枚あたり Anlas を消費する。衣装（costume）と「衣装も参照する」は V5 のみ。
# 立ち絵差分では同一性の固定が目的なので、既定強度は Adventure の立ち絵生成と同じにする
PROMPT_EXPANDER_REFERENCE_TYPES: Final[tuple[str, ...]] = (
    "character",
    "style",
    "character&style",
    "costume",
)
assert set(PROMPT_EXPANDER_REFERENCE_TYPES) == set(PRECISE_REFERENCE_TYPES)
DEFAULT_PROMPT_EXPANDER_REFERENCE_TYPE: Final[str] = "character"
DEFAULT_PROMPT_EXPANDER_REFERENCE_STRENGTH: Final[float] = 0.85
DEFAULT_PROMPT_EXPANDER_REFERENCE_FIDELITY: Final[float] = 1.0
PROMPT_EXPANDER_ANLAS_PER_REFERENCE: Final[int] = 5
# 1 回の生成で送れる精密参照の枚数（通常プレイの精密参照と同じ上限）
PROMPT_EXPANDER_REFERENCE_MAX_COUNT: Final[int] = 6
# 精密参照に付ける登場人物（キャスト）の上限。名前は参照カードの表示名を兼ねる
PROMPT_EXPANDER_CAST_MAX: Final[int] = PROMPT_EXPANDER_REFERENCE_MAX_COUNT
PROMPT_EXPANDER_CAST_NAME_MAX_LEN: Final[int] = 40
PROMPT_EXPANDER_CAST_TAGS_MAX_LEN: Final[int] = 1000

# 背景透過。V5 系はプロンプト指示でネイティブ透過 PNG を返し、V4.5 系は白背景で生成して
# フロントの切り抜き処理（imageAlpha.ts）で透過にする。negative は複数ビュー・キャラクター
# シート化を抑える語だけに留め、複数人を禁じる語は入れない（複数キャラの透過生成も許すため）
TRANSPARENT_BACKGROUND_TAGS_V5: Final[tuple[str, ...]] = (
    "transparent background",
    "no shadow",
)
TRANSPARENT_BACKGROUND_TAGS_V45: Final[tuple[str, ...]] = (
    "simple background",
    "white background",
    "no shadow",
)
TRANSPARENT_BACKGROUND_NEGATIVE_TAGS: Final[tuple[str, ...]] = (
    "multiple views",
    "reference sheet",
    "character sheet",
    "turnaround",
)

# 背景透過タグの強調（V4.5 系のみ）。NovelAI の {} 記法は 1 段ごとに重み 1.05 倍で、
# V4/V4.5 でも有効。無強調だと白背景の指定がモデルに無視されて背景が描かれ、
# フロントの切り抜き（imageAlpha.ts）が失敗することがあるため既定で 2 段掛ける。
# V5 はネイティブ透過 PNG を返すので強調しない。
PROMPT_EXPANDER_TRANSPARENT_EMPHASIS_LEVELS: Final[tuple[int, ...]] = (0, 1, 2, 3)
DEFAULT_PROMPT_EXPANDER_TRANSPARENT_EMPHASIS: Final[int] = 2
# 強調対象は背景そのものを決めるタグだけ。no shadow は素のまま置く
TRANSPARENT_BACKGROUND_EMPHASIZED_TAGS: Final[frozenset[str]] = frozenset(
    {"simple background", "white background"}
)

# 漫画モード（NovelAI Diffusion V5 のコマ割り・吹き出し生成を LLM 拡張で支援する）
# panel_count は 0 が「おまかせ」（LLM が指示文から 2〜4 コマを選ぶ）
PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO: Final[int] = 0
PROMPT_EXPANDER_MANGA_PANEL_COUNT_MIN: Final[int] = 1
PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX: Final[int] = 6
PROMPT_EXPANDER_MANGA_LAYOUTS: Final[tuple[str, ...]] = (
    "auto",
    "vertical",
    "horizontal",
    "grid",
)
DEFAULT_PROMPT_EXPANDER_MANGA_LAYOUT: Final[str] = "auto"
# セリフ・効果音の言語（auto は指示文の言語に合わせる）
PROMPT_EXPANDER_MANGA_TEXT_LANGUAGES: Final[tuple[str, ...]] = ("auto", "ja", "en")
DEFAULT_PROMPT_EXPANDER_MANGA_TEXT_LANGUAGE: Final[str] = "auto"
# 読み順（rtl = 日本式: 右上始まりで右→左・上→下、ltr = 西洋式）
PROMPT_EXPANDER_MANGA_READING_DIRECTIONS: Final[tuple[str, ...]] = ("rtl", "ltr")
DEFAULT_PROMPT_EXPANDER_MANGA_READING_DIRECTION: Final[str] = "rtl"
# これまでの話（漫画で続きのページを作るときに LLM へ渡す前のページ）。
# 選べるページ数と、ページごとに渡す各欄の字数（超えた分は切り詰める）
PROMPT_EXPANDER_STORY_CONTEXT_MAX: Final[int] = 5
PROMPT_EXPANDER_STORY_SYNOPSIS_MAX_LEN: Final[int] = 1200
PROMPT_EXPANDER_STORY_SCRIPT_MAX_LEN: Final[int] = 1500
PROMPT_EXPANDER_STORY_CHARACTER_MAX_LEN: Final[int] = 600
PROMPT_EXPANDER_STORY_PROMPT_MAX_LEN: Final[int] = 2000


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


def supports_manga_mode(image_model: str | None) -> bool:
    """漫画モード（コマ割り・文字描画）は V5 系モデルのみ対応。"""
    return is_v5_image_model(image_model)


def supports_precise_reference(image_model: str | None) -> bool:
    """精密参照（character reference）を使えるモデルか。V5 Full の節約モードは非対応。"""
    return (
        is_prompt_expander_image_model(image_model)
        and precise_reference_format(image_model) is not None
    )


def reference_strength_max(image_model: str | None) -> float:
    """モデルで送れる精密参照の強度の上限（V4.5 は 1.0、V5 は 5.0）。"""
    reference_format = precise_reference_format(image_model) or "v4_5"
    return PRECISE_REFERENCE_STRENGTH_MAX[reference_format]


def normalize_reference_type(value: object) -> str:
    """保存値・入力値を参照種別のいずれかに丸める（不正値は既定値）。"""
    return (
        value  # type: ignore[return-value]
        if isinstance(value, str) and value in PROMPT_EXPANDER_REFERENCE_TYPES
        else DEFAULT_PROMPT_EXPANDER_REFERENCE_TYPE
    )


def emphasize_tag(tag: str, level: int) -> str:
    """NovelAI の {} 記法でタグを強調する。level 0 は素通し。"""
    if level <= 0:
        return tag
    return "{" * level + tag + "}" * level


def normalize_transparent_emphasis(value: object) -> int:
    """保存値・入力値を強調レベルの範囲へ丸める（不正値は既定値）。"""
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_PROMPT_EXPANDER_TRANSPARENT_EMPHASIS
    if value not in PROMPT_EXPANDER_TRANSPARENT_EMPHASIS_LEVELS:
        return DEFAULT_PROMPT_EXPANDER_TRANSPARENT_EMPHASIS
    return value


def transparent_background_tags(
    image_model: str | None, emphasis: int = 0
) -> tuple[str, ...]:
    """背景透過のために正プロンプト末尾へ足すタグ（モデル世代で分岐）。

    emphasis は V4.5 系の背景タグにだけ効く。V5 はネイティブ透過なので常に無強調。
    """
    if is_v5_image_model(image_model):
        return TRANSPARENT_BACKGROUND_TAGS_V5
    level = max(0, emphasis)
    if level == 0:
        return TRANSPARENT_BACKGROUND_TAGS_V45
    return tuple(
        emphasize_tag(tag, level)
        if tag in TRANSPARENT_BACKGROUND_EMPHASIZED_TAGS
        else tag
        for tag in TRANSPARENT_BACKGROUND_TAGS_V45
    )


def normalize_manga_panel_count(value: object) -> int:
    """保存値・入力値を 0（おまかせ）または範囲内の整数に丸める。"""
    if isinstance(value, bool) or not isinstance(value, int):
        return PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO
    if value < PROMPT_EXPANDER_MANGA_PANEL_COUNT_MIN:
        return PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO
    return min(value, PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX)
