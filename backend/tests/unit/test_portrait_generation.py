"""立ち絵プロンプトの年齢指定と生成経路の検証。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.services.portrait_generation import (
    build_portrait_prompt,
    generate_portrait_bytes,
)


@pytest.mark.parametrize(
    ("tags", "add_proportions"),
    [
        ("1boy, young adult, slim, suit", True),
        ("1girl, 21 years old, petite, coat", True),
        ("1boy, short black hair, suit", False),
        ("1boy, young, suit", False),
        ("1boy, child, coat", False),
        ("1boy, adult, child, suit", False),
        ("1boy, adult, chibi", False),
        ("1girl, adult, 1.3::super-deformed::", False),
        ("1boy, adult, super deformed style", False),
    ],
)
def test_portrait_proportions_respect_age_and_style(
    tags: str, add_proportions: bool
) -> None:
    prompt = build_portrait_prompt(tags, "nai-diffusion-4-5-full")
    assert ("adult proportions" in prompt) is add_proportions
    assert prompt.startswith(tags + ", ")
    assert "full body standing portrait, simple background, white background" in prompt
    assert "transparent background" not in prompt


def test_portrait_preserves_weighted_proportions_without_duplicates() -> None:
    prompt = build_portrait_prompt(
        "1boy, adult, 1.2::adult proportions::", "nai-diffusion-4-5-full"
    )
    assert prompt.count("adult proportions") == 1
    assert "1.2::adult proportions::" in prompt


def test_portrait_keeps_v5_background_and_quality_tags() -> None:
    prompt = build_portrait_prompt(
        "1girl, adult, coat", "nai-diffusion-5-full", nsfw_mode=True
    )
    assert "adult proportions" in prompt
    assert "transparent background" in prompt
    assert "white background" not in prompt
    assert prompt.endswith("very aesthetic, best quality, nsfw")


@pytest.mark.asyncio
async def test_shared_portrait_generator_sends_built_prompt(monkeypatch) -> None:
    generate = AsyncMock(return_value=SimpleNamespace(images=[b"portrait"], cost_usd=0))
    monkeypatch.setattr(
        "gateway.services.portrait_generation.image_service.generate_image", generate
    )
    tags = "1boy, young adult, black hair, shirt, trousers"
    result = await generate_portrait_bytes(
        tags=tags,
        nsfw_mode=False,
        provider="novelai",
        image_model="nai-diffusion-4-5-full",
        reference_bytes=None,
        seed=123,
    )
    assert result == b"portrait"
    assert generate.await_args.args[0] == build_portrait_prompt(
        tags, "nai-diffusion-4-5-full"
    )
    assert generate.await_args.kwargs["seed"] == 123
    assert generate.await_args.kwargs["character_references"] is None
