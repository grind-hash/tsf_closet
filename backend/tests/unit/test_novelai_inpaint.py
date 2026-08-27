"""NovelAI インペイント経路（マスク正規化・infill アクション・モデル差し替え）のテスト。"""

from __future__ import annotations

import base64
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from gateway.services import image_generation as ig


def _png(size: tuple[int, int], color: str = "green") -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _mask_png(size: tuple[int, int], box: tuple[int, int, int, int]) -> bytes:
    """box の内側だけ不透明な白、それ以外は透明の RGBA マスク。"""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    for x in range(box[0], box[2]):
        for y in range(box[1], box[3]):
            img.putpixel((x, y), (255, 255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client(monkeypatch):
    """リクエスト直前の req を捕まえられるようにしたクライアント。"""
    instance = ig.NovelAIImageClient(
        api_key="test-key",
        model="nai-diffusion-4-5-full",
        negative_prompt="lowres",
        i2i_strength=0.9,
        i2i_noise=0.2,
    )
    sent: dict[str, object] = {}

    async def _generate(req):
        sent["req"] = req
        return [Image.new("RGB", (8, 8), "purple")]

    fake_client = SimpleNamespace(
        api_client=SimpleNamespace(image=SimpleNamespace(generate=_generate))
    )

    async def _fake_get_client():
        return fake_client

    monkeypatch.setattr(instance, "_get_client", _fake_get_client)

    async def _convert(_params, _client):
        return SimpleNamespace(model=None, action=None, parameters=SimpleNamespace())

    monkeypatch.setattr(ig, "async_convert_user_params_to_api_request", _convert)
    instance._sent = sent  # type: ignore[attr-defined]
    return instance


@pytest.mark.asyncio
async def test_mask_switches_to_infill_and_inpaint_model(client):
    base = _png((832, 1216))
    await client.generate(
        prompt="1girl, smiling",
        image_bytes=base,
        mask_bytes=_mask_png((832, 1216), (200, 200, 400, 400)),
        inpaint_strength_override=0.8,
        raw_prompt=True,
    )
    req = client._sent["req"]
    assert req.action == "infill"
    assert req.model == "nai-diffusion-4-5-full-inpainting"
    assert req.parameters.add_original_image is False
    assert req.parameters.inpaintImg2ImgStrength == 0.8
    assert req.parameters.img2img is None
    assert req.parameters.mask


@pytest.mark.asyncio
async def test_no_mask_keeps_img2img(client):
    await client.generate(
        prompt="1girl",
        image_bytes=_png((832, 1216)),
        raw_prompt=True,
    )
    req = client._sent["req"]
    assert req.action == "img2img"
    assert req.model == "nai-diffusion-4-5-full"
    assert not hasattr(req.parameters, "mask")


@pytest.mark.parametrize(
    "size",
    [(832, 1216), (1216, 832), (1024, 1024)],
)
@pytest.mark.asyncio
async def test_mask_grid_follows_base_size(client, size):
    """マスクの量子化はベース画像の 1/8 で行う（固定値だと非 portrait で歪む）。"""
    box = (size[0] // 4, size[1] // 4, size[0] // 4 + 96, size[1] // 4 + 96)
    await client.generate(
        prompt="1girl",
        image_bytes=_png(size),
        mask_bytes=_mask_png(size, box),
        raw_prompt=True,
    )
    raw = base64.b64decode(client._sent["req"].parameters.mask)
    mask = Image.open(BytesIO(raw))
    assert mask.size == size
    assert mask.mode == "L"
    bbox = mask.getbbox()
    assert bbox is not None
    # 1/8 グリッドで量子化されるので、白領域の境界は 8 の倍数に揃う
    assert all(value % 8 == 0 for value in bbox), bbox
