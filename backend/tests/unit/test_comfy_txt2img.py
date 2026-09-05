"""ComfyUI の txt2img 経路(背景など編集元画像なしの生成)のテスト。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from gateway.services.comfy import ComfyUIClient, ComfyUIError
from gateway.services.image_generation import ImageGenerationService, _comfy_size
from gateway.settings.config import BASE_DIR, settings

WORKFLOWS_DIR = BASE_DIR / "workflows"
EDIT_LOCAL = WORKFLOWS_DIR / "qwen_image_edit_template_local.json"
EDIT_LOCAL_NSFW = WORKFLOWS_DIR / "qwen_image_edit_template_local_nsfw.json"
TXT2IMG_LOCAL = WORKFLOWS_DIR / "qwen_image_txt2img_template_local.json"
TXT2IMG_LOCAL_NSFW = WORKFLOWS_DIR / "qwen_image_txt2img_template_local_nsfw.json"


def _install_fake_comfy(monkeypatch, captured: dict) -> None:
    """ComfyUI の HTTP API を MockTransport で置き換え、投入されたグラフを記録する。"""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/prompt":
            captured["prompt"] = json.loads(request.content)
            return httpx.Response(200, json={"prompt_id": "pid-1"})
        if request.method == "POST" and path == "/upload/image":
            captured["uploads"] = captured.get("uploads", 0) + 1
            return httpx.Response(200, json={"name": "uploaded.png"})
        if path == "/history/pid-1":
            return httpx.Response(
                200,
                json={
                    "pid-1": {
                        "status": {"status_str": "success", "completed": True},
                        "outputs": {
                            "60": {
                                "images": [
                                    {
                                        "filename": "out.png",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        },
                    }
                },
            )
        if path == "/view":
            return httpx.Response(200, content=b"png-bytes")
        return httpx.Response(404, text=f"unexpected {request.method} {path}")

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def fake_async_client(**kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)


@pytest.mark.parametrize(
    ("edit_name", "expected"),
    [
        ("qwen_image_edit_template_local.json", TXT2IMG_LOCAL),
        ("qwen_image_edit_template_local_nsfw.json", TXT2IMG_LOCAL_NSFW),
        # 導出先が存在しない / 命名規則に合わない場合は同梱の既定へ倒す
        ("qwen_image_edit_template.json", TXT2IMG_LOCAL),
        ("custom_workflow.json", TXT2IMG_LOCAL),
    ],
)
def test_get_txt2img_workflow_path_derives_from_edit_workflow(
    monkeypatch, edit_name, expected
) -> None:
    monkeypatch.setattr(settings, "comfyui_txt2img_workflow_path", None)

    assert settings.get_txt2img_workflow_path(WORKFLOWS_DIR / edit_name) == expected


def test_get_txt2img_workflow_path_prefers_explicit_setting(
    monkeypatch, tmp_path
) -> None:
    explicit = tmp_path / "my_txt2img.json"
    monkeypatch.setattr(settings, "comfyui_txt2img_workflow_path", explicit)

    assert settings.get_txt2img_workflow_path(EDIT_LOCAL) == explicit


def test_txt2img_templates_use_empty_latent_without_image_inputs() -> None:
    """同梱の txt2img テンプレートは LoadImage を持たず、空 latent をサンプラーに繋ぐ。"""
    for path in (TXT2IMG_LOCAL, TXT2IMG_LOCAL_NSFW):
        graph = json.loads(path.read_text(encoding="utf-8"))
        class_types = {node["class_type"] for node in graph.values()}
        assert "LoadImage" not in class_types
        assert "VAEEncode" not in class_types
        sampler = next(n for n in graph.values() if n["class_type"] == "KSampler")
        latent = graph[sampler["inputs"]["latent_image"][0]]
        assert latent["class_type"] == "EmptySD3LatentImage"
        assert latent["inputs"]["width"] == "__WIDTH__"
        assert latent["inputs"]["height"] == "__HEIGHT__"
        for node in graph.values():
            if node["class_type"] == "TextEncodeQwenImageEditPlus":
                assert "image1" not in node["inputs"]


@pytest.mark.asyncio
async def test_text_to_image_submits_empty_latent_graph_without_upload(
    monkeypatch,
) -> None:
    captured: dict = {}
    _install_fake_comfy(monkeypatch, captured)
    client = ComfyUIClient(
        base_url="http://comfy.test",
        workflow_path=EDIT_LOCAL,
        request_timeout=5,
        poll_interval=0.01,
    )

    result = await client.text_to_image(
        prompt="cozy cafe, no humans",
        negative_prompt="people",
        width=1216,
        height=832,
        seed=42,
        workflow_path=TXT2IMG_LOCAL_NSFW,
    )

    assert result.images == [b"png-bytes"]
    assert "uploads" not in captured
    graph = captured["prompt"]["prompt"]
    sampler = graph["3"]["inputs"]
    assert sampler["seed"] == 42
    latent = graph[sampler["latent_image"][0]]["inputs"]
    assert (latent["width"], latent["height"]) == (1216, 832)
    assert graph["111"]["inputs"]["prompt"] == "cozy cafe, no humans"
    assert graph["110"]["inputs"]["prompt"] == "people"
    assert "78" not in graph


@pytest.mark.asyncio
async def test_text_to_image_reports_missing_template(tmp_path) -> None:
    client = ComfyUIClient(base_url="http://comfy.test", workflow_path=EDIT_LOCAL)

    with pytest.raises(ComfyUIError, match="txt2img workflow template not found"):
        await client.text_to_image(prompt="x", workflow_path=tmp_path / "missing.json")


def test_comfy_size_presets() -> None:
    assert _comfy_size(None) == (1216, 832)
    assert _comfy_size("landscape") == (1216, 832)
    assert _comfy_size("portrait") == (832, 1216)
    assert _comfy_size("square") == (1024, 1024)
    assert _comfy_size("unknown") == (1216, 832)


@pytest.mark.asyncio
async def test_generate_image_selfhost_without_source_uses_txt2img(
    monkeypatch,
) -> None:
    """selfhost で編集元画像が無いときは txt2img へ回し、サイズと編集用パスから
    導いたテンプレートを渡す。"""
    monkeypatch.setattr(settings, "comfyui_txt2img_workflow_path", None)
    service = ImageGenerationService(provider="selfhost")
    fake_client = SimpleNamespace(
        text_to_image=AsyncMock(return_value=SimpleNamespace(images=[b"bg"])),
        image_edit=AsyncMock(),
    )
    service._comfy_client = fake_client

    result = await service.generate_image(
        "scenery",
        image_bytes=None,
        size_override="landscape",
        negative_prompt="people",
        seed=7,
        workflow_path=EDIT_LOCAL_NSFW,
    )

    assert result.provider == "selfhost"
    assert result.images == [b"bg"]
    fake_client.image_edit.assert_not_awaited()
    kwargs = fake_client.text_to_image.await_args.kwargs
    assert kwargs["prompt"] == "scenery"
    assert (kwargs["width"], kwargs["height"]) == (1216, 832)
    assert kwargs["negative_prompt"] == "people"
    assert kwargs["seed"] == 7
    assert kwargs["workflow_path"] == TXT2IMG_LOCAL_NSFW


@pytest.mark.asyncio
async def test_generate_image_selfhost_with_source_still_edits() -> None:
    service = ImageGenerationService(provider="selfhost")
    fake_client = SimpleNamespace(
        text_to_image=AsyncMock(),
        image_edit=AsyncMock(return_value=SimpleNamespace(images=[b"edited"])),
    )
    service._comfy_client = fake_client

    result = await service.generate_image("edit", image_bytes=b"src")

    assert result.images == [b"edited"]
    fake_client.text_to_image.assert_not_awaited()
    assert fake_client.image_edit.await_args.kwargs["image_bytes"] == b"src"
