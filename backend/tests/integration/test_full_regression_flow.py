import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.routes.achievements_router import router as achievements_router
from gateway.settings import router as settings_router
from tests.support.stubs import StubSettingsService

_settings_router_mod = importlib.import_module("gateway.routes.settings_router")


def test_regression_smoke_for_settings_and_achievements(monkeypatch, isolated_db):
    app = FastAPI()
    app.include_router(settings_router, prefix="/api")
    app.include_router(achievements_router, prefix="/api")

    state = {"nsfw_mode": False, "difficulty": "normal", "language": "ja"}

    monkeypatch.setattr(
        _settings_router_mod,
        "settings_service",
        StubSettingsService(state),
    )

    with TestClient(app) as client:
        put_response = client.put(
            "/api/settings/user",
            json={"nsfw_mode": True, "difficulty": "easy", "language": "en"},
        )
        get_response = client.get("/api/settings/user")
        achievements_response = client.get("/api/achievements")

    assert put_response.status_code == 200
    assert get_response.status_code == 200
    assert achievements_response.status_code == 200
