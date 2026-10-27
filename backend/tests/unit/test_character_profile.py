"""登場人物の性格プロフィール（正規化・自動生成のプロバイダ）のテスト。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.services import character_profile
from gateway.services.character_profile import (
    CharacterProfileGenerationError,
    character_persona_for_prompt,
    format_profile_line_ja,
    normalize_character_profile,
)


def test_normalize_coerces_enums_and_interests() -> None:
    profile = normalize_character_profile(
        {
            "personality": "x" * 900,
            "reaction_style": "angry",
            "gender": "other",
            "interests": "料理、手芸, 読書",
            "pronoun": "わたし",
        }
    )
    assert profile["reaction_style"] == "default"
    assert profile["gender"] == ""
    assert profile["interests"] == ["料理", "手芸", "読書"]
    assert len(profile["personality"]) == 500
    assert profile["tsf_attitude"] == ""
    assert profile["memo"] == ""


def test_normalize_keeps_valid_values() -> None:
    profile = normalize_character_profile(
        {"reaction_style": "shy", "gender": "woman", "interests": ["a", " ", "b"]}
    )
    assert profile["reaction_style"] == "shy"
    assert profile["gender"] == "woman"
    assert profile["interests"] == ["a", "b"]


def test_profile_line_empty_when_nothing_set() -> None:
    assert format_profile_line_ja(None) == ""
    assert format_profile_line_ja(normalize_character_profile({})) == ""


def _stub_services(monkeypatch, *, content: str, user_settings: dict):
    generate = AsyncMock(
        return_value=SimpleNamespace(content=content, cost_usd=0.0, provider="stub")
    )
    from gateway.services import llm_service as llm_module
    from gateway.services import session as session_module

    monkeypatch.setattr(llm_module.llm_service, "generate_text", generate)
    monkeypatch.setattr(
        session_module.session_store,
        "get_user_settings",
        AsyncMock(return_value=user_settings),
    )
    return generate


@pytest.mark.asyncio
async def test_generate_uses_feeling_provider_and_user_text_model(monkeypatch) -> None:
    content = (
        "```json\n"
        + json.dumps(
            {
                "personality": "明るい",
                "reaction_style": "cheerful",
                "pronoun": "わたし",
                "gender": "woman",
                "interests": ["料理"],
                "tsf_attitude": "興味がある",
            },
            ensure_ascii=False,
        )
        + "\n```"
    )
    generate = _stub_services(
        monkeypatch,
        content=content,
        user_settings={"novelai_text_model": "glm-4-6"},
    )

    profile = await character_profile.generate_character_profile(
        name="サクラ",
        appearance_natural="",
        appearance_tags="1girl, long hair",
        memo="料理が得意",
    )

    kwargs = generate.await_args.kwargs
    assert kwargs["novelai_model_override"] == "glm-4-6"
    # 別プロバイダへ振り替えない（FEELING_PROVIDER に従う）
    assert "provider_override" not in kwargs
    assert "サクラ" in kwargs["user_prompt"]
    assert "料理が得意" in kwargs["user_prompt"]
    assert profile["reaction_style"] == "cheerful"
    assert profile["gender"] == "woman"
    assert profile["memo"] == "料理が得意"


@pytest.mark.asyncio
async def test_generate_raises_on_invalid_json(monkeypatch) -> None:
    _stub_services(monkeypatch, content="性格は明るいです", user_settings={})
    with pytest.raises(CharacterProfileGenerationError):
        await character_profile.generate_character_profile(
            name="サクラ", appearance_natural="", appearance_tags="", memo=""
        )


@pytest.mark.asyncio
async def test_generate_extracts_speech_from_memo_when_asked(monkeypatch) -> None:
    content = json.dumps(
        {
            "personality": "明るい",
            "reaction_style": "cheerful",
            "pronoun": "あたし",
            "gender": "woman",
            "interests": [],
            "tsf_attitude": "",
            "speech_style": "砕けたタメ口",
            "sample_lines": ["「ほら、行くよ」", "「しょうがないなあ」"],
        },
        ensure_ascii=False,
    )
    generate = _stub_services(monkeypatch, content=content, user_settings={})

    profile = await character_profile.generate_character_profile(
        name="サクラ",
        appearance_natural="",
        appearance_tags="",
        memo="タメ口で話す。口癖は「ほら、行くよ」「しょうがないなあ」",
        include_speech=True,
    )

    assert "sample_lines" in generate.await_args.kwargs["system_prompt"]
    assert profile["speech_style"] == "砕けたタメ口"
    # 配列で返っても 1 行に 1 つの形にそろえる
    assert profile["sample_lines"] == "「ほら、行くよ」\n「しょうがないなあ」"


@pytest.mark.asyncio
async def test_generate_ignores_speech_unless_asked(monkeypatch) -> None:
    content = json.dumps(
        {
            "personality": "明るい",
            "reaction_style": "cheerful",
            "pronoun": "あたし",
            "gender": "woman",
            "speech_style": "砕けたタメ口",
            "sample_lines": "「ほら」",
        },
        ensure_ascii=False,
    )
    generate = _stub_services(monkeypatch, content=content, user_settings={})

    profile = await character_profile.generate_character_profile(
        name="サクラ", appearance_natural="", appearance_tags="", memo="タメ口"
    )

    # 通常プレイの登場人物の下書きでは、話し方の項目を求めず、返っても捨てる
    assert "sample_lines" not in generate.await_args.kwargs["system_prompt"]
    assert profile["speech_style"] == ""
    assert profile["sample_lines"] == ""


def test_persona_for_prompt_trims_and_drops_empty_fields() -> None:
    profile = normalize_character_profile(
        {
            "personality": "p" * 500,
            "reaction_style": "default",
            "pronoun": "僕",
            "gender": "man",
            "interests": ["a", "b", "c", "d", "e", "f"],
            "memo": "種",
            "greeting": "やあ",
            "sample_lines": "\n".join(
                f"セリフ{index:02d}" + "。" * 20 for index in range(30)
            ),
            "knowledge": "k" * 900,
        }
    )
    persona = character_persona_for_prompt(" ユウ ", profile)
    assert persona["name"] == "ユウ"
    assert persona["gender"] == "male"
    assert len(persona["personality"]) == 300
    assert persona["interests"] == ["a", "b", "c", "d", "e"]
    # セリフ例は行の途中で切らない
    assert len(persona["sample_lines"]) <= 300
    assert all(
        line.startswith("セリフ") for line in persona["sample_lines"].split("\n")
    )
    # 1 行しかない長文は上限で切る
    assert len(persona["knowledge"]) == 600
    # 既定の反応・自動生成の種・挨拶・空の項目は載せない
    for key in ("reaction_style", "memo", "greeting", "tsf_attitude", "speech_style"):
        assert key not in persona
