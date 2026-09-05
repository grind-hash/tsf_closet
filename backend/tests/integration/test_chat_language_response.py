import importlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.routes.game_router import router
from tests.support.stubs import StubSessionStore

game_router_module = importlib.import_module("gateway.routes.game_router")
llm_service_module = importlib.import_module("gateway.services.llm_service")


def test_chat_response_contains_language(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    monkeypatch.setattr(
        game_router_module, "session_store", StubSessionStore(language="en")
    )

    async def fake_generate_feeling(**_):
        return SimpleNamespace(content="Hello there")

    monkeypatch.setattr(
        llm_service_module,
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
    assert payload["language"] == "en"


def test_chat_response_language_query_overrides_settings(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    monkeypatch.setattr(
        game_router_module, "session_store", StubSessionStore(language="ja")
    )

    async def fake_generate_feeling(**_):
        return SimpleNamespace(content="Hello there")

    monkeypatch.setattr(
        llm_service_module,
        "llm_service",
        SimpleNamespace(generate_feeling=fake_generate_feeling),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/game/chat",
            params={"session_id": "s1", "message": "hi", "language": "en"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["language"] == "en"
