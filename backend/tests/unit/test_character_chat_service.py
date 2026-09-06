"""キャラチャットのスレッド CRUD と 1 発言のストリーム(判定 → 返答 → 保存 → 着替え → 要約)。"""

from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from sqlalchemy import select

from gateway.databases.models import CharacterChatMessage, CharacterChatThread, User
from gateway.databases.models import History as HistoryORM
from gateway.databases.models import PlaySummary as PlaySummaryORM
from gateway.databases.models import Session as SessionORM
from gateway.databases.models import SessionStats as SessionStatsORM
from gateway.services import character_chat_service as module
from gateway.services.character_chat_service import (
    CharacterChatError,
    CharacterChatService,
    normalize_chat_reply,
)
from gateway.services.session import DEFAULT_USER_ID

PLAN_EMPTY = json.dumps({"lookups": [], "appearance_request": None})


def _png(color: str = "red") -> bytes:
    buf = BytesIO()
    Image.new("RGB", (32, 48), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def service(isolated_db, tmp_path: Path, monkeypatch) -> CharacterChatService:
    svc = CharacterChatService()
    svc._images_dir = tmp_path / "character_chat_images"
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    monkeypatch.setattr(module, "base_portrait_dir", lambda: bundled)
    monkeypatch.setattr(
        module.settings_service,
        "get_memory_text",
        AsyncMock(return_value="メイド服を好む"),
    )
    return svc


async def _seed_session(factory, image: Path, *, session_id: str = "sess-1") -> None:
    image.write_bytes(_png())
    async with factory() as db:
        if await db.get(User, DEFAULT_USER_ID) is None:
            db.add(User(id=DEFAULT_USER_ID))
        db.add(
            SessionORM(
                id=session_id,
                user_id=DEFAULT_USER_ID,
                current_image_path=str(image),
                character_id="char1",
                transformation_count=2,
            )
        )
        db.add(
            HistoryORM(
                id=f"{session_id}-h1",
                session_id=session_id,
                instruction="メイド服に着替える",
                image_path=str(image),
                feeling_text="恥ずかしい",
                after_description="1girl, brown hair, black eyes, maid dress, apron, standing",
                instruction_type="dress_up",
                created_at=datetime(2026, 9, 1, 10, 0, 0),
            )
        )
        db.add(
            SessionStatsORM(
                session_id=session_id, bloom=30, shame=60, adaptation=10, nsfw_mode=0
            )
        )
        db.add(
            PlaySummaryORM(
                session_id=session_id,
                title="メイドの一日",
                summary="メイド服で給仕をした",
                timeline_json="[]",
            )
        )
        await db.commit()


def _llm_router(
    *, plan: str = PLAN_EMPTY, appearance: str | None = None, summary: str = "要約"
):
    """generate_text の差し替え。system prompt の種類で返す JSON を切り替える。"""
    calls: list[str] = []

    async def fake_generate_text(system_prompt, user_prompt, **kwargs):
        if "retrieval planner" in system_prompt:
            calls.append("plan")
            return SimpleNamespace(content=plan, cost_usd=0.001)
        if "appearance tags" in system_prompt:
            calls.append("appearance")
            return SimpleNamespace(content=appearance or "{}", cost_usd=0.001)
        calls.append("summary")
        return SimpleNamespace(content=summary, cost_usd=0.001)

    return fake_generate_text, calls


def _fake_stream(chunks: list[str], captured: dict):
    async def fake_stream(system_prompt, user_prompt, **kwargs):
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        captured["history"] = kwargs.get("history")
        for chunk in chunks:
            yield chunk

    return fake_stream


async def _collect(generator) -> list[dict]:
    return [event async for event in generator]


def test_normalize_chat_reply_strips_prefix_and_keeps_paragraphs() -> None:
    assert normalize_chat_reply(
        "セレナ「こんにちは。\n\nお元気ですか？」", "セレナ"
    ) == ("こんにちは。\n\nお元気ですか？")
    assert (
        normalize_chat_reply("[expression=happy gesture=nod]\nやあ", "セレナ") == "やあ"
    )
    assert normalize_chat_reply("", "セレナ") == ""


@pytest.mark.asyncio
async def test_base_thread_is_idempotent(service: CharacterChatService) -> None:
    first = await service.get_or_create_base_thread()
    second = await service.get_or_create_base_thread()
    assert first["id"] == second["id"]
    assert first["kind"] == "base"
    assert first["name"] == "セレナ"
    assert first["portrait_missing"] is True
    assert first["portrait_url"] is None
    assert first["message_count"] == 0
    assert "silver hair" in first["appearance"]["identity_tags"]
    threads = await service.list_threads()
    assert [thread["id"] for thread in threads] == [first["id"]]


@pytest.mark.asyncio
async def test_base_thread_uses_bundled_portrait(
    service: CharacterChatService, tmp_path: Path
) -> None:
    (tmp_path / "bundled" / "serena.png").write_bytes(_png("blue"))
    thread = await service.get_or_create_base_thread()
    assert thread["portrait_missing"] is False
    assert thread["portrait_url"].endswith(
        f"/character-chat/images/{thread['id']}/serena.png"
    )
    assert (
        service.image_file(thread["id"], "serena.png")
        == tmp_path / "bundled" / "serena.png"
    )
    with pytest.raises(CharacterChatError):
        service.image_file(thread["id"], "../../missing.png")


@pytest.mark.asyncio
async def test_create_session_thread_snapshots_persona(
    service: CharacterChatService, isolated_db, tmp_path: Path
) -> None:
    await _seed_session(isolated_db.async_factory, tmp_path / "start.png")
    # 履歴を指定しないときは現在の姿と現在の統計をそのまま写す
    thread = await service.create_session_thread(
        source_session_id="sess-1", source_history_id=None
    )
    assert thread["kind"] == "session"
    assert thread["name"] == "水瀬ユウヤ"
    assert thread["pronoun"] == "僕"
    assert thread["portrait_missing"] is False
    assert thread["appearance"]["portrait_kind"] == "scene"
    assert (
        thread["appearance"]["identity_tags"] == "1girl, brown hair, black eyes, apron"
    )
    assert thread["appearance"]["clothing_tags"] == "maid dress"
    assert thread["appearance"]["source"]["session_id"] == "sess-1"
    copied = list((service._images_dir / thread["id"]).glob("source-*.png"))
    assert len(copied) == 1
    assert service.image_file(thread["id"], copied[0].name) == copied[0]

    async with isolated_db.async_factory() as db:
        row = await db.get(CharacterChatThread, thread["id"])
        persona = json.loads(row.persona_json)
        assert persona["character_name"] == "水瀬ユウヤ"
        assert persona["stats"]["bloom"] == 30
        assert persona["transformation_count"] == 2
        assert persona["timeline"][0]["text"] == "メイド服に着替える"
        assert row.source_session_id == "sess-1"
        assert row.source_history_id is None

    # 履歴時点を指定すると統計はその時点の再構築値になり、変身回数は経緯から数える
    at_point = await service.create_session_thread(
        source_session_id="sess-1", source_history_id="sess-1-h1"
    )
    async with isolated_db.async_factory() as db:
        row = await db.get(CharacterChatThread, at_point["id"])
        persona = json.loads(row.persona_json)
        assert persona["transformation_count"] == 1
        assert row.source_history_id == "sess-1-h1"


@pytest.mark.asyncio
async def test_create_session_thread_rejects_missing_source(
    service: CharacterChatService,
) -> None:
    with pytest.raises(CharacterChatError) as excinfo:
        await service.create_session_thread(
            source_session_id="nope", source_history_id=None
        )
    assert excinfo.value.code == "source_not_found"


@pytest.mark.asyncio
async def test_delete_thread_removes_rows_and_images(
    service: CharacterChatService, isolated_db, tmp_path: Path
) -> None:
    await _seed_session(isolated_db.async_factory, tmp_path / "start.png")
    thread = await service.create_session_thread(
        source_session_id="sess-1", source_history_id=None
    )
    directory = service._images_dir / thread["id"]
    assert directory.is_dir()
    await service.delete_thread(thread["id"])
    assert not directory.exists()
    async with isolated_db.async_factory() as db:
        assert await db.get(CharacterChatThread, thread["id"]) is None
    with pytest.raises(CharacterChatError):
        await service.get_thread(thread["id"])


@pytest.mark.asyncio
async def test_stream_message_event_order_and_persistence(
    service: CharacterChatService, isolated_db, monkeypatch
) -> None:
    thread = await service.get_or_create_base_thread()
    fake_generate_text, calls = _llm_router()
    captured: dict = {}
    monkeypatch.setattr(module.llm_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        module.llm_service,
        "generate_feeling_stream",
        _fake_stream(["セレナ「こんにちは、", "お久しぶりです」"], captured),
    )

    events = await _collect(
        service.stream_message(thread_id=thread["id"], content="  やあ  ")
    )
    kinds = [event["event"] for event in events]
    assert kinds == [
        "status",
        "status",
        "chat_chunk",
        "chat_chunk",
        "chat_done",
        "cost",
        "complete",
    ]
    assert events[0]["data"] == {"phase": "plan"}
    assert events[1]["data"] == {"phase": "reply"}
    done = events[4]["data"]
    assert done["user_message"]["content"] == "やあ"
    assert done["character_message"]["content"] == "こんにちは、お久しぶりです"
    assert done["thread"]["message_count"] == 2
    assert calls == ["plan"]
    assert captured["history"] == []
    assert "メイド服を好む" in captured["system"]
    assert "セレナ" in captured["system"]
    assert captured["user"] == "やあ"

    async with isolated_db.async_factory() as db:
        rows = (
            (
                await db.execute(
                    select(CharacterChatMessage)
                    .where(CharacterChatMessage.thread_id == thread["id"])
                    .order_by(CharacterChatMessage.created_at)
                )
            )
            .scalars()
            .all()
        )
    assert [(row.role, row.content) for row in rows] == [
        ("user", "やあ"),
        ("character", "こんにちは、お久しぶりです"),
    ]

    # 2 往復目は直前の会話が history として渡る
    await _collect(service.stream_message(thread_id=thread["id"], content="元気？"))
    assert captured["history"] == [
        {"role": "user", "content": "やあ"},
        {"role": "assistant", "content": "こんにちは、お久しぶりです"},
    ]
    detail = await service.get_thread(thread["id"])
    assert detail["message_count"] == 4
    assert [m["role"] for m in detail["messages"]] == [
        "user",
        "character",
        "user",
        "character",
    ]


@pytest.mark.asyncio
async def test_stream_message_replies_when_planner_fails(
    service: CharacterChatService, monkeypatch
) -> None:
    thread = await service.get_or_create_base_thread()

    async def broken(system_prompt, user_prompt, **kwargs):
        raise RuntimeError("planner down")

    monkeypatch.setattr(module.llm_service, "generate_text", broken)
    monkeypatch.setattr(
        module.llm_service, "generate_feeling_stream", _fake_stream(["やあ"], {})
    )
    events = await _collect(
        service.stream_message(thread_id=thread["id"], content="やあ")
    )
    assert [event["event"] for event in events] == [
        "status",
        "status",
        "chat_chunk",
        "chat_done",
        "complete",
    ]


@pytest.mark.asyncio
async def test_stream_message_rejects_empty_and_unknown(
    service: CharacterChatService,
) -> None:
    thread = await service.get_or_create_base_thread()
    with pytest.raises(CharacterChatError) as excinfo:
        await _collect(service.stream_message(thread_id=thread["id"], content="   "))
    assert excinfo.value.code == "invalid_input"
    with pytest.raises(CharacterChatError) as missing:
        await _collect(service.stream_message(thread_id="nope", content="やあ"))
    assert missing.value.code == "thread_not_found"


@pytest.mark.asyncio
async def test_stream_message_runs_lookups_and_changes_appearance(
    service: CharacterChatService, isolated_db, tmp_path: Path, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory, tmp_path / "start.png")
    thread = await service.get_or_create_base_thread()
    plan = json.dumps(
        {
            "lookups": [
                {"kind": "tendencies"},
                {"kind": "recent_sessions", "limit": 3},
            ],
            "appearance_request": "赤いドレスに着替えて",
        }
    )
    appearance = json.dumps(
        {
            "identity_tags": "1girl, solo, silver hair, green eyes",
            "clothing_tags": "red dress, high heels",
            "description": "赤いドレス姿",
        }
    )
    fake_generate_text, calls = _llm_router(plan=plan, appearance=appearance)
    captured: dict = {}
    monkeypatch.setattr(module.llm_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        module.llm_service,
        "generate_feeling_stream",
        _fake_stream(["着替えました"], captured),
    )
    portrait_mock = AsyncMock(return_value=_png("green"))
    monkeypatch.setattr(module, "generate_portrait_bytes", portrait_mock)

    events = await _collect(
        service.stream_message(
            thread_id=thread["id"], content="最近の傾向は？赤いドレスに着替えて"
        )
    )
    kinds = [event["event"] for event in events]
    assert kinds == [
        "status",
        "status",
        "chat_chunk",
        "chat_done",
        "status",
        "portrait_image",
        "cost",
        "complete",
    ]
    assert events[4]["data"] == {"phase": "portrait"}
    assert "傾向・統計" in captured["system"]
    assert "最近のセッション" in captured["system"]
    assert "水瀬ユウヤ" in captured["system"]
    assert "着替え中" in captured["system"]
    assert set(calls) == {"plan", "appearance"}
    portrait = events[5]["data"]
    assert portrait["appearance"]["clothing_tags"] == "red dress, high heels"
    assert portrait["appearance"]["portrait_kind"] == "standing"
    assert portrait["image_url"].startswith(
        f"/character-chat/images/{thread['id']}/portrait-"
    )
    kwargs = portrait_mock.await_args.kwargs
    assert (
        kwargs["tags"] == "1girl, solo, silver hair, green eyes, red dress, high heels"
    )
    assert kwargs["reference_bytes"] is None
    filename = portrait["image_url"].rsplit("/", 1)[-1]
    assert (service._images_dir / thread["id"] / filename).is_file()

    detail = await service.get_thread(thread["id"])
    assert detail["portrait_url"] == portrait["image_url"]
    assert detail["messages"][1]["meta"]["lookups"] == ["tendencies", "recent_sessions"]
    assert detail["messages"][1]["meta"]["portrait_filename"] == filename


@pytest.mark.asyncio
async def test_stream_message_portrait_failure_is_non_fatal(
    service: CharacterChatService, monkeypatch
) -> None:
    thread = await service.get_or_create_base_thread()
    plan = json.dumps({"lookups": [], "appearance_request": "ドレスに着替えて"})
    fake_generate_text, _ = _llm_router(plan=plan, appearance="{}")
    monkeypatch.setattr(module.llm_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        module.llm_service, "generate_feeling_stream", _fake_stream(["はい"], {})
    )
    monkeypatch.setattr(
        module,
        "generate_portrait_bytes",
        AsyncMock(
            side_effect=module.PortraitGenerationError(
                "image_generation_failed", "失敗"
            )
        ),
    )
    events = await _collect(
        service.stream_message(thread_id=thread["id"], content="ドレスに着替えて")
    )
    kinds = [event["event"] for event in events]
    assert "portrait_error" in kinds
    assert kinds[-1] == "complete"
    error = next(event for event in events if event["event"] == "portrait_error")
    assert error["data"]["code"] == "image_generation_failed"
    detail = await service.get_thread(thread["id"])
    assert detail["message_count"] == 2


@pytest.mark.asyncio
async def test_summary_updates_every_n_messages(
    service: CharacterChatService, isolated_db, monkeypatch
) -> None:
    thread = await service.get_or_create_base_thread()
    fake_generate_text, calls = _llm_router(summary="これまでの話題: 挨拶")
    monkeypatch.setattr(module.llm_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        module.llm_service, "generate_feeling_stream", _fake_stream(["やあ"], {})
    )
    monkeypatch.setattr(module, "SUMMARY_EVERY", 2)
    events = await _collect(
        service.stream_message(thread_id=thread["id"], content="こんにちは")
    )
    assert {"event": "status", "data": {"phase": "memory"}} in events
    assert "summary" in calls
    async with isolated_db.async_factory() as db:
        row = await db.get(CharacterChatThread, thread["id"])
        assert row.summary_text == "これまでの話題: 挨拶"
        assert row.summary_message_count == 2


@pytest.mark.asyncio
async def test_set_appearance_from_source_and_regenerate(
    service: CharacterChatService, isolated_db, tmp_path: Path, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory, tmp_path / "start.png")
    thread = await service.get_or_create_base_thread()
    updated = await service.set_appearance_from_source(
        thread["id"], source_session_id="sess-1", source_history_id="sess-1-h1"
    )
    assert updated["name"] == "セレナ"
    assert updated["appearance"]["portrait_kind"] == "scene"
    assert (
        updated["appearance"]["identity_tags"] == "1girl, brown hair, black eyes, apron"
    )
    assert updated["portrait_url"] is not None
    assert updated["portrait_missing"] is False

    portrait_mock = AsyncMock(return_value=_png("green"))
    monkeypatch.setattr(module, "generate_portrait_bytes", portrait_mock)
    events = await _collect(service.stream_portrait_regeneration(thread["id"]))
    assert [event["event"] for event in events] == [
        "status",
        "portrait_image",
        "complete",
    ]
    assert portrait_mock.await_args.kwargs["reference_bytes"] is not None
    assert events[1]["data"]["appearance"]["portrait_kind"] == "standing"
    detail = await service.get_thread(thread["id"])
    assert detail["portrait_url"] == events[1]["data"]["image_url"]


@pytest.mark.asyncio
async def test_session_thread_exposes_persona_and_reset(
    service: CharacterChatService, isolated_db, tmp_path: Path, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory, tmp_path / "start.png")
    thread = await service.create_session_thread(
        source_session_id="sess-1", source_history_id=None
    )
    persona = thread["persona"]
    assert persona["character_name"] == "水瀬ユウヤ"
    assert persona["stage_label"] == "揺らぎ・葛藤"
    assert persona["transformation_count"] == 2
    assert persona["summary_title"] == "メイドの一日"
    assert persona["summary_text"] == "メイド服で給仕をした"
    assert persona["timeline"][0]["text"] == "メイド服に着替える"
    assert thread["can_reset_appearance"] is False

    monkeypatch.setattr(
        module, "generate_portrait_bytes", AsyncMock(return_value=_png("green"))
    )
    events = await _collect(service.stream_portrait_regeneration(thread["id"]))
    generated = events[1]["data"]["image_url"].rsplit("/", 1)[-1]
    changed = await service.get_thread(thread["id"])
    assert changed["appearance"]["portrait_kind"] == "standing"
    assert changed["can_reset_appearance"] is True
    assert (service._images_dir / thread["id"] / generated).is_file()

    reset = await service.reset_appearance(thread["id"])
    assert reset["appearance"]["portrait_kind"] == "scene"
    assert (
        reset["appearance"]["identity_tags"] == "1girl, brown hair, black eyes, apron"
    )
    assert "/source-" in reset["portrait_url"]
    assert reset["can_reset_appearance"] is False
    assert not (service._images_dir / thread["id"] / generated).exists()
    assert (await service.get_or_create_base_thread())["persona"] == {}


@pytest.mark.asyncio
async def test_reset_base_thread_returns_to_bundled_portrait(
    service: CharacterChatService, tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "bundled" / "serena.png").write_bytes(_png("blue"))
    thread = await service.get_or_create_base_thread()
    assert thread["can_reset_appearance"] is False
    monkeypatch.setattr(
        module, "generate_portrait_bytes", AsyncMock(return_value=_png("green"))
    )
    plan = json.dumps({"lookups": [], "appearance_request": "赤いドレスに着替えて"})
    appearance = json.dumps(
        {
            "identity_tags": "1girl, silver hair",
            "clothing_tags": "red dress",
            "description": "赤いドレス",
        }
    )
    fake_generate_text, _ = _llm_router(plan=plan, appearance=appearance)
    monkeypatch.setattr(module.llm_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        module.llm_service,
        "generate_feeling_stream",
        _fake_stream(["着替えました"], {}),
    )
    await _collect(
        service.stream_message(thread_id=thread["id"], content="赤いドレスに着替えて")
    )
    changed = await service.get_thread(thread["id"])
    assert changed["appearance"]["clothing_tags"] == "red dress"
    assert "/portrait-" in changed["portrait_url"]
    assert changed["can_reset_appearance"] is True

    reset = await service.reset_appearance(thread["id"])
    assert reset["portrait_url"].endswith("/serena.png")
    assert "purple long dress" in reset["appearance"]["clothing_tags"]
    assert reset["appearance"]["portrait_kind"] == "standing"
    assert reset["can_reset_appearance"] is False
