"""mask_service の一覧・保存・削除。"""

from __future__ import annotations

import base64
import json
import os
import time

import pytest

from gateway.services import mask_service
from gateway.settings.config import settings

PNG = base64.b64encode(b"\x89PNG-fake").decode()


@pytest.fixture
def mask_dirs(tmp_path, monkeypatch):
    system_dir = tmp_path / "base" / "images" / "masks"
    system_dir.mkdir(parents=True)
    (system_dir / "system_mask_upper_body.png").write_bytes(b"sys")
    monkeypatch.setattr(mask_service, "BASE_DIR", tmp_path / "base")
    monkeypatch.setattr(settings, "history_masks_dir", tmp_path / "history")
    monkeypatch.setattr(settings, "preset_masks_dir", tmp_path / "presets")
    return tmp_path


def test_list_masks_reports_existing_system_masks_only(mask_dirs):
    listing = mask_service.list_masks()
    assert [m.id for m in listing.system] == ["system:system_mask_upper_body.png"]
    assert listing.system[0].name == "上半身マスク（頭部以外）"
    assert listing.system[0].url == "/api/game/masks/system/system_mask_upper_body.png"
    assert listing.history == [] and listing.presets == []
    assert mask_service.system_mask_path("system_mask_upper_body.png") is not None
    assert mask_service.system_mask_path("system_entire_body.png") is None
    assert mask_service.system_mask_path("../etc/passwd") is None


def test_save_preset_writes_image_and_name(mask_dirs):
    listing = mask_service.save_mask(f"data:image/png;base64,{PNG}", "上半身だけ")
    assert len(listing.presets) == 1
    preset = listing.presets[0]
    assert preset.type == "preset" and preset.name == "上半身だけ"
    mask_id = preset.id.split(":", 1)[1]
    assert (
        settings.preset_masks_dir / f"{mask_id}.png"
    ).read_bytes() == b"\x89PNG-fake"
    meta = json.loads((settings.preset_masks_dir / f"{mask_id}.json").read_text())
    assert meta == {"name": "上半身だけ"}
    assert mask_service.preset_mask_path(mask_id) is not None
    # 区切り文字は落とすが、それ以外はそのまま（元の実装と同じ）
    assert mask_service.preset_mask_path("../" + mask_id) is None


def test_save_history_keeps_only_latest_twenty(mask_dirs):
    for index in range(21):
        mask_service.save_mask(PNG, None)
        # mtime の差で並びを決めるため僅かに待つ
        os.utime(
            sorted(settings.history_masks_dir.glob("*.png"))[0],
            (time.time() - 100 + index, time.time() - 100 + index),
        )
    listing = mask_service.list_masks()
    assert len(listing.history) == 20
    assert len(list(settings.history_masks_dir.glob("*.png"))) == 20


def test_save_rejects_invalid_base64(mask_dirs):
    with pytest.raises(mask_service.MaskError) as excinfo:
        mask_service.save_mask("%%%not-base64%%%", None)
    assert excinfo.value.code == "invalid_mask"


def test_delete_preset_removes_files_and_reports_missing(mask_dirs):
    listing = mask_service.save_mask(PNG, "x")
    mask_id = listing.presets[0].id.split(":", 1)[1]
    after = mask_service.delete_preset_mask(mask_id)
    assert after.presets == []
    assert not (settings.preset_masks_dir / f"{mask_id}.json").exists()
    with pytest.raises(mask_service.MaskError) as excinfo:
        mask_service.delete_preset_mask(mask_id)
    assert excinfo.value.code == "not_found"
