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


def test_expand_manga_narration_option_and_notation(client: TestClient):
    pe.llm_service.generate_text.return_value = SimpleNamespace(
        content=(
            '{"base_tags":"1girl, japanese text, text, border",'
            '"panel_description":"There are two comic panels. The first panel shows a girl.",'
            '"character_prompts":[]}'
        ),
        cost_usd=None,
    )
    res = client.post(
        "/api/prompt-expander/expand",
        json={
            "instruction": "①鏡を見る\n②【三日後】「え」",
            "image_model": "nai-diffusion-5-full",
            "text_model": "glm-4-6",
            "manga_mode": True,
            "manga": {"narration": True, "text_language": "ja"},
        },
    )
    assert res.status_code == 200, res.text
    system, user = pe.llm_service.generate_text.await_args.args[:2]
    assert "besides the ones marked with 【...】" in system
    assert '1. panel 2, narration box: "三日後"' in user
    # 落ちた記法の文字は定型文で補われる
    assert 'reads "三日後"' in res.json()["positive_prompt"]
    assert 'says "え"' in res.json()["positive_prompt"]

    res = client.get("/api/prompt-expander/settings")
    assert res.json()["settings"]["manga_narration"] is False
    res = client.put("/api/prompt-expander/settings", json={"manga_narration": True})
    assert res.json()["settings"]["manga_narration"] is True


