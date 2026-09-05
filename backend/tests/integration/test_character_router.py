"""Integration tests for character_router endpoints (spec 005, T014)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gateway.databases.base import Base
from gateway.databases.models import Session as SessionORM
from gateway.databases.models import User

character_router_module = importlib.import_module("gateway.routes.character_router")
character_router = character_router_module.router


@pytest.fixture
async def app_and_client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "router.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(User(id="user-1"))
        db.add(
            SessionORM(
                id="sess-1",
                user_id="user-1",
                current_image_path="img/start.png",
                character_id="char-1",
            )
        )
        await db.commit()

    monkeypatch.setattr(character_router_module, "async_session_factory", factory)

    app = FastAPI()
    app.include_router(character_router, prefix="/api")
    return app, factory


def test_create_and_list_two_characters(app_and_client):
    app, _ = app_and_client
    with TestClient(app) as client:
        resp = client.post(
            "/api/game/session/sess-1/characters",
            json={"name": "Alice"},
        )
        assert resp.status_code == 201, resp.text
        first = resp.json()
        assert first["slot_index"] == 0

        resp = client.post(
            "/api/game/session/sess-1/characters",
            json={"name": "Bob"},
        )
        assert resp.status_code == 201
        assert resp.json()["slot_index"] == 1

        resp = client.get("/api/game/session/sess-1/characters")
        assert resp.status_code == 200
        characters = resp.json()["characters"]
        assert [c["name"] for c in characters] == ["Alice", "Bob"]


def test_fifth_character_returns_422(app_and_client):
    app, _ = app_and_client
    with TestClient(app) as client:
        for i in range(4):
            resp = client.post(
                "/api/game/session/sess-1/characters",
                json={"name": f"Char{i}"},
            )
            assert resp.status_code == 201

        resp = client.post(
            "/api/game/session/sess-1/characters",
            json={"name": "Overflow"},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["code"] == "character_limit_exceeded"


def test_session_not_found_returns_404(app_and_client):
    app, _ = app_and_client
    with TestClient(app) as client:
        resp = client.get("/api/game/session/missing/characters")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "session_not_found"


def test_update_and_delete(app_and_client):
    app, _ = app_and_client
    with TestClient(app) as client:
        resp = client.post(
            "/api/game/session/sess-1/characters",
            json={"name": "Alice"},
        )
        char_id = resp.json()["id"]

        resp = client.put(
            f"/api/game/session/sess-1/characters/{char_id}",
            json={"position": "right"},
        )
        assert resp.status_code == 200
        assert resp.json()["position"] == "right"

        resp = client.delete(f"/api/game/session/sess-1/characters/{char_id}")
        assert resp.status_code == 204

        resp = client.get("/api/game/session/sess-1/characters")
        assert resp.json()["characters"] == []
