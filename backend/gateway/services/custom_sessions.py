"""カスタム画像（ユーザーがアップロードした主人公）で始めるセッションの補助。

画像とメタデータは `history_images/custom/` に置く。
- `{custom_image_id}.png` / `.json`: 再利用できるカスタムキャラクター
- `session_{session_id}.json`: セッションごとのプロフィール（性別・一人称・タグ）
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from ..settings.config import settings


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


def list_custom_characters() -> list[dict[str, Any]]:
    """保存済みのカスタムキャラクター（新しい順）をサムネイル付きで返す。"""
    directory = custom_images_dir()
    items: list[dict[str, Any]] = []
    for image_file in sorted(
        directory.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        metadata_file = image_file.with_suffix(".json")
        metadata: dict[str, Any] = {}
        if metadata_file.exists():
            try:
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            except Exception:
                metadata = {}
        items.append(
            {
                "id": image_file.stem,
                "thumbnail": base64.b64encode(image_file.read_bytes()).decode("utf-8"),
                "name": metadata.get("name", "カスタムキャラクター"),
                "description": metadata.get("description", ""),
                "pronoun": metadata.get("pronoun", "僕"),
                "personality": metadata.get("personality", ""),
                "gender": normalize_gender(metadata.get("gender", "other")),
                "base_tags": metadata.get("base_tags", ""),
            }
        )
    return items
