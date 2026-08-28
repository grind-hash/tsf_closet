"""avatar_router のアップロード・一覧・配信・改名・削除の統合テスト。"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gateway.databases.base import Base
from gateway.databases.models import AdventureRun, User
from gateway.services.session import DEFAULT_USER_ID
from gateway.settings.config import settings
from tests.unit.test_avatar_service import VRM0_PAYLOAD, make_glb

avatar_router_module = importlib.import_module("gateway.routes.avatar_router")
adventure_service_module = importlib.import_module("gateway.services.adventure_service")


@pytest.fixture
async def app(tmp_path: Path, monkeypatch):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'router.db'}", future=True
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(avatar_router_module, "async_session_factory", factory)
    # 削除時に Adventure run の割り当て解除が同じ DB を見るようにする
    monkeypatch.setattr(adventure_service_module, "async_session_factory", factory)
    monkeypatch.setattr(settings, "avatar_models_dir", tmp_path / "models")
    monkeypatch.setattr(settings, "avatar_upload_max_bytes", 1024 * 1024)
    application = FastAPI()
    application.include_router(avatar_router_module.router, prefix="/api")
    application.state.session_factory = factory
    yield application
    await engine.dispose()


def test_upload_list_file_rename_delete(app: FastAPI, tmp_path: Path) -> None:
    glb = make_glb(VRM0_PAYLOAD, b"bin")
    with TestClient(app) as client:
        resp = client.post(
            "/api/avatars",
            files={"file": ("alicia.vrm", glb, "model/gltf-binary")},
            data={"name": "Alicia"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        avatar_id = body["id"]
        assert body["name"] == "Alicia"
        assert body["vrm_spec_version"] == "0"
        assert body["file_size"] == len(glb)
        assert body["file_url"] == f"/avatars/{avatar_id}/file"
        assert body["meta"]["title"] == "Alicia Solid"
        assert (tmp_path / "models" / f"{avatar_id}.vrm").is_file()

        resp = client.get("/api/avatars")
        assert resp.status_code == 200
        assert [item["id"] for item in resp.json()["items"]] == [avatar_id]

        resp = client.get(f"/api/avatars/{avatar_id}/file")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("model/gltf-binary")
        assert resp.content == glb

        resp = client.patch(f"/api/avatars/{avatar_id}", json={"name": "Renamed"})
        assert resp.status_code == 200 and resp.json()["name"] == "Renamed"
        resp = client.patch(f"/api/avatars/{avatar_id}", json={"name": ""})
        assert resp.status_code == 422

        resp = client.delete(f"/api/avatars/{avatar_id}")
        assert resp.status_code == 204
        assert not (tmp_path / "models" / f"{avatar_id}.vrm").exists()
        assert client.get(f"/api/avatars/{avatar_id}/file").status_code == 404
        assert client.delete(f"/api/avatars/{avatar_id}").status_code == 404
        assert client.get("/api/avatars").json() == {"items": []}


async def test_delete_detaches_avatar_from_adventure_runs(app: FastAPI) -> None:
    """削除したモデルを表示中の run から割り当てを外す(残すと配信が 404 になる)。"""
    factory = app.state.session_factory
    glb = make_glb(VRM0_PAYLOAD, b"bin")
    with TestClient(app) as client:
        resp = client.post(
            "/api/avatars", files={"file": ("a.vrm", glb, "model/gltf-binary")}
        )
        assert resp.status_code == 201, resp.text
        avatar_id = resp.json()["id"]

    def make_run(run_id: str, avatar: str) -> AdventureRun:
        return AdventureRun(
            id=run_id,
            user_id=DEFAULT_USER_ID,
            preset="romance",
            title="t",
            objective="o",
            snapshot_json="{}",
            state_json=json.dumps(
                {"companion_mode": True, "companion_avatar_id": avatar, "sim": {}}
            ),
            current_image_path="cur.png",
            initial_image_path="init.png",
            text_model="glm-4-6",
            image_provider="novelai",
            image_model="nai-diffusion-4-5-full",
        )

    async with factory() as db:
        db.add(User(id=DEFAULT_USER_ID))
        db.add(make_run("run-using", avatar_id))
        db.add(make_run("run-other", "someone-else"))
        await db.commit()

    with TestClient(app) as client:
        assert client.delete(f"/api/avatars/{avatar_id}").status_code == 204

    async with factory() as db:
        using = await db.get(AdventureRun, "run-using")
        other = await db.get(AdventureRun, "run-other")
    assert using is not None and other is not None
    assert "companion_avatar_id" not in json.loads(using.state_json)
    assert json.loads(using.state_json)["companion_mode"] is True
    assert json.loads(other.state_json)["companion_avatar_id"] == "someone-else"


def test_upload_rejects_invalid_and_oversize(app: FastAPI, monkeypatch) -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/api/avatars",
            files={"file": ("bad.vrm", b"not a vrm", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_vrm"

        monkeypatch.setattr(settings, "avatar_upload_max_bytes", 64)
        resp = client.post(
            "/api/avatars",
            files={"file": ("big.vrm", b"x" * 4096, "model/gltf-binary")},
        )
        assert resp.status_code == 413
        assert resp.json()["detail"]["code"] == "file_too_large"
        assert client.get("/api/avatars").json() == {"items": []}
