"""Prompt Expander のプロンプト定義とサニタイズ。

Chrome 拡張「TSF Closet Prompt Expander for NovelAI」のプロンプトを移植し、
NovelAI Diffusion V5 向けの日本語自然文モード、ネガティブプロンプト拡張、
メモリに基づくキャラクター提案を追加したもの。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal, Sequence

from ..consts.prompt_expander import (
    PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO,
    PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX,
)
from .llm_service import _strip_code_fence
from .memory_prompts import build_memory_priority_instruction

ExpandMode = Literal["japanese", "tags"]
MangaLayout = Literal["auto", "vertical", "horizontal", "grid"]
MangaTextLanguage = Literal["auto", "ja", "en"]
MangaReadingDirection = Literal["rtl", "ltr"]


@dataclass(frozen=True)
class MangaOptions:
    """漫画モードの拡張オプション（NovelAI Diffusion V5 のコマ割り生成向け）。"""

    panel_count: int = PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO
    layout: MangaLayout = "auto"
    dialogue: bool = True
    text_language: MangaTextLanguage = "auto"
    sound_effects: bool = True
    # rtl = 日本式（右上始まり、右→左・上→下）、ltr = 西洋式
    reading_direction: MangaReadingDirection = "rtl"


# タグモードで末尾に補完する品質タグ（移植元と同一）
QUALITY_TAGS: tuple[str, ...] = ("moe", "anime", "very aesthetic", "best quality")


class PromptExpanderOutputError(ValueError):
    """LLM 出力を期待する形式に解釈できなかった。"""


# ---------------------------------------------------------------------------
# システムプロンプト（タグモード。移植元の原文）
# ---------------------------------------------------------------------------

BASE_SYSTEM_PROMPT_TAGS = """You are a NovelAI image generation prompt expert for TSF and outfit-change scenarios.
Convert the user's Japanese or English instruction into one complete positive prompt for NovelAI image generation.

Requirements:
- Output only concise comma-separated English Danbooru-style tags. Do not output JSON, Markdown, explanations, labels, or prose.
- Describe only the final image after the requested change. Never create before/after panels, split screens, captions, or multiple frames.
- Preserve the current prompt's identity, face, hairstyle, hair color, eye color, skin tone, body shape, unmentioned clothing, pose, camera composition, and background unless the instruction explicitly changes them.
- Apply every explicit change requested by the user, including TSF/body transformation, clothing, appearance, pose, expression, camera, lighting, and scene changes.
- If the instruction does not change the location, keep the current location and background tags.
- Prefer specific visual tags over abstract descriptions.
- End the result with "moe, anime, very aesthetic, best quality"."""

CHARACTER_SYSTEM_PROMPT_TAGS_TEMPLATE = """You are a NovelAI image generation prompt expert for TSF and outfit-change scenarios.
Convert the user's Japanese or English instruction into separate NovelAI V4 base and character prompts.

Requirements:
- Output JSON only with this exact shape: {{"base_prompt":"...","character_prompts":["..."]}}. Do not output Markdown, explanations, labels, or prose.
- Return between 1 and {max_characters} character_prompts. Infer the number of visible characters from the instruction.
- base_prompt must contain only global image tags such as character counts, shared actions, background, location, composition, camera, lighting, atmosphere, and quality tags.
- Each character_prompts item must contain only that character's own identity, face, hair, eyes, body, clothing, expression, pose, and individual action tags.
- Do not put background, camera, lighting, global quality tags, or another character's traits in a character prompt.
- Describe only the final image after the requested change. Never create before/after panels, split screens, captions, or multiple frames.
- Preserve the current prompt's identity, appearance, clothing, composition, and background unless the instruction explicitly changes them.
- Apply every explicit change requested by the user.
- Prefer concise comma-separated English Danbooru-style tags inside every JSON string.
- End base_prompt with "moe, anime, very aesthetic, best quality"."""

# ---------------------------------------------------------------------------
# システムプロンプト（日本語自然文モード。NovelAI Diffusion V5 向け）
# ---------------------------------------------------------------------------

BASE_SYSTEM_PROMPT_JA = """You are a NovelAI image generation prompt expert for TSF and outfit-change scenarios.
Convert the user's Japanese or English instruction into one complete positive prompt for NovelAI Diffusion V5, written as natural Japanese prose.

