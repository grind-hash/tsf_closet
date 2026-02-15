import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.settings import router

settings_router_module = importlib.import_module("gateway.routes.settings_router")


def test_user_settings_language_get_put_cycle(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    state = {"nsfw_mode": False, "difficulty": "normal", "language": "ja"}

    class StubSettingsService:
        async def get_user_settings(self):
            return state

        async def update_user_settings(
            self, nsfw_mode=None, difficulty=None, language=None
        ):
            if nsfw_mode is not None:
                state["nsfw_mode"] = nsfw_mode
            if difficulty is not None:
                state["difficulty"] = difficulty
            if language is not None:
                state["language"] = language
            return state

    monkeypatch.setattr(
        settings_router_module,
        "settings_service",
        StubSettingsService(),
    )

    with TestClient(app) as client:
        put_response = client.put("/api/settings/user", json={"language": "en"})
        get_response = client.get("/api/settings/user")

    assert put_response.status_code == 200
    assert put_response.json()["language"] == "en"
    assert get_response.status_code == 200
    assert get_response.json()["language"] == "en"
