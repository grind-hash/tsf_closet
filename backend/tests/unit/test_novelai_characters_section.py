"""Unit tests for NovelAI image-prompt session-character integration (spec 005 FR-010)."""

from __future__ import annotations

from types import SimpleNamespace

from gateway.services.character_service import build_novelai_characters_section
from gateway.services.prompts import build_novelai_prompt_generation_user


def _rec(slot_index: int, name: str, position: str, tags: str = "", natural: str = ""):
    return SimpleNamespace(
        slot_index=slot_index,
        name=name,
        position=position,
        appearance_tags=tags,
        appearance_natural=natural,
    )


def test_section_empty_when_no_records() -> None:
    assert build_novelai_characters_section([]) == ""


def test_section_includes_name_position_and_tags() -> None:
    records = [
        _rec(0, "Kana", "left", tags="1girl, long blonde hair, blue eyes"),
        _rec(1, "Yuu", "center", tags="1girl, short black hair"),
    ]
    result = build_novelai_characters_section(records)
    assert "Registered Characters" in result
    assert "Kana" in result
    assert "left" in result
    assert "1girl, long blonde hair, blue eyes" in result
    assert "Yuu" in result
    assert "center" in result


def test_section_sorts_by_slot_index() -> None:
    records = [
        _rec(2, "Third", "right", tags="t3"),
        _rec(0, "First", "left", tags="t1"),
        _rec(1, "Second", "center", tags="t2"),
    ]
    result = build_novelai_characters_section(records)
    p1 = result.index("First")
    p2 = result.index("Second")
    p3 = result.index("Third")
    assert p1 < p2 < p3


def test_section_falls_back_to_natural_when_tags_missing() -> None:
    records = [_rec(0, "Mira", "left", natural="a tall girl in a red dress")]
    result = build_novelai_characters_section(records)
    assert "appearance: a tall girl in a red dress" in result


def test_user_prompt_appends_section_when_provided() -> None:
    section = (
        "## Registered Characters\n- Character 1 (Kana, position: left, tags: 1girl)"
    )
    user = build_novelai_prompt_generation_user(
        instruction="go to beach",
        previous_prompt="1boy, solo",
        enable_multiple_people=True,
        session_characters_section=section,
    )
    assert section in user
    assert "go to beach" in user


def test_user_prompt_unchanged_when_section_none() -> None:
    base = build_novelai_prompt_generation_user(
        instruction="go to beach",
        previous_prompt="1boy, solo",
        enable_multiple_people=True,
    )
    with_none = build_novelai_prompt_generation_user(
        instruction="go to beach",
        previous_prompt="1boy, solo",
        enable_multiple_people=True,
        session_characters_section=None,
    )
    assert base == with_none
