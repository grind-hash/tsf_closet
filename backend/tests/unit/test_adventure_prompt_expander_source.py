"""Adventure の開始素材に Prompt Expander エントリを使う経路のテスト。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from pydantic import ValidationError

from gateway.routes.adventure_router import (
    AdventureCreateRequest,
    AdventureSetupGenerateRequest,
)
from gateway.services import adventure_service as adv
from gateway.services.adventure_service import AdventureError, AdventureService
from gateway.services.prompt_expander_service import PromptExpanderError


def _entry(tmp_path: Path, *, image_model: str = "nai-diffusion-5-full"):
    return SimpleNamespace(
        id="pe-entry-1",
        session_id="pe-sess",
        kind="generated",
        instruction="銀髪にして",
        positive_expand_mode="tags",
        negative_expand_mode="off",
        character_mode=True,
        final_prompt="1girl, silver hair, red dress",
        final_negative_prompt="",
        character_prompts_json='["1girl, silver hair", "1boy, glasses"]',
        image_model=image_model,
        text_model="glm-4-6",
        seed=1,
        i2i_strength=None,
        i2i_noise=None,
        image_size="portrait",
        source_kind="none",
        source_history_id=None,
        source_entry_id=None,
        image_path=str(tmp_path / "pe-entry-1.png"),
        created_at=datetime(2026, 8, 23, 12, 0, 0),
    )


@pytest.fixture
def pe_source(tmp_path: Path, monkeypatch):
    png_path = tmp_path / "pe-entry-1.png"
    buf = BytesIO()
    Image.new("RGB", (64, 64), "red").save(buf, format="PNG")
    png_path.write_bytes(buf.getvalue())

    @asynccontextmanager
    async def _fake_factory():
        yield object()

    monkeypatch.setattr(adv, "async_session_factory", _fake_factory)
    entry = _entry(tmp_path)
    monkeypatch.setattr(
        adv.PromptExpanderService, "get_entry", AsyncMock(return_value=entry)
    )
    monkeypatch.setattr(adv, "resolve_entry_image_file", lambda e: png_path)
    return entry, png_path


@pytest.mark.asyncio
async def test_build_snapshot_from_prompt_expander_entry(pe_source):
    entry, png_path = pe_source
    service = AdventureService()
    snapshot, image_path, appearance, nsfw = await service._build_snapshot(
        None, None, source_prompt_expander_entry_id="pe-entry-1"
    )
    assert image_path == png_path
    assert (
        appearance == "1girl, silver hair, red dress, 1girl, silver hair, 1boy, glasses"
    )
    assert nsfw is True
    assert snapshot["source_prompt_expander_entry_id"] == "pe-entry-1"
    assert snapshot["source_session_id"] is None
    assert snapshot["character_name"] is None
    assert snapshot["attributes"] == [] and snapshot["timeline"] == []
    assert snapshot["stats"] is None
    assert snapshot["clothing"] == ""


@pytest.mark.asyncio
async def test_build_snapshot_curated_entry_is_sfw(
    pe_source, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(
        adv.PromptExpanderService,
        "get_entry",
        AsyncMock(
            return_value=_entry(tmp_path, image_model="nai-diffusion-4-5-curated")
        ),
    )
    _, _, _, nsfw = await AdventureService()._build_snapshot(
        None, None, source_prompt_expander_entry_id="pe-entry-1"
    )
    assert nsfw is False


@pytest.mark.asyncio
async def test_build_snapshot_errors(pe_source, monkeypatch):
    service = AdventureService()
    with pytest.raises(AdventureError) as exc:
        await service._build_snapshot(None, None)
    assert exc.value.code == "source_not_found"

    monkeypatch.setattr(adv, "resolve_entry_image_file", lambda e: None)
    with pytest.raises(AdventureError) as exc:
        await service._build_snapshot(None, None, source_prompt_expander_entry_id="x")
    assert exc.value.code == "image_not_found"

    monkeypatch.setattr(
        adv.PromptExpanderService,
        "get_entry",
        AsyncMock(side_effect=PromptExpanderError("entry_not_found", "missing")),
    )
    with pytest.raises(AdventureError) as exc:
        await service._build_snapshot(None, None, source_prompt_expander_entry_id="x")
    assert exc.value.code == "source_not_found"


def test_request_models_require_a_source():
    with pytest.raises(ValidationError):
        AdventureCreateRequest(preset="escape")
    with pytest.raises(ValidationError):
        AdventureSetupGenerateRequest(preset="escape")
    ok = AdventureCreateRequest(preset="escape", source_prompt_expander_entry_id="pe-1")
    assert ok.source_session_id is None
    assert ok.source_prompt_expander_entry_id == "pe-1"
    assert (
        AdventureSetupGenerateRequest(
            preset="romance", source_prompt_expander_entry_id="pe-1"
        ).source_prompt_expander_entry_id
        == "pe-1"
    )
    # リプレイは素材未指定を許す
    assert (
        AdventureCreateRequest(preset="romance", replay_run_id="run-1").replay_run_id
        == "run-1"
    )
    # 従来どおりセッション指定も有効
    assert (
        AdventureCreateRequest(
            preset="escape", source_session_id="sess"
        ).source_session_id
        == "sess"
    )
