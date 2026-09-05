import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.settings import router
from tests.support.stubs import StubSettingsService

settings_router_module = importlib.import_module("gateway.routes.settings_router")


def test_settings_api_backward_compatible_with_new_language_field(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    state = {"nsfw_mode": False, "difficulty": "normal", "language": "ja"}

    monkeypatch.setattr(
        settings_router_module,
        "settings_service",
        StubSettingsService(state),
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
