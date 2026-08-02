import asyncio
from types import SimpleNamespace
from contextlib import asynccontextmanager
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
    monkeypatch.setattr(service, "_get_novelai_client", lambda nsfw_mode: client)

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

    def get_client(nsfw_mode: bool):
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
