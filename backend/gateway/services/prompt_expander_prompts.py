"""Prompt Expander のプロンプト定義とサニタイズ。

Chrome 拡張「TSF Closet Prompt Expander for NovelAI」のプロンプトを移植し、
NovelAI Diffusion V5 向けの日本語自然文モード、ネガティブプロンプト拡張、
メモリに基づくキャラクター提案を追加したもの。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from ..consts.prompt_expander import (
    PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO,
    PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX,
    PROMPT_EXPANDER_STORY_CHARACTER_MAX_LEN,
    PROMPT_EXPANDER_STORY_PROMPT_MAX_LEN,
    PROMPT_EXPANDER_STORY_SCRIPT_MAX_LEN,
    PROMPT_EXPANDER_STORY_SYNOPSIS_MAX_LEN,
)
from .llm_json import strip_code_fence
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
    # 指示文に【】が無くても、場面転換・時間経過で LLM がナレーション枠を足してよいか
    narration: bool = False


@dataclass(frozen=True)
class CastMember:
    """名前を付けた精密参照から作る登場人物。外見タグは空でもよい。"""

    name: str
    appearance_tags: str = ""


def normalize_cast_name(name: str) -> str:
    """キャスト名の照合キー（前後空白と大文字小文字を無視する）。"""
    return " ".join(str(name or "").split()).casefold()


def dedupe_cast(cast: Sequence[CastMember]) -> list[CastMember]:
    """空の名前を除き、同じ名前は先頭だけ残す。"""
    result: list[CastMember] = []
    seen: set[str] = set()
    for member in cast:
        key = normalize_cast_name(member.name)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(
            CastMember(
                name=" ".join(member.name.split()),
                appearance_tags=" ".join(str(member.appearance_tags or "").split()),
            )
        )
    return result


# キャストがあるとき、キャラ枠の出力を名前付きの object に切り替える（Python 側で
# 名前から登場人物を特定し、抜けた外見タグを補うため）
CHARACTER_ITEMS_PLAIN_SHAPE = '"character_prompts":["..."]'
CHARACTER_ITEMS_NAMED_SHAPE = '"character_prompts":[{"name":"...","prompt":"..."}]'

CAST_CHARACTER_RULE = (
    "\n- Cast: the user message lists named characters whose look is fixed by "
    "reference images, each with a token such as [[1]]. Each character_prompts "
    'item is an object: "name" is the cast name when that item shows the cast '
    "member looking as described in the cast list, otherwise an empty string "
    '"" (for example another character, or the cast member in a different form '
    'such as before a transformation); "prompt" is the character prompt written '
    "by the rules above. For a cast member, include their appearance from the "
    "cast list (hair color, hair length, hairstyle, eye color, and clothing with "
    "colors) unless the instruction explicitly changes it."
    "\n- The image model cannot read names. Never write a cast name anywhere "
    "except inside quoted dialogue that itself mentions the name. Wherever "
    "base_prompt or panel_description refers to a cast member, write their token "
    "exactly as given (for example: [[1]] waves at [[2]]); the server replaces "
    "each token with a short visual description. Describe characters outside the "
    "cast by appearance."
)

# キャストの目印。LLM にはこの形でコマ説明に書かせ、サーバーが見た目の言い回しに置き換える
_CAST_TOKEN_PATTERN = re.compile(r"\[\[\s*(\d{1,2})\s*\]\]")


def cast_token(index: int) -> str:
    """キャストの 1 始まりの番号から目印（[[1]] など）を作る。"""
    return f"[[{index}]]"


def replace_cast_tokens(text: str, descriptions: Sequence[str]) -> str:
    """目印 [[n]] を n 番目のキャストの見た目の言い回しに置き換える。

    範囲外の番号は消す（画像モデルに目印の文字列を渡さないため）。
    """
    if not text or "[[" not in text:
        return text

    def _sub(match: re.Match[str]) -> str:
        index = int(match.group(1)) - 1
        return descriptions[index] if 0 <= index < len(descriptions) else ""

    replaced = _CAST_TOKEN_PATTERN.sub(_sub, text)
    return re.sub(r"[ \t]{2,}", " ", replaced)


MANGA_SCRIPT_CAST_RULE = (
    "\n- A cast list is given with the synopsis. Use those names for the "
    "characters, including as the speaker name right before 「...」 or 『...』, "
    "and keep each cast member's look as listed unless the synopsis changes it."
)


_QUOTE_OPEN_CLOSE = {'"': '"', "“": "”", "「": "」", "『": "』"}


def strip_quoted_segments(prompt: str) -> str:
    """カンマ区切りのプロンプトから、引用符を含む要素（台詞の吹き出し）を除く。

    引用符の中のカンマでは区切らない。キャストのいる漫画でキャラ枠に台詞が
    残ると、そのキャラが出る全コマに同じ吹き出しが描かれるための安全策。
    """
    tokens: list[str] = []
    current: list[str] = []
    closing: str | None = None
    for char in prompt or "":
        if closing is not None:
            current.append(char)
            if char == closing:
                closing = None
            continue
        if char in _QUOTE_OPEN_CLOSE:
            closing = _QUOTE_OPEN_CLOSE[char]
            current.append(char)
            continue
        if char == ",":
            tokens.append("".join(current))
            current = []
            continue
        current.append(char)
    tokens.append("".join(current))
    kept = [
        token.strip()
        for token in tokens
        if token.strip() and not any(q in token for q in '"“”「」『』')
    ]
    return ", ".join(kept)


def build_cast_block(
    cast: Sequence[CastMember], *, descriptions: Sequence[str] | None = None
) -> str:
    """登場人物の一覧を user プロンプト用の文にする。空なら ""。

    descriptions（見た目の言い回し）を渡すと、プロンプト化用に目印 [[n]] と
    置き換え後の言い回しも並べる。ネーム下書きでは名前だけで足りるので渡さない。
    """
    members = dedupe_cast(cast)
    if not members:
        return ""
    appearance = [m.appearance_tags or "appearance not specified" for m in members]
    if descriptions is None:
        lines = [f"- {m.name}: {a}" for m, a in zip(members, appearance, strict=True)]
        return (
            "Cast (named characters fixed by reference images; name: appearance):\n"
            + "\n".join(lines)
        )
    lines = [
        f"- {cast_token(index)} {m.name} (drawn as: "
        f"{descriptions[index - 1] if index <= len(descriptions) else 'a character'}): {a}"
        for index, (m, a) in enumerate(zip(members, appearance, strict=True), start=1)
    ]
    return (
        "Cast (named characters fixed by reference images; token name (drawn as: "
        "visual description): appearance):\n" + "\n".join(lines)
    )


# ---------------------------------------------------------------------------
# 漫画モードの記法（指示文中の括弧でセリフ・モノローグ・ナレーション・効果音を指定する）
#   「セリフ」→吹き出し / 『モノローグ』→思考の雲 / 【ナレーション】→ナレーション枠 /
#   《効果音》→擬音 / 行頭の①②③ または "1:" →コマ番号。空の括弧は内容を LLM に任せる。
# ---------------------------------------------------------------------------

MangaTextKind = Literal["speech", "monologue", "narration", "sfx"]


@dataclass(frozen=True)
class MangaNotationText:
    """指示文で括弧により指定された文字要素。text が空なら内容は LLM に任せる。"""

    kind: MangaTextKind
    text: str
    # 直近の行頭コマ番号（無ければ None）
    panel: int | None = None


@dataclass(frozen=True)
class MangaNotation:
    texts: tuple[MangaNotationText, ...] = ()
    panel_numbers: tuple[int, ...] = ()

    @property
    def has_texts(self) -> bool:
        return bool(self.texts)

    @property
    def max_panel(self) -> int | None:
        return max(self.panel_numbers) if self.panel_numbers else None

    def has_kind(self, kind: MangaTextKind) -> bool:
        return any(item.kind == kind for item in self.texts)

    def required_texts(self) -> list[MangaNotationText]:
        """原文のまま描くべき（空でない）文字要素。"""
        return [item for item in self.texts if item.text]


_NOTATION_KINDS: tuple[MangaTextKind, ...] = ("speech", "monologue", "narration", "sfx")
_NOTATION_PATTERN = re.compile(
    r"「([^「」]*)」|『([^『』]*)』|【([^【】]*)】|《([^《》]*)》"
)
# ①〜⑳、または "1:" "1." "1)" 形式（"3:00" のような時刻には一致させない）
_PANEL_PREFIX_PATTERN = re.compile(
    r"^\s*(?:([\u2460-\u2473])|([1-9])\s*[:：.．)）](?!\d))"
)


def _panel_number(match: re.Match[str]) -> int:
    circled, digit = match.group(1), match.group(2)
    if circled:
        return ord(circled) - 0x2460 + 1
    return int(digit)


def extract_manga_notation(instruction: str) -> MangaNotation:
    """指示文から記法（括弧の種類とコマ番号）を抜き出す。"""
    texts: list[MangaNotationText] = []
    panels: list[int] = []
    current: int | None = None
    for line in (instruction or "").splitlines():
        prefix = _PANEL_PREFIX_PATTERN.match(line)
        if prefix:
            current = _panel_number(prefix)
            if current not in panels:
                panels.append(current)
        for match in _NOTATION_PATTERN.finditer(line):
            for index, kind in enumerate(_NOTATION_KINDS):
                value = match.group(index + 1)
                if value is not None:
                    texts.append(
                        MangaNotationText(kind=kind, text=value.strip(), panel=current)
                    )
                    break
    return MangaNotation(texts=tuple(texts), panel_numbers=tuple(panels))


_NOTATION_KIND_LABELS: dict[MangaTextKind, str] = {
    "speech": "speech bubble",
    "monologue": "thought cloud",
    "narration": "narration box",
    "sfx": "sound effect",
}

# 出力から欠けた文字要素を補うときの定型文（引用符内だけが描画される）
_NOTATION_SENTENCES: dict[MangaTextKind, str] = {
    "speech": 'There\'s a speech bubble that says "{text}".',
    "monologue": 'There\'s a thought cloud that says "{text}".',
    "narration": 'There\'s a narration box at the top of the panel that reads "{text}".',
    "sfx": 'There\'s also a "{text}" visible in the panel.',
}


def ensure_manga_notation_texts(
    base: str, characters: Sequence[str] | None, notation: MangaNotation
) -> str:
    """記法で指定された文字が出力に無ければ、定型の英文でベースプロンプト末尾に補う。

    LLM がセリフを言い換えたり落としたりしても、ユーザーの原文が必ず描かれるようにする。
    """
    haystack = [base, *(characters or [])]
    missing = [
        item
        for item in notation.required_texts()
        if not any(item.text in text for text in haystack)
    ]
    if not missing:
        return base
    sentences: list[str] = []
    for item in missing:
        sentence = _NOTATION_SENTENCES[item.kind].format(text=item.text)
        if item.panel:
            sentence = f"In panel {item.panel}, {sentence[0].lower()}{sentence[1:]}"
        sentences.append(sentence)
    return f"{base.rstrip()} {' '.join(sentences)}"


def build_manga_notation_block(notation: MangaNotation) -> str:
    """user プロンプトに付ける「指示文で指定された文字」の一覧。"""
    if not notation.has_texts:
        return ""
    lines = []
    for index, item in enumerate(notation.texts, start=1):
        label = _NOTATION_KIND_LABELS[item.kind]
        where = f"panel {item.panel}, " if item.panel else ""
        content = (
            f'"{item.text}"'
            if item.text
            else "(no text given: write suitable content yourself)"
        )
        lines.append(f"{index}. {where}{label}: {content}")
    return (
        "Marked text in the instruction (render verbatim, in this order):\n"
        + "\n".join(lines)
    )


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

# 日本語の空似言葉（false friend）に関する語彙注意。タグモード・漫画モードの本体と、
# 着せ替えのタグ生成（llm_service.generate_novelai_image_prompt）に追記する。
# 「ショーツ」は女性下着（panties）であり、英語の shorts（短パン）ではない。
# 逆に「ハーフパンツ」「ズボン」は外衣で、下着の panties ではない。
JAPANESE_TAG_GLOSSARY_RULE = (
    '\n- Japanese vocabulary note: the Japanese word ショーツ ("shorts") '
    'means women\'s underwear; render it as "panties", never as "shorts". Use the tag '
    '"shorts" only for outerwear explicitly described as such (denim shorts, gym shorts, etc.). '
    "Conversely, ズボン and fashion terms ending in パンツ (ハーフパンツ, ショートパンツ, "
    "短パン, ワイドパンツ, スキニーパンツ, etc.) are outerwear bottoms: render them as shorts "
    'or pants (e.g. "shorts", "knee-length shorts", "pants", "wide-leg pants"), never as '
    "underwear."
)

# 背景透過モード（Prompt Expander の「画像の背景を透過」ON）。本体の「背景を保持する」規則より
# 優先させ、背景・情景を一切書かせない。背景タグ自体は生成時にサーバーが足すので LLM には書かせない。
TRANSPARENT_BACKGROUND_RULE_TAGS = (
    "\n- Transparent background mode is ON: the background will be made transparent "
    "after generation. This overrides every rule above about preserving or keeping the "
    "current location or background. Do not output any location, scenery, floor, sky, "
    "furniture, or background tags, and do not put them in base_prompt. Describe only the "
    "subject(s): identity, body, clothing, pose, expression, camera framing, and the "
    'lighting on the figure. Do not add background tags such as "simple background" or '
    '"white background" yourself; the server appends them.'
)
TRANSPARENT_BACKGROUND_RULE_JA = (
    "\n- Transparent background mode is ON: the background will be made transparent "
    "after generation. This overrides every rule above about preserving or keeping the "
    "current location or background. Do not mention any location, scenery, room, floor, "
    "sky, furniture, or surroundings in the prose, and do not put them in base_prompt. "
    "Describe only the subject(s): identity, body, clothing, pose, expression, camera "
    "framing, and the lighting on the figure. Do not write background wording yourself; "
    "the server appends the background instruction."
)

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
- {notation_rule}
- {dialogue_rule}
- {sfx_rule}
- {narration_rule}
- Everything except the text inside quotation marks must be written in English. Never write the panel description, appearance, or actions in Japanese: the image model renders Japanese prose as caption boxes. Japanese may appear only inside the quotation marks of dialogue, thoughts, narration boxes, and sound effects.
- The only written words that may appear in the image are the quoted dialogue, thoughts, narration boxes, and sound effects allowed above. Do not describe titles, signs, labels, or any other on-screen text.
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
    "ja": 'There\'s a speech bubble next to the girl that says "これ、僕にぴったり…！"',
}
MANGA_SFX_EXAMPLES: dict[str, str] = {
    "en": 'there\'s also a "SLAM" visible on the table',
    "ja": 'there\'s also a "ドン！" visible on the table',
}
MANGA_THOUGHT_EXAMPLES: dict[str, str] = {
    "en": 'There\'s a thought cloud above the girl that says "Is this really me?"',
    # TS 直後の人物は一人称が元のまま（僕）なので、例文もそれに合わせる
    "ja": 'There\'s a thought cloud above the girl that says "これが僕…？"',
}
MANGA_NARRATION_EXAMPLES: dict[str, str] = {
    "en": (
        "There's a narration box at the top of the panel that reads \"Three days "
        'later."'
    ),
    "ja": 'There\'s a narration box at the top of the panel that reads "三日後。"',
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


def _manga_text_tags(
    options: MangaOptions, notation: MangaNotation | None = None
) -> str:
    """base_tags に必ず含めさせる文字描画系タグの説明。

    トグルが OFF でも記法で文字が指定されていれば文字系タグを入れる。
    """
    has_bubbles = options.dialogue or (
        notation is not None
        and (notation.has_kind("speech") or notation.has_kind("monologue"))
    )
    has_text = (
        has_bubbles
        or options.sound_effects
        or options.narration
        or (notation is not None and notation.has_texts)
    )
    if not has_text:
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
    if has_bubbles:
        tags.append('"speech bubble"')
    tags.append('"border"')
    return ", ".join(tags)


def _manga_panel_count_rule(
    options: MangaOptions, notation: MangaNotation | None
) -> str:
    notation_max = notation.max_panel if notation is not None else None
    if options.panel_count <= PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO:
        if notation_max:
            count = min(notation_max, PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX)
            plural = "s" if count != 1 else ""
            return (
                f"Describe exactly {count} comic panel{plural}, following the panel "
                "numbers written in the instruction."
            )
        return (
            "Decide how many comic panels (between 2 and 4) best fit the user's "
            "instruction, then describe each panel."
        )
    count = min(options.panel_count, PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX)
    plural = "s" if count != 1 else ""
    return f"Describe exactly {count} comic panel{plural}."


def _manga_direction(options: MangaOptions) -> MangaReadingDirection:
    return (
        options.reading_direction
        if options.reading_direction in ("rtl", "ltr")
        else "rtl"
    )


# キャストのいる漫画は、コマ説明を LLM に文で書かせず、コマごとの中身を JSON で受けて
# サーバーが組み立てる。画像モデルはコマの中で先に書かれた人物を描き、後の人物を落とし
# やすく、台詞は描かれた人物に付くため、話す人物を先に・台詞を同じ文に・人数を明記する
# 形に揃える（V5 の実生成で、この形なら話者の取り違えが無くなることを確認）。
# キャラ枠はそのキャラが出る全コマに効くので、外見と服だけを入れさせる。
MANGA_CAST_SYSTEM_PROMPT_TEMPLATE = """You are a NovelAI Diffusion V5 image generation prompt expert for TSF and outfit-change scenarios, specialized in multi-panel comic (manga) pages with speech bubbles.
Convert the user's Japanese or English instruction into the content of one comic page. The server writes the final panel description from your JSON, so fill in each field exactly as asked.

