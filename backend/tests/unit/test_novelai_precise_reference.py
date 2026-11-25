"""NovelAI の精密参照: V5 は変換後のリクエストへ直接設定し、V4.5 は SDK 経由で送る。"""

from __future__ import annotations

import base64
import json
import warnings
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from gateway.services import image_generation as ig


def _png(size: tuple[int, int] = (64, 96), mode: str = "RGB", color=(10, 20, 30)):
    buf = BytesIO()
    Image.new(mode, size, color).save(buf, format="PNG")
    return buf.getvalue()


def _client(monkeypatch, model: str):
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
        return [Image.new("RGB", (8, 8))]

    fake_client = SimpleNamespace(
        api_client=SimpleNamespace(image=SimpleNamespace(generate=_generate))
    )

    async def _fake_get_client():
        return fake_client

    monkeypatch.setattr(instance, "_get_client", _fake_get_client)
    return instance, sent


def _dumped_parameters(req) -> dict:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        payload = json.loads(req.model_dump_json(exclude_none=True))
    assert [str(w.message) for w in caught] == []
    return payload["parameters"]


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["nai-diffusion-5-full", "nai-diffusion-5-curated"])
async def test_v5_sets_director_references_directly(monkeypatch, model):
    client, sent = _client(monkeypatch, model)
    refs = [
        {"image": _png(), "type": "character&style", "include_outfit": True},
        {"image": _png(), "type": "character&style", "include_outfit": False},
        {"image": _png(), "type": "character", "include_outfit": True},
        {"image": _png(), "type": "character", "include_outfit": False},
        {"image": _png(), "type": "style", "strength": 5},
        # 通常プレイからは base64 文字列で届く
        {
            "image": base64.b64encode(_png()).decode(),
            "type": "costume",
            "strength": 2.05,
        },
    ]
    refs[0]["strength"] = 0.3
    refs[3]["strength"] = 2.15

    await client.generate("1girl", character_references=refs)

    params = _dumped_parameters(sent["req"])
    assert [
        d["caption"]["base_caption"] for d in params["director_reference_descriptions"]
    ] == [
        "character&style",
        "character&style_anyoutfit",
        "character_mainoutfit",
        "character",
        "style",
        "costume",
    ]
    assert all(
        d["legacy_uc"] is False for d in params["director_reference_descriptions"]
    )
    assert params["director_reference_strength_values"] == [
        0.3,
        1.0,
        1.0,
        2.15,
        5.0,
        2.05,
    ]
    assert params["director_reference_secondary_strength_values"] == [0.0] * 6
    assert params["director_reference_information_extracted"] == [1.0] * 6
    assert len(params["director_reference_images"]) == 6
    assert params["params_version"] == 4
    assert params["normalize_reference_strength_multiple"] is True
    assert sent["req"].model == model


@pytest.mark.asyncio
async def test_v5_clamps_strength_to_five(monkeypatch):
    client, sent = _client(monkeypatch, "nai-diffusion-5-full")

    await client.generate(
        "1girl",
        character_references=[{"image": _png(), "type": "style", "strength": 9}],
    )

    params = _dumped_parameters(sent["req"])
    assert params["director_reference_strength_values"] == [5.0]


@pytest.mark.asyncio
async def test_v5_reference_image_is_padded_and_flattened_on_white(monkeypatch):
    client, sent = _client(monkeypatch, "nai-diffusion-5-full")
    # 透明部分の RGB に赤を残した透過 PNG。白背景に合成されないと赤が出る
    transparent = _png(size=(1024, 1536), mode="RGBA", color=(255, 0, 0, 0))

    await client.generate(
        "1girl", character_references=[{"image": transparent, "type": "character"}]
    )

    encoded = sent["req"].parameters.director_reference_images[0]
    image = Image.open(BytesIO(base64.b64decode(encoded)))
    assert image.size == (1024, 1536)
    assert image.convert("RGB").getpixel((512, 768)) == (255, 255, 255)


@pytest.mark.asyncio
async def test_v5_inpaint_drops_references(monkeypatch):
    client, sent = _client(monkeypatch, "nai-diffusion-5-full")
    mask = _png(size=(64, 96), mode="L", color=255)

    await client.generate(
        "1girl",
        image_bytes=_png(),
        mask_bytes=mask,
        character_references=[{"image": _png(), "type": "character"}],
    )

    params = sent["req"].parameters
    assert params.director_reference_images is None
    assert sent["req"].model == "nai-diffusion-5-full-inpainting"


@pytest.mark.asyncio
async def test_economy_model_drops_references(monkeypatch):
    client, sent = _client(monkeypatch, "nai-diffusion-5-full-medium")

    await client.generate(
        "1girl", character_references=[{"image": _png(), "type": "character"}]
    )

    assert sent["req"].parameters.director_reference_images is None


@pytest.mark.asyncio
async def test_v45_drops_costume_and_clamps_strength(monkeypatch):
    client, sent = _client(monkeypatch, "nai-diffusion-4-5-full")

    await client.generate(
        "1girl",
        character_references=[
            {"image": _png(), "type": "costume", "strength": 1.0},
            {
                "image": _png(),
                "type": "character",
                "include_outfit": True,
                "strength": 3.0,
                "fidelity": 0.75,
            },
        ],
    )

    params = _dumped_parameters(sent["req"])
    assert [
        d["caption"]["base_caption"] for d in params["director_reference_descriptions"]
    ] == ["character"]
    assert params["director_reference_strength_values"] == [1.0]
    assert params["director_reference_secondary_strength_values"] == [0.25]
    assert params["params_version"] == 3


@pytest.mark.asyncio
async def test_v45_with_only_costume_sends_no_references(monkeypatch):
    client, sent = _client(monkeypatch, "nai-diffusion-4-5-full")

    await client.generate(
        "1girl", character_references=[{"image": _png(), "type": "costume"}]
    )

    assert sent["req"].parameters.director_reference_images is None
