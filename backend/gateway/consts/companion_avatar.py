"""対面会話モードの 3D アバター(VRM)向け表情・身振りの語彙。

LLM は手番ごと(判定出力)・トーク返答ごと(先頭ヘッダ行)にキーを 1 つずつ
選ぶ。フロントエンドは同じキー集合を ``constants/companionAvatar.ts`` に
持ち、VRM のプリセット表情と手続き的モーションへ写す。ここに無いキーを
プロンプトへ載せてはならない(実装の無い要素を LLM に選ばせない)。
"""

from __future__ import annotations

import re

# VRM 1.0 のプリセット表情名。0.x では joy→happy / sorrow→sad / fun→relaxed に
# ライブラリ側で対応付けられ、surprised が無いモデルは neutral 扱いになる
AVATAR_EXPRESSIONS: dict[str, str] = {
    "neutral": "calm, no particular emotion",
    "happy": "smiling, pleased, amused",
    "sad": "downcast, hurt, wistful",
    "angry": "annoyed, pouting, offended",
    "surprised": "startled, wide-eyed",
    "relaxed": "content, soft, at ease",
}

# フロントエンドが手続き的に再生する身振り。全身モーション素材は使わない
AVATAR_GESTURES: dict[str, str] = {
    "idle": "no particular gesture; calm listening posture",
    "nod": "a small nod of agreement or acknowledgement",
    "shake_head": "shaking the head to deny or refuse",
    "tilt_head": "tilting the head, curious or puzzled",
    "lean_forward": "leaning in with interest or intimacy",
    "lean_back": "pulling back, startled, shy, or hesitant",
    "look_away": "turning the face away, embarrassed or sulking",
    "bounce": "a light happy bounce of excitement",
}

AVATAR_EXPRESSION_DEFAULT = "neutral"
AVATAR_GESTURE_DEFAULT = "idle"


def _normalize_key(value: object, allowed: dict[str, str]) -> str | None:
    if value is None:
        return None
    key = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return key if key in allowed else None


def normalize_avatar_expression(value: object) -> str | None:
    """語彙に無い表情は None(FE 側で neutral に倒す)。"""
    return _normalize_key(value, AVATAR_EXPRESSIONS)


def normalize_avatar_gesture(value: object) -> str | None:
    """語彙に無い身振りは None(FE 側で idle に倒す)。"""
    return _normalize_key(value, AVATAR_GESTURES)


def get_avatar_expression_guide() -> str:
    return ", ".join(f"{key} ({desc})" for key, desc in AVATAR_EXPRESSIONS.items())


def get_avatar_gesture_guide() -> str:
    return ", ".join(f"{key} ({desc})" for key, desc in AVATAR_GESTURES.items())


def avatar_expression_keys() -> tuple[str, ...]:
    return tuple(AVATAR_EXPRESSIONS)


def avatar_gesture_keys() -> tuple[str, ...]:
    return tuple(AVATAR_GESTURES)


# 判定(resolution)プロンプトへ載せる指示。対面会話モードのときだけ使う
AVATAR_RESOLUTION_INSTRUCTION: str = (
    "partner_expression is the partner's facial expression during this turn's "
    "narrative, exactly one of: {expressions}. partner_gesture is one visible "
    "motion matching the partner's reaction in that narrative, exactly one of: "
    "{gestures}. Choose both from the narrative text only; when nothing clearly "
    "fits use neutral and idle."
)

# トーク返答の先頭ヘッダ行の指示。対面会話モードのときだけ使う
AVATAR_TALK_HEADER_INSTRUCTION: str = (
    "Begin your reply with exactly one header line of the form "
    "[expression=<key> gesture=<key>] followed by a newline, then the spoken "
    "words. expression is one of: {expressions}. gesture is one of: {gestures}. "
    "The header is machine-read and never shown, so it must not contain anything "
    "else; the spoken words must not repeat it."
)

# 先頭ヘッダ行。改行が無い・カンマ区切り・大文字でも受ける
TALK_HEADER_RE = re.compile(
    r"^\s*\[\s*expression\s*=\s*([A-Za-z_\-]+)\s*[,\s]\s*gesture\s*=\s*([A-Za-z_\-]+)"
    r"\s*\]\s*\n?",
    re.IGNORECASE,
)


def parse_talk_header(text: str) -> tuple[str | None, str | None, str]:
    """先頭ヘッダを解析して (expression, gesture, 残り) を返す。無ければ (None, None, text)。"""
    source = str(text or "")
    match = TALK_HEADER_RE.match(source)
    if match is None:
        return None, None, source
    return (
        normalize_avatar_expression(match.group(1)),
        normalize_avatar_gesture(match.group(2)),
        source[match.end() :],
    )


def avatar_resolution_instruction() -> str:
    return AVATAR_RESOLUTION_INSTRUCTION.format(
        expressions=get_avatar_expression_guide(),
        gestures=get_avatar_gesture_guide(),
    )


def avatar_talk_header_instruction() -> str:
    return AVATAR_TALK_HEADER_INSTRUCTION.format(
        expressions=", ".join(AVATAR_EXPRESSIONS),
        gestures=", ".join(AVATAR_GESTURES),
    )


__all__ = [
    "AVATAR_EXPRESSIONS",
    "AVATAR_EXPRESSION_DEFAULT",
    "AVATAR_GESTURES",
    "AVATAR_GESTURE_DEFAULT",
    "TALK_HEADER_RE",
    "avatar_expression_keys",
    "avatar_gesture_keys",
    "avatar_resolution_instruction",
    "avatar_talk_header_instruction",
    "get_avatar_expression_guide",
    "get_avatar_gesture_guide",
    "normalize_avatar_expression",
    "normalize_avatar_gesture",
    "parse_talk_header",
]