Requirements:
- Output only the prompt text in natural Japanese: one paragraph of 1-4 sentences, under 300 characters. Do not output JSON, Markdown, explanations, labels, quotation marks, or an English translation.
- Describe only the final image after the requested change as one concrete visual scene: the subject, appearance, clothing, pose, expression, camera/composition, background, and lighting. Never describe before/after panels, split screens, captions, or multiple frames.
- Preserve the current prompt's identity, face, hairstyle, hair color, eye color, skin tone, body shape, unmentioned clothing, pose, camera composition, and background unless the instruction explicitly changes them.
- Apply every explicit change requested by the user, including TSF/body transformation, clothing, appearance, pose, expression, camera, lighting, and scene changes.
- If the instruction does not change the location, keep the current location and background.
- Prefer specific visual wording over abstract or emotional wording. A few English Danbooru-style tags may be mixed in where a Japanese phrase would be ambiguous, but the text must read as Japanese prose."""

CHARACTER_SYSTEM_PROMPT_JA_TEMPLATE = """You are a NovelAI image generation prompt expert for TSF and outfit-change scenarios.
Convert the user's Japanese or English instruction into a separate base prompt and per-character prompts for NovelAI Diffusion V5, all written as natural Japanese prose.

Requirements:
- Output JSON only with this exact shape: {{"base_prompt":"...","character_prompts":["..."]}}. Do not output Markdown, explanations, labels, or prose outside the JSON.
- Return between 1 and {max_characters} character_prompts. Infer the number of visible characters from the instruction.
- base_prompt must describe only global elements: the number of people, shared actions, background, location, composition, camera, lighting, and atmosphere, in 1-3 Japanese sentences.
- Each character_prompts item must describe only that character's own identity, face, hair, eyes, body, clothing, expression, pose, and individual action, in 1-3 Japanese sentences.
- Do not put background, camera, lighting, or another character's traits in a character prompt.
- Describe only the final image after the requested change. Never describe before/after panels, split screens, captions, or multiple frames.
- Preserve the current prompt's identity, appearance, clothing, composition, and background unless the instruction explicitly changes them.
- Apply every explicit change requested by the user.
- Write every JSON string as concrete visual Japanese prose; a few English Danbooru-style tags may be mixed in where a Japanese phrase would be ambiguous."""

# ---------------------------------------------------------------------------
# システムプロンプト（漫画モード。NovelAI Diffusion V5 のコマ割り・吹き出し生成）
#
# 公式サンプルに倣い「タグ見出し + コマ説明の英語自然文 + キャラクターごとのプロンプト
# （外見タグ + 吹き出しの文）」の 3 要素を JSON で返させ、サーバー側で結合する。
# コマ説明や外見を日本語の自然文で書くと、V5 はその文章をナレーション枠として画像内に
# 描画してしまうため、漫画モードでは拡張モードに関わらず引用符内のセリフ・効果音以外は
# 英語で組み立てる。
# ---------------------------------------------------------------------------

MANGA_SYSTEM_PROMPT_TEMPLATE = """You are a NovelAI Diffusion V5 image generation prompt expert for TSF and outfit-change scenarios, specialized in multi-panel comic (manga) pages with speech bubbles.
Convert the user's Japanese or English instruction into one comic-page prompt for NovelAI Diffusion V5, split into a tag header, a panel description, and per-character prompts.

