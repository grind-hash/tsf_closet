"""お気に入りプロンプト API の結合テスト。"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.databases.models import User
from gateway.routes.favorite_prompts_router import router


async def _seed(factory):
    async with factory() as db:
        db.add(User(id="default-user"))
        await db.commit()


@pytest.fixture
def client(isolated_db):
    asyncio.run(_seed(isolated_db.async_factory))
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as test_client:
        yield test_client


def test_crud_flow(client: TestClient):
    res = client.get("/api/favorite-prompts")
    assert res.status_code == 200
    assert res.json() == {"categories": [], "prompts": []}

    res = client.post(
        "/api/favorite-prompts/categories", json={"label": "衣装", "color": "#aabbcc"}
    )
    assert res.status_code == 201
    category = res.json()
    assert category["color"] == "#AABBCC"

    res = client.post(
        "/api/favorite-prompts",
        json={
            "label": "白ワンピース",
            "content": "white dress, ",
            "category_id": category["id"],
        },
    )
    assert res.status_code == 201
    prompt = res.json()
    assert prompt["category_id"] == category["id"]
    assert prompt["color"] == "#6B7280"

    res = client.patch(
        f"/api/favorite-prompts/{prompt['id']}",
        json={"content": "white sundress", "category_id": None},
    )
    assert res.status_code == 200
    assert res.json()["content"] == "white sundress"
    assert res.json()["category_id"] is None
    assert res.json()["label"] == "白ワンピース"

    res = client.patch(
        f"/api/favorite-prompts/categories/{category['id']}", json={"label": "服"}
    )
    assert res.status_code == 200
    assert res.json()["label"] == "服"

    res = client.get("/api/favorite-prompts")
    body = res.json()
    assert [c["label"] for c in body["categories"]] == ["服"]
    assert [p["label"] for p in body["prompts"]] == ["白ワンピース"]

    res = client.delete(f"/api/favorite-prompts/categories/{category['id']}")
    assert res.status_code == 200
    res = client.delete(f"/api/favorite-prompts/{prompt['id']}")
    assert res.status_code == 200
    assert client.get("/api/favorite-prompts").json() == {
        "categories": [],
        "prompts": [],
    }


def test_errors_use_coded_detail(client: TestClient):
    res = client.post("/api/favorite-prompts", json={"label": " ", "content": "x"})
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "label_required"

    res = client.post(
        "/api/favorite-prompts",
        json={"label": "a", "content": "x", "category_id": "missing"},
    )
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "category_not_found"

    res = client.patch("/api/favorite-prompts/missing", json={"label": "x"})
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "prompt_not_found"

    res = client.delete("/api/favorite-prompts/missing")
    assert res.status_code == 404
    res = client.delete("/api/favorite-prompts/categories/missing")
    assert res.status_code == 404
