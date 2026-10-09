import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.services.image_generation import ImageGenerationService, NovelAIImageClient
from gateway.services.model_execution_gate import ModelExecutionGate


@pytest.mark.asyncio
async def test_same_model_requests_are_serialized() -> None:
    gate = ModelExecutionGate()
    active = 0
    max_active = 0

    async def worker() -> None:
        nonlocal active, max_active
        async with gate.hold("text", "novelai", "glm-4-6"):
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(worker(), worker(), worker())

    assert max_active == 1


@pytest.mark.asyncio
async def test_different_text_models_can_run_in_parallel() -> None:
    gate = ModelExecutionGate()
    active = 0
    max_active = 0
    ready = asyncio.Event()

    async def worker(model: str) -> None:
        nonlocal active, max_active
        async with gate.hold("text", "novelai", model):
            active += 1
            max_active = max(max_active, active)
            if active == 2:
                ready.set()
            await asyncio.wait_for(ready.wait(), timeout=0.5)
            active -= 1

    await asyncio.gather(worker("glm-4-6"), worker("xialong-v1"))

    assert max_active == 2


@pytest.mark.asyncio
async def test_novelai_landscape_size_reaches_low_level_client(monkeypatch) -> None:
    service = ImageGenerationService(provider="novelai")
    generate = AsyncMock(return_value=SimpleNamespace(images=[b"image"]))
    client = SimpleNamespace(
        model="nai-diffusion-4-5-full",
        inpaint_model="nai-diffusion-4-5-full-inpainting",
        generate=generate,
    )
    monkeypatch.setattr(
        service, "_get_novelai_client", lambda nsfw_mode, model=None: client
    )

    await service.edit_image(
        b"source",
        "visual novel scene",
        provider_override="novelai",
        size_override="landscape",
    )

    assert generate.await_args.kwargs["size_override"] == "landscape"


@pytest.mark.asyncio
async def test_novelai_model_override_controls_gate_and_low_level_client(
    monkeypatch,
) -> None:
    service = ImageGenerationService(provider="novelai")
    generate = AsyncMock(return_value=SimpleNamespace(images=[b"image"]))
    client = SimpleNamespace(
        model="nai-diffusion-4-5-curated",
        inpaint_model="nai-diffusion-4-5-curated-inpainting",
        generate=generate,
    )
    held_models: list[str] = []
    client_modes: list[bool] = []

    @asynccontextmanager
    async def hold(_category: str, _provider: str, model: str):
        held_models.append(model)
        yield

    def get_client(nsfw_mode: bool, model: str | None = None):
        client_modes.append(nsfw_mode)
        return client

    monkeypatch.setattr(service, "_get_novelai_client", get_client)
    monkeypatch.setattr(
        "gateway.services.image_generation.model_execution_gate.hold", hold
    )

    await service.generate_image(
        "visual novel scene",
        provider_override="novelai",
        nsfw_mode=False,
        novelai_model_override="nai-diffusion-4-5-full",
    )

    assert held_models == ["nai-diffusion-4-5-full"]
    assert client_modes == [True]
    assert generate.await_args.kwargs["model_override"] == "nai-diffusion-4-5-full"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("image_bytes", "expected_action"),
    [(None, "generate"), (b"source", "img2img")],
)
async def test_novelai_action_matches_source_image(
    monkeypatch, image_bytes, expected_action
) -> None:
    client = NovelAIImageClient(api_key="test", nsfw_mode=True)
    request = SimpleNamespace(model=None, action=None, parameters=SimpleNamespace())
    generated_image = SimpleNamespace(
        save=lambda buffer, **_kwargs: buffer.write(b"image")
    )
    sdk_client = SimpleNamespace(
        api_client=SimpleNamespace(
            image=SimpleNamespace(generate=AsyncMock(return_value=[generated_image]))
        )
    )
    monkeypatch.setattr(client, "_get_client", AsyncMock(return_value=sdk_client))
    monkeypatch.setattr(
        "gateway.services.image_generation.async_convert_user_params_to_api_request",
        AsyncMock(return_value=request),
    )

    await client.generate("visual novel scene", image_bytes=image_bytes)

    assert request.action == expected_action


