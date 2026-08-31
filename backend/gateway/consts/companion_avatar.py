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
    "bow": "a polite bow for greetings, thanks, or apology",
    "look_down": "lowering the gaze, shy, sad, or lost in thought",
    "perk_up": "straightening up suddenly, alert or realizing something",
    "shrink": "curling up small, anxious, guilty, or apologetic",
    "sway": "swaying side to side, happy, playful, or humming",
    "double_bounce": "bouncing twice, thrilled and unable to stay still",
    "wave_hand": "waving one hand, a friendly hello or goodbye",
    "raise_hand": "raising one hand high, volunteering or eager agreement",
    "reach_out": "reaching one hand toward you, offering, inviting, or worried",
    "cheer": "throwing both arms up in celebration or triumph",
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
    "{gestures}. Choose both from the narrative text only. Pick the most "
    "specific gesture whose description matches what the partner visibly does "
    "or how the reaction feels; prefer a hand or body movement over a generic "
    "nod when the descriptions offer one, and use idle only when the partner "
    "stays still. When nothing clearly fits use neutral and idle."
)

# トーク返答の先頭ヘッダ行の指示。対面会話モードのときだけ使う
AVATAR_TALK_HEADER_INSTRUCTION: str = (
    "Begin your reply with exactly one header line of the form "
    "[expression=<key> gesture=<key>] followed by a newline, then the spoken "
    "words. expression is one of: {expressions}. gesture is one of: {gestures}. "
    "Write the header exactly in that form, with the literal field names "
    "expression= and gesture=; never abbreviate it or merge the two fields. "
    "Pick the pair whose descriptions best match the feeling of your reply, "
    "using the full vocabulary rather than defaulting to neutral and idle. "
    "The header is machine-read and never shown, so it must not contain anything "
    "else; the spoken words must not repeat it."
)

# 衣装差分(同じキャラクターとして登録した VRM が 2 件以上)があるときだけ、
# 物語生成へ載せる指示。着替えは player_input か場面が求めたときに限る
AVATAR_WARDROBE_NARRATIVE_INSTRUCTION: str = (
    "partner_wardrobe lists the looks (outfit and hairstyle variants of the "
    "partner's 3D model) the partner can wear: partner_wardrobe.current is what "
    "the partner is wearing right now and partner_wardrobe.options are the only "
    "other looks available. The partner changes clothes or hairstyle only when "
    "player_input asks for it or the scene plainly calls for it (bathing, "
    "swimming, dressing up to go out); when that happens, pick one option and "
    "describe the partner in it so the new look is recognizable from its label. "
    "Otherwise keep the current look and never mention the list itself."
)

# 判定(resolution)プロンプトへ載せる指示。衣装差分があるときだけ使う
AVATAR_WARDROBE_RESOLUTION_INSTRUCTION: str = (
    "partner_outfit is the key of the partner_wardrobe option the partner is "
    "wearing at the end of this turn's narrative, exactly one of: {keys}. "
    "partner_wardrobe.current.key is what the partner wore before this turn: "
    "keep that key unless the narrative clearly shows the partner now in "
    "different clothes or a different hairstyle that matches another option."
)

# 先頭ヘッダ行の角括弧ブロック。正規形は [expression=<key> gesture=<key>] だが、
# LLM が [happy=nod] や [expression: happy, gesture: nod] のように略記・変形
# させることがあるため、ブロックは広く受けて中身を parse_talk_header で判定する
TALK_HEADER_RE = re.compile(r"^\s*\[([^\[\]\n]{1,120})\]\s*\n?")
# ラベル付きの値(expression=happy / gesture: nod)
_TALK_HEADER_LABEL_RE = re.compile(
    r"(expression|gesture)\s*[=:]\s*([A-Za-z_\-]+)", re.IGNORECASE
)
# ラベルが無いときに語彙のキーとして解釈するトークン
_TALK_HEADER_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z_\-]*")


def parse_talk_header(text: str) -> tuple[str | None, str | None, str]:
    """先頭ヘッダを解析して (expression, gesture, 残り) を返す。無ければ (None, None, text)。

    expression / gesture のラベルを含むか、語彙のキーとして解釈できるトークンを
    含む先頭の角括弧ブロックだけをヘッダとして剥がす。それ以外の角括弧は
    セリフの一部として残す。
    """
    source = str(text or "")
    match = TALK_HEADER_RE.match(source)
    if match is None:
        return None, None, source
    body = match.group(1)
    expression: str | None = None
    gesture: str | None = None
    labeled = False
    for label, value in _TALK_HEADER_LABEL_RE.findall(body):
        labeled = True
        if label.lower() == "expression":
            expression = expression or normalize_avatar_expression(value)
        else:
            gesture = gesture or normalize_avatar_gesture(value)
    if not labeled:
        for token in _TALK_HEADER_TOKEN_RE.findall(body):
            expression = expression or normalize_avatar_expression(token)
            gesture = gesture or normalize_avatar_gesture(token)
        if expression is None and gesture is None:
            return None, None, source
    return expression, gesture, source[match.end() :]


def avatar_resolution_instruction() -> str:
    return AVATAR_RESOLUTION_INSTRUCTION.format(
        expressions=get_avatar_expression_guide(),
        gestures=get_avatar_gesture_guide(),
    )


def avatar_talk_header_instruction() -> str:
    # トークは物語本文を経由しないため、キー名だけでは身振りの意味が伝わらない。
    # 判定プロンプトと同じく説明つきの語彙を渡す
    return AVATAR_TALK_HEADER_INSTRUCTION.format(
        expressions=get_avatar_expression_guide(),
        gestures=get_avatar_gesture_guide(),
    )


def avatar_wardrobe_narrative_instruction() -> str:
    return AVATAR_WARDROBE_NARRATIVE_INSTRUCTION


def avatar_wardrobe_resolution_instruction(keys: tuple[str, ...]) -> str:
    return AVATAR_WARDROBE_RESOLUTION_INSTRUCTION.format(keys=", ".join(keys))


def normalize_avatar_outfit_key(value: object) -> str | None:
    """LLM が返した衣装キーを文字列に整える。空・非文字列相当は None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text[:80] if text else None


__all__ = [
    "AVATAR_EXPRESSIONS",
    "AVATAR_EXPRESSION_DEFAULT",
    "AVATAR_GESTURES",
    "AVATAR_GESTURE_DEFAULT",
    "AVATAR_WARDROBE_NARRATIVE_INSTRUCTION",
    "AVATAR_WARDROBE_RESOLUTION_INSTRUCTION",
    "TALK_HEADER_RE",
    "avatar_expression_keys",
    "avatar_gesture_keys",
    "avatar_resolution_instruction",
    "avatar_talk_header_instruction",
    "avatar_wardrobe_narrative_instruction",
    "avatar_wardrobe_resolution_instruction",
    "get_avatar_expression_guide",
    "get_avatar_gesture_guide",
    "normalize_avatar_expression",
    "normalize_avatar_gesture",
    "normalize_avatar_outfit_key",
    "parse_talk_header",
]
