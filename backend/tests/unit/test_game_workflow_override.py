"""着せ替えゲーム用ワークフローの差し替え (COMFYUI_GAME_*_WORKFLOW_PATH) のテスト。"""

from __future__ import annotations

import json

import pytest

from gateway.settings.config import BASE_DIR, settings

WORKFLOWS_DIR = BASE_DIR / "workflows"
EDIT_LOCAL = WORKFLOWS_DIR / "qwen_image_edit_template_local.json"
EDIT_LOCAL_NSFW = WORKFLOWS_DIR / "qwen_image_edit_template_local_nsfw.json"
EDIT_LOCAL_GGUF = WORKFLOWS_DIR / "qwen_image_edit_template_local_gguf.json"
EDIT_LOCAL_NSFW_GGUF = WORKFLOWS_DIR / "qwen_image_edit_template_local_nsfw_gguf.json"
TXT2IMG_LOCAL = WORKFLOWS_DIR / "qwen_image_txt2img_template_local.json"
TXT2IMG_LOCAL_NSFW = WORKFLOWS_DIR / "qwen_image_txt2img_template_local_nsfw.json"
TXT2IMG_LOCAL_GGUF = WORKFLOWS_DIR / "qwen_image_txt2img_template_local_gguf.json"
TXT2IMG_LOCAL_NSFW_GGUF = (
    WORKFLOWS_DIR / "qwen_image_txt2img_template_local_nsfw_gguf.json"
)


@pytest.mark.parametrize(
    ("workflow_name", "expected"),
    [("instruct_game", EDIT_LOCAL), ("instruct_game_nsfw", EDIT_LOCAL_NSFW)],
)
def test_game_workflow_uses_default_without_override(
    monkeypatch, workflow_name, expected
) -> None:
    monkeypatch.setattr(settings, "comfyui_game_workflow_path", None)
    monkeypatch.setattr(settings, "comfyui_game_nsfw_workflow_path", None)

    assert settings.get_workflow_path(workflow_name) == expected


def test_game_workflow_override_applies_only_to_non_nsfw(monkeypatch) -> None:
    monkeypatch.setattr(settings, "comfyui_game_workflow_path", EDIT_LOCAL_GGUF)
    monkeypatch.setattr(settings, "comfyui_game_nsfw_workflow_path", None)

    assert settings.get_workflow_path("instruct_game") == EDIT_LOCAL_GGUF
    assert settings.get_workflow_path("instruct_game_nsfw") == EDIT_LOCAL_NSFW
    # ゲーム以外のワークフロー名には影響しない
    assert settings.get_workflow_path("qwen_image_edit_local") == EDIT_LOCAL


def test_game_nsfw_workflow_override_applies_only_to_nsfw(
    monkeypatch, tmp_path
) -> None:
    custom = tmp_path / "my_nsfw_workflow.json"
    monkeypatch.setattr(settings, "comfyui_game_workflow_path", None)
    monkeypatch.setattr(settings, "comfyui_game_nsfw_workflow_path", custom)

    assert settings.get_workflow_path("instruct_game_nsfw") == custom
    assert settings.get_workflow_path("instruct_game") == EDIT_LOCAL


@pytest.mark.parametrize(
    ("gguf_path", "base_path"),
    [
        (EDIT_LOCAL_GGUF, EDIT_LOCAL),
        (TXT2IMG_LOCAL_GGUF, TXT2IMG_LOCAL),
        (EDIT_LOCAL_NSFW_GGUF, EDIT_LOCAL_NSFW),
        (TXT2IMG_LOCAL_NSFW_GGUF, TXT2IMG_LOCAL_NSFW),
    ],
)
def test_gguf_templates_differ_from_base_only_in_unet_loader(
    gguf_path, base_path
) -> None:
    """GGUF 版は拡散モデルの読み込みノードだけを差し替え、他は元テンプレートと揃える。"""
    gguf_graph = json.loads(gguf_path.read_text(encoding="utf-8"))
    base_graph = json.loads(base_path.read_text(encoding="utf-8"))

    loader = gguf_graph.pop("37")
    base_graph.pop("37")

    assert loader["class_type"] == "UnetLoaderGGUF"
    assert loader["inputs"]["unet_name"].endswith(".gguf")
    assert gguf_graph == base_graph
