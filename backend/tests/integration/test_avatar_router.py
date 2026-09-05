"""avatar_router のアップロード・一覧・配信・改名・削除の統合テスト。"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.databases.models import AdventureRun, User
from gateway.services.session import DEFAULT_USER_ID
from gateway.settings.config import settings
from tests.unit.test_avatar_service import NO_TITLE_PAYLOAD, VRM0_PAYLOAD, make_glb

avatar_router_module = importlib.import_module("gateway.routes.avatar_router")
adventure_service_module = importlib.import_module("gateway.services.adventure_service")


@pytest.fixture
def app(isolated_db, tmp_path: Path, monkeypatch):
    # isolated_db が avatar_router / adventure_service の session factory を差し替える
    factory = isolated_db.async_factory
    monkeypatch.setattr(settings, "avatar_models_dir", tmp_path / "models")
    monkeypatch.setattr(settings, "avatar_upload_max_bytes", 1024 * 1024)
    application = FastAPI()
    application.include_router(avatar_router_module.router, prefix="/api")
    application.state.session_factory = factory
    return application


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
        assert resp.json()["character_name"] is None
        resp = client.patch(f"/api/avatars/{avatar_id}", json={"name": ""})
        assert resp.status_code == 422
        # 何も指定しない更新は 422
        assert client.patch(f"/api/avatars/{avatar_id}", json={}).status_code == 422

        # キャラクター分類の付け替え。未指定の name は据え置き
        resp = client.patch(
            f"/api/avatars/{avatar_id}",
            json={"character_name": "サクラ", "variant_label": "水着"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"
        assert resp.json()["character_name"] == "サクラ"
        assert resp.json()["variant_label"] == "水着"
        # 空文字で未分類へ戻す
        resp = client.patch(f"/api/avatars/{avatar_id}", json={"character_name": ""})
        assert resp.status_code == 200 and resp.json()["character_name"] is None
        assert resp.json()["variant_label"] == "水着"

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


def test_upload_classifies_character_from_filename(app: FastAPI) -> None:
    """``名前_衣装_….vrm`` は同じキャラクターとして自動分類し、指定があれば従う。"""
    glb = make_glb(VRM0_PAYLOAD, b"bin")
    with TestClient(app) as client:
        auto = client.post(
            "/api/avatars",
            files={"file": ("サクラ_水着_髪束ねたVer.vrm", glb, "model/gltf-binary")},
        )
        assert auto.status_code == 201, auto.text
        assert auto.json()["character_name"] == "サクラ"
        assert auto.json()["variant_label"] == "水着 髪束ねたVer"

        # 空のフォーム欄は FastAPI が未指定に落とすため、未分類は auto_classify=false
        forced = client.post(
            "/api/avatars",
            files={"file": ("サクラ_ドレス.vrm", glb, "model/gltf-binary")},
            data={"auto_classify": "false"},
        )
        assert forced.status_code == 201, forced.text
        assert forced.json()["character_name"] is None
        assert forced.json()["variant_label"] is None

        explicit = client.post(
            "/api/avatars",
            files={"file": ("plain.vrm", glb, "model/gltf-binary")},
            data={"character_name": "サクラ", "variant_label": "制服"},
        )
        assert explicit.status_code == 201, explicit.text
        assert explicit.json()["character_name"] == "サクラ"
        assert explicit.json()["variant_label"] == "制服"

        items = client.get("/api/avatars").json()["items"]
        assert sorted(item["character_name"] or "" for item in items) == [
            "",
            "サクラ",
            "サクラ",
        ]


def test_auto_classify_endpoint_updates_unset_models(app: FastAPI) -> None:
    glb = make_glb(NO_TITLE_PAYLOAD, b"bin")
    with TestClient(app) as client:
        legacy = client.post(
            "/api/avatars",
            files={"file": ("サクラ_水着.vrm", glb, "model/gltf-binary")},
            data={"auto_classify": "false"},
        ).json()
        assert legacy["character_name"] is None
        decided = client.post(
            "/api/avatars",
            files={"file": ("サクラ_ドレス.vrm", glb, "model/gltf-binary")},
            data={"character_name": "別名", "variant_label": "手入力"},
        ).json()

        resp = client.post("/api/avatars/auto-classify")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["updated"] == 1 and body["updated_ids"] == [legacy["id"]]
        by_id = {item["id"]: item for item in body["items"]}
        assert by_id[legacy["id"]]["character_name"] == "サクラ"
        assert by_id[legacy["id"]]["variant_label"] == "水着"
        assert by_id[decided["id"]]["character_name"] == "別名"
        assert by_id[decided["id"]]["variant_label"] == "手入力"

        # 二度目は更新なし、一覧はそのまま返る
        again = client.post("/api/avatars/auto-classify").json()
        assert again["updated"] == 0 and len(again["items"]) == 2


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
