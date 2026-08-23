"""Prompt Expander API の結合テスト（LLM/画像生成/Anlas はモック）。"""

from __future__ import annotations

import asyncio
import base64
import sys
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gateway.databases.base import Base
from gateway.databases.models import User
from gateway.routes.prompt_expander_router import router
from gateway.services import prompt_expander_service as pe
from gateway.services.anlas_service import AnlasBalance, NovelAIUsage
from gateway.services.image_generation import ImageGenerationResult


def _png(color: str = "red") -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="PNG")
    return buf.getvalue()


def _png_b64(color: str = "red") -> str:
    return base64.b64encode(_png(color)).decode()


async def _setup_database(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed(factory):
    async with factory() as db:
        db.add(User(id="default-user"))
        await db.commit()


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "pe_api.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    asyncio.run(_setup_database(engine))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    asyncio.run(_seed(factory))

    router_module = sys.modules["gateway.routes.prompt_expander_router"]
    monkeypatch.setattr(router_module, "async_session_factory", factory)
    monkeypatch.setattr(pe, "async_session_factory", factory)
    monkeypatch.setattr(pe.settings, "prompt_expander_images_dir", tmp_path / "imgs")
    monkeypatch.setattr(pe.settings, "novelai_api_key", "test-key")

    async def _no_global_memory(user_id: str = "default-user"):
        return None

    monkeypatch.setattr(pe.settings_service, "get_memory_text", _no_global_memory)

    async def _anlas():
        return AnlasBalance(
            fixed_anlas=100,
            purchased_anlas=5,
            total_anlas=105,
            usage=NovelAIUsage(
                percent=80, is_negative=False, time_until_next_percent=600
            ),
        )

    monkeypatch.setattr(pe, "fetch_anlas_safely", _anlas)
    monkeypatch.setattr(
        pe.image_service,
        "generate_image",
        AsyncMock(
            return_value=ImageGenerationResult(
                images=[_png("purple")],
                provider="novelai",
                model="nai-diffusion-5-full",
                seed=99,
            )
        ),
    )
    monkeypatch.setattr(
        pe.llm_service,
        "generate_text",
        AsyncMock(
            return_value=SimpleNamespace(content="1girl, red dress", cost_usd=None)
        ),
    )

    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as test_client:
        yield test_client
    asyncio.run(engine.dispose())


def test_settings_get_and_put(client: TestClient):
    res = client.get("/api/prompt-expander/settings")
    assert res.status_code == 200
    body = res.json()
    assert body["settings"]["text_model"] == "glm-4-6"
    assert body["settings"]["confirm_before_generate"] is True
    assert [o["id"] for o in body["text_model_options"]] == ["glm-4-6", "xialong-v1"]
    assert body["max_character_prompts"]["nai-diffusion-5-full"] == 22
    assert body["max_character_prompts"]["nai-diffusion-4-5-full"] == 6
    assert body["image_sizes"] == ["portrait", "landscape", "square"]
    assert body["novelai_configured"] is True

    res = client.put(
        "/api/prompt-expander/settings",
        json={"image_model": "nai-diffusion-5-curated", "seed": 12, "use_memory": True},
    )
    assert res.status_code == 200
    assert res.json()["settings"]["image_model"] == "nai-diffusion-5-curated"
    assert res.json()["settings"]["seed"] == 12

    res = client.put("/api/prompt-expander/settings", json={"seed": None})
    assert res.status_code == 200
    assert res.json()["settings"]["seed"] is None
    assert res.json()["settings"]["image_model"] == "nai-diffusion-5-curated"

    res = client.put("/api/prompt-expander/settings", json={"text_model": "gpt-4"})
    assert res.status_code == 422


def test_session_entry_flow(client: TestClient, tmp_path: Path):
    res = client.post("/api/prompt-expander/sessions", json={"title": "テスト"})
    assert res.status_code == 201
    session = res.json()
    assert session["title"] == "テスト" and session["entry_count"] == 0

    res = client.post(
        f"/api/prompt-expander/sessions/{session['id']}/uploads",
        json={
            "image": "data:image/png;base64," + _png_b64("blue"),
            "instruction": "参考",
        },
    )
    assert res.status_code == 201
    uploaded = res.json()
    assert uploaded["kind"] == "uploaded"
    assert uploaded["image_url"] == f"/prompt-expander/images/{uploaded['id']}"

    res = client.post(
        f"/api/prompt-expander/sessions/{session['id']}/generate",
        json={
            "prompt": "銀髪の少女。",
            "negative_prompt": "眼鏡",
            "character_prompts": ["1girl, a"],
            "character_mode": True,
            "instruction": "銀髪にして",
            "positive_expand_mode": "japanese",
            "image_model": "nai-diffusion-5-full",
            "text_model": "glm-4-6",
            "image_size": "portrait",
            "source_kind": "entry",
            "source_entry_id": uploaded["id"],
            "i2i_strength": 0.5,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    entry = body["entry"]
    assert entry["seed"] == 99
    assert entry["source_kind"] == "entry"
    assert entry["character_prompts"] == ["1girl, a"]
    assert body["anlas"]["total_anlas"] == 105
    assert body["anlas"]["usage"]["percent"] == 80
    kwargs = pe.image_service.generate_image.await_args.kwargs
    assert kwargs["raw_prompt"] is True and kwargs["image_bytes"] == _png("blue")

    res = client.get(f"/api/prompt-expander/images/{entry['id']}")
    assert res.status_code == 200
    assert res.content == _png("purple")
    assert client.get("/api/prompt-expander/images/missing").status_code == 404

    res = client.get(f"/api/prompt-expander/sessions/{session['id']}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["session"]["entry_count"] == 2
    assert [e["id"] for e in detail["entries"]] == [entry["id"], uploaded["id"]]

    res = client.get("/api/prompt-expander/entries", params={"page": 1, "page_size": 1})
    assert res.status_code == 200
    assert res.json()["total"] == 2 and res.json()["has_more"] is True
    assert res.json()["items"][0]["id"] == entry["id"]

    res = client.patch(
        f"/api/prompt-expander/sessions/{session['id']}", json={"title": "改名"}
    )
    assert res.status_code == 200 and res.json()["title"] == "改名"

    res = client.delete(f"/api/prompt-expander/entries/{uploaded['id']}")
    assert res.status_code == 204
    assert not (tmp_path / "imgs" / session["id"] / f"{uploaded['id']}.png").exists()

    res = client.delete(f"/api/prompt-expander/sessions/{session['id']}")
    assert res.status_code == 204
    assert not (tmp_path / "imgs" / session["id"]).exists()
    assert (
        client.get(f"/api/prompt-expander/sessions/{session['id']}").status_code == 404
    )
    assert client.get("/api/prompt-expander/sessions").json()["sessions"] == []


def test_generate_validation_errors(client: TestClient):
    res = client.post("/api/prompt-expander/sessions", json={})
    session_id = res.json()["id"]
    res = client.post(
        f"/api/prompt-expander/sessions/{session_id}/generate",
        json={
            "prompt": "x",
            "image_model": "nai-diffusion-4-5-full",
            "character_prompts": [f"c{i}" for i in range(7)],
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "too_many_characters"
    res = client.post(
        f"/api/prompt-expander/sessions/{session_id}/generate",
        json={
            "prompt": "x",
            "image_model": "nai-diffusion-4-5-full",
            "source_kind": "entry",
        },
    )
    assert res.status_code == 422
    res = client.post(
        "/api/prompt-expander/sessions/missing/generate",
        json={"prompt": "x", "image_model": "nai-diffusion-4-5-full"},
    )
    assert res.status_code == 404


def test_expand_and_suggest(client: TestClient):
    res = client.post(
        "/api/prompt-expander/expand",
        json={
            "instruction": "赤いドレスに",
            "image_model": "nai-diffusion-4-5-full",
            "text_model": "glm-4-6",
        },
    )
    assert res.status_code == 200, res.text
    assert (
        res.json()["positive_prompt"]
        == "1girl, red dress, moe, anime, very aesthetic, best quality"
    )
    assert res.json()["character_prompts"] is None
    assert res.json()["text_model"] == "glm-4-6"

    res = client.post(
        "/api/prompt-expander/expand",
        json={
            "instruction": "",
            "image_model": "nai-diffusion-4-5-full",
            "text_model": "glm-4-6",
        },
    )
    assert res.status_code == 422

    res = client.post(
        "/api/prompt-expander/suggest-characters",
        json={
            "text_model": "glm-4-6",
            "image_model": "nai-diffusion-5-full",
            "count": 2,
        },
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "memory_empty"

    client.put("/api/prompt-expander/settings", json={"memory_text": "銀髪が好き"})
    pe.llm_service.generate_text.return_value = SimpleNamespace(
        content='{"suggestions":[{"title":"銀髪","prompt":"1girl, silver hair"}]}',
        cost_usd=None,
    )
    res = client.post(
        "/api/prompt-expander/suggest-characters",
        json={
            "text_model": "glm-4-6",
            "image_model": "nai-diffusion-5-full",
            "count": 1,
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["suggestions"] == [
        {"title": "銀髪", "prompt": "1girl, silver hair"}
    ]