def test_manga_script_draft_api(client: TestClient):
    pe.llm_service.generate_text.return_value = SimpleNamespace(
        content="①鏡を見る「え…？」\n②戸惑う『どうして…』", cost_usd=None
    )
    res = client.post(
        "/api/prompt-expander/manga-script",
        json={
            "instruction": "彼女が変わってしまう",
            "image_model": "nai-diffusion-5-full",
            "text_model": "glm-4-6",
            "manga": {"panel_count": 2, "dialogue": True},
        },
    )
    assert res.status_code == 200, res.text
    assert res.json() == {
        "script": "①鏡を見る「え…？」\n②戸惑う『どうして…』",
        "text_model": "glm-4-6",
    }
    system = pe.llm_service.generate_text.await_args.args[0]
    assert "Write exactly 2 panels." in system

    res = client.post(
        "/api/prompt-expander/manga-script",
        json={
            "instruction": "彼女が変わってしまう",
            "image_model": "nai-diffusion-4-5-full",
            "text_model": "glm-4-6",
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "manga_requires_v5"


def test_settings_restore_seed_roundtrip(client: TestClient):
    res = client.get("/api/prompt-expander/settings")
    assert res.json()["settings"]["restore_seed"] is False

    res = client.put("/api/prompt-expander/settings", json={"restore_seed": True})
    assert res.status_code == 200
    assert res.json()["settings"]["restore_seed"] is True

    res = client.get("/api/prompt-expander/settings")
    assert res.json()["settings"]["restore_seed"] is True


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
    # 右クリック保存で拡張子付きのファイル名になるよう inline のままファイル名を付ける
    assert res.headers["content-disposition"] == (
        f'inline; filename="{entry["id"]}.png"'
    )
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


def test_suggest_characters_accepts_input_text_without_memory(client: TestClient):
    pe.llm_service.generate_text.return_value = SimpleNamespace(
        content='{"suggestions":[{"title":"店員","prompt":"1girl, waitress"}]}',
        cost_usd=None,
    )
    res = client.post(
        "/api/prompt-expander/suggest-characters",
        json={
            "text_model": "glm-4-6",
            "image_model": "nai-diffusion-5-full",
            "count": 1,
            "input_text": "カフェで働く少女",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["suggestions"] == [{"title": "店員", "prompt": "1girl, waitress"}]
    system, user = pe.llm_service.generate_text.await_args.args[:2]
    assert "カフェで働く少女" in user
    assert "No preference memory is available" in system


def test_expand_manga_mode_api(client: TestClient):
    pe.llm_service.generate_text.return_value = SimpleNamespace(
        content=(
            '{"base_tags":"1girl, english text, text, speech bubble, border",'
            '"panel_description":"There are two comic panels. The first panel shows a girl.",'
            '"character_prompts":[]}'
        ),
        cost_usd=None,
    )
    res = client.post(
        "/api/prompt-expander/expand",
        json={
            "instruction": "2コマ漫画",
            "image_model": "nai-diffusion-5-full",
            "text_model": "glm-4-6",
            "manga_mode": True,
            "manga": {"panel_count": 2, "layout": "vertical", "text_language": "en"},
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["positive_prompt"].startswith(
        "1girl, english text, text, speech bubble, border, "
    )
    assert res.json()["positive_prompt"].endswith(
        "There are two comic panels. The first panel shows a girl."
    )
    assert res.json()["character_prompts"] is None
    system_prompt = pe.llm_service.generate_text.await_args.args[0]
    assert "Describe exactly 2 comic panels." in system_prompt

    # V4.5 では 422
    res = client.post(
        "/api/prompt-expander/expand",
        json={
            "instruction": "2コマ漫画",
            "image_model": "nai-diffusion-4-5-full",
            "text_model": "glm-4-6",
            "manga_mode": True,
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "manga_requires_v5"

    # 範囲外のコマ数はバリデーションエラー
    res = client.post(
        "/api/prompt-expander/expand",
        json={
            "instruction": "2コマ漫画",
            "image_model": "nai-diffusion-5-full",
            "text_model": "glm-4-6",
            "manga_mode": True,
            "manga": {"panel_count": 7},
        },
    )
    assert res.status_code == 422

    # 設定の漫画項目が保存・応答される
    res = client.put(
        "/api/prompt-expander/settings",
        json={"manga_mode": True, "manga_panel_count": 3, "manga_layout": "grid"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["settings"]["manga_mode"] is True
    assert body["settings"]["manga_panel_count"] == 3
    assert body["settings"]["manga_layout"] == "grid"
    assert body["manga_panel_count_max"] == 6
    assert body["manga_layouts"] == ["auto", "vertical", "horizontal", "grid"]
    assert body["manga_text_languages"] == ["auto", "ja", "en"]
    assert body["manga_reading_directions"] == ["rtl", "ltr"]
    assert body["settings"]["manga_reading_direction"] == "rtl"

    # 読み順は拡張リクエストにも載る
    res = client.post(
        "/api/prompt-expander/expand",
        json={
            "instruction": "2コマ漫画",
            "image_model": "nai-diffusion-5-full",
            "text_model": "glm-4-6",
            "manga_mode": True,
            "manga": {"panel_count": 2, "reading_direction": "ltr"},
        },
    )
    assert res.status_code == 200, res.text
    system_prompt = pe.llm_service.generate_text.await_args.args[0]
    assert "Reading order is Western style" in system_prompt


def test_settings_reference_and_transparent_fields(client: TestClient):
    body = client.get("/api/prompt-expander/settings").json()
    assert body["settings"]["use_precise_reference"] is False
    assert body["settings"]["reference_type"] == "character"
    assert body["settings"]["reference_strength"] == 0.85
    assert body["settings"]["reference_fidelity"] == 1.0
    assert body["settings"]["transparent_background"] is False
    assert body["reference_types"] == ["character", "style", "character&style"]
    assert body["anlas_per_reference"] == 5

    res = client.put(
        "/api/prompt-expander/settings",
        json={
            "use_precise_reference": True,
            "reference_type": "character&style",
            "reference_strength": 0.4,
            "reference_fidelity": 0.7,
            "transparent_background": True,
        },
    )
    assert res.status_code == 200, res.text
    saved = res.json()["settings"]
    assert saved["use_precise_reference"] is True
    assert saved["reference_type"] == "character&style"
    assert saved["reference_strength"] == 0.4
    assert saved["reference_fidelity"] == 0.7
    assert saved["transparent_background"] is True
    assert (
        client.put(
            "/api/prompt-expander/settings", json={"reference_strength": 1.5}
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/prompt-expander/settings", json={"reference_type": "vibe"}
        ).status_code
        == 422
    )


def test_generate_with_inpaint_mask(client: TestClient):
    session_id = client.post("/api/prompt-expander/sessions", json={}).json()["id"]
    base = client.post(
        f"/api/prompt-expander/sessions/{session_id}/uploads",
        json={"image": _png_b64("green")},
    ).json()

    res = client.post(
        f"/api/prompt-expander/sessions/{session_id}/generate",
        json={
            "prompt": "1girl, smiling",
            "image_model": "nai-diffusion-4-5-full",
            "source_kind": "entry",
            "source_entry_id": base["id"],
            "i2i_strength": 0.8,
            "inpaint_mask": _png_b64("white"),
        },
    )
    assert res.status_code == 200, res.text
    entry = res.json()["entry"]
    assert entry["inpaint"] is True
    assert entry["mask_url"] == f"/prompt-expander/entries/{entry['id']}/mask"
    assert pe.image_service.generate_image.await_args.kwargs["mask_bytes"] is not None

    # マスクは配信され、同じ領域で作り直せる
    mask_res = client.get(f"/api/prompt-expander/entries/{entry['id']}/mask")
    assert mask_res.status_code == 200
    assert mask_res.headers["content-type"] == "image/png"

    res = client.post(
        f"/api/prompt-expander/sessions/{session_id}/generate",
        json={
            "prompt": "1girl, angry",
            "image_model": "nai-diffusion-4-5-full",
            "source_kind": "entry",
            "source_entry_id": base["id"],
            "inpaint_mask_entry_id": entry["id"],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["entry"]["inpaint"] is True

    # 元画像が無いインペイントは 422（黙って通常生成に落とさない）
    res = client.post(
        f"/api/prompt-expander/sessions/{session_id}/generate",
        json={
            "prompt": "1girl",
            "image_model": "nai-diffusion-4-5-full",
            "inpaint_mask": _png_b64("white"),
        },
    )
    assert res.status_code == 422, res.text

    # マスクなしのエントリにはマスク配信が無い
    plain = client.post(
        f"/api/prompt-expander/sessions/{session_id}/generate",
        json={"prompt": "1girl", "image_model": "nai-diffusion-4-5-full"},
    ).json()["entry"]
    assert plain["inpaint"] is False and plain["mask_url"] is None
    assert (
        client.get(f"/api/prompt-expander/entries/{plain['id']}/mask").status_code
        == 404
    )


def test_generate_with_reference_and_transparent_background(client: TestClient):
    session_id = client.post("/api/prompt-expander/sessions", json={}).json()["id"]
    res = client.post(
        f"/api/prompt-expander/sessions/{session_id}/generate",
        json={
            "prompt": "1girl, standing",
            "image_model": "nai-diffusion-4-5-full",
            "reference_kind": "upload",
            "reference_image": _png_b64("blue"),
            "reference_type": "character",
            "reference_strength": 0.85,
            "reference_fidelity": 1.0,
            "transparent_background": True,
        },
    )
    assert res.status_code == 200, res.text
    entry = res.json()["entry"]
    assert entry["reference_kind"] == "upload"
    assert entry["reference_type"] == "character"
    assert entry["reference_strength"] == 0.85
    assert entry["transparent_background"] is True
    # 保存値は接尾辞なし、送信値は白背景タグ付き（V4.5）。
    # 強調は API 既定の 2 段（{{}}）が載る
    assert entry["final_prompt"] == "1girl, standing"
    call = pe.image_service.generate_image.await_args
    assert call.args[0] == (
        "1girl, standing, {{simple background}}, {{white background}}, no shadow"
    )
    assert len(call.kwargs["character_references"]) == 1
    # 一覧・単体取得でも新項目が返る
    listed = client.get("/api/prompt-expander/entries").json()["items"][0]
    assert listed["reference_kind"] == "upload"
    assert listed["transparent_background"] is True

    # V5 では精密参照は 422
    res = client.post(
        f"/api/prompt-expander/sessions/{session_id}/generate",
        json={
            "prompt": "1girl",
            "image_model": "nai-diffusion-5-full",
            "reference_kind": "upload",
            "reference_image": _png_b64("blue"),
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "precise_reference_requires_v45"

    # 種別と ID の不整合、範囲外の強度は 422
    res = client.post(
        f"/api/prompt-expander/sessions/{session_id}/generate",
        json={
            "prompt": "1girl",
            "image_model": "nai-diffusion-4-5-full",
            "reference_kind": "entry",
        },
    )
    assert res.status_code == 422
    res = client.post(
        f"/api/prompt-expander/sessions/{session_id}/generate",
        json={
            "prompt": "1girl",
            "image_model": "nai-diffusion-4-5-full",
            "reference_strength": 2,
        },
    )
    assert res.status_code == 422


def test_expand_accepts_transparent_background(client: TestClient):
    res = client.post(
        "/api/prompt-expander/expand",
        json={
            "instruction": "赤いドレスに",
            "image_model": "nai-diffusion-4-5-full",
            "text_model": "glm-4-6",
            "transparent_background": True,
        },
    )
    assert res.status_code == 200, res.text
    system_prompt = pe.llm_service.generate_text.await_args.args[0]
    assert "Transparent background mode is ON" in system_prompt
