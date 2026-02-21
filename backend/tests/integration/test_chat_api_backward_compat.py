from types import SimpleNamespace
import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.routes.game_router import router

game_router_module = importlib.import_module("gateway.routes.game_router")
llm_service_module = importlib.import_module("gateway.services.llm_service")


class StubSessionStore:
    async def get_session_by_id(self, session_id: str):
        return SimpleNamespace(character_id=None, transformation_count=1)

    async def get_session_stats(self, session_id: str):
        return SimpleNamespace(bloom=40, nsfw_mode=False)

    async def create_session_stats(self, session_id: str):
        return SimpleNamespace(bloom=40, nsfw_mode=False)

    async def get_conversation_history(self, session_id: str):
        return []

    async def get_history(self, session_id: str):
        return []

    async def add_conversation(
        self, session_id: str, role: str, content: str, **kwargs
    ):
        return None

    async def get_session_attribute_texts(self, session_id: str):
        return []

    async def get_user_settings(self):
        return {"language": "ja", "difficulty": "normal", "nsfw_mode": False}


def test_chat_api_keeps_existing_response_fields(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    monkeypatch.setattr(game_router_module, "session_store", StubSessionStore())

    async def fake_generate_feeling(**_):
        return SimpleNamespace(content="こんにちは")

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
    assert "session_id" in payload
    assert "character_response" in payload
    assert "psychological_state" in payload
    assert "language" in payload
