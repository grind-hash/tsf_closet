"""POST /api/game/start と /start-preset がセッション・統計・初期履歴を作ることを確認する。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.databases.models import User
from gateway.routes.game_router import router
from gateway.services import session as session_module
from gateway.services.characters import character_manager
from gateway.settings.config import settings


@pytest.fixture
def client(isolated_db, tmp_path, monkeypatch):
    # sessions.user_id の外部キー先。アプリ起動時に作られる既定ユーザーに相当する
    with isolated_db.sync_factory() as db:
        db.add(User(id=session_module.DEFAULT_USER_ID))
        db.commit()
    history_dir = tmp_path / "history_images"
    history_dir.mkdir()
    monkeypatch.setattr(settings, "history_images_dir", history_dir)
    monkeypatch.setattr(
        session_module.session_store, "_history_images_dir", history_dir
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as test_client:
        yield test_client


def test_start_with_default_character_creates_initial_history(client):
    if not character_manager.get_all():
        pytest.skip("template characters are not available")
    response = client.post(
        "/api/game/start", json={"difficulty": "bogus", "nsfw_mode": True}
    )
    assert response.status_code == 200
    payload = response.json()
    # 応答スキーマ(GameStartResponse)は session_id だけを返す
    assert set(payload) == {"session_id"}

    session = client.get("/api/game/session").json()
    assert session["session_id"] == payload["session_id"]
    assert [item["instruction"] for item in session["history"]] == ["初期状態"]
    # 不正な難易度は normal に丸め、nsfw_mode は統計に保存される
    assert session["stats"]["difficulty"] == "normal"
    assert session["stats"]["nsfwMode"] is True


def test_start_with_unknown_character_is_400(client):
    response = client.post("/api/game/start", json={"character_id": "nope"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_character"


def test_start_preset_uses_the_character_portrait(client, isolated_db):
    from io import BytesIO

    from PIL import Image

    from gateway.databases.models import CharacterPreset

    portrait_dir = settings.history_images_dir.parent / "character_images" / "p1"
    portrait_dir.mkdir(parents=True)
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    (portrait_dir / "source-1.png").write_bytes(buffer.getvalue())
    with isolated_db.sync_factory() as db:
        db.add(
            CharacterPreset(
                id="p1",
                name="ミナト",
                appearance_tags="short black hair",
                profile_json='{"gender": "man", "pronoun": "俺"}',
                portrait_path="character_images/p1/source-1.png",
            )
        )
        db.add(CharacterPreset(id="p2", name="ハルト", appearance_tags=""))
        db.commit()

    response = client.post(
        "/api/game/start-preset", json={"preset_id": "p1", "self_mode": True}
    )
    missing_portrait = client.post("/api/game/start-preset", json={"preset_id": "p2"})

    assert response.status_code == 200
    session = client.get("/api/game/session").json()
    assert session["session_id"] == response.json()["session_id"]
    assert session["self_mode"] is True
    assert [item["instruction"] for item in session["history"]] == ["初期状態"]
    assert missing_portrait.status_code == 400
    assert missing_portrait.json()["detail"]["error"] == "image_not_found"
