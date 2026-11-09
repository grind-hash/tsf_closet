"""AI箱庭のアバター画像: プロンプトの組み立てと、横に並んだ2人目の取り除き。"""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from gateway.services import hakoniwa_images as images

SIZE = (400, 600)


def _png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _figures(boxes: list[tuple[int, int, int, int]], *, transparent: bool) -> bytes:
    background = (0, 0, 0, 0) if transparent else (255, 255, 255, 255)
    image = Image.new("RGBA", SIZE, background)
    draw = ImageDraw.Draw(image)
    for box in boxes:
        draw.rectangle(box, fill=(180, 60, 60, 255))
    return _png(image)


def _columns_with_figure(data: bytes) -> list[int]:
    image = Image.open(BytesIO(data)).convert("RGBA")
    mask = images._figure_mask(image)
    return [
        x
        for x in range(image.width)
        if mask.crop((x, 0, x + 1, image.height)).getbbox()
    ]


@pytest.mark.parametrize("transparent", [True, False])
def test_two_side_by_side_figures_become_one_centered(transparent: bool) -> None:
    # 左の人物(十分な大きさがある中でいちばん左)を残す
    data = _figures([(20, 100, 120, 580), (220, 60, 360, 590)], transparent=transparent)

    result = images.isolate_single_figure(data)

    columns = _columns_with_figure(result)
    assert columns, "a figure must remain"
    width = columns[-1] - columns[0] + 1
    assert 95 <= width <= 110
    center = (columns[0] + columns[-1]) / 2
    assert abs(center - SIZE[0] / 2) <= 3
    image = Image.open(BytesIO(result))
    assert image.size == SIZE
    corner = image.convert("RGBA").getpixel((2, 2))
    assert corner == ((0, 0, 0, 0) if transparent else (255, 255, 255, 255))


def test_touching_figures_are_split_at_the_valley() -> None:
    # 2人の手が細くつながっていて、列が途切れない
    data = _figures(
        [(40, 60, 170, 590), (170, 300, 230, 306), (230, 60, 360, 590)],
        transparent=True,
    )

    columns = _columns_with_figure(images.isolate_single_figure(data))

    assert columns[-1] - columns[0] + 1 < 220


def test_a_small_figure_on_the_left_is_not_kept() -> None:
    # 左の塊が小さすぎる(最大の 60% 未満)ときは大きい方を残す
    data = _figures([(20, 400, 90, 590), (200, 60, 360, 590)], transparent=True)

    columns = _columns_with_figure(images.isolate_single_figure(data))

    assert 150 <= columns[-1] - columns[0] + 1 <= 175


def test_single_figure_and_small_detached_items_are_kept() -> None:
    single = _figures([(140, 60, 260, 590)], transparent=True)
    with_prop = _figures([(140, 60, 260, 590), (330, 300, 360, 340)], transparent=True)

    assert images.isolate_single_figure(single) == single
    assert images.isolate_single_figure(with_prop) == with_prop


@pytest.mark.asyncio
@pytest.mark.parametrize("nsfw_mode", [True, False])
async def test_avatar_prompt_keeps_nsfw_setting_and_adds_pose_tags(
    monkeypatch, nsfw_mode: bool
) -> None:
    captured: dict = {}
    duplicated = _figures([(20, 100, 120, 580), (220, 60, 360, 590)], transparent=True)

    async def fake_portrait(**kwargs):
        captured.update(kwargs)
        return duplicated

    monkeypatch.setattr(images, "generate_portrait_bytes", fake_portrait)

    result = await images.generate_avatar_bytes(
        "1girl, long brown hair, delivery uniform",
        image_model="nai-diffusion-5-full",
        nsfw_mode=nsfw_mode,
    )

    assert captured["image_model"] == "nai-diffusion-5-full"
    assert captured["nsfw_mode"] is nsfw_mode
    assert captured["transparent_background"] is True
    assert captured["tags"].endswith(images.AVATAR_POSE_TAGS)
    assert captured["raw_prompt"] is True
    assert "side-by-side" in captured["extra_negative"]
    # 2人並びは1人に直して返す
    assert result != duplicated


@pytest.mark.asyncio
async def test_portrait_request_keeps_nsfw_and_sends_tags_only(monkeypatch) -> None:
    from types import SimpleNamespace

    from gateway.services import portrait_generation

    captured: dict = {}

    async def fake_generate_image(prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        single = _figures([(140, 60, 260, 590)], transparent=True)
        return SimpleNamespace(images=[single], cost_usd=None)

    monkeypatch.setattr(
        portrait_generation.image_service, "generate_image", fake_generate_image
    )
    monkeypatch.setattr(images, "resolve_image_provider", lambda: "novelai")

    await images.generate_avatar_bytes(
        "1girl, long brown hair", image_model="nai-diffusion-5-full", nsfw_mode=True
    )

    assert captured["raw_prompt"] is True
    assert captured["transparent_background"] is True
    assert captured["novelai_model_override"] == "nai-diffusion-5-full"
    assert "nsfw" in captured["prompt"]
    assert "transparent background" in captured["prompt"]
    assert "side-by-side" not in captured["prompt"]
    assert "split screen" in captured["negative_prompt"]
