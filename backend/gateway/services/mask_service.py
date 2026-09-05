"""インペイント用マスク（NovelAI 専用）の一覧・保存・削除。

- システムマスク: `images/masks/` の固定ファイル
- 履歴マスク: 変身時に自動保存（最新 20 件を保持）
- プリセットマスク: ユーザーが名前を付けて保存（`.json` に名前を持つ）
"""

from __future__ import annotations

import base64
import contextlib
import json
import uuid
from datetime import datetime
from pathlib import Path

from ..schemas.novelai import MaskInfo, MaskListResponse
from ..settings.config import BASE_DIR, settings

SYSTEM_MASK_LABELS = {
    "system_mask_upper_body.png": "上半身マスク（頭部以外）",
    "system_mask_upper_body_and_head.png": "上半身マスク（頭部含む）",
    "system_mask_bottom_body.png": "下半身マスク",
    "system_entire_body_excluding_face.png": "全身マスク（頭部以外）",
    "system_entire_body.png": "全身マスク",
}

HISTORY_MASK_LIMIT = 20


class MaskError(RuntimeError):
    """マスク操作のエラー。`code` は invalid_mask / not_found / delete_failed。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _safe_id(mask_id: str) -> str:
    return mask_id.replace("/", "").replace("\\", "")


def system_mask_path(filename: str) -> Path | None:
    """登録済みのシステムマスクなら実ファイルの Path、それ以外は None。"""
    if filename not in SYSTEM_MASK_LABELS:
        return None
    path = BASE_DIR / "images" / "masks" / filename
    return path if path.exists() else None


def history_mask_path(mask_id: str) -> Path | None:
    path = settings.history_masks_dir / f"{_safe_id(mask_id)}.png"
    return path if path.exists() else None


def preset_mask_path(mask_id: str) -> Path | None:
    path = settings.preset_masks_dir / f"{_safe_id(mask_id)}.png"
    return path if path.exists() else None


def _by_mtime_desc(directory: Path) -> list[Path]:
    return sorted(
        directory.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True
    )


def list_masks() -> MaskListResponse:
    """システムマスク、履歴マスク（最新 20 件）、ユーザープリセットを返す。"""
    system_dir = BASE_DIR / "images" / "masks"
    history_dir = settings.history_masks_dir
    preset_dir = settings.preset_masks_dir
    history_dir.mkdir(parents=True, exist_ok=True)
    preset_dir.mkdir(parents=True, exist_ok=True)

    system_masks = [
        MaskInfo(
            id=f"system:{filename}",
            name=label,
            type="system",
            url=f"/api/game/masks/system/{filename}",
        )
        for filename, label in SYSTEM_MASK_LABELS.items()
        if (system_dir / filename).exists()
    ]
    history_masks = [
        MaskInfo(
            id=f"history:{path.stem}",
            name=path.stem,
            type="history",
            url=f"/api/game/masks/history/{path.stem}",
            created_at=datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        )
        for path in _by_mtime_desc(history_dir)[:HISTORY_MASK_LIMIT]
    ]
    preset_masks = []
    for path in _by_mtime_desc(preset_dir):
        # メタデータファイルから名前を読み込み
        meta_path = preset_dir / f"{path.stem}.json"
        name = path.stem
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                name = meta.get("name", path.stem)
            except Exception:
                name = path.stem
        preset_masks.append(
            MaskInfo(
                id=f"preset:{path.stem}",
                name=name,
                type="preset",
                url=f"/api/game/masks/preset/{path.stem}",
                created_at=datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            )
        )
    return MaskListResponse(
        system=system_masks, history=history_masks, presets=preset_masks
    )


def save_mask(mask_base64: str, name: str | None) -> MaskListResponse:
    """マスクを保存して最新一覧を返す。name があればプリセット、無ければ履歴。"""
    history_dir = settings.history_masks_dir
    preset_dir = settings.preset_masks_dir
    history_dir.mkdir(parents=True, exist_ok=True)
    preset_dir.mkdir(parents=True, exist_ok=True)

    data = mask_base64
    if data.startswith("data:"):
        _, data = data.split(",", 1)
    try:
        mask_bytes = base64.b64decode(data)
    except Exception as exc:
        raise MaskError("invalid_mask", "mask_base64 が不正です") from exc

    mask_id = uuid.uuid4().hex
    if name:
        (preset_dir / f"{mask_id}.png").write_bytes(mask_bytes)
        (preset_dir / f"{mask_id}.json").write_text(
            json.dumps({"name": name}, ensure_ascii=False), encoding="utf-8"
        )
    else:
        (history_dir / f"{mask_id}.png").write_bytes(mask_bytes)
        # 上限を超えた古い履歴マスクは削除する
        for old in _by_mtime_desc(history_dir)[HISTORY_MASK_LIMIT:]:
            with contextlib.suppress(OSError):
                old.unlink()
    return list_masks()


def delete_preset_mask(mask_id: str) -> MaskListResponse:
    """プリセットマスクを削除し、最新の一覧を返す。"""
    safe_id = _safe_id(mask_id)
    png_path = settings.preset_masks_dir / f"{safe_id}.png"
    meta_path = settings.preset_masks_dir / f"{safe_id}.json"
    if not png_path.exists():
        raise MaskError("not_found", "preset mask not found")
    try:
        png_path.unlink()
    except OSError as exc:
        raise MaskError("delete_failed", "Failed to delete preset mask") from exc
    if meta_path.exists():
        with contextlib.suppress(OSError):  # メタデータ削除失敗は無視
            meta_path.unlink()
    return list_masks()
