"""services/llm_json.py: フェンス除去・JSON 抽出・検証と修復ループ。"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field, ValidationError

from gateway.services.llm_json import (
    StructuredOutputError,
    extract_json_object,
    generate_validated,
    strip_code_fence,
    validate_model_json,
)


class _Out(BaseModel):
    title: str = Field(max_length=10)
    count: int = 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('```\n{"a": 1}\n```', '{"a": 1}'),
        ('{"a": 1}', '{"a": 1}'),
        ('  {"a": 1}  ', '{"a": 1}'),
        ('```json\n{"a": 1}```', '{"a": 1}'),
        ('```json\n{"a": 1}\n```\n```', '{"a": 1}'),
        ('{"a": 1}\n```', '{"a": 1}'),
        ("", ""),
        (None, ""),
        ("「そのまま」", "「そのまま」"),
    ],
)
def test_strip_code_fence(raw, expected) -> None:
    assert strip_code_fence(raw) == expected


def test_extract_json_object_ignores_surrounding_prose() -> None:
    assert extract_json_object(
        'Here you go:\n```json\n{"a": {"b": 1}}\n```\nDone.'
    ) == ('{"a": {"b": 1}}')
    assert extract_json_object("no braces here") == "no braces here"
    assert extract_json_object("} {") == "} {"


def test_validate_model_json_accepts_fenced_and_control_characters() -> None:
    assert validate_model_json(_Out, '```json\n{"title": "ok"}\n```').title == "ok"
    # 文字列内の生の改行は厳密パースでは不正だが、strict=False で救済する
    assert validate_model_json(_Out, '{"title": "a\nb"}').title == "a\nb"
    with pytest.raises(ValidationError):
        validate_model_json(_Out, '{"title": "this title is far too long"}')
    with pytest.raises(ValidationError):
        validate_model_json(_Out, "not json at all")


async def test_generate_validated_returns_first_valid_output() -> None:
    calls: list[tuple[str, str]] = []

    async def generate(system: str, user: str) -> str:
        calls.append((system, user))
        return '{"title": "fine"}'

    result = await generate_validated(
        _Out, generate=generate, system_prompt="SYS", user_prompt="USER"
    )
    assert result.title == "fine"
    assert calls == [("SYS", "USER")]


async def test_generate_validated_repairs_once_with_errors_and_source() -> None:
    calls: list[tuple[str, str]] = []
    outputs = iter(['{"title": "this title is far too long"}', '{"title": "short"}'])

    async def generate(system: str, user: str) -> str:
        calls.append((system, user))
        return next(outputs)

    result = await generate_validated(
        _Out,
        generate=generate,
        system_prompt="SYS",
        user_prompt="USER",
        repair_system_prompt="REPAIR-SYS",
    )
    assert result.title == "short"
    assert len(calls) == 2
    assert calls[1][0] == "REPAIR-SYS"
    assert "Fix these validation errors" in calls[1][1]
    assert "this title is far too long" in calls[1][1]


async def test_generate_validated_raises_after_second_failure() -> None:
    async def generate(system: str, user: str) -> str:
        return '{"title": "this title is far too long"}'

    with pytest.raises(StructuredOutputError) as info:
        await generate_validated(
            _Out,
            generate=generate,
            system_prompt="SYS",
            user_prompt="USER",
            repair_prompt=lambda err, raw: f"custom:{raw}",
        )
    assert info.value.model_name == "_Out"
    assert info.value.raw == info.value.repaired
    assert isinstance(info.value.first_error, ValidationError)
    assert isinstance(info.value.second_error, ValidationError)
