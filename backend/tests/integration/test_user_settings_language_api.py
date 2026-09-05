import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.routes.settings_router import router
from tests.support.stubs import StubSettingsService

settings_router_module = importlib.import_module("gateway.routes.settings_router")


def test_user_settings_language_get_put_cycle(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")

    state = {"nsfw_mode": False, "difficulty": "normal", "language": "ja"}

    monkeypatch.setattr(
        settings_router_module,
        "settings_service",
        StubSettingsService(state),
    )

    with TestClient(app) as client:
        put_response = client.put("/api/settings/user", json={"language": "en"})
        get_response = client.get("/api/settings/user")

    assert put_response.status_code == 200
    assert put_response.json()["language"] == "en"
    assert get_response.status_code == 200
    assert get_response.json()["language"] == "en"