Requirements:
- Output JSON only with this exact shape: {{"base_tags":"...","panels":[{{"position":"...","people":[{{"who":"[[1]]","action":"...","says":["..."],"thinks":["..."]}}],"scene":"...","narration":"","sfx":""}}],"character_prompts":[{{"name":"...","prompt":"..."}}]}}. Do not output Markdown, explanations, labels, or prose outside the JSON.
- base_tags: concise comma-separated English Danbooru-style tags for the whole page only: the total number of distinct characters on the page as count tokens (for example "2girls" or "1boy, 1girl"), style and quality tags, and {text_tags}. Do not describe individual panels or characters here.
- panels: {panel_count_rule} One object per panel, in reading order. {reading_rule} "position" is where the panel sits on the page (top right, top left, bottom right, bottom left, rightmost, leftmost, full-width bottom, ...).{layout_rule}
- people: every character visible in that panel. "who" is the cast token exactly as listed (for example [[1]]) for a cast member, or a short English visual description (for example "a waiter in a black apron") for anyone else; never a name. "action" is that person's own action, pose, and expression in this panel as a short English phrase without a subject (for example "standing happily and holding a large cardboard box"). "says" lists that person's spoken lines in this panel and "thinks" lists their unspoken thoughts; leave them empty when the person does not speak.
- scene: the background, props, and camera of that panel as a short English phrase, without people (for example "a bedroom, a cardboard box on the floor, medium shot").
- Inside "action" and "scene", refer to a cast member only by their token (for example "looking up at [[2]]" or "the bedroom of [[1]]"), never by name.
- {notation_rule}
- {dialogue_rule}
- {sfx_rule}
- {narration_rule}
- character_prompts: Return between 1 and {max_characters} items, exactly one per distinct character on the page (not one per panel). Each item is an object: "name" is the cast name when the item shows the cast member looking as described in the cast list, otherwise an empty string "" (for example another character, or the cast member in a different form such as before a transformation); "prompt" contains only the look that stays the same in every panel: identity, face, hair, eyes, body, and clothing as concise comma-separated English Danbooru-style tags. For a cast member, include their appearance from the cast list (hair color, hair length, hairstyle, eye color, and clothing with colors) unless the instruction explicitly changes it. A character prompt applies to every panel the character appears in, so never put actions, poses, expressions, held items, or speech in it.
- Everything except the text inside "says", "thinks", "narration", and "sfx" must be written in English. Never write names: the image model cannot read them.
- The only written words that may appear in the image are the dialogue, thoughts, narration boxes, and sound effects in those fields. Do not describe titles, signs, labels, or any other on-screen text.
- The same character must keep identical identity, hair, eyes, body, and clothing across all panels unless the story explicitly changes them. If a character's appearance changes between panels (for example a TSF transformation), describe each stage in that person's "action" and make the character_prompts item describe the final stage.
- Apply every explicit change requested by the user, including TSF/body transformation, clothing, appearance, pose, expression, camera, lighting, and scene changes.
- Prefer specific visual wording over abstract or emotional wording."""


MANGA_CAST_READING_RULES: dict[str, str] = {
    "rtl": (
        "Reading order is Japanese manga style: right to left, then top to bottom; "
        "the first panel is at the top right."
    ),
    "ltr": (
        "Reading order is Western style: left to right, then top to bottom; the "
        'first panel is at the top left. Include the tag "left-to-right manga" in '
        "base_tags."
    ),
}
MANGA_CAST_LAYOUT_HINTS: dict[str, str] = {
    "auto": "",
    "vertical": (
        " The panels are stacked vertically, so use positions such as top, middle, "
        "and bottom."
    ),
    "horizontal": (
        " The panels sit side by side in a single row, so use positions such as "
        "rightmost, middle, and leftmost."
    ),
    "grid": (
        " The panels form a grid of two columns, so use positions such as top "
        "right, top left, bottom right, and bottom left."
    ),
}
# 組み立てたコマ説明の冒頭に置くコマ割りの説明
MANGA_CAST_LAYOUT_STATEMENTS: dict[str, dict[str, str]] = {
    "auto": {"rtl": "", "ltr": ""},
    "vertical": {
        "rtl": "The panels are stacked vertically from top to bottom.",
        "ltr": "The panels are stacked vertically from top to bottom.",
    },
    "horizontal": {
        "rtl": "The panels are arranged side by side in a single row.",
        "ltr": "The panels are arranged side by side in a single row.",
    },
    "grid": {
        "rtl": "The panels are arranged in a grid of two columns.",
        "ltr": "The panels are arranged in a grid of two columns.",
    },
}


def build_manga_cast_system_prompt(
    *,
    options: MangaOptions,
    max_characters: int,
    notation: MangaNotation | None = None,
) -> str:
    """キャストのいる漫画の system プロンプト本体（コマごとの中身を JSON で返させる）。"""
    direction = _manga_direction(options)
    text_language = _manga_text_language_phrase(options.text_language)
    corner = "top right" if direction == "rtl" else "top left"
    notation_rule = (
        "Notation in the user instruction: 「...」 is a spoken line, 『...』 is an "
        "unspoken thought, 【...】 is a narration box (usually in the "
        f"{corner} corner of the panel), 《...》 is a sound effect, and a line "
        'starting with ①②③ or "1:" belongs to that panel number. A name written '
        "right before 「...」 or 『...』 is the speaker: put the line in that "
        'person\'s "says" or "thinks" in the panel it belongs to, and make '
        "sure that person is listed in that panel's people. Copy every marked "
        "text verbatim (do not translate, paraphrase, shorten, or drop it). Empty "
        "brackets such as 「」 or 【】 mean: place that kind of text there and "
        f"write suitable content yourself in {text_language}."
    )
    if options.dialogue:
        dialogue_rule = (
            "Lines in says and thinks are rendered as written: they must be in "
            f"{text_language}, short (at most 12 words or 20 Japanese characters "
            "per bubble). Give most panels a short line that carries the story."
        )
    else:
        dialogue_rule = (
            "Leave says and thinks empty except for the lines marked with 「...」 "
            "or 『...』 in the instruction."
        )
    if options.sound_effects:
        sfx_rule = (
            "sfx: at most one short onomatopoeia per panel when it fits the action "
            f"(in {text_language}), otherwise an empty string."
        )
    else:
        sfx_rule = (
            "sfx: only sound effects marked with 《...》 in the instruction, "
            "otherwise an empty string."
        )
    if options.narration:
        narration_rule = (
            "narration: besides the ones marked with 【...】, at most one short "
            "narration box per panel where a scene change, time skip, or story "
            f"voice helps (in {text_language}, at most 20 Japanese characters or "
            "12 words), otherwise an empty string."
        )
    else:
        narration_rule = (
            "narration: only text marked with 【...】 in the instruction, otherwise "
            "an empty string. Do not invent narration boxes or captions."
        )
    return MANGA_CAST_SYSTEM_PROMPT_TEMPLATE.format(
        text_tags=_manga_text_tags(options, notation),
        panel_count_rule=_manga_panel_count_rule(options, notation),
        reading_rule=MANGA_CAST_READING_RULES[direction],
        layout_rule=MANGA_CAST_LAYOUT_HINTS.get(options.layout, ""),
        max_characters=max_characters,
        notation_rule=notation_rule,
        dialogue_rule=dialogue_rule,
        sfx_rule=sfx_rule,
        narration_rule=narration_rule,
    )


def build_manga_system_prompt(
    *,
    options: MangaOptions,
    character_mode: bool,
    max_characters: int,
    notation: MangaNotation | None = None,
    with_cast: bool = False,
) -> str:
    """漫画モードの system プロンプト本体（成人向けルール・メモリ節は呼び出し側で付与）。

    拡張モード（日本語／タグ）には依存しない。引用符内のセリフ・効果音以外は常に英語。
    notation（指示文の記法）があれば、コマ数のおまかせは記法のコマ番号に合わせる。
    """
    if character_mode and with_cast:
        return build_manga_cast_system_prompt(
            options=options, max_characters=max_characters, notation=notation
        )
    panel_count_rule = _manga_panel_count_rule(options, notation)
    direction = _manga_direction(options)
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
    corner = "top right" if direction == "rtl" else "top left"
    notation_rule = (
        "Notation in the user instruction: 「...」 is a spoken line (speech bubble), "
        "『...』 is an unspoken thought (thought cloud), 【...】 is narration (a "
        "rectangular narration box, not a bubble, usually in the "
        f"{corner} corner of the panel), 《...》 is a sound effect, and a line "
        'starting with ①②③ or "1:" belongs to that panel number. A name written '
        "right before 「...」 or 『...』 is the speaker. Render every marked text "
        "verbatim inside the quotation marks of your English sentence (do not "
        "translate, paraphrase, shorten, or drop it) in the panel it belongs to. "
        "Empty brackets such as 「」 or 【】 mean: place that kind of text there and "
        f"write suitable content yourself in {text_language}."
    )
    if options.dialogue:
        dialogue_rule = (
            "Speech: write every spoken line as an English sentence like: "
            f"{MANGA_SPEECH_EXAMPLES[example_key]} and every unspoken thought like: "
            f"{MANGA_THOUGHT_EXAMPLES[example_key]}. Put each line in "
            f"{speech_target}. Only the text inside the quotes is rendered: it must "
            f"be in {text_language}, short (at most 12 words or 20 Japanese "
            "characters per bubble), and written exactly as it should appear in "
            "the image."
        )
    else:
        dialogue_rule = (
            "Do not add any speech bubbles, thought clouds, or written dialogue "
            "beyond the lines marked with 「...」 or 『...』 in the instruction."
        )
    if options.sound_effects:
        sfx_rule = (
            "Sound effects: you may add at most one short onomatopoeia per panel "
            "when it fits the action, written as an English sentence like: "
            f"{MANGA_SFX_EXAMPLES[example_key]}. The quoted sound-effect text must "
            f"be in {text_language}."
        )
    else:
        sfx_rule = (
            "Do not add sound effects or onomatopoeia text beyond the ones marked "
            "with 《...》 in the instruction."
        )
    if options.narration:
        narration_rule = (
            "Narration: besides the ones marked with 【...】, you may add at most "
            "one narration box per panel where a scene change, time skip, or story "
            "voice helps, written as an English sentence like: "
            f"{MANGA_NARRATION_EXAMPLES[example_key]}. Put narration boxes in "
            "panel_description (never in character_prompts). The quoted narration "
            f"text must be in {text_language} and short (at most 20 Japanese "
            "characters or 12 words)."
        )
    else:
        narration_rule = (
            "Narration: add a narration box only where the instruction marks one "
            "with 【...】, written as an English sentence like: "
            f"{MANGA_NARRATION_EXAMPLES[example_key]}, in panel_description. Do not "
            "invent additional narration boxes or captions."
        )

    transformation_rule = (
        " and make that character's character_prompts item describe the final stage"
        if character_mode
        else ""
    )

    return MANGA_SYSTEM_PROMPT_TEMPLATE.format(
        text_tags=_manga_text_tags(options, notation),
        transformation_rule=transformation_rule,
        panel_count_rule=panel_count_rule,
        panel_example=MANGA_PANEL_EXAMPLES[direction],
        reading_rule=MANGA_READING_RULES[direction],
        layout_rule=layout_rule,
        character_rule=character_rule,
        notation_rule=notation_rule,
        dialogue_rule=dialogue_rule,
        sfx_rule=sfx_rule,
        narration_rule=narration_rule,
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
# これまでの話（漫画で続きのページを作るときに渡す前のページ）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StoryPage:
    """これまでの話の 1 ページ。前に生成したエントリの保存内容から作る。

    synopsis はページのあらすじ（ネームから作ったページは下書き元のあらすじ）、
    script はネーム（ネームから作ったページだけ）、final_prompt は生成に使ったプロンプト。
    """

    synopsis: str = ""
    script: str = ""
    character_prompts: tuple[str, ...] = ()
    final_prompt: str = ""


STORY_CONTEXT_HEADING = (
    "Story so far (earlier pages of this same comic, oldest first; reference "
    "only, do not redraw them):"
)

MANGA_STORY_CONTINUITY_RULE = (
    "\n- Story so far: the user message lists earlier pages of this same comic, "
    "oldest first, and this page continues right after the latest one. Treat "
    "them as established facts: keep each continuing character's hair, eyes, "
    "body, clothing (items and colors), accessories, and any transformation that "
    "has already happened exactly as on the latest page, and keep the same "
    "location and time of day, unless this page's synopsis or instruction "
    "explicitly changes them. Do not redraw or repeat earlier panels, and do not "
    "reuse their dialogue."
)

# プロンプト化では、引き継ぐ外見を前のページのプロンプトから書き写させる。
# 人数タグは変身前のページ（boy など）に引きずられやすいため、今の姿で数えさせる
MANGA_STORY_PROMPT_CARRYOVER_RULE = (
    "\n- For each continuing character, carry over the appearance and clothing "
    "tags from the latest page's character prompts (or its image prompt when it "
    "has none) into this page's prompts. Count people in base_tags (1girl, 1boy, "
    "2girls, ...) by how each character looks on this page: a character who has "
    "transformed is counted by their current body, never by their look on "
    "earlier pages."
)


def _clip_story_text(text: str, limit: int) -> str:
    """これまでの話に渡す文を limit 字までに切り詰める（超えたら末尾に … を付ける）。"""
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "…"


def build_story_context_block(
    pages: Sequence[StoryPage], *, include_script: bool
) -> str:
    """これまでの話を user プロンプト用の文にする。ページが無ければ ""。

    include_script はネームを渡すか（ネーム下書きでは渡し、プロンプト化では渡さない。
    プロンプト化の出力は JSON で、文脈の「」の台詞を書き写すと壊れやすいため）。
    キャラ枠と最終プロンプトは台詞の要素を除き、最終プロンプトは最後のページだけ渡す。
    """
    if not pages:
        return ""
    lines = [STORY_CONTEXT_HEADING]
    last = len(pages) - 1
    for index, page in enumerate(pages):
        lines.append(
            f"Page {index + 1} (latest)" if index == last else f"Page {index + 1}"
        )
        synopsis = _clip_story_text(
            page.synopsis, PROMPT_EXPANDER_STORY_SYNOPSIS_MAX_LEN
        )
        if synopsis:
            lines.append(f"Synopsis: {synopsis}")
        if include_script:
            script = _clip_story_text(page.script, PROMPT_EXPANDER_STORY_SCRIPT_MAX_LEN)
            if script:
                lines.append("Script:\n" + script)
        characters = [
            _clip_story_text(
                strip_quoted_segments(prompt), PROMPT_EXPANDER_STORY_CHARACTER_MAX_LEN
            )
            for prompt in page.character_prompts
        ]
        characters = [item for item in characters if item]
        if characters:
            lines.append(
                "Character prompts:\n"
                + "\n".join(
                    f"{number}. {item}"
                    for number, item in enumerate(characters, start=1)
                )
            )
        if index == last:
            prompt = _clip_story_text(
                strip_quoted_segments(page.final_prompt),
                PROMPT_EXPANDER_STORY_PROMPT_MAX_LEN,
            )
            if prompt:
                lines.append(f"Image prompt: {prompt}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ネームの下書き（あらすじ → 記法付きのコマ割り台本。プロンプト化の前段）
# ---------------------------------------------------------------------------

MANGA_SCRIPT_SYSTEM_PROMPT_TEMPLATE = """You are a manga storyboard (ネーム) writer for TSF and outfit-change scenarios.
Turn the user's synopsis or rough idea into a panel-by-panel comic script. A NovelAI Diffusion V5 prompt writer will later convert this script into an image prompt, so every panel must be a concrete, drawable scene.

