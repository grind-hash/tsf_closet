"""NovelAIImageClient の raw_prompt 経路とノイズ既定値修正のテスト。"""

from __future__ import annotations

import pytest

from gateway.services import image_generation as ig


class _Captured(Exception):
    def __init__(self, params):
        super().__init__("captured")
        self.params = params


@pytest.fixture
def client(monkeypatch):
    instance = ig.NovelAIImageClient(
        api_key="test-key",
        model="nai-diffusion-4-5-full",
        negative_prompt="lowres, bad anatomy",
        i2i_strength=0.9,
        i2i_noise=0.2,
    )

    async def _fake_get_client():
        return object()

    monkeypatch.setattr(instance, "_get_client", _fake_get_client)

    async def _capture(params, _client):
        raise _Captured(params)

    monkeypatch.setattr(ig, "async_convert_user_params_to_api_request", _capture)
    return instance


async def _run(client: ig.NovelAIImageClient, **kwargs):
    with pytest.raises(_Captured) as exc:
        await client.generate(**kwargs)
    return exc.value.params


@pytest.mark.asyncio
async def test_raw_prompt_keeps_japanese_punctuation_and_no_suffix(client):
    params = await _run(
        client,
        prompt="  銀髪の少女が、赤いドレスを着ている。\n背景は公園。 ",
        negative_prompt_override="眼鏡、帽子",
        raw_prompt=True,
    )
    assert params.prompt == "銀髪の少女が、赤いドレスを着ている。 背景は公園。"
    assert "single frame" not in params.prompt
    assert params.negative_prompt == "眼鏡、帽子"


@pytest.mark.asyncio
async def test_raw_prompt_empty_negative_stays_empty(client):
    params = await _run(
        client, prompt="1girl", negative_prompt_override="", raw_prompt=True
    )
    assert params.negative_prompt is None
    params = await _run(
        client, prompt="1girl", negative_prompt_override=None, raw_prompt=True
    )
    assert params.negative_prompt is None


@pytest.mark.asyncio
async def test_non_raw_prompt_is_unchanged(client):
    params = await _run(
        client, prompt="少女、赤いドレス。", negative_prompt_override=None
    )
    assert params.prompt.startswith("少女, 赤いドレス, , single frame")
    assert "no before/after panels" in params.prompt
    assert params.negative_prompt.startswith("lowres, bad anatomy, split screen")


@pytest.mark.asyncio
async def test_raw_prompt_with_characters_has_no_auto_negative(client):
    params = await _run(
        client,
        prompt="2girls",
        negative_prompt_override="",
        raw_prompt=True,
        characters=[{"prompt": "1girl, a"}, {"prompt": "1girl, b"}],
    )
    assert params.negative_prompt is None
    assert params.characters is not None and len(params.characters) == 2


@pytest.mark.asyncio
async def test_noise_zero_is_respected(client):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    # 画像をパースしないよう I2iParams 生成前に捕捉されることはないので、
    # 実在の小さな PNG を使う
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="PNG")
    png = buf.getvalue()
    params = await _run(
        client,
        prompt="1girl",
        image_bytes=png,
        noise_override=0.0,
        inpaint_strength_override=0.5,
        raw_prompt=True,
    )
    assert params.i2i is not None
    assert params.i2i.noise == 0.0
    assert params.i2i.strength == 0.5
    params = await _run(client, prompt="1girl", image_bytes=png, raw_prompt=False)
    assert params.i2i.noise == pytest.approx(0.2)
