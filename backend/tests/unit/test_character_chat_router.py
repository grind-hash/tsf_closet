"""キャラチャットのルーター: HTTP / SSE への変換とエラーコードの写し。"""

from __future__ import annotations

import importlib
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.services.character_chat_service import CharacterChatError

router_module = importlib.import_module("gateway.routes.character_chat_router")


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router_module.router, prefix="/api")
    return TestClient(app)


def test_create_requires_a_source(client: TestClient) -> None:
    response = client.post("/api/character-chat/threads", json={})
    assert response.status_code == 422


def test_not_found_codes_map_to_404(client: TestClient, monkeypatch) -> None:
    async def missing(thread_id, **kwargs):
        raise CharacterChatError("thread_not_found", "無い")

    monkeypatch.setattr(router_module.character_chat_service, "get_thread", missing)
    response = client.get("/api/character-chat/threads/nope")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "thread_not_found"


def test_message_stream_emits_named_events(client: TestClient, monkeypatch) -> None:
    async def fake_stream(*, thread_id, content):
        assert thread_id == "t1"
        assert content == "やあ"
        yield {"event": "status", "data": {"phase": "plan"}}
        yield {"event": "chat_chunk", "data": {"chunk": "こんにちは"}}
        yield {"event": "complete", "data": {}}

    monkeypatch.setattr(
        router_module.character_chat_service, "stream_message", fake_stream
    )
    with client.stream(
        "POST",
        "/api/character-chat/threads/t1/messages/stream",
        json={"content": "やあ"},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())
    assert "event: status" in body
    assert '{"phase": "plan"}' in body
    assert "こんにちは" in body
    assert "event: complete" in body


def test_message_stream_converts_service_error(client: TestClient, monkeypatch) -> None:
    async def broken(*, thread_id, content):
        raise CharacterChatError("invalid_model_output", "解析できません")
        yield  # pragma: no cover - ジェネレータにするため

    monkeypatch.setattr(router_module.character_chat_service, "stream_message", broken)
    with client.stream(
        "POST",
        "/api/character-chat/threads/t1/messages/stream",
        json={"content": "やあ"},
    ) as response:
        body = "".join(response.iter_text())
    line = next(line for line in body.splitlines() if line.startswith("data:"))
    payload = json.loads(line[len("data:") :])
    assert payload["code"] == "invalid_model_output"
    assert payload["phase"] == "chat"
    assert payload["retryable"] is True


def test_message_rejects_empty_content(client: TestClient) -> None:
    response = client.post(
        "/api/character-chat/threads/t1/messages/stream", json={"content": ""}
    )
    assert response.status_code == 422


def test_portrait_stream_reports_unexpected_exceptions(
    client: TestClient, monkeypatch
) -> None:
    async def broken(thread_id, **kwargs):
        raise RuntimeError("provider down")
        yield  # pragma: no cover

    monkeypatch.setattr(
        router_module.character_chat_service, "stream_portrait_regeneration", broken
    )
    with client.stream(
        "POST", "/api/character-chat/threads/t1/portrait/stream"
    ) as response:
        body = "".join(response.iter_text())
    line = next(line for line in body.splitlines() if line.startswith("data:"))
    payload = json.loads(line[len("data:") :])
    assert payload["code"] == "internal_error"
    assert payload["message"] == "provider down"
    assert payload["phase"] == "portrait"


def test_adventure_thread_endpoint_maps_run_not_found(
    client: TestClient, monkeypatch
) -> None:
    async def missing(run_id):
        raise CharacterChatError("run_not_found", "無い")

    monkeypatch.setattr(
        router_module.character_chat_service, "get_or_create_adventure_thread", missing
    )
    response = client.post("/api/character-chat/threads/adventure/nope")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "run_not_found"


def test_adventure_appearance_endpoint_validates_mode(
    client: TestClient, monkeypatch
) -> None:
    calls: list[str] = []

    async def fake(thread_id, *, mode):
        calls.append(mode)
        return {"id": thread_id}

    monkeypatch.setattr(
        router_module.character_chat_service, "set_adventure_appearance", fake
    )
    ok = client.post(
        "/api/character-chat/threads/t1/appearance/adventure", json={"mode": "scene"}
    )
    assert ok.status_code == 200 and calls == ["scene"]
    bad = client.post(
        "/api/character-chat/threads/t1/appearance/adventure", json={"mode": "x"}
    )
    assert bad.status_code == 422


def test_portrait_stream_accepts_optional_options(
    client: TestClient, monkeypatch
) -> None:
    seen: list[tuple[str, bool]] = []

    async def fake(thread_id, *, reference, use_precise_reference):
        seen.append((reference, use_precise_reference))
        yield {"event": "complete", "data": {}}

    monkeypatch.setattr(
        router_module.character_chat_service, "stream_portrait_regeneration", fake
    )
    with client.stream("POST", "/api/character-chat/threads/t1/portrait/stream"):
        pass
    with client.stream(
        "POST",
        "/api/character-chat/threads/t1/portrait/stream",
        json={"reference": "scene", "use_precise_reference": True},
    ):
        pass
    assert seen == [("current", False), ("scene", True)]