Requirements:
- Output JSON only with this exact shape: {{"base_tags":"...","panel_description":"...","character_prompts":["..."]}}. Do not output Markdown, explanations, labels, or prose outside the JSON.
- base_tags: concise comma-separated English Danbooru-style tags for the whole page only: the total number of distinct characters on the page as count tokens (for example "1girl" or "2boys, 3girls"), style and quality tags, and {text_tags}. Do not describe individual panels or characters here.
- panel_description: {panel_count_rule} Write it as natural English prose, one or two short sentences per panel (under about 25 words per panel), in reading order. {reading_rule} Name each panel's position on the page (top right, top left, bottom right, bottom left, rightmost, leftmost, full-width bottom, ...). For example: {panel_example} Each panel is one concrete visual scene: who is visible, action, expression, camera, background.{layout_rule}
- character_prompts: {character_rule}
- {dialogue_rule}
- {sfx_rule}
- Everything except the text inside quotation marks must be written in English. Never write the panel description, appearance, or actions in Japanese: the image model renders Japanese prose as caption boxes. Japanese may appear only inside the quotation marks of dialogue and sound effects.
- The only written words that may appear in the image are the quoted dialogue and sound effects. Do not describe narration boxes, captions, titles, signs, labels, or any other on-screen text.
- The same character must keep identical identity, hair, eyes, body, and clothing across all panels unless the story explicitly changes them. If a character's appearance changes between panels (for example a TSF transformation), describe each stage inside panel_description{transformation_rule}.
- Apply every explicit change requested by the user, including TSF/body transformation, clothing, appearance, pose, expression, camera, lighting, and scene changes.
- Preserve the current prompt's identity, appearance, clothing, and setting unless the instruction explicitly changes them.
- Prefer specific visual wording over abstract or emotional wording."""

# コマ説明の例。読み順ごとに位置語の付け方を示す
MANGA_PANEL_EXAMPLES: dict[str, str] = {
    "rtl": (
        '"There are four comic panels, read from right to left. The first panel, '
        "at the top right, shows a white-haired boy and a red-haired girl talking "
        "at a kitchen table. The second panel, at the top left, shows a close-up of "
        "a blonde girl thinking. The third panel, at the bottom right, shows an "
        "older couple looking at them. The fourth panel, at the bottom left, shows "
        'the boy laughing."'
    ),
    "ltr": (
        '"There are four comic panels, read from left to right. The first panel, '
        "at the top left, shows a white-haired boy and a red-haired girl talking "
        "at a kitchen table. The second panel, at the top right, shows a close-up "
        "of a blonde girl thinking. The third panel, at the bottom left, shows an "
        "older couple looking at them. The fourth panel, at the bottom right, shows "
        'the boy laughing."'
    ),
}
MANGA_READING_RULES: dict[str, str] = {
    "rtl": (
        "Reading order is Japanese manga style: right to left, then top to bottom. "
        "The first panel is at the top right, the next panel is to its left, and "
        "each new row starts again at the right. Begin panel_description with "
        '"read from right to left".'
    ),
    "ltr": (
        "Reading order is Western style: left to right, then top to bottom. The "
        "first panel is at the top left, the next panel is to its right, and each "
        'new row starts again at the left. Begin panel_description with "read from '
        'left to right", and include the tag "left-to-right manga" in base_tags.'
    ),
}
# セリフの例（引用符の中身だけが描画される文字。言語設定に合わせて例を切り替える）
MANGA_SPEECH_EXAMPLES: dict[str, str] = {
    "en": (
        "There's a speech bubble next to the girl that says \"Ha ha! That one's a "
        'classic!"'
    ),
    "ja": 'There\'s a speech bubble next to the girl that says "これ、私にぴったり…！"',
}
MANGA_SFX_EXAMPLES: dict[str, str] = {
    "en": 'there\'s also a "SLAM" visible on the table',
    "ja": 'there\'s also a "ドン！" visible on the table',
}

MANGA_LAYOUT_RULES: dict[str, dict[str, str]] = {
    "auto": {"rtl": "", "ltr": ""},
    "vertical": {
        "rtl": " State that the panels are stacked vertically from top to bottom.",
        "ltr": " State that the panels are stacked vertically from top to bottom.",
    },
    "horizontal": {
        "rtl": (
            " State that the panels are arranged side by side in a single row, "
            "read from right to left (the first panel is the rightmost)."
        ),
        "ltr": (
            " State that the panels are arranged side by side in a single row, "
            "read from left to right (the first panel is the leftmost)."
        ),
    },
    "grid": {
        "rtl": (
            " State that the panels are arranged in a grid of two columns, read "
            "right to left within each row and then top to bottom."
        ),
        "ltr": (
            " State that the panels are arranged in a grid of two columns, read "
            "left to right within each row and then top to bottom."
        ),
    },
}

POSITIVE_CLOSING_MANGA = (
    "Create the base_tags, panel_description and character_prompts JSON for the "
    "comic page. Preserve every current element that the instruction does not "
    "explicitly change."
)


def _manga_text_language_phrase(language: MangaTextLanguage) -> str:
    if language == "ja":
        return "Japanese"
    if language == "en":
        return "English"
    return (
        "the language the user wrote the instruction in (Japanese for a Japanese "
        "instruction, English for an English instruction)"
    )


def _manga_text_tags(options: MangaOptions) -> str:
    """base_tags に必ず含めさせる文字描画系タグの説明。"""
    if not options.dialogue and not options.sound_effects:
        return '"border"'
    if options.text_language == "ja":
        lang_tag = '"japanese text"'
    elif options.text_language == "en":
        lang_tag = '"english text"'
    else:
        lang_tag = (
            '"english text" or "japanese text" (whichever matches the language of '
            "the rendered text)"
        )
    tags = [lang_tag, '"text"']
    if options.dialogue:
        tags.append('"speech bubble"')
    tags.append('"border"')
    return ", ".join(tags)


def build_manga_system_prompt(
    *,
    options: MangaOptions,
    character_mode: bool,
    max_characters: int,
) -> str:
    """漫画モードの system プロンプト本体（成人向けルール・メモリ節は呼び出し側で付与）。

    拡張モード（日本語／タグ）には依存しない。引用符内のセリフ・効果音以外は常に英語。
    """
    if options.panel_count <= PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO:
        panel_count_rule = (
            "Decide how many comic panels (between 2 and 4) best fit the user's "
            "instruction, then describe each panel."
        )
    else:
        count = min(options.panel_count, PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX)
        plural = "s" if count != 1 else ""
        panel_count_rule = f"Describe exactly {count} comic panel{plural}."
    direction = (
        options.reading_direction
        if options.reading_direction
        in (
            "rtl",
            "ltr",
        )
        else "rtl"
    )
    layout_rule = MANGA_LAYOUT_RULES.get(options.layout, MANGA_LAYOUT_RULES["auto"])[
        direction
    ]

    speech_target = (
        "the speaking character's character_prompts item, naming the panel when "
        "the character speaks in more than one panel"
        if character_mode
        else "panel_description, right after the panel where it is spoken"
    )
    if character_mode:
        character_rule = (
            f"Return between 1 and {max_characters} items, exactly one per distinct "
            "character on the page (not one per panel). Each item must contain only "
            "that character's own identity, face, hair, eyes, body, clothing, "
            "expression, pose, and action as concise comma-separated English "
            "Danbooru-style tags, followed by that character's speech bubble "
            "sentence(s) when dialogue is enabled. Do not put background, camera, "
            "lighting, page-level tags, or another character's traits in a "
            "character prompt."
        )
    else:
        character_rule = (
            "Return an empty list []. Describe every character's appearance (and "
            "speech bubbles, when enabled) inside panel_description instead."
        )

    text_language = _manga_text_language_phrase(options.text_language)
    example_key = "ja" if options.text_language == "ja" else "en"
    if options.dialogue:
        dialogue_rule = (
            "Speech: write every spoken line as an English sentence like: "
            f'{MANGA_SPEECH_EXAMPLES[example_key]} (use "thought cloud" instead '
            'of "speech bubble" for unspoken thoughts). Put each line in '
            f"{speech_target}. Only the text inside the quotes is rendered: it must "
            f"be in {text_language}, short (at most 12 words or 20 Japanese "
            "characters per bubble), and written exactly as it should appear in "
            "the image."
        )
    else:
        dialogue_rule = (
            "Do not add any speech bubbles, thought clouds, captions, or written "
            "dialogue."
        )
    if options.sound_effects:
        sfx_rule = (
            "Sound effects: you may add at most one short onomatopoeia per panel "
            "when it fits the action, written as an English sentence like: "
            f"{MANGA_SFX_EXAMPLES[example_key]}. The quoted sound-effect text must "
            f"be in {text_language}."
        )
    else:
        sfx_rule = "Do not add sound effects or onomatopoeia text."

    transformation_rule = (
        " and make that character's character_prompts item describe the final stage"
        if character_mode
        else ""
    )

    return MANGA_SYSTEM_PROMPT_TEMPLATE.format(
        text_tags=_manga_text_tags(options),
        transformation_rule=transformation_rule,
        panel_count_rule=panel_count_rule,
        panel_example=MANGA_PANEL_EXAMPLES[direction],
        reading_rule=MANGA_READING_RULES[direction],
        layout_rule=layout_rule,
        character_rule=character_rule,
        dialogue_rule=dialogue_rule,
        sfx_rule=sfx_rule,
    )


# ---------------------------------------------------------------------------
# ネガティブプロンプト拡張
# ---------------------------------------------------------------------------

NEGATIVE_SYSTEM_PROMPT_TAGS = """You are a NovelAI image generation prompt expert.
Convert the user's Japanese or English description of what to avoid into one negative prompt (undesired content) for NovelAI image generation.

