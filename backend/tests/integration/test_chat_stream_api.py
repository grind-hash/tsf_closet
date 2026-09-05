"""GET /api/game/chat/stream の SSE 形式（data: 行 + JSON ペイロード）を固定する。"""

from __future__ import annotations

import importlib
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.routes.game_router import router
from tests.support.stubs import StubSessionStore

conversation_module = importlib.import_module("gateway.services.conversation_service")


def _events(body: str) -> list[dict]:
    # 1 イベント = "data: {...}\n\n"。ping コメント行は無視する
    blocks = [b for b in body.split("\n\n") if b.strip()]
    payloads = []
    for block in blocks:
        for line in block.split("\n"):
            if line.startswith("data:"):
                payloads.append(json.loads(line[5:].strip()))
    return payloads


def _client(monkeypatch, *, store: StubSessionStore, chunks: list[str], retry: str):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    monkeypatch.setattr(conversation_module, "session_store", store)

    async def fake_stream(**_):
        for chunk in chunks:
            yield chunk

    async def fake_generate_feeling(**_):
        return SimpleNamespace(content=retry)

    monkeypatch.setattr(
        conversation_module,
        "llm_service",
        SimpleNamespace(
            generate_feeling_stream=fake_stream, generate_feeling=fake_generate_feeling
        ),
    )
    return TestClient(app)


def test_chat_stream_emits_text_chunks_then_done(monkeypatch):
    store = StubSessionStore(language="ja")
    with _client(
        monkeypatch,
        store=store,
        chunks=["こんにちは、", "今日はとても良い天気ですね"],
        retry="",
    ) as client:
        response = client.get(
            "/api/game/chat/stream", params={"session_id": "s1", "message": "hi"}
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "data: " in response.text and "event:" not in response.text
    events = _events(response.text)
    assert [e["type"] for e in events] == ["text", "text", "done"]
    assert [e["chunk"] for e in events[:2]] == [
        "こんにちは、",
        "今日はとても良い天気ですね",
    ]
    done = events[-1]
    assert done["full_response"] == "こんにちは、今日はとても良い天気ですね"
    assert done["language"] == "ja"
    assert done["play_memory_update"] == "skipped"
    # ユーザー発言は履歴取得後に保存され、応答も保存される
    assert store.calls.index("conversation_history") < store.calls.index("save:user")
    assert store.calls[-1] == "save:character"


def test_chat_stream_language_mismatch_falls_back_to_retry(monkeypatch):
    store = StubSessionStore(language="en")
    with _client(
        monkeypatch,
        store=store,
        chunks=["こんにちは、今日はとても良い天気ですね"],
        retry="Hello there, it is a lovely day today",
    ) as client:
        response = client.get(
            "/api/game/chat/stream", params={"session_id": "s1", "message": "hi"}
        )

    events = _events(response.text)
    assert [e["type"] for e in events] == ["text", "error"]
    assert events[-1]["fallback"] == "Hello there, it is a lovely day today"
    assert events[-1]["language"] == "en"
    assert store.calls.count("save:character") == 1
