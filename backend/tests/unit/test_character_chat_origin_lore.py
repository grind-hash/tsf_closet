"""案内役キャラの「別の層の記憶」(同梱 Markdown)の読み込み。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gateway.consts import character_chat as consts


@pytest.fixture
def lore_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(consts, "_ORIGIN_LORE_DIR", tmp_path)
    monkeypatch.setattr(consts, "_origin_lore_cache", {})
    return tmp_path


def test_bundled_lore_files_ship_with_both_languages() -> None:
    """配布物に含める前提なので、同梱ファイルそのものが読めることを守る。"""
    ja = consts.load_origin_lore("ja")
    en = consts.load_origin_lore("en")
    assert "エデン・レイヤー" in ja
    assert "オリジン・コア" in ja
    assert "Eden Layer" in en
    assert "Origin Core" in en
    assert len(ja) <= consts.ORIGIN_LORE_MAX_CHARS
    assert len(en) <= consts.ORIGIN_LORE_MAX_CHARS


def test_missing_files_disable_quietly(lore_dir: Path) -> None:
    assert consts.load_origin_lore("ja") == ""
    assert consts.load_origin_lore("en") == ""
    assert consts.load_origin_lore("fr") == ""


def test_english_falls_back_to_japanese(lore_dir: Path) -> None:
    (lore_dir / consts.ORIGIN_LORE_FILENAMES["ja"]).write_text(
        "  日本語の記憶  \n", encoding="utf-8"
    )
    assert consts.load_origin_lore("en") == "日本語の記憶"
    (lore_dir / consts.ORIGIN_LORE_FILENAMES["en"]).write_text(
        "English memory", encoding="utf-8"
    )
    assert consts.load_origin_lore("en") == "English memory"


def test_reloads_when_file_changes_and_clips_length(lore_dir: Path) -> None:
    path = lore_dir / consts.ORIGIN_LORE_FILENAMES["ja"]
    path.write_text("最初の版", encoding="utf-8")
    assert consts.load_origin_lore("ja") == "最初の版"

    # mtime を進めて書き換えると、再起動なしで新しい本文になる
    path.write_text("あ" * (consts.ORIGIN_LORE_MAX_CHARS + 50), encoding="utf-8")
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 10))
    reloaded = consts.load_origin_lore("ja")
    assert len(reloaded) == consts.ORIGIN_LORE_MAX_CHARS

    # 消えたら空に戻る(キャッシュに残った古い本文を返さない)
    path.unlink()
    assert consts.load_origin_lore("ja") == ""