Requirements:
- Output only the script as plain text lines. No title, headings, Markdown, code fences, explanations, or notes.
- {panel_rule} Start each panel on its own line with a circled number (①, ②, ③, ...) followed by a short description of what is visible in that panel (who, action, expression, camera, background) written in {description_language}. One panel per line.
- Notation for text drawn in the image, placed on the same line as its panel: 「...」 for a spoken line (write the speaker's name right before it when more than one character appears), 『...』 for an unspoken thought, 【...】 for a narration box, 《...》 for a sound effect. Only the text inside these brackets is drawn: keep each under 20 Japanese characters or 12 words, written in {text_language}.
- {dialogue_rule}
- {sfx_rule}
- {narration_rule}
- Keep each character's identity, hair, eyes, body, and clothing consistent across panels. If the story involves a transformation, show its stages in order.
- Follow the synopsis faithfully and add only the details needed to make each panel drawable. Do not use any other brackets or symbols for emphasis."""

MANGA_SCRIPT_USER_PROMPT_TEMPLATE = (
    "Synopsis:\n{synopsis}\n\nWrite the storyboard script now."
)
# これまでの話があるとき。あらすじは続きのページの分として渡す
MANGA_SCRIPT_CONTINUATION_USER_PROMPT_TEMPLATE = (
    "Synopsis of the next page:\n{synopsis}\n\n"
    "Write the storyboard script for the next page now."
)


def build_manga_script_prompts(
    *,
    synopsis: str,
    options: MangaOptions,
    nsfw: bool,
    memory_text: str = "",
    language: str = "ja",
    cast: Sequence[CastMember] = (),
    story_pages: Sequence[StoryPage] = (),
) -> tuple[str, str]:
    """ネーム下書きの (system, user) プロンプトを返す。

    cast（名前を付けた精密参照の登場人物）があれば、その名前を話者名に使わせる。
    story_pages（これまでの話）があれば、その続きのページとして書かせる。
    """
    if options.panel_count <= PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO:
        panel_rule = "Write between 2 and 4 panels."
    else:
        count = min(options.panel_count, PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX)
        plural = "s" if count != 1 else ""
        panel_rule = f"Write exactly {count} panel{plural}."
    if options.dialogue:
        dialogue_rule = (
            "Give most panels a short spoken line or thought that carries the story; "
            "do not repeat the description inside the bubble."
        )
    else:
        dialogue_rule = (
            "Do not write 「...」 or 『...』 lines unless the synopsis explicitly "
            "provides them."
        )
    if options.sound_effects:
        sfx_rule = (
            "Add a 《...》 sound effect only where an action needs one (at most one "
            "per panel)."
        )
    else:
        sfx_rule = (
            "Do not add 《...》 sound effects unless the synopsis explicitly provides "
            "them."
        )
    if options.narration:
        narration_rule = (
            "Add a 【...】 narration box where a scene change, time skip, or story "
            "voice helps (at most one per panel)."
        )
    else:
        narration_rule = (
            "Do not add 【...】 narration unless the synopsis explicitly provides it."
        )
    system = MANGA_SCRIPT_SYSTEM_PROMPT_TEMPLATE.format(
        panel_rule=panel_rule,
        description_language=(
            "the same language as the synopsis (Japanese for a Japanese synopsis, "
            "English for an English one)"
        ),
        text_language=_manga_text_language_phrase(options.text_language),
        dialogue_rule=dialogue_rule,
        sfx_rule=sfx_rule,
        narration_rule=narration_rule,
    )
    cast_block = build_cast_block(cast)
    if cast_block:
        system += MANGA_SCRIPT_CAST_RULE
    story_block = build_story_context_block(story_pages, include_script=True)
    if story_block:
        system += MANGA_STORY_CONTINUITY_RULE
    system += _content_rule(nsfw) + build_memory_priority_instruction(
        (memory_text or "").strip(), language
    )
    template = (
        MANGA_SCRIPT_CONTINUATION_USER_PROMPT_TEMPLATE
        if story_block
        else MANGA_SCRIPT_USER_PROMPT_TEMPLATE
    )
    user = template.format(synopsis=synopsis.strip())
    if story_block:
        user = f"{story_block}\n\n{user}"
    if cast_block:
        user = f"{cast_block}\n\n{user}"
    return system, user


def sanitize_manga_script(raw: str) -> str:
    """ネーム下書きの LLM 出力を、記法付きの行だけに整える。

    コードフェンス・空行を除き、行頭のコマ番号（①〜⑳ または "1:"）が 1 行も無ければ不正とする。
    """
    text = strip_code_fence(raw or "")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        raise PromptExpanderOutputError("空のネームが返されました")
    if not any(_PANEL_PREFIX_PATTERN.match(line) for line in lines):
        raise PromptExpanderOutputError(
            "ネームの形式が不正です（コマ番号で始まる行がありません）"
        )
    return "\n".join(lines)


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

# 入力欄の下書きがあるとき: メモリだけだと毎回似た提案になるので、下書きを状況の起点にして幅を出す
SUGGEST_INPUT_BIAS_RULE = (
    "\n- The user's current prompt draft is included in the request. Treat it as the "
    "situational starting point: bias each suggestion so it fits or plays against that "
    "draft, so the set varies around what the user is writing now instead of repeating "
    "the same designs every time."
)

# メモリが空で下書きだけあるとき
SUGGEST_NO_MEMORY_RULE = (
    "\n- No preference memory is available this time; ground the suggestions in the "
    "current prompt draft instead of memory."
)

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
    manga_notation: MangaNotation | None = None,
    transparent_background: bool = False,
    with_cast: bool = False,
    with_story: bool = False,
) -> str:
    """正プロンプト拡張の system プロンプトを組み立てる。

    構成は移植元と同じく「本体 → 成人向けルール → メモリ節（最優先指示）」。
    manga を渡すと漫画モード（コマ割り・吹き出し）の本体に差し替える。
    transparent_background は本体直後に背景を書かせない規則を足す（漫画モードでは無視）。
    with_cast はキャラ枠 ON でキャストがあるとき、キャラ枠を名前付き object で出させる。
    with_story は漫画でこれまでの話を渡すとき、前のページの外見を引き継ぐ規則を足す。
    """
    if manga is not None:
        # 漫画モードは拡張モードに依存しない（引用符内以外は常に英語）
        base = build_manga_system_prompt(
            options=manga,
            character_mode=character_mode,
            max_characters=max_characters,
            notation=manga_notation,
            with_cast=with_cast,
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
    # キャストのいる漫画は専用の本体（コマごとの JSON）にキャストの規則が入っている
    if with_cast and character_mode and manga is None:
        base = (
            base.replace(CHARACTER_ITEMS_PLAIN_SHAPE, CHARACTER_ITEMS_NAMED_SHAPE)
            + CAST_CHARACTER_RULE
        )
    if manga is None and transparent_background:
        base += (
            TRANSPARENT_BACKGROUND_RULE_JA
            if mode == "japanese"
            else TRANSPARENT_BACKGROUND_RULE_TAGS
        )
    if manga is not None and with_story:
        base += MANGA_STORY_CONTINUITY_RULE + MANGA_STORY_PROMPT_CARRYOVER_RULE
    if manga is not None or mode == "tags":
        base += JAPANESE_TAG_GLOSSARY_RULE
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
    manga_notation: MangaNotation | None = None,
    cast: Sequence[CastMember] = (),
    cast_descriptions: Sequence[str] = (),
    story_pages: Sequence[StoryPage] = (),
) -> str:
    """正プロンプト拡張の user プロンプトを組み立てる（移植元の形式を踏襲）。

    キャラ枠 ON のときだけ cast（登場人物の一覧。目印 [[n]] と見た目の言い回し付き）を足す。
    漫画のときだけ story_pages（これまでの話。ネームは除く）を指示の前に足す。
    """
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
    if character_mode:
        cast_block = build_cast_block(cast, descriptions=cast_descriptions)
        if cast_block:
            parts.append(cast_block)
    if context_description and context_description.strip():
        parts.append(
            "Current image description (reference only):\n"
            + context_description.strip()
        )
    if manga:
        story_block = build_story_context_block(story_pages, include_script=False)
        if story_block:
            parts.append(story_block)
    parts.append("User instruction:\n" + instruction.strip())
    if manga:
        if manga_notation is not None and manga_notation.has_texts:
            parts.append(build_manga_notation_block(manga_notation))
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
    if mode == "tags":
        base += JAPANESE_TAG_GLOSSARY_RULE
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


def build_suggest_user_prompt(input_text: str | None = None) -> str:
    """キャラクター提案の user プロンプト。下書きがあれば前置する。"""
    draft = (input_text or "").strip()
    if not draft:
        return SUGGEST_USER_PROMPT
    return "Current prompt draft:\n" + draft + "\n\n" + SUGGEST_USER_PROMPT


def build_suggest_characters_prompts(
    *,
    memory_text: str,
    count: int,
    mode: ExpandMode,
    nsfw: bool,
    language: str = "ja",
    input_text: str | None = None,
) -> tuple[str, str]:
    """キャラクター提案の (system, user) プロンプトを返す。

    input_text（入力欄の下書き）があれば、メモリに加えて提案の方向付けに使う。
    """
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
    draft = (input_text or "").strip()
    memory_clean = (memory_text or "").strip()
    system = SUGGEST_CHARACTERS_SYSTEM_PROMPT_TEMPLATE.format(
        count=count, style_rule=style_rule, gender_example=gender_example
    )
    if draft:
        system += SUGGEST_INPUT_BIAS_RULE
        if not memory_clean:
            system += SUGGEST_NO_MEMORY_RULE
    system += _content_rule(nsfw) + build_memory_priority_instruction(
        memory_clean, language
    )
    return system, build_suggest_user_prompt(draft)


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


# カンマ区切りの単独トークン "shorts" だけに一致する（denim shorts / boyshorts は不一致）。
# JSON 文字列の値（"character": "1girl, shorts"）の先頭・末尾にある場合も一致させる。
_FALSE_FRIEND_SHORTS_PATTERN = re.compile(
    r'(^|[,"])(\s*)shorts(\s*)(?=[,"]|$)', re.IGNORECASE | re.MULTILINE
)


def replace_false_friend_tokens(prompt: str, instruction: str | None) -> str:
    """指示に「ショーツ」が含まれるとき、出力中の単独タグ shorts を panties に置換する。

    LLM が「ショーツ」を英語の shorts（短パン）として直訳した場合の決定的な保険。
    複数語のタグ（denim shorts）や連結語（boyshorts）は変更しない。空白・改行は保持する。
    """
    if not prompt or not instruction or "ショーツ" not in instruction:
        return prompt
    return _FALSE_FRIEND_SHORTS_PATTERN.sub(
        lambda m: f"{m.group(1)}{m.group(2)}panties{m.group(3)}", prompt
    )


def sanitize_tag_prompt(raw: str, *, ensure_quality: bool = True) -> str:
    """タグ形式の LLM 出力を 1 行のカンマ区切りに整える（移植元の手順）。"""
    text = _unwrap_quoted(strip_code_fence(raw or ""))
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
    text = _unwrap_quoted(strip_code_fence(raw or ""))
    text = _strip_labels(text)
    text = _CHARACTER_LABEL_PATTERN.sub("", text, count=1)
    return " ".join(text.split()).strip()


def sanitize_by_mode(raw: str, mode: ExpandMode, *, ensure_quality: bool) -> str:
    if mode == "japanese":
        return sanitize_prose_prompt(raw)
    return sanitize_tag_prompt(raw, ensure_quality=ensure_quality)


def _load_json_object(raw: str) -> object:
    text = strip_code_fence(raw or "")
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


def _parse_character_items(
    characters_raw: list[object], sanitize: Callable[[str], str]
) -> list[tuple[str, str]]:
    """character_prompts の要素を (名前, プロンプト) の組にする。

    要素は文字列（名前なし）か {"name","prompt"} の object。空のプロンプトは組ごと除き、
    名前とプロンプトがずれないようにする。
    """
    items: list[tuple[str, str]] = []
    for item in characters_raw:
        if isinstance(item, str):
            name, prompt_raw = "", item
        elif isinstance(item, dict) and isinstance(item.get("prompt"), str):
            name_raw = item.get("name")
            name = " ".join(name_raw.split()) if isinstance(name_raw, str) else ""
            prompt_raw = item["prompt"]
        else:
            continue
        prompt = sanitize(prompt_raw)
        if prompt:
            items.append((name, prompt))
    return items


def parse_character_json_named(
    raw: str,
    *,
    max_characters: int,
    mode: ExpandMode,
) -> tuple[str, list[tuple[str, str]]]:
    """{"base_prompt","character_prompts"} 形式の出力を解析し、キャラ枠を名前付きで返す。

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
    items = _parse_character_items(
        characters_raw,
        lambda text: sanitize_by_mode(text, mode, ensure_quality=False),
    )
    if not base or not items:
        raise PromptExpanderOutputError("空のプロンプトが含まれています。")
    return base, items[:max_characters]


def parse_character_json(
    raw: str,
    *,
    max_characters: int,
    mode: ExpandMode,
) -> tuple[str, list[str]]:
    """{"base_prompt","character_prompts"} 形式の出力を解析し整形して返す（名前は捨てる）。"""
    base, items = parse_character_json_named(
        raw, max_characters=max_characters, mode=mode
    )
    return base, [prompt for _, prompt in items]


def parse_manga_json(
    raw: str,
    *,
    max_characters: int,
    character_mode: bool,
) -> tuple[str, list[str] | None]:
    """漫画モードの出力を解析する（キャラ枠の名前は捨てる）。"""
    base, items = parse_manga_json_named(
        raw, max_characters=max_characters, character_mode=character_mode
    )
    return base, None if items is None else [prompt for _, prompt in items]


@dataclass(frozen=True)
class CastLook:
    """キャストをコマ説明で指す言い回しと、人数・代名詞を決める名詞（girl など）。"""

    description: str
    noun: str = "character"


_NOUN_PLURALS = {
    "girl": "girls",
    "boy": "boys",
    "woman": "women",
    "man": "men",
    "person": "people",
    "character": "characters",
}
_NOUN_PRONOUNS = {"girl": "her", "woman": "her", "boy": "him", "man": "him"}
_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
    "eleventh",
    "twelfth",
)
_NUMBER_WORDS = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
)
_MAX_COMPOSED_PANELS = len(_ORDINALS)


