"""build_chat_messages(チャット履歴付き messages 配列)のテスト。"""

from __future__ import annotations

from gateway.services.llm_service import build_chat_messages


def test_build_chat_messages_without_history() -> None:
    assert build_chat_messages("sys", "hi") == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    assert build_chat_messages("sys", "hi", None) == build_chat_messages("sys", "hi")


def test_build_chat_messages_inserts_history_between_system_and_user() -> None:
    history = [
        {"role": "user", "content": "おはよう"},
        {"role": "assistant", "content": "おはよ"},
        # role 不正・空 content は無視する
        {"role": "system", "content": "ignored"},
        {"role": "user", "content": ""},
        {"role": "tool", "content": "x"},
    ]
    assert build_chat_messages("sys", "元気？", history) == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "おはよう"},
        {"role": "assistant", "content": "おはよ"},
        {"role": "user", "content": "元気？"},
    ]
