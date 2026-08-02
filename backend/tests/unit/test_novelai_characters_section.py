"""Unit tests for NovelAI image-prompt session-character integration (spec 005 FR-010)."""

from __future__ import annotations

from types import SimpleNamespace

from gateway.services.character_service import (
    build_novelai_characters_section,
    extract_protagonist_tags_from_history,
)
from gateway.services.prompts import build_novelai_prompt_generation_user


def _rec(
    slot_index: int,
    name: str,
    position: str,
    tags: str = "",
    natural: str = "",
    is_protagonist: bool = False,
):
    return SimpleNamespace(
        slot_index=slot_index,
        name=name,
        position=position,
        appearance_tags=tags,
        appearance_natural=natural,
        is_protagonist=is_protagonist,
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


# ---------------------------------------------------------------------------
# Protagonist integration (FR-010 follow-up)
# ---------------------------------------------------------------------------


def test_extract_protagonist_tags_returns_first_character_tags() -> None:
    payload = (
        '{"characters": ['
        '{"tags": "1boy, short black hair, blue eyes", "position": "center"},'
        '{"tags": "1girl, long blonde hair", "position": "left"}'
        '], "scene": "beach"}'
    )
    assert (
        extract_protagonist_tags_from_history(payload)
        == "1boy, short black hair, blue eyes"
    )


def test_extract_protagonist_tags_handles_code_fenced_json() -> None:
    payload = (
        "```json\n"
        '{"characters": [{"tags": "1boy, glasses", "position": "center"}],'
        ' "scene": "cafe"}\n'
        "```"
    )
    assert extract_protagonist_tags_from_history(payload) == "1boy, glasses"


def test_extract_protagonist_tags_handles_single_line_code_fence() -> None:
    # Real-world payload observed in production: fence + language + JSON all on one line.
    payload = (
        '```json {"characters": ['
        '{"tags": "1girl, short black hair, black eyes, lime yellow bra",'
        ' "position": "center"},'
        '{"tags": "1boy, penis, standing", "position": "right"}'
        '], "scene": "runway"} ```'
    )
    assert (
        extract_protagonist_tags_from_history(payload)
        == "1girl, short black hair, black eyes, lime yellow bra"
    )


def test_extract_protagonist_tags_accepts_plain_novelai_tag_list() -> None:
    # Opus JSON-split success path stores character[0].prompt as after_description.
    plain = "masterpiece, best quality, 1boy, solo, short black hair, blue eyes"
    assert extract_protagonist_tags_from_history(plain) == plain


def test_extract_protagonist_tags_accepts_plain_1girl_list() -> None:
    plain = "1girl, long blonde hair, school uniform, blue eyes"
    assert extract_protagonist_tags_from_history(plain) == plain


def test_extract_protagonist_tags_returns_none_for_japanese_narrative() -> None:
    # Non-Opus dress-up history is free-text and must not be treated as tags.
    narrative = "セーラー服に変身した姿"
    assert extract_protagonist_tags_from_history(narrative) is None
    reality = "「性別が逆転する」という現実改変により変化した姿"
    assert extract_protagonist_tags_from_history(reality) is None


def test_extract_protagonist_tags_returns_none_for_empty_characters() -> None:
    assert extract_protagonist_tags_from_history('{"characters": []}') is None


def test_extract_protagonist_tags_returns_none_when_input_missing() -> None:
    assert extract_protagonist_tags_from_history(None) is None
    assert extract_protagonist_tags_from_history("") is None


def test_section_includes_protagonist_when_tags_provided() -> None:
    result = build_novelai_characters_section(
        [],
        protagonist_name="Hash",
        protagonist_tags="1boy, short black hair, blue eyes",
    )
    assert "Registered Characters" in result
    assert "Character 1 (Hash" in result
    assert "[protagonist]" in result
    assert "1boy, short black hair, blue eyes" in result
    assert "position: center" in result


def test_section_renumbers_supporting_characters_after_protagonist() -> None:
    records = [
        _rec(0, "Kana", "left", tags="1girl, blonde"),
        _rec(1, "Yuu", "right", tags="1girl, black hair"),
    ]
    result = build_novelai_characters_section(
        records,
        protagonist_name="Hash",
        protagonist_tags="1boy, short black hair",
    )
    p_protagonist = result.index("Character 1 (Hash")
    p_kana = result.index("Character 2 (Kana")
    p_yuu = result.index("Character 3 (Yuu")
    assert p_protagonist < p_kana < p_yuu


def test_section_empty_when_no_records_and_no_protagonist() -> None:
    assert (
        build_novelai_characters_section(
            [],
            protagonist_name="Hash",
            protagonist_tags=None,
        )
        == ""
    )
    assert (
        build_novelai_characters_section(
            [],
            protagonist_name=None,
            protagonist_tags="",
        )
        == ""
    )


def test_section_uses_default_name_when_protagonist_name_missing() -> None:
    result = build_novelai_characters_section(
        [],
        protagonist_name=None,
        protagonist_tags="1boy, solo",
    )
    assert "Character 1 (Protagonist" in result
