from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.settings import router as settings_router
from gateway.routes.achievements_router import router as achievements_router
import importlib

_settings_router_mod = importlib.import_module("gateway.routes.settings_router")


def test_regression_smoke_for_settings_and_achievements(
    monkeypatch, isolated_achievement_db
):
    app = FastAPI()
    app.include_router(settings_router, prefix="/api")
    app.include_router(achievements_router, prefix="/api")

    state = {"nsfw_mode": False, "difficulty": "normal", "language": "ja"}

    class StubSessionStore:
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

    monkeypatch.setattr("gateway.services.session.session_store", StubSessionStore())

    class StubSettingsService:
        async def get_user_settings(self, user_id="default-user"):
            return dict(state)

        async def update_user_settings(
            self,
            user_id="default-user",
            nsfw_mode=None,
            difficulty=None,
            language=None,
            **_other_fields,
        ):
            if nsfw_mode is not None:
                state["nsfw_mode"] = nsfw_mode
            if difficulty is not None:
                state["difficulty"] = difficulty
            if language is not None:
                state["language"] = language
            return dict(state)

        def get_settings_for_session(self, session_id, settings_model_cls):
            return settings_model_cls()

        def update_settings_for_session(
            self,
            session_id,
            updates,
            settings_model_cls,
            inpaint_model_cls,
            change_model_cls,
        ):
            return settings_model_cls()

        def reset_settings_for_session(self, session_id):
            return {"message": "Settings reset to defaults", "session_id": session_id}

        @staticmethod
        def utc_now_iso():
            from datetime import datetime

            return datetime.utcnow().isoformat()

    monkeypatch.setattr(
        _settings_router_mod,
        "settings_service",
        StubSettingsService(),
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