def _clean_phrase(value: object) -> str:
    text = " ".join(str(value or "").split())
    return text.replace('"', "").strip().rstrip(".").strip()


def _clean_lines(value: object) -> list[str]:
    items = value if isinstance(value, list) else [value] if value else []
    lines = []
    for item in items:
        if not isinstance(item, str):
            continue
        line = " ".join(item.split()).replace('"', "").strip()
        if line:
            lines.append(line)
    return lines


def _number_word(count: int) -> str:
    return _NUMBER_WORDS[count] if 0 <= count < len(_NUMBER_WORDS) else str(count)


@dataclass(frozen=True)
class _PanelPerson:
    description: str
    noun: str
    action: str
    says: tuple[str, ...]
    thinks: tuple[str, ...]

    @property
    def speaks(self) -> bool:
        return bool(self.says or self.thinks)

    def phrase(self) -> str:
        pronoun = _NOUN_PRONOUNS.get(self.noun, "them")
        text = f"{self.description} {self.action}".strip()
        for line in self.says:
            text += f', with a speech bubble next to {pronoun} that says "{line}"'
        for line in self.thinks:
            text += f', with a thought cloud above {pronoun} that says "{line}"'
        return text


def _resolve_panel_person(
    raw: dict, looks: Sequence[CastLook], cast_keys: Sequence[str]
) -> _PanelPerson | None:
    who = str(raw.get("who") or "").strip()
    token = _CAST_TOKEN_PATTERN.search(who)
    index: int | None = None
    if token:
        index = int(token.group(1)) - 1
    elif normalize_cast_name(who) in cast_keys:
        index = cast_keys.index(normalize_cast_name(who))
    if index is not None and 0 <= index < len(looks):
        description, noun = looks[index].description, looks[index].noun
    else:
        description = _clean_phrase(_CAST_TOKEN_PATTERN.sub("", who))
        if not description:
            return None
        noun = "person"
    return _PanelPerson(
        description=description,
        noun=noun,
        action=_clean_phrase(raw.get("action")),
        says=tuple(_clean_lines(raw.get("says"))),
        thinks=tuple(_clean_lines(raw.get("thinks"))),
    )