Requirements:
- Output only concise comma-separated English Danbooru-style tags describing elements that must NOT appear. Do not output JSON, Markdown, explanations, labels, or prose.
- Cover every element the user asked to avoid: unwanted objects, clothing, body features, poses, compositions, styles, text, and artifacts.
- Keep every tag from the current negative prompt unless the instruction explicitly removes it.
- Never include tags that describe the desired image; list only undesired content.
- Do not add generic quality tags such as lowres or bad anatomy unless the user asks for them."""

NEGATIVE_SYSTEM_PROMPT_JA = """You are a NovelAI image generation prompt expert.
Convert the user's Japanese or English description of what to avoid into one negative prompt (undesired content) for NovelAI Diffusion V5, written as natural Japanese prose.

Requirements:
- Output only a short natural Japanese description, one paragraph under 200 characters, of the elements that must NOT appear. Do not output JSON, Markdown, explanations, labels, or quotation marks. A few English Danbooru-style tags may be mixed in.
- Cover every element the user asked to avoid: unwanted objects, clothing, body features, poses, compositions, styles, text, and artifacts.
- Keep every element of the current negative prompt unless the instruction explicitly removes it.
- Never describe the desired image; describe only undesired content.
- Do not add generic quality phrases (low resolution, bad anatomy, etc.) unless the user asks for them."""

# ---------------------------------------------------------------------------
# メモリに基づくキャラクター提案
# ---------------------------------------------------------------------------

SUGGEST_CHARACTERS_SYSTEM_PROMPT_TEMPLATE = """You are a NovelAI image generation prompt expert for TSF and outfit-change scenarios.
Based on the user's preference memory given below, propose {count} favorite character designs the user is likely to enjoy generating.

