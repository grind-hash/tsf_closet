import importlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.routes.game_router import router
from tests.support.stubs import StubSessionStore

conversation_module = importlib.import_module("gateway.services.conversation_service")


def test_chat_api_keeps_existing_response_fields(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    monkeypatch.setattr(conversation_module, "session_store", StubSessionStore())

    async def fake_generate_feeling(**_):
        return SimpleNamespace(content="こんにちは")

    monkeypatch.setattr(
        conversation_module,
        "llm_service",
        SimpleNamespace(generate_feeling=fake_generate_feeling),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/game/chat",
            params={"session_id": "s1", "message": "hi"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert "session_id" in payload
    assert "character_response" in payload
    assert "psychological_state" in payload
    assert "language" in payload


def test_chat_loads_history_before_saving_current_message(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    store = StubSessionStore()
    monkeypatch.setattr(conversation_module, "session_store", store)

    async def fake_generate_feeling(**_):
        return SimpleNamespace(content="こんにちは")

    monkeypatch.setattr(
        conversation_module,
        "llm_service",
        SimpleNamespace(generate_feeling=fake_generate_feeling),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/game/chat",
            params={"session_id": "s1", "message": "現在の発言"},
        )

    assert response.status_code == 200
    assert store.calls.index("conversation_history") < store.calls.index("save:user")
    assert store.calls.index("timeline") < store.calls.index("save:user")
