"""Integration tests for character_router endpoints (spec 005, T014)."""

from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.databases.models import Session as SessionORM
from gateway.databases.models import User
from gateway.services.character_service import CHARACTER_LIMIT

character_router_module = importlib.import_module("gateway.routes.character_router")
character_router = character_router_module.router


@pytest.fixture
async def app_and_client(isolated_db):
    factory = isolated_db.async_factory
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


def test_character_over_limit_returns_422(app_and_client):
    app, _ = app_and_client
    with TestClient(app) as client:
        for i in range(CHARACTER_LIMIT):
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


def test_cast_fields_round_trip(app_and_client):
    app, _ = app_and_client
    with TestClient(app) as client:
        resp = client.post(
            "/api/game/session/sess-1/characters",
            json={
                "name": "Sakura",
                "negative_tags": "glasses",
                "on_stage": False,
                "thumbnail_url": "/prompt-expander/images/abc",
                "profile": {
                    "personality": "面倒見がよい",
                    "reaction_style": "cheerful",
                    "pronoun": "わたし",
                    "gender": "woman",
                    "interests": ["料理"],
                },
            },
        )
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert created["negative_tags"] == "glasses"
        assert created["on_stage"] is False
        assert created["thumbnail_url"] == "/prompt-expander/images/abc"
        assert created["profile"]["pronoun"] == "わたし"

        resp = client.put(
            f"/api/game/session/sess-1/characters/{created['id']}",
            json={"on_stage": True, "profile": {"reaction_style": "shy"}},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["on_stage"] is True
        assert updated["profile"]["reaction_style"] == "shy"
        # 他の列は変わらない
        assert updated["negative_tags"] == "glasses"


def test_external_thumbnail_url_is_rejected(app_and_client):
    app, _ = app_and_client
    with TestClient(app) as client:
        resp = client.post(
            "/api/game/session/sess-1/characters",
            json={"name": "Sakura", "thumbnail_url": "https://example.com/a.png"},
        )
        assert resp.status_code == 422


def test_group_preset_save_and_apply_replaces_non_protagonists(app_and_client):
    app, factory = app_and_client
    with TestClient(app) as client:
        for name in ("Sakura", "Mio"):
            client.post(
                "/api/game/session/sess-1/characters",
                json={"name": name, "negative_tags": f"neg-{name}"},
            )
        resp = client.post(
            "/api/game/character-group-presets",
            json={"name": "いつもの二人", "from_session_id": "sess-1"},
        )
        assert resp.status_code == 201, resp.text
        group = resp.json()
        assert [m["name"] for m in group["members"]] == ["Sakura", "Mio"]
        assert group["members"][0]["negative_tags"] == "neg-Sakura"

        # 登場人物を入れ替えてから組み合わせを適用すると、元の二人に戻る
        listed = client.get("/api/game/session/sess-1/characters").json()
        for character in listed["characters"]:
            client.delete(f"/api/game/session/sess-1/characters/{character['id']}")
        client.post("/api/game/session/sess-1/characters", json={"name": "Ren"})

        resp = client.post(
            f"/api/game/session/sess-1/characters/from-group/{group['id']}"
        )
        assert resp.status_code == 200, resp.text
        names = [c["name"] for c in resp.json()["characters"]]
        assert names == ["Sakura", "Mio"]

        resp = client.get("/api/game/character-group-presets")
        assert [g["name"] for g in resp.json()["groups"]] == ["いつもの二人"]

        resp = client.delete(f"/api/game/character-group-presets/{group['id']}")
        assert resp.status_code == 204
        resp = client.post(
            f"/api/game/session/sess-1/characters/from-group/{group['id']}"
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "group_preset_not_found"


def test_resolve_source_missing_session_returns_404(app_and_client):
    app, _ = app_and_client
    with TestClient(app) as client:
        resp = client.post(
            "/api/game/characters/resolve-source",
            json={"session_id": "missing"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "source_not_found"

        resp = client.post("/api/game/characters/resolve-source", json={})
        assert resp.status_code == 422


def test_generate_profile_failure_returns_502(app_and_client, monkeypatch):
    from gateway.services.character_profile import CharacterProfileGenerationError

    async def fail(**_kwargs):
        raise CharacterProfileGenerationError("invalid_json")

    monkeypatch.setattr(character_router_module, "generate_character_profile", fail)
    app, _ = app_and_client
    with TestClient(app) as client:
        resp = client.post(
            "/api/game/characters/generate-profile",
            json={"name": "Sakura", "memo": "料理が得意"},
        )
        assert resp.status_code == 502
        assert resp.json()["detail"]["code"] == "llm_failure"


def _add_history(factory, history_id: str, states, minutes: int):
    import asyncio
    import json
    from datetime import datetime, timedelta

    from gateway.databases.models import History

    async def _insert():
        async with factory() as db:
            db.add(
                History(
                    id=history_id,
                    session_id="sess-1",
                    instruction=history_id,
                    image_path=f"img/{history_id}.png",
                    character_states_json=json.dumps(states),
                    created_at=datetime(2026, 9, 26, 10, 0)
                    + timedelta(minutes=minutes),
                )
            )
            await db.commit()

    asyncio.run(_insert())


def _delete_history(factory, history_id: str):
    import asyncio

    from gateway.databases.models import History

    async def _delete():
        async with factory() as db:
            await db.delete(await db.get(History, history_id))
            await db.commit()

    asyncio.run(_delete())


def test_list_returns_current_look_from_history(app_and_client):
    app, factory = app_and_client
    with TestClient(app) as client:
        emma = client.post(
            "/api/game/session/sess-1/characters",
            json={"name": "エマ", "appearance_tags": "1girl, red hair, hostess dress"},
        ).json()
        resp = client.get("/api/game/session/sess-1/characters")
        [before] = resp.json()["characters"]
        assert before["look_source"] == "spec"
        assert before["current_tags"] is None

        _add_history(
            factory,
            "hist-1",
            [{"character_id": emma["id"], "tags": "1girl, red hair, bikini"}],
            minutes=1,
        )
        _add_history(
            factory,
            "hist-2",
            [{"character_id": emma["id"], "tags": "1girl, red hair, maid"}],
            minutes=2,
        )
        [current] = client.get("/api/game/session/sess-1/characters").json()[
            "characters"
        ]
        assert current["look_source"] == "history"
        assert current["current_tags"] == "1girl, red hair, maid"
        # 設定は書き換わらない
        assert current["appearance_tags"] == "1girl, red hair, hostess dress"

        # 最新の履歴を消すと、1 つ前の姿に戻る
        _delete_history(factory, "hist-2")
        [reverted] = client.get("/api/game/session/sess-1/characters").json()[
            "characters"
        ]
        assert reverted["current_tags"] == "1girl, red hair, bikini"

        # 「設定の姿に戻す」: 次の手番から設定の姿で描く
        resp = client.put(
            f"/api/game/session/sess-1/characters/{emma['id']}",
            json={"reset_look": True},
        )
        assert resp.status_code == 200
        reset = resp.json()
        assert reset["look_source"] == "spec"
        assert reset["current_tags"] == "1girl, red hair, bikini"
