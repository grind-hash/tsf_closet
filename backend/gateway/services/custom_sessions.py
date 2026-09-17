"""カスタム画像（ユーザーがアップロードした主人公）で始めるセッションの補助。

画像とメタデータは `history_images/custom/` に置く。
- `{custom_image_id}.png` / `.json`: 再利用できるカスタムキャラクター
- `session_{session_id}.json`: セッションごとのプロフィール（性別・一人称・タグ）
"""

from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path
from typing import Any

from ..settings.config import settings

logger = logging.getLogger(__name__)

# 保存済みカスタムキャラクターの ID(uuid)。外部から受けた値をパスに使う前に形を確かめる
_CUSTOM_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,80}")


def normalize_gender(value: str | None) -> str:
    """性別値を man/woman/other に正規化"""
    if not value:
        return "other"
    normalized = value.strip().lower()
    if normalized in {"man", "male", "男性", "男"}:
        return "man"
    if normalized in {"woman", "female", "女性", "女"}:
        return "woman"
    return "other"


def custom_images_dir() -> Path:
    directory = settings.history_images_dir / "custom"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def load_custom_session_metadata(session_id: str) -> dict[str, Any]:
    """カスタムセッションのメタデータを読む。無い・壊れているときは空 dict。"""
    metadata_path = (
        settings.history_images_dir / "custom" / f"session_{session_id}.json"
    )
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_custom_session_metadata(session_id: str, metadata: dict[str, Any]) -> None:
    path = custom_images_dir() / f"session_{session_id}.json"
    path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")


def delete_custom_session_metadata(session_id: str) -> None:
    """セッションごとのプロフィールを消す。無ければ何もしない。"""
    path = settings.history_images_dir / "custom" / f"session_{session_id}.json"
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning(
            "Failed to delete custom session metadata %s: %s: %s",
            path,
            type(exc).__name__,
            exc,
        )


def save_custom_character(
    custom_image_id: str, image_bytes: bytes, metadata: dict[str, Any]
) -> None:
    """カスタムキャラクターの画像とメタデータを保存する。"""
    directory = custom_images_dir()
    (directory / f"{custom_image_id}.png").write_bytes(image_bytes)
    (directory / f"{custom_image_id}.json").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )


def custom_character_image_path(custom_image_id: str) -> Path:
    return custom_images_dir() / f"{custom_image_id}.png"


def _read_custom_metadata(image_file: Path) -> dict[str, Any]:
    """カスタムキャラクターの画像に並ぶメタデータ。無い・壊れているときは空 dict。"""
    metadata_file = image_file.with_suffix(".json")
    if not metadata_file.exists():
        return {}
    try:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return metadata if isinstance(metadata, dict) else {}


def _custom_profile(custom_image_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """メタデータを既定値で補った人物設定。"""
    return {
        "id": custom_image_id,
        "name": metadata.get("name", "カスタムキャラクター"),
        "description": metadata.get("description", ""),
        "pronoun": metadata.get("pronoun", "僕"),
        "personality": metadata.get("personality", ""),
        "gender": normalize_gender(metadata.get("gender", "other")),
        "base_tags": metadata.get("base_tags", ""),
    }


def _custom_image_files() -> list[Path]:
    """保存済みカスタムキャラクターの画像(新しい順)。"""
    return sorted(
        custom_images_dir().glob("*.png"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def list_custom_characters() -> list[dict[str, Any]]:
    """保存済みのカスタムキャラクター（新しい順）をサムネイル付きで返す。"""
    items: list[dict[str, Any]] = []
    for image_file in _custom_image_files():
        profile = _custom_profile(image_file.stem, _read_custom_metadata(image_file))
        items.append(
            {
                **profile,
                "thumbnail": base64.b64encode(image_file.read_bytes()).decode("utf-8"),
            }
        )
    return items


def list_custom_character_profiles(limit: int | None = None) -> list[dict[str, Any]]:
    """保存済みのカスタムキャラクターの人物設定（新しい順）。画像は読まない。"""
    files = _custom_image_files()
    if limit is not None:
        files = files[: max(0, limit)]
    return [
        _custom_profile(image_file.stem, _read_custom_metadata(image_file))
        for image_file in files
    ]


def load_custom_character_profile(custom_image_id: str | None) -> dict[str, Any] | None:
    """保存済みカスタムキャラクターの人物設定。ID が不正・画像が無いときは None。"""
    if not custom_image_id or not _CUSTOM_ID_PATTERN.fullmatch(custom_image_id):
        return None
    image_file = custom_character_image_path(custom_image_id)
    if not image_file.exists():
        return None
    return _custom_profile(custom_image_id, _read_custom_metadata(image_file))
