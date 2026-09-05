"""履歴遡及対象とプロンプト反映の単体テスト。"""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from gateway.databases.models import (
    Conversation as ConversationORM,
)
from gateway.databases.models import (
    History as HistoryORM,
)
from gateway.databases.models import (
    Session as SessionORM,
)
from gateway.databases.models import (
    User,
)
from gateway.models import PlayRequest
from gateway.routes.game_router import PlayStreamRequest, preview_prompt
from gateway.services.game_service import game_service
from gateway.services.history_context import (
    build_history_context,
    resolve_history_lookback_enabled,
)
from gateway.services.session import DatabaseSessionStore


def test_operation_defaults_preserve_existing_behavior() -> None:
    assert resolve_history_lookback_enabled(None, instruction_type="action") is True
    assert (
        resolve_history_lookback_enabled(None, instruction_type="conversation") is True
    )
    assert resolve_history_lookback_enabled(None, instruction_type="dress_up") is False
    assert (
        resolve_history_lookback_enabled(None, transformation_type="reality") is False
    )


def test_explicit_value_overrides_operation_default() -> None:
    assert resolve_history_lookback_enabled(False, instruction_type="action") is False
    assert resolve_history_lookback_enabled(True, instruction_type="dress_up") is True


def test_history_context_keeps_chronological_order_and_labels() -> None:
    result = build_history_context(
        [
            ("dress_up", "白いドレスに着替える"),
            ("conversation", "似合っている？"),
            ("reality_alter", "ここではこれが制服だったことにする"),
        ]
    )

    assert result.index("白いドレス") < result.index("似合っている")
    assert result.index("似合っている") < result.index("制服だった")
    assert "[着替]" in result
    assert "[会話]" in result
    assert "[改変]" in result
    assert "過去の変更を再実行しない" in result


@pytest.mark.asyncio
async def test_recent_history_helpers_select_latest_entries_in_chronological_order(
    isolated_db, tmp_path: Path
) -> None:
    factory = isolated_db.async_factory
    start = datetime(2026, 1, 1, 12, 0, 0)

    async with factory() as db_session:
        db_session.add(User(id="history-user"))
        db_session.add(
            SessionORM(
                id="history-session",
                user_id="history-user",
                current_image_path="images/current.png",
            )
        )
        db_session.add_all(
            [
                HistoryORM(
                    id="history-old",
                    session_id="history-session",
                    instruction="古すぎる指示",
                    instruction_type="dress_up",
                    image_path="images/old.png",
                    created_at=start,
                ),
                ConversationORM(
                    id="conversation-user-old",
                    session_id="history-session",
                    role="user",
                    content="少し古い会話",
                    instruction_type="conversation",
                    created_at=start + timedelta(minutes=1),
                ),
                HistoryORM(
                    id="history-recent",
                    session_id="history-session",
                    instruction="直近の行動",
                    instruction_type="action",
                    image_path="images/recent.png",
                    created_at=start + timedelta(minutes=2),
                ),
                ConversationORM(
                    id="conversation-assistant",
                    session_id="history-session",
                    role="assistant",
                    content="AI応答",
                    instruction_type="conversation",
                    created_at=start + timedelta(minutes=3),
                ),
                ConversationORM(
                    id="conversation-user-recent",
                    session_id="history-session",
                    role="user",
                    content="直近の会話",
                    instruction_type="conversation",
                    created_at=start + timedelta(minutes=4),
                ),
            ]
        )
        await db_session.commit()

    store = DatabaseSessionStore(history_images_dir=tmp_path / "history-images")
    timeline = await store.get_recent_instructions("history-session", limit=2)
    conversation = await store.get_conversation_history("history-session", limit=2)

    assert timeline == [
        ("action", "直近の行動"),
        ("conversation", "直近の会話"),
    ]
    assert [message.content for message in conversation] == [
        "AI応答",
        "直近の会話",
    ]


def test_request_models_accept_optional_history_flag() -> None:
    assert PlayRequest(instruction="着替える").use_history_lookback is None
    assert PlayStreamRequest(instruction="着替える").use_history_lookback is None
    assert (
        PlayRequest(
            instruction="着替える", use_history_lookback=True
        ).use_history_lookback
        is True
    )