def compose_cast_panel_description(
    panels: Sequence[object],
    *,
    looks: Sequence[CastLook],
    cast_names: Sequence[str],
    reading_direction: str = "rtl",
    layout: str = "auto",
) -> str:
    """コマごとの中身（JSON）からコマ説明の英文を組み立てる。

    画像モデルはコマの中で先に書かれた人物を描き、後の人物を落としやすく、台詞は描かれた
    人物に付く。そこで話す人物を先に置き、台詞を同じ文に入れ、人数を明記する。
    """
    direction = "ltr" if reading_direction == "ltr" else "rtl"
    cast_keys = [normalize_cast_name(name) for name in cast_names]
    usable = [panel for panel in panels if isinstance(panel, dict)]
    usable = usable[:_MAX_COMPOSED_PANELS]
    if not usable:
        return ""
    count = len(usable)
    reading = (
        "read from right to left" if direction == "rtl" else "read from left to right"
    )
    parts = [
        f"There {'is' if count == 1 else 'are'} {_number_word(count)} comic "
        f"panel{'' if count == 1 else 's'}, {reading}."
    ]
    statement = MANGA_CAST_LAYOUT_STATEMENTS.get(layout, {}).get(direction, "")
    if statement:
        parts.append(statement)
    for ordinal, panel in zip(_ORDINALS, usable, strict=False):
        people_raw = panel.get("people")
        people = [
            person
            for person in (
                _resolve_panel_person(item, looks, cast_keys)
                for item in (people_raw if isinstance(people_raw, list) else [])
                if isinstance(item, dict)
            )
            if person is not None
        ]
        # 話す人物を先に（同じ条件の中では元の順を保つ）
        people.sort(key=lambda person: not person.speaks)
        position = _clean_phrase(panel.get("position"))
        head = f"The {ordinal} panel" + (f", at the {position}," if position else "")
        scene = _clean_phrase(panel.get("scene"))
        if not people:
            sentence = f"{head} shows {scene or 'the scene'}."
        elif len(people) == 1:
            sentence = f"{head} shows {people[0].phrase()}."
        else:
            nouns = {person.noun for person in people}
            plural = (
                _NOUN_PLURALS.get(next(iter(nouns)), "people")
                if len(nouns) == 1
                else "people"
            )
            phrases = [person.phrase() for person in people]
            joined = ", ".join(phrases[:-1]) + f", and {phrases[-1]}"
            sentence = f"{head} shows {_number_word(len(people))} {plural}: {joined}."
        if people and scene:
            sentence += f" Background: {scene}."
        narration = _clean_lines(panel.get("narration"))
        for text in narration:
            sentence += f' There\'s a narration box at the top of the panel that reads "{text}".'
        for text in _clean_lines(panel.get("sfx")):
            sentence += f' There\'s also a "{text}" sound effect.'
        parts.append(sentence)
    return " ".join(parts)


