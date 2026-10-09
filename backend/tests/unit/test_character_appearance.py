"""Tests for the Japanese session-character prompt section (spec 005, T026)."""

from __future__ import annotations

from gateway.services.character_service import (
    build_session_characters_prompt_section,
)


def test_build_prompt_section_empty_returns_empty():
    assert build_session_characters_prompt_section([]) == ""


def test_build_prompt_section_includes_position_and_appearance():
    class _Stub:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    chars = [
        _Stub(
            name="Alice",
            position="left",
            appearance_natural="金髪のお嬢様",
            appearance_tags="blonde, gown",
            slot_index=0,
        ),
        _Stub(
            name="Bob",
            position="right",
            appearance_natural="",
            appearance_tags="",
            slot_index=1,
        ),
    ]
    text = build_session_characters_prompt_section(chars)
    assert "Alice" in text
    assert "Bob" in text
    assert "blonde, gown" in text
    assert "金髪" in text
