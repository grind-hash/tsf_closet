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

# isolated_db は fixture 実行時に import 済みのモジュールだけ session factory を差し替える。
# 遅延 import される adventure_service を先に読み込み、単体ファイル実行でも DB を揃える
import gateway.services.adventure_service  # noqa: F401
from gateway.databases.models import AvatarModel as AvatarModelORM
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


async def _seed_session(
    factory, image: Path, *, session_id: str = "sess-1", self_mode: bool = False
) -> None:
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
                self_mode=self_mode,
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
        if self_mode:
            db.add(
                HistoryORM(
                    id=f"{session_id}-h2",
                    session_id=session_id,
                    instruction="水着に着替える",
                    image_path=str(image),
                    feeling_text="女性として過ごすのも悪くない",
                    after_description="1girl, brown hair, black eyes, swimsuit, standing",
                    instruction_type="dress_up",
                    created_at=datetime(2026, 9, 1, 11, 0, 0),
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
    *,
    plan: str = PLAN_EMPTY,
    appearance: str | list[str] | None = None,
    summary: str = "要約",
    prompts: list[tuple[str, str]] | None = None,
):
    """generate_text の差し替え。system prompt の種類で返す JSON を切り替える。

    appearance にリストを渡すと呼び出しごとに順に返す(再試行の検証用。末尾を繰り返す)。
    prompts を渡すと (種類, user prompt) を記録する。
    """
    calls: list[str] = []
    appearance_queue = (
        list(appearance) if isinstance(appearance, list) else [appearance or "{}"]
    )

    async def fake_generate_text(system_prompt, user_prompt, **kwargs):
        if "retrieval planner" in system_prompt:
            calls.append("plan")
            kind = "plan"
            content = plan
        elif "appearance tags" in system_prompt:
            calls.append("appearance")
            kind = "appearance"
            content = (
                appearance_queue.pop(0)
                if len(appearance_queue) > 1
                else appearance_queue[0]
            )
        else:
            calls.append("summary")
            kind = "summary"
            content = summary
        if prompts is not None:
            prompts.append((kind, user_prompt))
        return SimpleNamespace(content=content, cost_usd=0.001)

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


def test_recent_monologues_respects_history_point() -> None:
    rows = [
        SimpleNamespace(
            id="h1", instruction="  メイド服に  着替える ", feeling_text=" 恥ずかしい "
        ),
        SimpleNamespace(id="h2", instruction="行動", feeling_text=""),
        SimpleNamespace(id="h3", instruction="水着", feeling_text="x" * 300),
        SimpleNamespace(id="h4", instruction="後", feeling_text="後の心の声"),
    ]
    all_rows = module._recent_monologues(rows, until_history_id=None)
    assert [item["text"][:5] for item in all_rows] == [
        "恥ずかしい",
        "xxxxx",
        "後の心の声",
    ]
    assert all_rows[0]["instruction"] == "メイド服に 着替える"
    assert len(all_rows[1]["text"]) == module.PERSONA_MONOLOGUE_CHARS
    until = module._recent_monologues(rows, until_history_id="h3")
    assert [item["text"][:5] for item in until] == ["恥ずかしい", "xxxxx"]
    many = [
        SimpleNamespace(id=str(i), instruction="", feeling_text=str(i))
        for i in range(9)
    ]
    assert [
        item["text"] for item in module._recent_monologues(many, until_history_id=None)
    ] == [
        "4",
        "5",
        "6",
        "7",
        "8",
    ]


@pytest.mark.asyncio
async def test_create_self_mode_session_thread(
    service: CharacterChatService, isolated_db, tmp_path: Path, monkeypatch
) -> None:
    # 自分自身モードは stats が動かないので、プロフィールとそのときの心の声を根拠にする
    await _seed_session(
        isolated_db.async_factory, tmp_path / "start.png", self_mode=True
    )
    monkeypatch.setattr(
        module.settings_service,
        "get_self_profile",
        AsyncMock(
            return_value={
                "display_name": "自分",
                "pronoun": "俺",
                "gender": "man",
                "personality": "論理的で前向き",
                "reaction_style": "bold",
                "tsf_attitude": "抵抗はない",
                "interests": ["筋トレ"],
            }
        ),
    )
    thread = await service.create_session_thread(
        source_session_id="sess-1", source_history_id=None
    )
    assert thread["name"] == "自分"
    assert thread["pronoun"] == "俺"
    persona = thread["persona"]
    assert persona["self_mode"] is True
    assert persona["stage"] is None
    assert persona["stage_label"] == ""
    assert "stats" not in persona
    assert "recent_monologues" not in persona
    async with isolated_db.async_factory() as db:
        row = await db.get(CharacterChatThread, thread["id"])
        stored = json.loads(row.persona_json)
        assert [item["text"] for item in stored["recent_monologues"]] == [
            "恥ずかしい",
            "女性として過ごすのも悪くない",
        ]
        assert stored["recent_monologues"][-1]["instruction"] == "水着に着替える"

    fake_generate_text, _ = _llm_router()
    captured: dict = {}
    monkeypatch.setattr(module.llm_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        module.llm_service,
        "generate_feeling_stream",
        _fake_stream(["悪くないよ"], captured),
    )
    await _collect(
        service.stream_message(thread_id=thread["id"], content="いまどんな感じ？")
    )
    system = captured["system"]
    assert "自分自身モード" in system
    assert "性格: 論理的で前向き" in system
    assert "興味・関心: 筋トレ" in system
    assert "女性として過ごすのも悪くない" in system
    assert "通常は 2〜5 文" in system
    assert "開花" not in system
    assert "心理段階:" not in system
    assert "抵抗・困惑" not in system
    assert "元に戻りたい" not in system

    # 履歴時点を指定すると、心の声もその時点までに絞られる
    at_point = await service.create_session_thread(
        source_session_id="sess-1", source_history_id="sess-1-h1"
    )
    async with isolated_db.async_factory() as db:
        row = await db.get(CharacterChatThread, at_point["id"])
        stored = json.loads(row.persona_json)
        assert [item["text"] for item in stored["recent_monologues"]] == ["恥ずかしい"]


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
async def test_origin_lore_is_attached_only_when_planned_for_base_thread(
    service: CharacterChatService, isolated_db, tmp_path: Path, monkeypatch
) -> None:
    """「別の層の記憶」は判定 LLM が呼んだ手番だけ、案内役キャラにだけ載る。"""
    captured: dict = {}
    monkeypatch.setattr(
        module.llm_service,
        "generate_feeling_stream",
        _fake_stream(["……その名前を、どこで？"], captured),
    )
    monkeypatch.setattr(
        module, "load_origin_lore", lambda language: f"テスト用の記憶({language})"
    )
    base = await service.get_or_create_base_thread()

    # 判定 LLM が false のときは、名前が出ていても載せない
    plain, _ = _llm_router()
    monkeypatch.setattr(module.llm_service, "generate_text", plain)
    await _collect(
        service.stream_message(thread_id=base["id"], content="イツキって知ってる？")
    )
    assert "別の層の記憶" not in captured["system"]
    assert "テスト用の記憶" not in captured["system"]

    # true のときだけ、言語に合った本文が枠付きで載る
    invoked, _ = _llm_router(
        plan=json.dumps(
            {"lookups": [], "appearance_request": None, "origin_lore": "true"}
        )
    )
    monkeypatch.setattr(module.llm_service, "generate_text", invoked)
    await _collect(
        service.stream_message(
            thread_id=base["id"], content="エデン・レイヤーって知ってる？"
        )
    )
    assert "[別の層の記憶]" in captured["system"]
    assert "テスト用の記憶(ja)" in captured["system"]

    # 過去セッション由来のキャラには、判定 LLM が true でも載せない
    await _seed_session(isolated_db.async_factory, tmp_path / "start.png")
    session_thread = await service.create_session_thread(
        source_session_id="sess-1", source_history_id=None
    )
    await _collect(
        service.stream_message(
            thread_id=session_thread["id"], content="エデン・レイヤーって知ってる？"
        )
    )
    assert "別の層の記憶" not in captured["system"]
    assert "テスト用の記憶" not in captured["system"]


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
    lookups = detail["messages"][1]["meta"]["lookups"]
    assert [item["kind"] for item in lookups] == ["tendencies", "recent_sessions"]
    assert lookups[0]["query"] is None
    assert "セッション総数" in lookups[0]["text"]
    assert "水瀬ユウヤ" in lookups[1]["text"]
    assert lookups[1]["session_ids"] == ["sess-1"]
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


@pytest.mark.asyncio
async def test_portrait_regeneration_surfaces_provider_errors(
    service: CharacterChatService, monkeypatch
) -> None:
    thread = await service.get_or_create_base_thread()
    monkeypatch.setattr(
        module,
        "generate_portrait_bytes",
        AsyncMock(side_effect=TimeoutError()),
    )
    with pytest.raises(CharacterChatError) as excinfo:
        await _collect(service.stream_portrait_regeneration(thread["id"]))
    assert excinfo.value.code == "image_generation_failed"
    assert "TimeoutError" in str(excinfo.value)


# ---------------------------------------------------------------------------
# adventure 種(TSF シナリオの攻略対象)
# ---------------------------------------------------------------------------

from gateway.databases.models import AdventureRun as AdventureRunORM  # noqa: E402
from gateway.databases.models import AdventureTurn as AdventureTurnORM  # noqa: E402
from gateway.services.character_chat_service import _HeaderBuffer  # noqa: E402


async def _seed_avatar(
    factory,
    avatar_id: str,
    *,
    name: str | None = None,
    character_name: str | None = None,
    variant_label: str | None = None,
) -> None:
    """登録済み 3D モデルの行だけを入れる(ファイル本体は要らない)。"""
    async with factory() as db:
        db.add(
            AvatarModelORM(
                id=avatar_id,
                name=name or avatar_id,
                character_name=character_name,
                variant_label=variant_label,
                file_path=f"{avatar_id}.vrm",
                file_size=1,
                vrm_spec_version="0",
                meta_json="{}",
                created_at=datetime(2026, 9, 1, 10, 0, 0),
            )
        )
        await db.commit()


async def _seed_run(
    factory,
    tmp_path: Path,
    *,
    composite: bool,
    companion: bool = False,
    avatar_id: str | None = None,
    talk_log: list[dict] | None = None,
    run_id: str = "run-1",
    partner_appearance: str = "1girl, brown hair, blue eyes",
    npc_tags: list[str] | None = None,
) -> dict[str, Path]:
    run_dir = tmp_path / "adventure_images" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    scene1 = run_dir / "scene-1.png"
    scene2 = run_dir / "scene-2.png"
    partner_portrait = run_dir / "partner-0-abc12345.png"
    partner_source = run_dir / "partner_initial.png"
    scene1.write_bytes(_png("red"))
    scene2.write_bytes(_png("blue"))
    partner_portrait.write_bytes(_png("green"))
    partner_source.write_bytes(_png("white"))
    partner_entry = {
        "name": "美咲",
        "description": "笑顔",
        "clothing": "school uniform",
        "action": "",
    }
    state = {
        "milestones": [],
        "completed_milestones": [],
        "clues": [],
        "reality_rules": ["猫耳が生えている"],
        "visual_state": {
            "location": "campus",
            "appearance": "",
            "clothing": "",
            "surroundings": "",
            "main_characters": [partner_entry],
        },
        "sim": {
            "total_days": 5,
            "affection": 40,
            "money": 5000,
            "partner_name": "美咲",
            "player_name": "ケン",
            "partner_appearance": partner_appearance,
            "partner_profile": "明るい先輩",
            "partner_speech_style": "casual",
            "job": {"name": "カフェ", "wage": 3000},
            "gift_catalog": [],
            "hidden_preferences": {"likes_hint": "甘いもの"},
            "given_gifts": [],
            "confessed": False,
        },
        "enable_composite_scene": composite,
        "companion_mode": companion,
        "companion_avatar_id": avatar_id,
        "partner_portrait_path": str(partner_portrait),
        "opening_partner_portrait_path": str(partner_portrait),
        "partner_image_path": str(partner_source),
        "talk_log": talk_log or [],
        "use_precise_reference": False,
    }
    if npc_tags is not None:
        state["last_image_prompt"] = {
            "scene_tags": "campus, afternoon",
            "player_tags": "1boy, short hair",
            "npc_tags": npc_tags,
        }
    async with factory() as db:
        if await db.get(User, DEFAULT_USER_ID) is None:
            db.add(User(id=DEFAULT_USER_ID))
        db.add(
            AdventureRunORM(
                id=run_id,
                user_id=DEFAULT_USER_ID,
                preset="romance",
                title="放課後の約束",
                objective="仲良くなる",
                snapshot_json="{}",
                state_json=json.dumps(state, ensure_ascii=False),
                current_image_path=str(scene2),
                initial_image_path=str(scene1),
                turn_count=2,
                max_turns=10,
                language="ja",
                nsfw_mode=False,
                text_model="glm-4-6",
                image_provider="novelai",
                image_model="nai-diffusion-4-5-full",
            )
        )
        db.add(
            AdventureTurnORM(
                id=f"{run_id}-t1",
                run_id=run_id,
                client_turn_id="c1",
                turn_number=1,
                user_input="挨拶する",
                input_kind="free_text",
                narrative="美咲が笑った。",
                state_delta_json=json.dumps(
                    {
                        "sim": {"affection": 30},
                        "visual_state": {"main_characters": [partner_entry]},
                    }
                ),
                image_path=str(scene1),
                created_at=datetime(2026, 9, 1, 10, 0, 0),
            )
        )
        db.add(
            AdventureTurnORM(
                id=f"{run_id}-t2",
                run_id=run_id,
                client_turn_id="c2",
                turn_number=2,
                user_input="一人で散歩",
                input_kind="free_text",
                narrative="誰もいない道を歩いた。",
                state_delta_json=json.dumps(
                    {"sim": {"affection": 40}, "visual_state": {"main_characters": []}}
                ),
                image_path=str(scene2),
                created_at=datetime(2026, 9, 1, 11, 0, 0),
            )
        )
        await db.commit()
    return {
        "scene1": scene1,
        "scene2": scene2,
        "partner_portrait": partner_portrait,
        "partner_source": partner_source,
    }


def test_header_buffer_strips_split_header_and_passes_plain_text() -> None:
    enabled = _HeaderBuffer(enabled=True)
    assert enabled.feed("[expression=hap") == []
    assert enabled.feed("py gesture=nod]\n") == []
    assert enabled.feed("やっほー") == ["やっほー"]
    assert enabled.flush() == []
    plain = _HeaderBuffer(enabled=True)
    assert plain.feed("こんにちは") == ["こんにちは"]
    disabled = _HeaderBuffer(enabled=False)
    assert disabled.feed("[expression=happy gesture=nod]\nx") == [
        "[expression=happy gesture=nod]\nx"
    ]
    trailing = _HeaderBuffer(enabled=True)
    assert trailing.feed("[expression=sad gesture=bow]") == []
    assert trailing.flush() == []


@pytest.mark.asyncio
async def test_adventure_thread_defaults_to_scene_in_composite_mode(
    service: CharacterChatService, isolated_db, tmp_path: Path
) -> None:
    files = await _seed_run(
        isolated_db.async_factory,
        tmp_path,
        composite=True,
        talk_log=[
            {"id": "a", "role": "user", "text": "やあ", "after_turn": 1},
            {
                "id": "b",
                "role": "partner",
                "text": "やっほー",
                "after_turn": 1,
                "expression": "happy",
                "gesture": "nod",
            },
        ],
    )
    thread = await service.get_or_create_adventure_thread("run-1")
    assert thread["kind"] == "adventure"
    assert thread["source_run_id"] == "run-1"
    assert thread["name"] == "美咲"
    # 合成モードの既定は、相手が写っている最新の場面画像(手番 1)をそのまま
    assert thread["appearance"]["portrait_kind"] == "scene"
    assert thread["appearance"]["identity_tags"] == "1girl, brown hair, blue eyes"
    assert thread["appearance"]["clothing_tags"] == "school uniform"
    assert thread["appearance"]["source"]["adventure_mode"] == "default"
    copied = list((service._images_dir / thread["id"]).glob("source-*.png"))
    assert len(copied) == 1
    assert copied[0].read_bytes() == files["scene1"].read_bytes()
    assert thread["can_reset_appearance"] is False
    adventure = thread["adventure"]
    assert adventure["available"] is True
    assert adventure["partner_name"] == "美咲"
    assert adventure["player_name"] == "ケン"
    assert adventure["affection"] == 40
    assert adventure["scene_image_url"] == "/adventure/images/run-1/scene-1.png"
    assert adventure["partner_portrait_url"].endswith("/partner-0-abc12345.png")
    assert adventure["companion_avatar_url"] is None
    # 旧トークログはメッセージとして取り込まれ、run の state からは消える
    detail = await service.get_thread(thread["id"])
    assert [(m["role"], m["content"]) for m in detail["messages"]] == [
        ("user", "やあ"),
        ("character", "やっほー"),
    ]
    assert detail["messages"][1]["meta"]["expression"] == "happy"
    assert detail["messages"][1]["meta"]["after_turn"] == 1
    async with isolated_db.async_factory() as db:
        run = await db.get(AdventureRunORM, "run-1")
        assert "talk_log" not in json.loads(run.state_json)
    # 冪等: 同じ run は同じスレッド
    again = await service.get_or_create_adventure_thread("run-1")
    assert again["id"] == thread["id"]
    assert again["message_count"] == 2
    persona = thread["persona"]
    assert persona["summary_title"] == "放課後の約束"
    assert persona["summary_text"] == "明るい先輩"
    assert persona["attributes"] == ["猫耳が生えている"]


@pytest.mark.asyncio
async def test_adventure_thread_defaults_to_partner_portrait_when_not_composite(
    service: CharacterChatService, isolated_db, tmp_path: Path
) -> None:
    files = await _seed_run(isolated_db.async_factory, tmp_path, composite=False)
    thread = await service.get_or_create_adventure_thread("run-1")
    assert thread["appearance"]["portrait_kind"] == "standing"
    copied = list((service._images_dir / thread["id"]).glob("source-*.png"))
    assert copied[0].read_bytes() == files["partner_portrait"].read_bytes()


@pytest.mark.asyncio
async def test_adventure_appearance_modes_and_reset(
    service: CharacterChatService, isolated_db, tmp_path: Path, monkeypatch
) -> None:
    files = await _seed_run(isolated_db.async_factory, tmp_path, composite=True)
    thread = await service.get_or_create_adventure_thread("run-1")
    switched = await service.set_adventure_appearance(
        thread["id"], mode="partner_portrait"
    )
    assert switched["appearance"]["portrait_kind"] == "standing"
    assert switched["adventure"]["appearance_mode"] == "partner_portrait"
    assert switched["can_reset_appearance"] is True
    latest = max(
        (service._images_dir / thread["id"]).glob("source-*.png"),
        key=lambda item: item.stat().st_mtime_ns,
    )
    assert latest.read_bytes() == files["partner_portrait"].read_bytes()

    portrait_mock = AsyncMock(return_value=_png("black"))
    monkeypatch.setattr(module, "generate_portrait_bytes", portrait_mock)
    events = await _collect(
        service.stream_portrait_regeneration(
            thread["id"], reference="scene", use_precise_reference=True
        )
    )
    assert [event["event"] for event in events] == [
        "status",
        "portrait_image",
        "complete",
    ]
    kwargs = portrait_mock.await_args.kwargs
    assert kwargs["reference_bytes"] == files["scene1"].read_bytes()
    assert kwargs["use_character_reference"] is True
    assert kwargs["tags"].startswith("1girl, brown hair, blue eyes")
    custom = await service.get_thread(thread["id"])
    assert custom["adventure"]["appearance_mode"] == "custom"
    assert custom["appearance"]["portrait_kind"] == "standing"

    reset = await service.reset_appearance(thread["id"])
    assert reset["adventure"]["appearance_mode"] == "default"
    assert reset["appearance"]["portrait_kind"] == "scene"
    assert reset["can_reset_appearance"] is False


@pytest.mark.asyncio
async def test_adventure_message_reads_live_state_and_feeds_next_turn(
    service: CharacterChatService, isolated_db, tmp_path: Path, monkeypatch
) -> None:
    await _seed_run(
        isolated_db.async_factory,
        tmp_path,
        composite=True,
        talk_log=[{"id": "a", "role": "user", "text": "古い話", "after_turn": 1}],
    )
    thread = await service.get_or_create_adventure_thread("run-1")
    fake_generate_text, _ = _llm_router()
    captured: dict = {}
    monkeypatch.setattr(module.llm_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        module.llm_service,
        "generate_feeling_stream",
        _fake_stream(["やっほー"], captured),
    )
    events = await _collect(
        service.stream_message(thread_id=thread["id"], content="やあ")
    )
    assert [event["event"] for event in events][-2:] == ["cost", "complete"]
    system = captured["system"]
    assert "You are 美咲" in system
    assert "SPEECH REGISTER" in system
    assert '"affection": 40' in system
    assert "猫耳が生えている" in system
    assert "明るい先輩" in system
    assert "メイド服を好む" in system
    assert "[expression=<key> gesture=<key>]" not in system
    done = next(event for event in events if event["event"] == "chat_done")["data"]
    assert done["user_message"]["meta"]["after_turn"] == 2
    assert done["character_message"]["meta"]["after_turn"] == 2
    # 3D モデルを表示していない返答には表情・身振りを残さない
    assert done["character_message"]["meta"].get("expression") is None

    # 次の手番へは前の手番(2)以降の発言だけを渡す(取り込んだ古いトークは除く)
    recent = await service.recent_adventure_messages("run-1", after_turn=2)
    assert recent == [
        {"role": "user", "text": "やあ", "after_turn": 2},
        {"role": "partner", "text": "やっほー", "after_turn": 2},
    ]
    from gateway.services.adventure_service import adventure_service

    run = await adventure_service.get_run_orm("run-1")
    assert await adventure_service._recent_chat_for_run(run) == recent

    # run の好感度が上がれば、次の発言の文脈はライブで追従する
    async with isolated_db.async_factory() as db:
        run_row = await db.get(AdventureRunORM, "run-1")
        state = json.loads(run_row.state_json)
        state["sim"]["affection"] = 80
        state["sim"]["partner_appearance"] = "1girl, silver hair, blue eyes"
        run_row.state_json = json.dumps(state, ensure_ascii=False)
        await db.commit()
    await _collect(service.stream_message(thread_id=thread["id"], content="元気？"))
    assert '"affection": 80' in captured["system"]
    synced = await service.get_thread(thread["id"])
    assert synced["appearance"]["identity_tags"] == "1girl, silver hair, blue eyes"
    assert synced["adventure"]["affection"] == 80


@pytest.mark.asyncio
async def test_adventure_companion_reply_header_is_stripped_and_recorded(
    service: CharacterChatService, isolated_db, tmp_path: Path, monkeypatch
) -> None:
    await _seed_run(
        isolated_db.async_factory,
        tmp_path,
        composite=False,
        companion=True,
        avatar_id="avatar-1",
    )
    await _seed_avatar(isolated_db.async_factory, "avatar-1", name="misaki")
    thread = await service.get_or_create_adventure_thread("run-1")
    assert thread["adventure"]["companion_avatar_url"] == "/avatars/avatar-1/file"
    # run の対面会話モデルがそのままキャラチャットの 3D モデルになる
    assert thread["avatar"]["source"] == "run"
    assert thread["avatar"]["url"] == "/avatars/avatar-1/file"
    fake_generate_text, _ = _llm_router()
    captured: dict = {}
    monkeypatch.setattr(module.llm_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        module.llm_service,
        "generate_feeling_stream",
        _fake_stream(
            ["[expression=hap", "py gesture=nod]\n", "やっほー、", "元気？"], captured
        ),
    )
    events = await _collect(
        service.stream_message(thread_id=thread["id"], content="やあ")
    )
    chunks = [e["data"]["chunk"] for e in events if e["event"] == "chat_chunk"]
    assert chunks == ["やっほー、", "元気？"]
    assert "[expression=<key> gesture=<key>]" in captured["system"]
    done = next(event for event in events if event["event"] == "chat_done")["data"]
    assert done["character_message"]["content"] == "やっほー、元気？"
    assert done["character_message"]["meta"]["expression"] == "happy"
    assert done["character_message"]["meta"]["gesture"] == "nod"


@pytest.mark.asyncio
async def test_adventure_thread_survives_run_deletion(
    service: CharacterChatService, isolated_db, tmp_path: Path, monkeypatch
) -> None:
    await _seed_run(isolated_db.async_factory, tmp_path, composite=True)
    thread = await service.get_or_create_adventure_thread("run-1")
    from gateway.services.adventure_service import adventure_service

    await adventure_service.delete_run("run-1")
    detail = await service.get_thread(thread["id"])
    assert detail["adventure"]["available"] is False
    assert detail["adventure"]["partner_name"] == "美咲"
    assert detail["portrait_missing"] is False
    fake_generate_text, _ = _llm_router()
    captured: dict = {}
    monkeypatch.setattr(module.llm_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        module.llm_service, "generate_feeling_stream", _fake_stream(["…"], captured)
    )
    events = await _collect(
        service.stream_message(thread_id=thread["id"], content="いる？")
    )
    assert events[-1]["event"] == "complete"
    assert "has ended or been deleted" in captured["system"]
    assert "明るい先輩" in captured["system"]
    with pytest.raises(CharacterChatError) as excinfo:
        await service.set_adventure_appearance(thread["id"], mode="scene")
    assert excinfo.value.code == "run_not_found"


@pytest.mark.asyncio
async def test_adventure_thread_rejects_missing_or_non_romance_runs(
    service: CharacterChatService, isolated_db, tmp_path: Path
) -> None:
    with pytest.raises(CharacterChatError) as missing:
        await service.get_or_create_adventure_thread("nope")
    assert missing.value.code == "run_not_found"
    await _seed_run(isolated_db.async_factory, tmp_path, composite=True, run_id="run-2")
    async with isolated_db.async_factory() as db:
        run = await db.get(AdventureRunORM, "run-2")
        run.preset = "infiltration"
        await db.commit()
    with pytest.raises(CharacterChatError) as plain:
        await service.get_or_create_adventure_thread("run-2")
    assert plain.value.code == "talk_unavailable"


_JAPANESE_TAGS = json.dumps(
    {
        "identity_tags": "1girl, solo, silver hair, green eyes",
        "clothing_tags": "シフォンブラウス, 総レースタイトスカート",
        "description": "着替えた",
    }
)
_ENGLISH_TAGS = json.dumps(
    {
        "identity_tags": "1girl, solo, silver hair, green eyes",
        "clothing_tags": "white chiffon blouse, black lace pencil skirt",
        "description": "シフォンブラウスとレースのタイトスカート姿",
    }
)
_DRESS_UP_PLAN = json.dumps(
    {
        "lookups": [],
        "appearance_request": "シフォンブラウスと、総レースタイトスカートに着替えよう",
    }
)


@pytest.mark.asyncio
async def test_stream_message_retries_when_appearance_tags_are_japanese(
    service: CharacterChatService, monkeypatch
) -> None:
    """依頼文を丸写しした日本語タグは 1 回だけ再生成し、英語タグで立ち絵を描く。"""
    thread = await service.get_or_create_base_thread()
    prompts: list[tuple[str, str]] = []
    fake_generate_text, calls = _llm_router(
        plan=_DRESS_UP_PLAN,
        appearance=[_JAPANESE_TAGS, _ENGLISH_TAGS],
        prompts=prompts,
    )
    monkeypatch.setattr(module.llm_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        module.llm_service, "generate_feeling_stream", _fake_stream(["着替えたよ"], {})
    )
    portrait_mock = AsyncMock(return_value=_png("blue"))
    monkeypatch.setattr(module, "generate_portrait_bytes", portrait_mock)

    events = await _collect(
        service.stream_message(
            thread_id=thread["id"],
            content="シフォンブラウスと、総レースタイトスカートに着替えよう",
        )
    )
    kinds = [event["event"] for event in events]
    assert "portrait_image" in kinds
    assert "portrait_error" not in kinds
    assert calls == ["plan", "appearance", "appearance"]
    retry_prompt = [user for kind, user in prompts if kind == "appearance"][1]
    assert "rejected_previous_output" in retry_prompt
    assert "総レースタイトスカート" in retry_prompt
    portrait = next(event for event in events if event["event"] == "portrait_image")
    assert (
        portrait["data"]["appearance"]["clothing_tags"]
        == "white chiffon blouse, black lace pencil skirt"
    )
    assert portrait_mock.await_args.kwargs["tags"] == (
        "1girl, solo, silver hair, green eyes, "
        "white chiffon blouse, black lace pencil skirt"
    )


@pytest.mark.asyncio
async def test_stream_message_refuses_persisting_japanese_tags(
    service: CharacterChatService, monkeypatch
) -> None:
    """再試行でも日本語が残るなら、通じないタグで描かず portrait_error にして姿を据え置く。"""
    thread = await service.get_or_create_base_thread()
    before = (await service.get_thread(thread["id"]))["appearance"]
    fake_generate_text, calls = _llm_router(
        plan=_DRESS_UP_PLAN, appearance=[_JAPANESE_TAGS, _JAPANESE_TAGS]
    )
    monkeypatch.setattr(module.llm_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        module.llm_service, "generate_feeling_stream", _fake_stream(["着替えたよ"], {})
    )
    portrait_mock = AsyncMock(return_value=_png("blue"))
    monkeypatch.setattr(module, "generate_portrait_bytes", portrait_mock)

    events = await _collect(
        service.stream_message(
            thread_id=thread["id"],
            content="シフォンブラウスと、総レースタイトスカートに着替えよう",
        )
    )
    kinds = [event["event"] for event in events]
    assert kinds[-1] == "complete"
    assert "portrait_image" not in kinds
    error = next(event for event in events if event["event"] == "portrait_error")
    assert error["data"]["code"] == "appearance_tags_not_english"
    assert "総レースタイトスカート" in error["data"]["message"]
    assert calls == ["plan", "appearance", "appearance"]
    portrait_mock.assert_not_awaited()
    after = (await service.get_thread(thread["id"]))["appearance"]
    assert after["clothing_tags"] == before["clothing_tags"]
    assert after["identity_tags"] == before["identity_tags"]


@pytest.mark.asyncio
async def test_adventure_thread_uses_turn_portrait_tags_not_initial_appearance(
    service: CharacterChatService, isolated_db, tmp_path: Path
) -> None:
    """姿のタグは開始素材の記述(partner_appearance)ではなく、その手番の npc_tags から組む。"""
    await _seed_run(
        isolated_db.async_factory,
        tmp_path,
        composite=False,
        partner_appearance="1girl, brown hair, blue eyes, sex, lying on back, legs spread",
        npc_tags=[
            "1girl, brown hair, blue eyes, 21yo, slight blush, looking down shyly, "
            "silver sequin dress, black stockings, supporting character, "
            "secondary focus, behind protagonist"
        ],
    )
    thread = await service.get_or_create_adventure_thread("run-1")
    assert (
        thread["appearance"]["identity_tags"]
        == "1girl, brown hair, blue eyes, 21yo, slight blush"
    )
    assert (
        thread["appearance"]["clothing_tags"] == "silver sequin dress, black stockings"
    )
    assert "sex" not in thread["appearance"]["identity_tags"]


@pytest.mark.asyncio
async def test_adventure_thread_falls_back_to_filtered_initial_appearance(
    service: CharacterChatService, isolated_db, tmp_path: Path
) -> None:
    """npc_tags が無い run は partner_appearance に倒すが、服装・場面タグは落とす。"""
    await _seed_run(
        isolated_db.async_factory,
        tmp_path,
        composite=False,
        partner_appearance="1girl, brown hair, blue eyes, sitting, red dress",
    )
    thread = await service.get_or_create_adventure_thread("run-1")
    assert thread["appearance"]["identity_tags"] == "1girl, brown hair, blue eyes"
    # 服装は場面の攻略対象エントリから
    assert thread["appearance"]["clothing_tags"] == "school uniform"


@pytest.mark.asyncio
async def test_base_thread_avatar_resolution_order(
    service: CharacterChatService, isolated_db, tmp_path: Path
) -> None:
    """案内役: 明示選択 → 同梱 serena.vrm → 名前一致の登録済みモデル → 2D 立ち絵。"""
    factory = isolated_db.async_factory
    thread = await service.get_or_create_base_thread()
    detail = await service.get_thread(thread["id"])
    assert detail["avatar"] == {
        "mode": "auto",
        "id": None,
        "url": None,
        "source": None,
        "name": None,
        "character_name": None,
        "variant_label": None,
        "variants": [],
        "missing": False,
    }

    # character_name が「セレナ」の登録済みモデル(衣装差分 2 件)は差分ラベル順の先頭
    await _seed_avatar(
        factory, "av-b", name="serena_b", character_name="セレナ", variant_label="水着"
    )
    await _seed_avatar(
        factory,
        "av-a",
        name="serena_a",
        character_name="セレナ",
        variant_label="ドレス",
    )
    detail = await service.get_thread(thread["id"])
    assert detail["avatar"]["source"] == "registered"
    assert detail["avatar"]["id"] == "av-a"
    assert detail["avatar"]["url"] == "/avatars/av-a/file"
    assert detail["avatar"]["name"] == "セレナ / ドレス"
    assert detail["avatar"]["variants"] == [
        {"id": "av-a", "label": "ドレス", "current": True},
        {"id": "av-b", "label": "水着", "current": False},
    ]

    # 同梱の専用モデルがあれば登録済みより優先する
    bundled = tmp_path / "bundled" / "serena.vrm"
    bundled.write_bytes(b"glTF")
    detail = await service.get_thread(thread["id"])
    assert detail["avatar"]["source"] == "bundled"
    assert detail["avatar"]["url"] == "/character-chat/avatar/base"
    assert detail["avatar"]["name"] == "セレナ"
    assert service.base_avatar_path() == bundled

    # 明示選択は同梱より優先。none で 2D に戻す
    chosen = await service.set_avatar(thread["id"], mode="model", avatar_id="av-b")
    assert chosen["avatar"]["mode"] == "model"
    assert chosen["avatar"]["id"] == "av-b"
    assert chosen["avatar"]["source"] == "registered"
    assert chosen["avatar"]["variants"][1] == {
        "id": "av-b",
        "label": "水着",
        "current": True,
    }
    none = await service.set_avatar(thread["id"], mode="none")
    assert none["avatar"]["mode"] == "none" and none["avatar"]["url"] is None
    with pytest.raises(CharacterChatError) as excinfo:
        await service.set_avatar(thread["id"], mode="model", avatar_id="nope")
    assert excinfo.value.code == "avatar_not_found"

    # 選んでいたモデルが削除されたら missing を立てて自動(同梱)へ倒す
    await service.set_avatar(thread["id"], mode="model", avatar_id="av-b")
    async with factory() as db:
        row = await db.get(AvatarModelORM, "av-b")
        await db.delete(row)
        await db.commit()
    detail = await service.get_thread(thread["id"])
    assert detail["avatar"]["missing"] is True
    assert detail["avatar"]["source"] == "bundled"
    # 「最初の姿に戻す」相当の appearance 操作でも 3D の指定は残る
    appearance = json.loads((await _thread_row(factory, thread["id"])).appearance_json)
    assert appearance["avatar"] == {"mode": "model", "avatar_id": "av-b"}


async def _thread_row(factory, thread_id: str) -> CharacterChatThread:
    async with factory() as db:
        row = await db.get(CharacterChatThread, thread_id)
        assert row is not None
        db.expunge(row)
        return row


@pytest.mark.asyncio
async def test_session_thread_avatar_matches_character_name(
    service: CharacterChatService, isolated_db, tmp_path: Path
) -> None:
    factory = isolated_db.async_factory
    await _seed_session(factory, tmp_path / "start.png")
    thread = await service.create_session_thread(
        source_session_id="sess-1", source_history_id=None
    )
    assert (await service.get_thread(thread["id"]))["avatar"]["url"] is None
    # 大文字小文字・前後の空白は無視して人物名と照合する
    await _seed_avatar(
        factory, "av-s", name="s", character_name=f" {thread['name'].upper()} "
    )
    await _seed_avatar(factory, "av-other", name="o", character_name="別人")
    detail = await service.get_thread(thread["id"])
    assert detail["avatar"]["source"] == "registered"
    assert detail["avatar"]["id"] == "av-s"


@pytest.mark.asyncio
async def test_adventure_thread_avatar_prefers_run_model_then_partner_name(
    service: CharacterChatService, isolated_db, tmp_path: Path
) -> None:
    factory = isolated_db.async_factory
    await _seed_run(
        factory, tmp_path, composite=False, companion=True, avatar_id="av-run"
    )
    await _seed_avatar(factory, "av-run", name="run_model")
    await _seed_avatar(factory, "av-name", name="misaki", character_name="美咲")
    thread = await service.get_or_create_adventure_thread("run-1")
    assert thread["avatar"]["source"] == "run"
    assert thread["avatar"]["id"] == "av-run"

    # run のモデルが削除されていれば攻略対象名で登録済みモデルを探す
    async with factory() as db:
        await db.delete(await db.get(AvatarModelORM, "av-run"))
        await db.commit()
    detail = await service.get_thread(thread["id"])
    assert detail["avatar"]["source"] == "registered"
    assert detail["avatar"]["id"] == "av-name"


@pytest.mark.asyncio
async def test_stream_message_with_avatar_updates_tags_without_portrait(
    service: CharacterChatService, isolated_db, tmp_path: Path, monkeypatch
) -> None:
    """3D モデル表示中: 表情ヘッダを求めて剥がし、着替えは外見タグだけ更新して立ち絵を描かない。"""
    (tmp_path / "bundled" / "serena.vrm").write_bytes(b"glTF")
    thread = await service.get_or_create_base_thread()
    fake_generate_text, calls = _llm_router(
        plan=_DRESS_UP_PLAN, appearance=_ENGLISH_TAGS
    )
    captured: dict = {}
    monkeypatch.setattr(module.llm_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        module.llm_service,
        "generate_feeling_stream",
        _fake_stream(["[expression=happy gesture=nod]\n", "着替えたよ"], captured),
    )
    portrait_mock = AsyncMock(return_value=_png("blue"))
    monkeypatch.setattr(module, "generate_portrait_bytes", portrait_mock)

    events = await _collect(
        service.stream_message(
            thread_id=thread["id"],
            content="シフォンブラウスと、総レースタイトスカートに着替えよう",
        )
    )
    kinds = [event["event"] for event in events]
    assert "[expression=<key> gesture=<key>]" in captured["system"]
    assert [e["data"]["chunk"] for e in events if e["event"] == "chat_chunk"] == [
        "着替えたよ"
    ]
    assert "appearance_updated" in kinds
    assert "portrait_image" not in kinds
    assert kinds[-1] == "complete"
    portrait_mock.assert_not_awaited()
    assert calls == ["plan", "appearance"]
    done = next(e for e in events if e["event"] == "chat_done")["data"]
    assert done["character_message"]["meta"]["expression"] == "happy"
    assert done["character_message"]["meta"]["gesture"] == "nod"
    updated = next(e for e in events if e["event"] == "appearance_updated")["data"]
    assert (
        updated["appearance"]["clothing_tags"]
        == "white chiffon blouse, black lace pencil skirt"
    )
    detail = await service.get_thread(thread["id"])
    assert (
        detail["appearance"]["clothing_tags"]
        == "white chiffon blouse, black lace pencil skirt"
    )
    assert detail["portrait_missing"] is True
