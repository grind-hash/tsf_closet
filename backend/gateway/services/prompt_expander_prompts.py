"""Prompt Expander のプロンプト定義とサニタイズ。

Chrome 拡張「TSF Closet Prompt Expander for NovelAI」のプロンプトを移植し、
NovelAI Diffusion V5 向けの日本語自然文モード、ネガティブプロンプト拡張、
メモリに基づくキャラクター提案を追加したもの。
"""

from __future__ import annotations

import json
import re
from typing import Literal, Sequence

from .llm_service import _strip_code_fence
from .memory_prompts import build_memory_priority_instruction

ExpandMode = Literal["japanese", "tags"]

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
) -> str:
    """正プロンプト拡張の system プロンプトを組み立てる。

    構成は移植元と同じく「本体 → 成人向けルール → メモリ節（最優先指示）」。
    """
    if mode == "japanese":
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
