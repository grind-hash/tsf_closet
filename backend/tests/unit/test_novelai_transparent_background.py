"""NovelAI の透過生成: V5 だけアルファ透過の指定を送り、アルファ付きの画像を RGBA で保存する。"""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from gateway.services import image_generation as ig


def _client(monkeypatch, model: str, image: Image.Image):
    instance = ig.NovelAIImageClient(
        api_key="test-key",
        model=model,
        negative_prompt="lowres",
        i2i_strength=0.9,
        i2i_noise=0.2,
    )
    sent: dict[str, object] = {}

    async def _generate(req):
        sent["req"] = req
        return [image]

    fake_client = SimpleNamespace(
        api_client=SimpleNamespace(image=SimpleNamespace(generate=_generate))
    )

    async def _fake_get_client():
        return fake_client

    monkeypatch.setattr(instance, "_get_client", _fake_get_client)
    return instance, sent


@pytest.mark.asyncio
async def test_v5_sends_alpha_flags_when_requested(monkeypatch):
    client, sent = _client(
        monkeypatch, "nai-diffusion-5-full", Image.new("RGB", (8, 8), "white")
    )

    await client.generate(prompt="1girl", seed=1, transparent_background=True)

    req = sent["req"]
    assert req.model == "nai-diffusion-5-full"
    assert req.parameters.straight_alpha is True
    assert req.parameters.tag_hint_transparent_background is True


@pytest.mark.asyncio
async def test_alpha_flags_are_not_sent_without_request_or_on_v45(monkeypatch):
    v5, v5_sent = _client(
        monkeypatch, "nai-diffusion-5-full", Image.new("RGB", (8, 8), "white")
    )
    v45, v45_sent = _client(
        monkeypatch, "nai-diffusion-4-5-full", Image.new("RGB", (8, 8), "white")
    )

    await v5.generate(prompt="1girl", seed=1)
    await v45.generate(prompt="1girl", seed=1, transparent_background=True)

    assert not v5_sent["req"].parameters.straight_alpha
    assert not v45_sent["req"].parameters.straight_alpha
    assert not v45_sent["req"].parameters.tag_hint_transparent_background


@pytest.mark.asyncio
async def test_palette_alpha_is_saved_as_rgba_with_faint_alpha_cleared(monkeypatch):
    source = Image.new("RGBA", (4, 1), (200, 100, 50, 255))
    source.putpixel((0, 0), (200, 100, 50, 3))
    client, _ = _client(monkeypatch, "nai-diffusion-5-full", source.convert("PA"))

    result = await client.generate(prompt="1girl", seed=1, transparent_background=True)

    saved = Image.open(BytesIO(result.images[0]))
    assert saved.mode == "RGBA"
    assert saved.getpixel((0, 0))[3] == 0
    assert saved.getpixel((1, 0))[3] == 255