@pytest.mark.asyncio
async def test_image_and_feeling_prompts_receive_history_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_instructions: list[str] = []
    feeling_prompts: list[str] = []

    async def fake_generate_image_edit_prompt(**kwargs):
        image_instructions.append(kwargs["instruction"])
        return SimpleNamespace(content="generated", provider="test", cost_usd=None)

    async def fake_generate_feeling(**kwargs):
        feeling_prompts.append(kwargs["user_prompt"])
        return SimpleNamespace(content="generated", provider="test", cost_usd=None)

    monkeypatch.setattr(
        "gateway.services.game_service.llm_service.generate_image_edit_prompt",
        fake_generate_image_edit_prompt,
    )
    monkeypatch.setattr(
        "gateway.services.game_service.llm_service.generate_feeling",
        fake_generate_feeling,
    )

    history_context = build_history_context([("action", "カフェへ移動する")])
    await game_service._generate_image_edit_prompt(
        instruction="制服に着替える",
        current_description="私服",
        use_memory=False,
        history_context=history_context,
    )
    await game_service._generate_feeling(
        before_desc="私服",
        after_desc="制服",
        instruction="制服に着替える",
        pronoun="僕",
        history_context=history_context,
    )

    assert "カフェへ移動する" in image_instructions[0]
    assert "カフェへ移動する" in feeling_prompts[0]


@pytest.mark.asyncio
async def test_streaming_feeling_modes_receive_history_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_prompts: list[str] = []

    async def fake_stream_feeling(**kwargs):
        captured_prompts.append(kwargs["user_prompt"])
        yield "ok"

    monkeypatch.setattr(game_service, "_stream_feeling", fake_stream_feeling)
    history_context = build_history_context([("conversation", "過去の会話")])

    async for _ in game_service._generate_feeling_stream(
        before_desc="私服",
        after_desc="制服",
        instruction="制服に着替える",
        pronoun="僕",
        use_memory=False,
        history_context=history_context,
    ):
        pass
    async for _ in game_service._generate_self_mode_feeling_stream(
        before_desc="私服",
        after_desc="制服",
        instruction="制服に着替える",
        self_profile={"personality": "慎重", "pronoun": "僕"},
        use_memory=False,
        history_context=history_context,
    ):
        pass
    async for _ in game_service._generate_reality_feeling_stream(
        before_desc="元の世界",
        after_desc="改変後の世界",
        instruction="世界を改変する",
        pronoun="僕",
        use_memory=False,
        history_context=history_context,
    ):
        pass
    async for _ in game_service._generate_feeling_stream(
        before_desc="私服",
        after_desc="制服",
        instruction="制服に着替える",
        pronoun="僕",
        use_memory=False,
        history_context="",
    ):
        pass

    assert all("過去の会話" in prompt for prompt in captured_prompts[:3])
    assert "過去の会話" not in captured_prompts[3]


@pytest.mark.asyncio
async def test_reality_image_prompt_receives_history_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_prompts: list[str] = []

    async def fake_generate_text(**kwargs):
        captured_prompts.append(kwargs["user_prompt"])
        return SimpleNamespace(content="generated", provider="test", cost_usd=None)

    monkeypatch.setattr(
        "gateway.services.game_service.llm_service.generate_text",
        fake_generate_text,
    )
    history_context = build_history_context([("action", "過去の行動")])

    await game_service._generate_reality_edit_prompt(
        instruction="世界を改変する",
        current_description="元の世界",
        use_memory=False,
        history_context=history_context,
    )

    assert "過去の行動" in captured_prompts[0]


@pytest.mark.asyncio
async def test_preview_route_propagates_history_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_preview_prompts(**kwargs):
        captured.update(kwargs)
        return {
            "image_edit_prompt": "image",
            "feeling_system_prompt": "system",
            "feeling_user_prompt": "user",
            "instruction_type": "dress_up",
            "novelai_tag_prompt": None,
        }

    monkeypatch.setattr(game_service, "preview_prompts", fake_preview_prompts)

    await preview_prompt(PlayRequest(instruction="着替える", use_history_lookback=True))

    assert captured["use_history_lookback"] is True
