"""POST /api/game/start と /start-custom がセッション・統計・初期履歴を作ることを確認する。"""

from __future__ import annotations

import base64

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


def test_start_custom_saves_image_and_metadata(client):
    image = base64.b64encode(b"\x89PNG-custom").decode()
    response = client.post(
        "/api/game/start-custom",
        json={
            "image": f"data:image/png;base64,{image}",
            "name": "サクラ",
            "gender": "female",
            "pronoun": "私",
            "base_tags": "1girl, black hair",
            "difficulty": "hard",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"session_id"}
    custom_dir = settings.history_images_dir / "custom"
    images = list(custom_dir.glob("*.png"))
    assert len(images) == 1 and images[0].read_bytes() == b"\x89PNG-custom"
    session_meta = (custom_dir / f"session_{payload['session_id']}.json").read_text()
    assert '"gender": "woman"' in session_meta and '"name": "サクラ"' in session_meta

    listing = client.get("/api/game/custom-characters").json()["characters"]
    assert listing[0]["name"] == "サクラ" and listing[0]["gender"] == "woman"


def test_start_custom_rejects_missing_image(client):
    response = client.post("/api/game/start-custom", json={"name": "x"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_image"


def test_start_custom_with_saved_profile_uses_stored_metadata(client):
    image = base64.b64encode(b"\x89PNG-saved").decode()
    first = client.post(
        "/api/game/start-custom",
        json={
            "image": image,
            "name": "サクラ",
            "gender": "female",
            "pronoun": "私",
            "base_tags": "1girl, black hair",
        },
    )
    assert first.status_code == 200
    custom_dir = settings.history_images_dir / "custom"
    character_id = next(path.stem for path in custom_dir.glob("*.png"))

    # 名前などを送らなくても(送っても)、保存済みの人物設定で始まる
    response = client.post(
        "/api/game/start-custom",
        json={
            "custom_character_id": character_id,
            "use_saved_profile": True,
            "name": "無視される",
        },
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    session_meta = (custom_dir / f"session_{session_id}.json").read_text(
        encoding="utf-8"
    )
    assert '"name": "サクラ"' in session_meta and '"pronoun": "私"' in session_meta
    assert '"gender": "woman"' in session_meta
    assert "無視される" not in session_meta
    assert client.get("/api/game/session").json()["session_id"] == session_id


def test_start_custom_with_unknown_saved_profile_keeps_active_session(client):
    image = base64.b64encode(b"\x89PNG-custom").decode()
    active = client.post(
        "/api/game/start-custom", json={"image": image, "name": "サクラ"}
    ).json()["session_id"]

    response = client.post(
        "/api/game/start-custom",
        json={"custom_character_id": "missing-id", "use_saved_profile": True},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "custom_character_not_found"
    # 見つからないときは、進行中のセッションを非アクティブ化しない
    assert client.get("/api/game/session").json()["session_id"] == active