def parse_manga_cast_json(
    raw: str,
    *,
    max_characters: int,
    looks: Sequence[CastLook],
    cast_names: Sequence[str],
    reading_direction: str = "rtl",
    layout: str = "auto",
) -> tuple[str, list[tuple[str, str]]]:
    """キャストのいる漫画の出力（base_tags・panels・character_prompts）を解析する。

    panels からコマ説明を組み立ててタグ見出しと結合する。panels が無く従来の
    panel_description が返ったときはそれを使う（目印の置き換えは呼び出し側）。
    """
    data = _load_json_object(raw)
    if not isinstance(data, dict):
        raise PromptExpanderOutputError("漫画プロンプトのJSON形式が不正です。")
    tags_raw = data.get("base_tags")
    if not isinstance(tags_raw, str):
        raise PromptExpanderOutputError("base_tagsが不正です。")
    tags = sanitize_tag_prompt(tags_raw, ensure_quality=True)
    panels = data.get("panels")
    description = ""
    if isinstance(panels, list):
        description = compose_cast_panel_description(
            panels,
            looks=looks,
            cast_names=cast_names,
            reading_direction=reading_direction,
            layout=layout,
        )
    if not description and isinstance(data.get("panel_description"), str):
        description = sanitize_prose_prompt(data["panel_description"])
    if not description:
        raise PromptExpanderOutputError("コマの内容が空です。")
    base = f"{tags}, {description}" if tags else description
    characters_raw = data.get("character_prompts")
    if not isinstance(characters_raw, list):
        raise PromptExpanderOutputError("character_promptsが不正です。")
    items = _parse_character_items(
        characters_raw,
        lambda text: sanitize_tag_prompt(text, ensure_quality=False),
    )
    if not items:
        raise PromptExpanderOutputError("キャラクタープロンプトが空です。")
    return base, items[:max_characters]


def parse_manga_json_named(
    raw: str,
    *,
    max_characters: int,
    character_mode: bool,
) -> tuple[str, list[tuple[str, str]] | None]:
    """{"base_tags","panel_description","character_prompts"} 形式の出力を解析する。

    base_tags（タグ）とpanel_description（英語の自然文）を結合して 1 つのベースプロンプト
    にする。品質タグはタグ見出し側に補完し、コマ説明文の後ろには付けない。
    キャラ枠は (名前, プロンプト) の組で返す。
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
    items = _parse_character_items(
        characters_raw,
        lambda text: sanitize_tag_prompt(text, ensure_quality=False),
    )
    if not items:
        raise PromptExpanderOutputError("キャラクタープロンプトが空です。")
    return base, items[:max_characters]


def parse_suggestions_json(
    raw: str,
    *,
    count: int,
    mode: ExpandMode,
) -> list[dict[str, str]]:
    """{"suggestions":[{"title","prompt"}]} 形式の出力を解析して返す。"""
    text = strip_code_fence(raw or "")
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