def _png_bytes(color: tuple[int, int, int], size: tuple[int, int] = (64, 64)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_novelai_v5_uses_sdk_base_model_and_wire_model(monkeypatch) -> None:
    """V5モデルはSDKパラメータへv4.5ベースを入れ、送信直前にreq.modelへ実名を書く。

    また、V5では精密参照(character reference)を防御的に破棄する。
    """
    client = NovelAIImageClient(
        api_key="test", nsfw_mode=True, model="nai-diffusion-5-full"
    )
    request = SimpleNamespace(model=None, action=None, parameters=SimpleNamespace())
    captured: dict = {}
    generated_image = SimpleNamespace(
        save=lambda buffer, **_kwargs: buffer.write(b"image")
    )
    sdk_client = SimpleNamespace(
        api_client=SimpleNamespace(
            image=SimpleNamespace(generate=AsyncMock(return_value=[generated_image]))
        )
    )
    monkeypatch.setattr(client, "_get_client", AsyncMock(return_value=sdk_client))

    async def convert(params, _client):
        captured["sdk_model"] = params.model
        captured["character_references"] = params.character_references
        return request

    monkeypatch.setattr(
        "gateway.services.image_generation.async_convert_user_params_to_api_request",
        convert,
    )

    result = await client.generate(
        "visual novel scene",
        character_references=[
            {"image": b"ref", "type": "character", "strength": 1.0, "fidelity": 1.0}
        ],
    )

    assert captured["sdk_model"] == "nai-diffusion-4-5-full"
    assert captured["character_references"] is None
    assert request.model == "nai-diffusion-5-full"
    assert result.model == "nai-diffusion-5-full"


async def _generate_with_sdk_conversion(
    client: NovelAIImageClient, monkeypatch, **kwargs
):
    """SDK の変換は実物を通し、送信直前のリクエストと結果を返す。"""
    generated_image = SimpleNamespace(
        save=lambda buffer, **_kwargs: buffer.write(b"image")
    )
    generate = AsyncMock(return_value=[generated_image])
    sdk_client = SimpleNamespace(
        api_client=SimpleNamespace(image=SimpleNamespace(generate=generate))
    )
    monkeypatch.setattr(client, "_get_client", AsyncMock(return_value=sdk_client))
    result = await client.generate("visual novel scene", **kwargs)
    return generate.await_args.args[0], result


_ECONOMY_CHARACTERS = [
    {"prompt": "1girl", "negative_prompt": "hat"},
    {"prompt": "1boy", "negative_prompt": "cap"},
]


@pytest.mark.asyncio
async def test_novelai_economy_sends_fixed_sampling_without_custom_negative(
    monkeypatch,
) -> None:
    """節約モードは steps 14・Euler Ancestral・heavy プリセット固定で、独自ネガティブを送らない。"""
    client = NovelAIImageClient(
        api_key="test",
        nsfw_mode=True,
        model="nai-diffusion-5-full-medium",
        negative_prompt="custom negative",
    )

    request, result = await _generate_with_sdk_conversion(
        client, monkeypatch, characters=_ECONOMY_CHARACTERS
    )

    params = request.parameters
    assert request.model == "nai-diffusion-5-full-medium"
    assert result.model == "nai-diffusion-5-full-medium"
    assert params.steps == 14
    assert params.sampler == "k_euler_ancestral"
    assert params.cfg_rescale == 0.0
    assert params.ucPreset == 0  # heavy（SDK 上は "strong"）
    for negative in (
        params.negative_prompt,
        params.v4_negative_prompt.caption.base_caption,
    ):
        assert "custom negative" not in negative
        assert "split screen" not in negative
    assert [c.uc for c in params.characterPrompts] == ["", ""]
    assert [
        c.char_caption for c in params.v4_negative_prompt.caption.char_captions
    ] == ["", ""]


@pytest.mark.asyncio
async def test_novelai_economy_inpaint_uses_regular_v5_inpaint_settings(
    monkeypatch,
) -> None:
    """節約モードでもインペイントは通常の V5 インペイントで送るため、通常の設定を使う。"""
    client = NovelAIImageClient(
        api_key="test",
        nsfw_mode=True,
        model="nai-diffusion-5-full-medium",
        negative_prompt="custom negative",
    )

    request, _result = await _generate_with_sdk_conversion(
        client,
        monkeypatch,
        image_bytes=_png_bytes((128, 128, 128)),
        mask_bytes=_png_bytes((255, 255, 255)),
        characters=_ECONOMY_CHARACTERS,
    )

    params = request.parameters
    assert request.model == "nai-diffusion-5-full-inpainting"
    assert params.steps == client.steps
    assert "custom negative" in params.negative_prompt
    assert [c.uc for c in params.characterPrompts] == ["hat", "cap"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "expected_inpaint"),
    [
        ("nai-diffusion-5-full", "nai-diffusion-5-full-inpainting"),
        # 節約モードのインペイントはモデル名が未確認のため通常の V5 Full インペイント
        ("nai-diffusion-5-full-medium", "nai-diffusion-5-full-inpainting"),
        # V5 CuratedのインペイントはNovelAI本家UIに合わせ4.5 curated inpainting
        ("nai-diffusion-5-curated", "nai-diffusion-4-5-curated-inpainting"),
        ("nai-diffusion-4-5-full", "nai-diffusion-4-5-full-inpainting"),
    ],
)
async def test_novelai_inpaint_model_follows_requested_model(
    monkeypatch, model, expected_inpaint
) -> None:
    nsfw_mode = "full" in model
    client = NovelAIImageClient(api_key="test", nsfw_mode=nsfw_mode, model=model)
    request = SimpleNamespace(model=None, action=None, parameters=SimpleNamespace())
    generated_image = SimpleNamespace(
        save=lambda buffer, **_kwargs: buffer.write(b"image")
    )
    sdk_client = SimpleNamespace(
        api_client=SimpleNamespace(
            image=SimpleNamespace(generate=AsyncMock(return_value=[generated_image]))
        )
    )
    monkeypatch.setattr(client, "_get_client", AsyncMock(return_value=sdk_client))
    monkeypatch.setattr(
        "gateway.services.image_generation.async_convert_user_params_to_api_request",
        AsyncMock(return_value=request),
    )

    result = await client.generate(
        "visual novel scene",
        image_bytes=_png_bytes((128, 128, 128)),
        mask_bytes=_png_bytes((255, 255, 255)),
    )

    assert request.model == expected_inpaint
    assert result.model == expected_inpaint
