"""LLMService のプロバイダー振り分け（_client_for / _vision_or_edit_client_for）の特性テスト。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.services.llm_service import LLMResult, LLMService
from gateway.settings.config import settings


def _stream_recorder(chunks: list[str], calls: list[dict]):
    async def _stream(system_prompt, user_prompt, **kwargs):
        calls.append({"system": system_prompt, "user": user_prompt, **kwargs})
        for chunk in chunks:
            yield chunk

    return _stream


@pytest.fixture
def service(monkeypatch):
    openrouter_stream_calls: list[dict] = []
    novelai_stream_calls: list[dict] = []
    litellm_stream_calls: list[dict] = []
    fakes = SimpleNamespace(
        openrouter=SimpleNamespace(
            describe_image=AsyncMock(
                return_value=LLMResult(content="or-vision", provider="openrouter")
            ),
            generate_text=AsyncMock(
                return_value=LLMResult(content="or-text", provider="openrouter")
            ),
            generate_text_stream=_stream_recorder(["o", "r"], openrouter_stream_calls),
            stream_calls=openrouter_stream_calls,
        ),
        novelai=SimpleNamespace(
            generate_text=AsyncMock(
                return_value=LLMResult(content="nai-text", provider="novelai")
            ),
            generate_text_stream=_stream_recorder(["n", "a"], novelai_stream_calls),
            stream_calls=novelai_stream_calls,
        ),
        litellm=SimpleNamespace(
            describe_image=AsyncMock(return_value="ll-vision"),
            generate_feeling=AsyncMock(return_value="ll-feeling"),
            generate_text=AsyncMock(return_value="ll-text"),
            generate_feeling_stream=_stream_recorder(["l", "l"], litellm_stream_calls),
            generate_image_edit_prompt=AsyncMock(return_value="ll-edit"),
            stream_calls=litellm_stream_calls,
        ),
    )
    svc = LLMService()
    monkeypatch.setattr(svc, "_get_openrouter_client", lambda: fakes.openrouter)
    monkeypatch.setattr(svc, "_get_novelai_client", lambda: fakes.novelai)
    monkeypatch.setattr(svc, "_get_litellm_client", lambda: fakes.litellm)
    monkeypatch.setattr(settings, "feeling_provider", "selfhost")
    monkeypatch.setattr(settings, "image_description_provider", "selfhost")
    return svc, fakes


async def test_feeling_and_text_use_the_matching_litellm_model(service) -> None:
    svc, fakes = service

    feeling = await svc.generate_feeling("sys", "user")
    text = await svc.generate_text("sys", "user")

    assert (feeling.content, feeling.provider, feeling.model) == (
        "ll-feeling",
        "selfhost",
        settings.litellm_feeling_model,
    )
    assert (text.content, text.model) == ("ll-text", settings.litellm_llm_model)
    fakes.litellm.generate_feeling.assert_awaited_once_with("sys", "user")
    fakes.litellm.generate_text.assert_awaited_once_with("sys", "user")


async def test_novelai_receives_model_override_and_optional_max_tokens(service) -> None:
    svc, fakes = service

    await svc.generate_feeling(
        "sys", "user", provider_override="novelai", novelai_model_override="glm-4-6"
    )
    await svc.generate_feeling(
        "sys", "user", provider_override="novelai", max_tokens=64
    )
    await svc.generate_text("sys", "user", provider_override="novelai")

    calls = [c.kwargs for c in fakes.novelai.generate_text.await_args_list]
    assert calls[0] == {"model_override": "glm-4-6"}
    assert calls[1] == {"model_override": None, "max_tokens": 64}
    assert calls[2] == {"model_override": None}


async def test_openrouter_uses_generate_text_for_every_purpose(service) -> None:
    svc, fakes = service

    feeling = await svc.generate_feeling("sys", "user", provider_override="openrouter")
    text = await svc.generate_text("sys", "user", provider_override="OpenRouter")

    assert feeling.provider == text.provider == "openrouter"
    assert fakes.openrouter.generate_text.await_count == 2


async def test_unknown_provider_falls_back_to_selfhost(service) -> None:
    svc, fakes = service

    result = await svc.generate_text("sys", "user", provider_override="comfyui")

    assert result.provider == "selfhost"
    fakes.litellm.generate_text.assert_awaited_once()


async def test_vision_and_edit_prompt_have_no_novelai_path(service) -> None:
    svc, fakes = service

    vision = await svc.describe_image(b"img", "describe", provider_override="novelai")
    edit = await svc.generate_image_edit_prompt(
        instruction="赤いドレス",
        current_description="白いシャツ",
        provider_override="novelai",
        nsfw_mode=False,
    )

    assert (vision.content, vision.provider, vision.model) == (
        "ll-vision",
        "selfhost",
        settings.litellm_llava_model,
    )
    assert (edit.content, edit.provider) == ("ll-edit", "selfhost")
    edit_kwargs = fakes.litellm.generate_image_edit_prompt.await_args.kwargs
    assert edit_kwargs["provider"] == "novelai"
    assert edit_kwargs["instruction"] == "赤いドレス"


async def test_openrouter_edit_prompt_is_built_from_the_shared_prompt_builders(
    service,
) -> None:
    svc, fakes = service

    await svc.generate_image_edit_prompt(
        instruction="赤いドレス",
        current_description="白いシャツ",
        provider_override="openrouter",
        extra_system_suffix="\nSUFFIX",
    )

    system_prompt, user_prompt = fakes.openrouter.generate_text.await_args.args
    assert system_prompt.endswith("SUFFIX")
    assert "赤いドレス" in user_prompt


async def test_stream_passes_provider_specific_arguments(service) -> None:
    svc, fakes = service
    history = [{"role": "user", "content": "before"}]

    def on_usage(cost):
        return None

    assert [
        c
        async for c in svc.generate_feeling_stream(
            "sys",
            "user",
            provider_override="openrouter",
            usage_callback=on_usage,
            history=history,
        )
    ] == ["o", "r"]
    assert fakes.openrouter.stream_calls[0] == {
        "system": "sys",
        "user": "user",
        "usage_callback": on_usage,
        "history": history,
    }

    assert [
        c
        async for c in svc.generate_feeling_stream(
            "sys",
            "user",
            provider_override="novelai",
            novelai_model_override="glm-4-6",
            max_tokens=32,
            history=history,
        )
    ] == ["n", "a"]
    assert fakes.novelai.stream_calls[0] == {
        "system": "sys",
        "user": "user",
        "model_override": "glm-4-6",
        "history": history,
        "max_tokens": 32,
    }

    assert [c async for c in svc.generate_feeling_stream("sys", "user")] == [
        "l",
        "l",
    ]
    assert fakes.litellm.stream_calls[0] == {
        "system": "sys",
        "user": "user",
        "history": None,
    }
