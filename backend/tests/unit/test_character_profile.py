"""登場人物の性格プロフィール（正規化・自動生成のプロバイダ）のテスト。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.services import character_profile
from gateway.services.character_profile import (
    CharacterProfileGenerationError,
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
