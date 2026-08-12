"""画像のみモードの回帰テスト。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from gateway.services.image_only_prompts import (
    build_image_only_edit_prompt,
    get_image_only_edit_system_prompt,
)


def test_play_stream_request_accepts_image_only() -> None:
    from gateway.routes.game_router import PlayStreamRequest

    request = PlayStreamRequest(
        instruction="自由に画像を編集する",
        instruction_type="image_only",
    )

    assert request.instruction_type == "image_only"


def test_image_only_prompt_allows_free_edits_and_preserves_identity() -> None:
    system_prompt = get_image_only_edit_system_prompt("selfhost")
    user_prompt = build_image_only_edit_prompt(
        "赤いドレスに着替えて夜の街に移動する",
        "A person with short black hair in a room",
    )

    assert "clothing, appearance, pose" in system_prompt
    assert "Preserve the subject's identity" in system_prompt
    assert "赤いドレスに着替えて夜の街に移動する" in user_prompt
    assert "short black hair" in user_prompt


def test_image_only_prompt_uses_novelai_tags() -> None:
    system_prompt = get_image_only_edit_system_prompt("novelai", nsfw_mode=True)

    assert "Danbooru-style tags" in system_prompt
    assert "nsfw, very aesthetic, best quality" in system_prompt


def _configure_image_only_service(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    Any,
    SimpleNamespace,
    AsyncMock,
    AsyncMock,
]:
    from gateway.services.game_service import GameService, llm_service, session_store
    from gateway.settings.config import settings

    service = GameService()
    session = SimpleNamespace(
        id="session-image-only",
        self_mode=False,
        transformation_count=4,
    )
    monkeypatch.setattr(settings, "image_provider", "selfhost")
    monkeypatch.setattr(settings, "image_description_provider", "selfhost")
    monkeypatch.setattr(
        service,
        "_get_or_create_session_for_stream",
        AsyncMock(return_value=(session, None, b"before-image")),
    )
    monkeypatch.setattr(service, "_load_custom_session_metadata", lambda _id: {})
    monkeypatch.setattr(
        "gateway.services.game_service.settings_service.get_history_lookback_count",
        lambda _id: 10,
    )
    monkeypatch.setattr(
        session_store,
        "get_user_settings",
        AsyncMock(
            return_value={
                "nsfw_mode": False,
                "difficulty": "normal",
                "language": "ja",
                "novelai_text_model": None,
            }
        ),
    )
    monkeypatch.setattr(
        session_store,
        "get_latest_history",
        AsyncMock(return_value=SimpleNamespace(after_description="previous prompt")),
    )
    monkeypatch.setattr(
        session_store,
        "get_session_attribute_texts",
        AsyncMock(return_value=[]),
    )
    stats_mock = AsyncMock()
    monkeypatch.setattr(session_store, "get_or_create_session_stats", stats_mock)
    add_history_mock = AsyncMock(
        return_value=SimpleNamespace(
            id="history-image-only",
            image_path="history_images/image-only.png",
        )
    )
    monkeypatch.setattr(session_store, "add_history", add_history_mock)
    update_session_mock = AsyncMock()
    monkeypatch.setattr(session_store, "update_session", update_session_mock)
    monkeypatch.setattr(
        service,
        "_describe_image",
        AsyncMock(return_value=("current image description", 0.01)),
    )
    monkeypatch.setattr(
        service,
        "_generate_image_only_edit_prompt",
        AsyncMock(return_value=("final image prompt", 0.02)),
    )
    monkeypatch.setattr(
        service,
        "_get_anlas_event",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(llm_service, "generate_feeling_stream", AsyncMock())
    return service, session, add_history_mock, update_session_mock


@pytest.mark.asyncio
async def test_image_only_saves_image_without_feeling_or_stats(monkeypatch) -> None:
    from gateway.services.game_service import llm_service, session_store

    service, session, add_history_mock, update_session_mock = (
        _configure_image_only_service(monkeypatch)
    )
    monkeypatch.setattr(
        service,
        "_generate_image",
        AsyncMock(return_value=(b"generated-image", 0.15, 12345)),
    )

    events = [
        event
        async for event in service.play_with_stream(
            session_id=session.id,
            character_id=None,
            character_image=None,
            instruction="自由に画像を編集する",
            instruction_type="image_only",
        )
    ]

    assert [event.type for event in events] == ["image", "cost", "complete"]
    assert events[-1].data["transformation_count"] == 4
    assert events[-1].data["feeling_text"] == ""
    add_history_mock.assert_awaited_once_with(
        session_id=session.id,
        instruction="自由に画像を編集する",
        image_data=b"generated-image",
        feeling_text="",
        before_description="current image description",
        after_description="final image prompt",
        instruction_type="image_only",
        seed=12345,
    )
    update_session_mock.assert_awaited_once_with(
        session_id=session.id,
        current_image_path="history_images/image-only.png",
    )
    session_store.get_or_create_session_stats.assert_not_awaited()
    llm_service.generate_feeling_stream.assert_not_awaited()


@pytest.mark.asyncio
async def test_image_only_failure_does_not_save_history(monkeypatch) -> None:
    from gateway.services.game_service import GameServiceError

    service, session, add_history_mock, update_session_mock = (
        _configure_image_only_service(monkeypatch)
    )
    monkeypatch.setattr(
        service,
        "_generate_image",
        AsyncMock(side_effect=GameServiceError("画像生成に失敗")),
    )

    events = [
        event
        async for event in service.play_with_stream(
            session_id=session.id,
            character_id=None,
            character_image=None,
            instruction="失敗する画像編集",
            instruction_type="image_only",
        )
    ]

    assert [event.type for event in events] == ["error"]
    add_history_mock.assert_not_awaited()
    update_session_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("use_memory", "expected_instruction"),
    [
        (
            True,
            "画像を編集する\n\n[ユーザーメモ]\n青い服を好む\n\n[自動メモ]\n夜の街にいる",
        ),
        (False, "画像を編集する"),
    ],
)
async def test_image_only_applies_play_memory_only_when_image_memory_is_enabled(
    monkeypatch,
    use_memory: bool,
    expected_instruction: str,
) -> None:
    from gateway.services.play_memory_service import play_memory_service

    service, session, _, _ = _configure_image_only_service(monkeypatch)
    play_context = "\n\n[ユーザーメモ]\n青い服を好む\n\n[自動メモ]\n夜の街にいる"
    build_context_mock = AsyncMock(return_value=play_context)
    monkeypatch.setattr(play_memory_service, "build_context", build_context_mock)
    monkeypatch.setattr(
        service,
        "_generate_image",
        AsyncMock(return_value=(b"generated-image", None, 12345)),
    )

    events = [
        event
        async for event in service.play_with_stream(
            session_id=session.id,
            character_id=None,
            character_image=None,
            instruction="画像を編集する",
            instruction_type="image_only",
            use_memory=use_memory,
            use_play_memory=True,
        )
    ]

    assert events[-1].type == "complete"
    build_context_mock.assert_awaited_once_with(
        session.id,
        enabled=True,
        language="ja",
    )
    service._generate_image_only_edit_prompt.assert_awaited_once()
    prompt_call = service._generate_image_only_edit_prompt.await_args.kwargs
    assert prompt_call["instruction"] == expected_instruction
    assert prompt_call["use_memory"] is use_memory
