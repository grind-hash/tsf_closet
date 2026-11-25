"""立ち絵プロンプトの年齢指定と生成経路の検証。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.services.portrait_generation import (
    V5_AUTO_REFERENCE_STRENGTH,
    build_portrait_prompt,
    character_reference_entry,
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


@pytest.mark.parametrize(
    ("outfit_changed", "has_fresh_portrait", "include_outfit"),
    [(False, False, True), (True, False, False), (True, True, True)],
)
def test_v5_character_reference_switches_outfit_flag(
    outfit_changed: bool, has_fresh_portrait: bool, include_outfit: bool
) -> None:
    """V5 は強度を下げず、旧衣装を引き継ぐかを include_outfit で表す。"""
    entry = character_reference_entry(
        b"ref",
        outfit_changed=outfit_changed,
        has_fresh_portrait=has_fresh_portrait,
        image_model="nai-diffusion-5-full",
    )
    assert entry == {
        "image": b"ref",
        "type": "character",
        "include_outfit": include_outfit,
        "strength": V5_AUTO_REFERENCE_STRENGTH,
        "fidelity": 1.0,
    }


def test_v45_character_reference_keeps_weak_reference_on_outfit_change() -> None:
    entry = character_reference_entry(
        b"ref",
        outfit_changed=True,
        has_fresh_portrait=False,
        image_model="nai-diffusion-4-5-full",
    )
    assert entry == {
        "image": b"ref",
        "type": "character",
        "strength": 0.35,
        "fidelity": 0.55,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("image_model", "expected_include_outfit"),
    [("nai-diffusion-5-full", False), ("nai-diffusion-5-full-medium", None)],
)
async def test_portrait_reference_on_v5_models(
    monkeypatch, image_model: str, expected_include_outfit: bool | None
) -> None:
    generate = AsyncMock(return_value=SimpleNamespace(images=[b"portrait"], cost_usd=0))
    monkeypatch.setattr(
        "gateway.services.portrait_generation.image_service.generate_image", generate
    )
    await generate_portrait_bytes(
        tags="1girl, adult, dress",
        nsfw_mode=True,
        provider="novelai",
        image_model=image_model,
        reference_bytes=b"current-portrait",
        use_character_reference=True,
    )
    references = generate.await_args.kwargs["character_references"]
    if expected_include_outfit is None:
        # 節約モードは精密参照に非対応
        assert references is None
    else:
        assert references[0]["include_outfit"] is expected_include_outfit
        assert references[0]["strength"] == V5_AUTO_REFERENCE_STRENGTH
