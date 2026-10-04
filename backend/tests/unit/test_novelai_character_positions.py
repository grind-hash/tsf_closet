"""NovelAI の複数人物プロンプトで、登録した立ち位置を座標指定で送るかのテスト。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from gateway.services import image_generation as ig


@pytest.fixture
def client(monkeypatch):
    """SDK の変換は本物のまま、送信直前の req を捕まえるクライアント。"""
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
    instance._sent = sent  # type: ignore[attr-defined]
    return instance


def _characters(*, fixed: bool) -> list[dict]:
    extra = {"fixed_position": True} if fixed else {}
    return [
        {"prompt": "1girl, brown hair", "position": (0.1, 0.5), **extra},
        {"prompt": "1girl, blonde hair", "position": (0.5, 0.5), **extra},
        {"prompt": "1boy, black hair", "position": (0.9, 0.5), **extra},
    ]


@pytest.mark.asyncio
async def test_fixed_positions_switch_to_custom_coordinates(client):
    await client.generate(prompt="room", characters=_characters(fixed=True), seed=1)
    req = client._sent["req"]
    assert req.parameters.use_coords is True
    assert req.parameters.v4_prompt.use_coords is True
    centers = [
        (c.centers[0].x, c.centers[0].y)
        for c in req.parameters.v4_prompt.caption.char_captions
    ]
    assert centers == [(0.1, 0.5), (0.5, 0.5), (0.9, 0.5)]


@pytest.mark.asyncio
async def test_positions_stay_ai_choice_without_fixed_flag(client):
    await client.generate(prompt="room", characters=_characters(fixed=False), seed=1)
    req = client._sent["req"]
    assert req.parameters.use_coords is False
    assert req.parameters.v4_prompt.use_coords is False
