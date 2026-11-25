"""custom_sessions（セッションごとのプロフィールと旧カスタムキャラクターの移行）。"""

from __future__ import annotations

import json
import os
import time

import pytest

from gateway.services import custom_sessions
from gateway.settings.config import settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("man", "man"),
        (" MALE ", "man"),
        ("男性", "man"),
        ("woman", "woman"),
        ("female", "woman"),
        ("女", "woman"),
        ("other", "other"),
        ("", "other"),
        (None, "other"),
        ("dragon", "other"),
    ],
)
def test_normalize_gender(raw, expected) -> None:
    assert custom_sessions.normalize_gender(raw) == expected


@pytest.fixture
def history_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "history_images_dir", tmp_path / "history_images")
    return tmp_path / "history_images"


def test_session_metadata_round_trip_and_missing(history_dir) -> None:
    assert custom_sessions.load_custom_session_metadata("none") == {}
    custom_sessions.save_custom_session_metadata(
        "s1", {"name": "サクラ", "gender": "woman"}
    )
    assert custom_sessions.load_custom_session_metadata("s1") == {
        "name": "サクラ",
        "gender": "woman",
    }
    (history_dir / "custom" / "session_s1.json").write_text("{broken", encoding="utf-8")
    assert custom_sessions.load_custom_session_metadata("s1") == {}


def _write_custom(history_dir, custom_id: str, png: bytes, metadata) -> None:
    """v0.11.0 以前の新規プレイが保存したカスタムキャラクターと同じ形で置く。"""
    directory = history_dir / "custom"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{custom_id}.png").write_bytes(png)
    (directory / f"{custom_id}.json").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )


def test_unimported_profiles_oldest_first_with_defaults(history_dir) -> None:
    _write_custom(history_dir, "old", b"old-png", {"name": "旧", "gender": "male"})
    _write_custom(history_dir, "new", b"new-png", {})
    _write_custom(history_dir, "done", b"png", {"imported_preset_id": "p1"})
    old_png = custom_sessions.custom_character_image_path("old")
    os.utime(old_png, (time.time() - 100, time.time() - 100))
    (history_dir / "custom" / "new.json").write_text("{broken", encoding="utf-8")
    # セッションごとのプロフィールは画像を持たないので対象外
    custom_sessions.save_custom_session_metadata("s1", {"name": "サクラ"})

    profiles = custom_sessions.list_unimported_custom_character_profiles()
    assert [item["id"] for item in profiles] == ["old", "new"]
    assert profiles[0]["name"] == "旧" and profiles[0]["gender"] == "man"
    newest = profiles[1]
    assert newest["name"] == "カスタムキャラクター"
    assert newest["pronoun"] == "僕"
    assert newest["gender"] == "other"


def test_imported_preset_id_after_marking(history_dir) -> None:
    _write_custom(history_dir, "abc-123", b"png", {"name": "サクラ"})
    assert custom_sessions.imported_preset_id("abc-123") is None

    custom_sessions.mark_custom_character_imported("abc-123", "preset-1")

    assert custom_sessions.imported_preset_id("abc-123") == "preset-1"
    assert custom_sessions.list_unimported_custom_character_profiles() == []
    # 元の人物設定は残す
    metadata = json.loads(
        (history_dir / "custom" / "abc-123.json").read_text(encoding="utf-8")
    )
    assert metadata["name"] == "サクラ"
    assert custom_sessions.imported_preset_id("missing") is None
    # パスとして危険な ID は読まない
    assert custom_sessions.imported_preset_id("../abc-123") is None
    assert custom_sessions.imported_preset_id(None) is None