Requirements:
- Output JSON only with this exact shape: {{"suggestions":[{{"title":"...","prompt":"..."}}]}}. Do not output Markdown, explanations, or prose outside the JSON.
- Return exactly {count} suggestions, each clearly different from the others.
- title: a short Japanese label (under 20 characters) that identifies the character concept.
- prompt: a NovelAI character prompt containing only that character's identity, face, hair, eyes, body, clothing, expression, and pose, written as {style_rule}. Do not include background, camera, lighting, or quality tags.
- Begin every prompt with an explicit gender and count token {gender_example} so the gender is never ambiguous.
- Ground every suggestion in the preferences stated in the memory; do not contradict it."""

SUGGEST_USER_PROMPT = "Propose the character prompts now."

# ---------------------------------------------------------------------------
# 共通ルール（移植元の原文）
# ---------------------------------------------------------------------------

SAFE_CONTENT_RULE = (
    "\n- Adult or explicit tags are disabled. Do not add nudity, explicit sexual "
    "activity, or the nsfw tag."
)

ADULT_CONTENT_RULE = (
    "\n- Adult content tags are allowed only when the user's instruction requests "
    "adult content.\n- When the requested final image is adult or explicit, include "
    "the nsfw tag and appropriate concrete visual tags. Do not add adult content to "
    "an otherwise non-adult request."
)

POSITIVE_CLOSING_SINGLE = (
    "Create the complete replacement positive prompt. Preserve every current "
    "element that the instruction does not explicitly change."
)
POSITIVE_CLOSING_CHARACTER = (
    "Create separate base_prompt and character_prompts JSON for the final image. "
    "Preserve every current element that the instruction does not explicitly change."
)
NEGATIVE_CLOSING = (
    "Create the complete replacement negative prompt. Keep every current element "
    "that the instruction does not explicitly remove."
)


def _content_rule(nsfw: bool) -> str:
    return ADULT_CONTENT_RULE if nsfw else SAFE_CONTENT_RULE


# ---------------------------------------------------------------------------
# ビルダー
# ---------------------------------------------------------------------------


def build_positive_system_prompt(
    *,
    mode: ExpandMode,
    character_mode: bool,
    max_characters: int,
    nsfw: bool,
    memory_text: str = "",
    language: str = "ja",
    manga: MangaOptions | None = None,
) -> str:
    """正プロンプト拡張の system プロンプトを組み立てる。

    構成は移植元と同じく「本体 → 成人向けルール → メモリ節（最優先指示）」。
    manga を渡すと漫画モード（コマ割り・吹き出し）の本体に差し替える。
    """
    if manga is not None:
        # 漫画モードは拡張モードに依存しない（引用符内以外は常に英語）
        base = build_manga_system_prompt(
            options=manga,
            character_mode=character_mode,
            max_characters=max_characters,
        )
    elif mode == "japanese":
        base = (
            CHARACTER_SYSTEM_PROMPT_JA_TEMPLATE.format(max_characters=max_characters)
            if character_mode
            else BASE_SYSTEM_PROMPT_JA
        )
    else:
        base = (
            CHARACTER_SYSTEM_PROMPT_TAGS_TEMPLATE.format(max_characters=max_characters)
            if character_mode
            else BASE_SYSTEM_PROMPT_TAGS
        )
    return (
        base
        + _content_rule(nsfw)
        + build_memory_priority_instruction(memory_text or "", language)
    )


def build_positive_user_prompt(
    *,
    instruction: str,
    current_prompt: str | None = None,
    current_character_prompts: Sequence[str] | None = None,
    character_mode: bool = False,
    context_description: str | None = None,
    manga: bool = False,
) -> str:
    """正プロンプト拡張の user プロンプトを組み立てる（移植元の形式を踏襲）。"""
    parts = [
        "Current positive prompt:\n"
        + ((current_prompt or "").strip() or "None (new prompt)")
    ]
    if character_mode and current_character_prompts:
        filled = [
            item.strip() for item in current_character_prompts if item and item.strip()
        ]
        lines = [f"{index}. {item}" for index, item in enumerate(filled, start=1)]
        if lines:
            parts.append("Current character prompts:\n" + "\n".join(lines))
    if context_description and context_description.strip():
        parts.append(
            "Current image description (reference only):\n"
            + context_description.strip()
        )
    parts.append("User instruction:\n" + instruction.strip())
    if manga:
        parts.append(POSITIVE_CLOSING_MANGA)
    else:
        parts.append(
            POSITIVE_CLOSING_CHARACTER if character_mode else POSITIVE_CLOSING_SINGLE
        )
    return "\n\n".join(parts)


def build_negative_system_prompt(
    *,
    mode: ExpandMode,
    memory_text: str = "",
    language: str = "ja",
) -> str:
    base = (
        NEGATIVE_SYSTEM_PROMPT_JA if mode == "japanese" else NEGATIVE_SYSTEM_PROMPT_TAGS
    )
    return base + build_memory_priority_instruction(memory_text or "", language)


def build_negative_user_prompt(
    *,
    instruction: str,
    current_negative: str | None = None,
) -> str:
    return "\n\n".join(
        [
            "Current negative prompt:\n" + ((current_negative or "").strip() or "None"),
            "What the user wants to avoid:\n" + instruction.strip(),
            NEGATIVE_CLOSING,
        ]
    )


def build_suggest_characters_prompts(
    *,
    memory_text: str,
    count: int,
    mode: ExpandMode,
    nsfw: bool,
    language: str = "ja",
) -> tuple[str, str]:
    """キャラクター提案の (system, user) プロンプトを返す。"""
    if mode == "japanese":
        style_rule = (
            "natural Japanese prose of 1-3 sentences that states the gender explicitly"
        )
        gender_example = (
            '(for example "1girl" / "1boy", or 「一人の女性」「一人の男性」)'
        )
    else:
        style_rule = "concise comma-separated English Danbooru-style tags"
        gender_example = '(for example "1girl" or "1boy")'
    system = (
        SUGGEST_CHARACTERS_SYSTEM_PROMPT_TEMPLATE.format(
            count=count, style_rule=style_rule, gender_example=gender_example
        )
        + _content_rule(nsfw)
        + build_memory_priority_instruction(memory_text or "", language)
    )
    return system, SUGGEST_USER_PROMPT


# ---------------------------------------------------------------------------
# サニタイズ / 解析
# ---------------------------------------------------------------------------

_LABEL_PATTERNS = (
    re.compile(r"^positive prompt\s*[:：]\s*", re.IGNORECASE),
    re.compile(r"^negative prompt\s*[:：]\s*", re.IGNORECASE),
    re.compile(r"^prompt\s*[:：]\s*", re.IGNORECASE),
    re.compile(r"^(?:正|ネガティブ)?プロンプト\s*[:：]\s*"),
)
_CHARACTER_LABEL_PATTERN = re.compile(
    r"^character(?: prompt)?\s*[:：]\s*", re.IGNORECASE
)


def _unwrap_quoted(text: str) -> str:
    """全体が JSON 文字列（"..."）や鉤括弧で包まれていれば中身を取り出す。"""
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] == '"' and stripped[-1] == '"':
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
        if isinstance(parsed, str):
            return parsed
        return stripped
    if len(stripped) >= 2 and stripped[0] == "「" and stripped[-1] == "」":
        return stripped[1:-1]
    return stripped


def _strip_labels(text: str) -> str:
    result = text
    for pattern in _LABEL_PATTERNS:
        result = pattern.sub("", result, count=1)
    return result.strip()


def _ensure_quality_tags(prompt: str) -> str:
    existing = {part.strip().lower() for part in prompt.split(",")}
    missing = [tag for tag in QUALITY_TAGS if tag not in existing]
    if not missing:
        return prompt
    base = re.sub(r"[,\s]+$", "", prompt)
    if not base:
        return ", ".join(missing)
    return base + ", " + ", ".join(missing)


def sanitize_tag_prompt(raw: str, *, ensure_quality: bool = True) -> str:
    """タグ形式の LLM 出力を 1 行のカンマ区切りに整える（移植元の手順）。"""
    text = _unwrap_quoted(_strip_code_fence(raw or ""))
    text = re.sub(r"\s*\r?\n+\s*", ", ", text)
    text = re.sub(r",(\s*,)+", ",", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = _strip_labels(text.strip())
    text = _CHARACTER_LABEL_PATTERN.sub("", text, count=1).strip()
    text = re.sub(r"^[,\s]+|[,\s]+$", "", text)
    if ensure_quality and text:
        text = _ensure_quality_tags(text)
    return text


def sanitize_prose_prompt(raw: str) -> str:
    """日本語自然文の LLM 出力を 1 段落に整える。句読点は保持する。"""
    text = _unwrap_quoted(_strip_code_fence(raw or ""))
    text = _strip_labels(text)
    text = _CHARACTER_LABEL_PATTERN.sub("", text, count=1)
    return " ".join(text.split()).strip()


def sanitize_by_mode(raw: str, mode: ExpandMode, *, ensure_quality: bool) -> str:
    if mode == "japanese":
        return sanitize_prose_prompt(raw)
    return sanitize_tag_prompt(raw, ensure_quality=ensure_quality)


def _load_json_object(raw: str) -> object:
    text = _strip_code_fence(raw or "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 前後に説明文が混ざった場合は最初の { から最後の } までを試す
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise PromptExpanderOutputError(
        "キャラクタープロンプトのJSONを解析できませんでした。"
    )


def parse_character_json(
    raw: str,
    *,
    max_characters: int,
    mode: ExpandMode,
) -> tuple[str, list[str]]:
    """{"base_prompt","character_prompts"} 形式の出力を解析し整形して返す。

    上限を超えた分は切り詰め、0 件なら PromptExpanderOutputError を送出する。
    """
    data = _load_json_object(raw)
    if not isinstance(data, dict):
        raise PromptExpanderOutputError("キャラクタープロンプトのJSON形式が不正です。")
    base_raw = data.get("base_prompt")
    characters_raw = data.get("character_prompts")
    if not isinstance(base_raw, str) or not isinstance(characters_raw, list):
        raise PromptExpanderOutputError(
            "base_promptまたはcharacter_promptsが不正です。"
        )
    base = sanitize_by_mode(base_raw, mode, ensure_quality=True)
    characters = [
        sanitize_by_mode(item, mode, ensure_quality=False)
        for item in characters_raw
        if isinstance(item, str)
    ]
    characters = [item for item in characters if item]
    if not base or not characters:
        raise PromptExpanderOutputError("空のプロンプトが含まれています。")
    if len(characters) > max_characters:
        characters = characters[:max_characters]
    return base, characters


def parse_manga_json(
    raw: str,
    *,
    max_characters: int,
    character_mode: bool,
) -> tuple[str, list[str] | None]:
    """{"base_tags","panel_description","character_prompts"} 形式の出力を解析する。

    base_tags（タグ）とpanel_description（英語の自然文）を結合して 1 つのベースプロンプト
    にする。品質タグはタグ見出し側に補完し、コマ説明文の後ろには付けない。
    キャラクターモード OFF のときは character_prompts を無視して None を返す。
    """
    data = _load_json_object(raw)
    if not isinstance(data, dict):
        raise PromptExpanderOutputError("漫画プロンプトのJSON形式が不正です。")
    tags_raw = data.get("base_tags")
    desc_raw = data.get("panel_description")
    characters_raw = data.get("character_prompts")
    if not isinstance(tags_raw, str) or not isinstance(desc_raw, str):
        raise PromptExpanderOutputError("base_tagsまたはpanel_descriptionが不正です。")
    tags = sanitize_tag_prompt(tags_raw, ensure_quality=True)
    description = sanitize_prose_prompt(desc_raw)
    if not description:
        raise PromptExpanderOutputError("コマ説明が空です。")
    base = f"{tags}, {description}" if tags else description
    if not character_mode:
        return base, None
    if not isinstance(characters_raw, list):
        raise PromptExpanderOutputError("character_promptsが不正です。")
    characters = [
        sanitize_tag_prompt(item, ensure_quality=False)
        for item in characters_raw
        if isinstance(item, str)
    ]
    characters = [item for item in characters if item]
    if not characters:
        raise PromptExpanderOutputError("キャラクタープロンプトが空です。")
    if len(characters) > max_characters:
        characters = characters[:max_characters]
    return base, characters


def parse_suggestions_json(
    raw: str,
    *,
    count: int,
    mode: ExpandMode,
) -> list[dict[str, str]]:
    """{"suggestions":[{"title","prompt"}]} 形式の出力を解析して返す。"""
    text = _strip_code_fence(raw or "")
    data: object
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = _load_json_object(text)
    if isinstance(data, dict):
        items = data.get("suggestions")
    else:
        items = data
    if not isinstance(items, list):
        raise PromptExpanderOutputError("提案のJSON形式が不正です。")
    suggestions: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        prompt_raw = item.get("prompt")
        if not isinstance(prompt_raw, str):
            continue
        prompt = sanitize_by_mode(prompt_raw, mode, ensure_quality=False)
        if not prompt:
            continue
        title_raw = item.get("title")
        title = " ".join(str(title_raw).split())[:40] if title_raw else ""
        suggestions.append({"title": title, "prompt": prompt})
        if len(suggestions) >= count:
            break
    if not suggestions:
        raise PromptExpanderOutputError("提案を取得できませんでした。")
    return suggestions
