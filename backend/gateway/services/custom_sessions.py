"""セッションごとのプロフィールと、旧カスタムキャラクターの移行の補助。

`history_images/custom/` に置くもの:
- `session_{session_id}.json`: セッションごとのプロフィール（性別・一人称・タグ）。
  キャラクター(CharacterPreset)から始めたセッションも使う
- `{custom_image_id}.png` / `.json`: v0.11.0 以前の新規プレイ「自分の画像を使用」で
  保存したカスタムキャラクター。v0.12.0 で新規作成をやめ、起動時にキャラクターへ
  取り込む。過去セッションの元画像として参照されるため消さない

キャラクターから始めたセッションの開始時点の立ち絵の写しは `history_images/preset_sessions/`
に置く。写しのファイル名はメタデータの base_image。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from ..settings.config import settings

logger = logging.getLogger(__name__)

# 旧カスタムキャラクターの ID(uuid)。DB に残る値をパスに使う前に形を確かめる
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


def preset_session_images_dir() -> Path:
    """キャラクターから始めたセッションの、開始時点の立ち絵の写しを置く場所。"""
    directory = settings.history_images_dir / "preset_sessions"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def delete_custom_session_metadata(session_id: str) -> None:
    """セッションごとのプロフィール(と立ち絵の写し)を消す。無ければ何もしない。"""
    base_image = str(load_custom_session_metadata(session_id).get("base_image") or "")
    if base_image:
        (preset_session_images_dir() / Path(base_image).name).unlink(missing_ok=True)
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


# ---------------------------------------------------------------------------
# 旧カスタムキャラクター(v0.11.0 以前)の移行
# ---------------------------------------------------------------------------


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
        "tsf_attitude": metadata.get("tsf_attitude", ""),
    }


def list_unimported_custom_character_profiles() -> list[dict[str, Any]]:
    """キャラクターへ取り込んでいないカスタムキャラクターの人物設定(古い順)。"""
    files = [
        path
        for path in custom_images_dir().glob("*.png")
        if not _read_custom_metadata(path).get("imported_preset_id")
    ]
    files.sort(key=lambda path: path.stat().st_mtime)
    return [
        _custom_profile(image_file.stem, _read_custom_metadata(image_file))
        for image_file in files
    ]


def mark_custom_character_imported(custom_image_id: str, preset_id: str) -> None:
    """カスタムキャラクターをキャラクターへ取り込んだ印を付ける。"""
    image_file = custom_character_image_path(custom_image_id)
    metadata = _read_custom_metadata(image_file)
    metadata["imported_preset_id"] = preset_id
    image_file.with_suffix(".json").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )


def imported_preset_id(custom_image_id: str | None) -> str | None:
    """カスタムキャラクターの取り込み先キャラクターの ID。未取り込み・ID 不正は None。

    v0.11.0 以前に保存された参照(サロンの予約など)をキャラクターへ読み替えるのに使う。
    """
    if not custom_image_id or not _CUSTOM_ID_PATTERN.fullmatch(custom_image_id):
        return None
    value = _read_custom_metadata(custom_character_image_path(custom_image_id)).get(
        "imported_preset_id"
    )
    return str(value) if value else None
