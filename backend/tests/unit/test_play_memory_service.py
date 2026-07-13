"""プレイメモサービスの単体テスト。"""

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from gateway.models import PlayMemoryUpdateRequest
from gateway.services import llm_service as llm_module
from gateway.services import play_memory_service as module


class StubSessionStore:
    def __init__(self, memory: object) -> None:
        self.memory = memory
        self.saved: str | None = None

    async def get_play_memory(self, _session_id: str) -> object:
        return self.memory

    async def save_play_memory_system_text(self, _session_id: str, text: str) -> object:
        self.saved = text
        return self.memory


@pytest.mark.asyncio
async def test_build_context_respects_user_then_system_order(monkeypatch) -> None:
    store = StubSessionStore(
        SimpleNamespace(
            user_enabled=True,
            user_text="ユーザー指定",
            system_enabled=True,
            system_text="自動要約",
        )
    )
    monkeypatch.setattr(module, "session_store", store)

    result = await module.PlayMemoryService().build_context("s1", enabled=True)

    assert result.index("ユーザー指定") < result.index("自動要約")
    assert "今回のユーザーの明示指示を常に最優先" in result


@pytest.mark.asyncio
async def test_build_context_returns_empty_when_master_is_disabled(monkeypatch) -> None:
    store = StubSessionStore(None)
    monkeypatch.setattr(module, "session_store", store)

    result = await module.PlayMemoryService().build_context("s1", enabled=False)

    assert result == ""


@pytest.mark.asyncio
async def test_rolling_update_skips_disabled_system_memory(monkeypatch) -> None:
    store = StubSessionStore(
        SimpleNamespace(system_enabled=False, system_text="以前の内容")
    )
    monkeypatch.setattr(module, "session_store", store)

    result = await module.PlayMemoryService().update_rolling(
        "s1",
        interaction_type="conversation",
        user_input="こんにちは",
        result_text="応答",
    )

    assert result is True
    assert store.saved is None


@pytest.mark.asyncio
async def test_text_generation_is_serialized_across_sessions(monkeypatch) -> None:
    active_calls = 0
    max_active_calls = 0

    async def generate_text(
        _system_prompt: str, _user_prompt: str, **_kwargs: object
    ) -> object:
        nonlocal active_calls, max_active_calls
        active_calls += 1
        max_active_calls = max(max_active_calls, active_calls)
        await asyncio.sleep(0)
        active_calls -= 1
        return SimpleNamespace(content="自動メモ")

    monkeypatch.setattr(
        llm_module,
        "llm_service",
        SimpleNamespace(generate_text=generate_text),
    )
    service = module.PlayMemoryService()

    await asyncio.gather(
        service._generate(
            previous="",
            interactions=[("conversation", "入力1", "応答1")],
            language="ja",
        ),
        service._generate(
            previous="",
            interactions=[("conversation", "入力2", "応答2")],
            language="ja",
        ),
    )

    assert max_active_calls == 1


def test_user_memory_rejects_more_than_4000_characters() -> None:
    with pytest.raises(ValidationError):
        PlayMemoryUpdateRequest(user_text="x" * 4001)
