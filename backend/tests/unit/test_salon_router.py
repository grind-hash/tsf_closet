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
    monkeypatch.setattr(
        salon_module,
        "_customer_pool",
        lambda: [Customer("template", "char1", "水瀬ユウヤ")],
    )
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
