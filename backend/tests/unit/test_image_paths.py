"""services/image_paths.resolve_stored_image_path のユニットテスト。

旧 GameService._resolve_image_path（data 相対 → BASE_DIR 相対）と
AdventureService._resolve_image / session_store.resolve_history_image_file
（文字列どおり → data 相対 → 履歴ディレクトリ直下の同名）の候補をすべて含むことを確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import gateway.settings.config as cfg_mod
from gateway.services.image_paths import resolve_stored_image_path


@pytest.fixture
def dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    data_dir = tmp_path / "data"
    history_dir = data_dir / "history_images"
    history_dir.mkdir(parents=True)
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    monkeypatch.setattr(cfg_mod.settings, "history_images_dir", history_dir)
    monkeypatch.setattr(cfg_mod, "BASE_DIR", base_dir)
    return {"data": data_dir, "history": history_dir, "base": base_dir}


def test_data_relative_found(dirs: dict[str, Path]) -> None:
    img = dirs["history"] / "test.png"
    img.write_bytes(b"PNG_DATA")

    result = resolve_stored_image_path("history_images/test.png")
    assert result == img
    assert result.read_bytes() == b"PNG_DATA"


def test_base_dir_fallback(dirs: dict[str, Path]) -> None:
    img = dirs["base"] / "images" / "characters" / "char1.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(b"CHAR_IMG")

    result = resolve_stored_image_path("images/characters/char1.png")
    assert result == img


def test_absolute_path_found(dirs: dict[str, Path], tmp_path: Path) -> None:
    img = tmp_path / "elsewhere" / "abs.png"
    img.parent.mkdir()
    img.write_bytes(b"ABS")

    result = resolve_stored_image_path(str(img))
    assert result == img


def test_history_dir_basename_fallback(dirs: dict[str, Path]) -> None:
    img = dirs["history"] / "moved.png"
    img.write_bytes(b"MOVED")

    result = resolve_stored_image_path("old_location/moved.png")
    assert result == img


def test_explicit_history_dir_overrides_settings(
    dirs: dict[str, Path], tmp_path: Path
) -> None:
    other_dir = tmp_path / "other_history"
    other_dir.mkdir()
    img = other_dir / "x.png"
    img.write_bytes(b"X")

    assert resolve_stored_image_path("gone/x.png") is None
    result = resolve_stored_image_path("gone/x.png", history_images_dir=other_dir)
    assert result == img


def test_not_found_returns_none(dirs: dict[str, Path]) -> None:
    assert resolve_stored_image_path("nonexistent/file.png") is None


def test_empty_or_none_returns_none(dirs: dict[str, Path]) -> None:
    assert resolve_stored_image_path("") is None
    assert resolve_stored_image_path(None) is None


def test_directory_is_not_a_match(dirs: dict[str, Path]) -> None:
    (dirs["history"] / "subdir").mkdir()

    assert resolve_stored_image_path("history_images/subdir") is None
