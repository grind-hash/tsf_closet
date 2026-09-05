import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.settings import router

settings_router_module = importlib.import_module("gateway.routes.settings_router")


def test_settings_api_backward_compatible_with_new_language_field(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    state = {"nsfw_mode": False, "difficulty": "normal", "language": "ja"}

    class StubSettingsService:
        async def get_user_settings(self):
            return state

        async def update_user_settings(
            self, nsfw_mode=None, difficulty=None, language=None, **_other_fields
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
        response = client.put(
            "/api/settings/user",
            json={"nsfw_mode": True, "difficulty": "hard", "language": "en"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["nsfw_mode"] is True
    assert payload["difficulty"] == "hard"
    assert payload["language"] == "en"
