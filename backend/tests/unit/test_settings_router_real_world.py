"""ユーザー設定 API が、キャラチャットの Web 検索・天気の設定有無を返す。"""

from __future__ import annotations

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.services import real_world_lookup

router_module = importlib.import_module("gateway.routes.settings_router")


def test_user_settings_reports_real_world_configuration(monkeypatch) -> None:
    async def fake_user_settings():
        return {"nsfw_mode": False, "difficulty": "normal", "language": "ja"}

    monkeypatch.setattr(
        router_module.settings_service, "get_user_settings", fake_user_settings
    )
    monkeypatch.setattr(real_world_lookup.settings, "tavily_api_key", "tvly-secret")
    monkeypatch.setattr(real_world_lookup.settings, "weather_location", "")
    app = FastAPI()
    app.include_router(router_module.router, prefix="/api")

    response = TestClient(app).get("/api/settings/user")

    assert response.status_code == 200
    body = response.json()
    assert body["web_search_configured"] is True
    assert body["weather_configured"] is False
    # キーの値そのものは返さない
    assert "tvly-secret" not in response.text
