"""custom_sessions（カスタム画像セッションの補助）。"""

from __future__ import annotations

import base64
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


def test_list_custom_characters_newest_first_with_defaults(history_dir) -> None:
    custom_sessions.save_custom_character(
        "old", b"old-png", {"id": "old", "name": "旧", "gender": "male"}
    )
    custom_sessions.save_custom_character("new", b"new-png", {"id": "new"})
    old_png = custom_sessions.custom_character_image_path("old")
    os.utime(old_png, (time.time() - 100, time.time() - 100))
    (history_dir / "custom" / "new.json").write_text("{broken", encoding="utf-8")

    items = custom_sessions.list_custom_characters()
    assert [item["id"] for item in items] == ["new", "old"]
    newest = items[0]
    assert newest["name"] == "カスタムキャラクター"
    assert newest["pronoun"] == "僕"
    assert newest["gender"] == "other"
    assert base64.b64decode(newest["thumbnail"]) == b"new-png"
    assert items[1]["name"] == "旧" and items[1]["gender"] == "man"
