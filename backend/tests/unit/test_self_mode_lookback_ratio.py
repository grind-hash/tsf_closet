"""Tests for self-mode lookback ratio (spec 004 T026, US4, FR-009).

`build_self_mode_conversation_prompt` の `lookback_count` 引数に対して、
``recent`` (= conversation_history) は ``ceil(lookback * 1.2)`` 件、
``timeline`` (= session_timeline) は ``ceil(lookback * 1.6)`` 件まで
参照されることを検証する。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gateway.services.self_mode_prompts import build_self_mode_conversation_prompt


def _make_history(n: int):
    return [
        SimpleNamespace(role="user" if i % 2 == 0 else "assistant", content=f"msg{i}")
        for i in range(n)
    ]


def _make_timeline(n: int):
    return [("action", f"step{i}") for i in range(n)]


@pytest.mark.parametrize(
    "lookback,expected_recent,expected_timeline",
    [
        (5, 6, 8),  # ceil(5*1.2)=6, ceil(5*1.6)=8
        (10, 12, 16),  # ceil(10*1.2)=12, ceil(10*1.6)=16
        (7, 9, 12),  # ceil(7*1.2)=8.4->9, ceil(7*1.6)=11.2->12
        (20, 24, 32),  # ceil(20*1.2)=24, ceil(20*1.6)=32
    ],
)
def test_self_mode_conversation_lookback_ratio(
    lookback, expected_recent, expected_timeline
):
    # 参照件数の上限を超える件数を渡す
    history = _make_history(50)
    timeline = _make_timeline(50)
    profile = {"display_name": "テスト", "pronoun": "私", "interests": []}

    _, user_prompt = build_self_mode_conversation_prompt(
        message="hello",
        conversation_history=history,
        current_outfit_desc="white dress",
        self_profile=profile,
        session_timeline=timeline,
        lookback_count=lookback,
    )

    # conversation_history からは末尾 expected_recent 件が prompt に含まれるはず。
    # 各メッセージは "msg{i}" を含むので、msg{50-expected_recent} が含まれて
    # msg{50-expected_recent-1} は含まれないことを確認。
    boundary_in = f"msg{50 - expected_recent}"
    boundary_out = f"msg{50 - expected_recent - 1}"
    assert boundary_in in user_prompt
    assert boundary_out not in user_prompt

    # session_timeline からは末尾 expected_timeline 件が含まれるはず。
    tl_boundary_in = f"step{50 - expected_timeline}"
    tl_boundary_out = f"step{50 - expected_timeline - 1}"
    assert tl_boundary_in in user_prompt
    assert tl_boundary_out not in user_prompt
