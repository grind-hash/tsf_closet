"""対面会話モードの 3D アバター語彙(表情・身振り)とトークヘッダ解析。"""

from __future__ import annotations

from gateway.consts.companion_avatar import (
    AVATAR_EXPRESSIONS,
    AVATAR_GESTURES,
    avatar_expression_keys,
    avatar_gesture_keys,
    avatar_resolution_instruction,
    avatar_talk_header_instruction,
    get_avatar_expression_guide,
    get_avatar_gesture_guide,
    normalize_avatar_expression,
    normalize_avatar_gesture,
    parse_talk_header,
)


def test_guides_enumerate_every_key() -> None:
    expression_guide = get_avatar_expression_guide()
    gesture_guide = get_avatar_gesture_guide()
    for key in AVATAR_EXPRESSIONS:
        assert f"{key} (" in expression_guide
    for key in AVATAR_GESTURES:
        assert f"{key} (" in gesture_guide
    assert avatar_expression_keys() == tuple(AVATAR_EXPRESSIONS)
    assert avatar_gesture_keys() == tuple(AVATAR_GESTURES)
    assert "neutral" in AVATAR_EXPRESSIONS and "idle" in AVATAR_GESTURES


def test_normalizers_accept_case_and_separators_and_reject_unknown() -> None:
    assert normalize_avatar_expression(" HAPPY ") == "happy"
    assert normalize_avatar_expression("Relaxed") == "relaxed"
    assert normalize_avatar_expression("wave") is None
    assert normalize_avatar_expression(None) is None
    assert normalize_avatar_expression(42) is None
    assert normalize_avatar_gesture("Shake-Head") == "shake_head"
    assert normalize_avatar_gesture("lean forward") == "lean_forward"
    assert normalize_avatar_gesture("dance") is None
    assert normalize_avatar_gesture("") is None


def test_parse_talk_header_variants() -> None:
    assert parse_talk_header("[expression=happy gesture=nod]\nやっほー") == (
        "happy",
        "nod",
        "やっほー",
    )
    # 改行なし・カンマ区切り・大文字でも受ける
    assert parse_talk_header("[expression=HAPPY, gesture=Nod]やっほー") == (
        "happy",
        "nod",
        "やっほー",
    )
    # 語彙外のキーはヘッダとしては剥がすが値は None
    assert parse_talk_header("[expression=wave gesture=dance]\nhi") == (
        None,
        None,
        "hi",
    )
    # ヘッダが無ければそのまま
    assert parse_talk_header("やっほー") == (None, None, "やっほー")
    assert parse_talk_header("") == (None, None, "")
    # 途中に現れる角括弧はヘッダ扱いしない
    assert parse_talk_header("うん [expression=happy gesture=nod]") == (
        None,
        None,
        "うん [expression=happy gesture=nod]",
    )


def test_prompt_instructions_mention_schema_and_keys() -> None:
    resolution = avatar_resolution_instruction()
    assert "partner_expression" in resolution and "partner_gesture" in resolution
    for key in (*AVATAR_EXPRESSIONS, *AVATAR_GESTURES):
        assert key in resolution
    # idle へ逃げず、説明に合う最も具体的な身振りを選ばせる
    assert "idle only when the partner stays still" in resolution
    talk = avatar_talk_header_instruction()
    assert "[expression=<key> gesture=<key>]" in talk
    for key in (*AVATAR_EXPRESSIONS, *AVATAR_GESTURES):
        assert key in talk
    # トークにも説明つきの語彙が載る(キー名だけでは意味が伝わらない)
    for description in AVATAR_GESTURES.values():
        assert description in talk
    assert "rather than defaulting to neutral and idle" in talk
