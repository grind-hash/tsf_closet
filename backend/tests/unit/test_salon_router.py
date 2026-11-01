"""サロンのルーター: 開店の入力検査、応答モデル、エラーコードの写し。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.consts.salon import SALON_DIFFICULTY_INITIAL_CASH
from gateway.databases.models import User
from gateway.routes.salon_router import router
from gateway.services import salon_service as salon_module
from gateway.services.salon_rules import Customer
from gateway.services.session import DEFAULT_USER_ID


@pytest.fixture
def client(isolated_db, monkeypatch) -> TestClient:
    with isolated_db.sync_factory() as db:
        db.add(User(id=DEFAULT_USER_ID))
        db.commit()

    async def fake_pool(_db):
        return [Customer("template", "char1", "水瀬ユウヤ")]

    monkeypatch.setattr(salon_module, "_customer_pool", fake_pool)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_create_run_with_difficulty(client: TestClient) -> None:
    response = client.post("/api/salon/runs", json={"name": "店", "difficulty": "hard"})

    assert response.status_code == 200
    body = response.json()
    assert body["difficulty"] == "hard"
    assert body["cash"] == body["initial_cash"] == SALON_DIFFICULTY_INITIAL_CASH["hard"]
    assert body["visits"][0]["customer"]["name"] == "水瀬ユウヤ"


def test_create_run_defaults_to_normal(client: TestClient) -> None:
    response = client.post("/api/salon/runs", json={"name": "店"})

    assert response.json()["difficulty"] == "normal"


def test_create_run_rejects_unknown_difficulty(client: TestClient) -> None:
    response = client.post(
        "/api/salon/runs", json={"name": "店", "difficulty": "nightmare"}
    )

    assert response.status_code == 422


def test_unknown_run_is_404_and_blank_name_is_400(client: TestClient) -> None:
    missing = client.get("/api/salon/runs/missing")
    blank = client.post("/api/salon/runs", json={"name": "  "})

    assert missing.status_code == 404
    assert missing.json()["detail"]["error"] == "salon_not_found"
    assert blank.status_code == 400
    assert blank.json()["detail"]["error"] == "empty_name"


def test_update_settings_toggles_sensitive(client: TestClient) -> None:
    run = client.post("/api/salon/runs", json={"name": "店"}).json()
    assert run["sensitive"] is False

    response = client.patch(
        f"/api/salon/runs/{run['id']}/settings", json={"sensitive": True}
    )

    assert response.status_code == 200
    assert response.json()["sensitive"] is True
    assert client.get(f"/api/salon/runs/{run['id']}").json()["sensitive"] is True
    missing = client.patch("/api/salon/runs/missing/settings", json={"sensitive": True})
    assert missing.status_code == 404
