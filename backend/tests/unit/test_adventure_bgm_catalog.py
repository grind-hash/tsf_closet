"""BGMカタログローダの単体テスト。

カタログJSONは実行中に書き換えられる前提のため、mtime による再読込と、
破損時に last-good / 組み込み既定へ劣化してターンを落とさないことを検証する。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from gateway.consts import adventure_bgm


def write_catalog(
    path: Path, *, tracks: list[dict], default_key: str = "daily"
) -> None:
    path.write_text(
        json.dumps({"default_key": default_key, "tracks": tracks}, ensure_ascii=False),
        encoding="utf-8",
    )


def bump_mtime(path: Path) -> None:
    """同一秒内の書き換えでは mtime が変わらないことがあるため明示的に進める。"""
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 10))


@pytest.fixture
def catalog_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "catalog.json"
    monkeypatch.setattr(adventure_bgm, "_CATALOG_PATH", path)
    monkeypatch.setattr(adventure_bgm, "_cache", None)
    return path


def test_catalog_accessors_reflect_json(catalog_path: Path) -> None:
    write_catalog(
        catalog_path,
        tracks=[
            {"key": "daily", "file": "daily.ogg", "description": "everyday scenes"},
            {"key": "bar", "file": "bar.ogg", "description": "cafes and bars"},
        ],
    )

    assert adventure_bgm.get_bgm_keys() == ("daily", "bar")
    assert adventure_bgm.get_bgm_default() == "daily"
    guide = adventure_bgm.get_bgm_prompt_guide()
    assert "daily (everyday scenes)" in guide
    assert "bar (cafes and bars)" in guide


def test_credit_is_preserved_verbatim(catalog_path: Path) -> None:
    """credit は表示文そのもの。バックエンドは加工せずそのまま保持する。"""
    write_catalog(
        catalog_path,
        tracks=[
            {
                "key": "daily",
                "file": "daily.ogg",
                "description": "everyday scenes",
                "credit": "SUNO v4.5-all で作成",
            },
            {
                "key": "bar",
                "file": "bar.ogg",
                "description": "cafes and bars",
                "credit": "○○の音楽素材 より配布",
            },
        ],
    )

    tracks = adventure_bgm.get_bgm_catalog().tracks
    assert tracks[0].credit == "SUNO v4.5-all で作成"
    assert tracks[1].credit == "○○の音楽素材 より配布"


def test_catalog_without_credit_still_loads(catalog_path: Path) -> None:
    """credit は任意（自作曲など表記不要な曲がある）。欠けても破損扱いにしない。"""
    write_catalog(
        catalog_path,
        tracks=[
            {"key": "daily", "file": "daily.ogg", "description": "everyday"},
            {"key": "bar", "file": "bar.ogg", "description": "cafes and bars"},
        ],
    )

    assert adventure_bgm.get_bgm_keys() == ("daily", "bar")
    assert all(track.credit is None for track in adventure_bgm.get_bgm_catalog().tracks)


def test_catalog_reloads_when_mtime_changes(catalog_path: Path) -> None:
    write_catalog(
        catalog_path,
        tracks=[{"key": "daily", "file": "daily.ogg", "description": "everyday"}],
    )
    assert adventure_bgm.get_bgm_keys() == ("daily",)

    write_catalog(
        catalog_path,
        tracks=[
            {"key": "daily", "file": "daily.ogg", "description": "everyday"},
            {"key": "test_scene", "file": "test.ogg", "description": "test scenes"},
        ],
    )
    bump_mtime(catalog_path)

    assert adventure_bgm.get_bgm_keys() == ("daily", "test_scene")


def test_broken_catalog_keeps_last_good(
    catalog_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_catalog(
        catalog_path,
        tracks=[{"key": "daily", "file": "daily.ogg", "description": "everyday"}],
    )
    assert adventure_bgm.get_bgm_keys() == ("daily",)

    catalog_path.write_text('{"default_key": "daily", "tracks": [', encoding="utf-8")
    bump_mtime(catalog_path)

    with caplog.at_level("WARNING"):
        assert adventure_bgm.get_bgm_keys() == ("daily",)
    assert any("BGM catalog" in record.message for record in caplog.records)


def test_broken_catalog_without_last_good_uses_builtin(
    catalog_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    catalog_path.write_text("not json", encoding="utf-8")

    with caplog.at_level("WARNING"):
        assert adventure_bgm.get_bgm_keys() == ("daily",)
    assert adventure_bgm.get_bgm_default() == "daily"


def test_missing_catalog_file_uses_builtin(catalog_path: Path) -> None:
    assert not catalog_path.exists()
    assert adventure_bgm.get_bgm_keys() == ("daily",)


def test_unknown_default_key_falls_back_to_first_track(catalog_path: Path) -> None:
    write_catalog(
        catalog_path,
        default_key="ghost",
        tracks=[{"key": "bar", "file": "bar.ogg", "description": "cafes"}],
    )
    assert adventure_bgm.get_bgm_default() == "bar"


def test_resolve_bgm_audio_path_guards_traversal_and_unknown(
    catalog_path: Path,
) -> None:
    write_catalog(
        catalog_path,
        tracks=[{"key": "daily", "file": "daily.ogg", "description": "everyday"}],
    )
    (catalog_path.parent / "daily.ogg").write_bytes(b"ogg")

    resolved = adventure_bgm.resolve_bgm_audio_path("daily.ogg")
    assert resolved == catalog_path.parent / "daily.ogg"

    # パス区切りを含む値・カタログ未登録のファイル名は拒否する
    assert adventure_bgm.resolve_bgm_audio_path("../catalog.json") is None
    assert adventure_bgm.resolve_bgm_audio_path("/etc/passwd") is None
    assert adventure_bgm.resolve_bgm_audio_path("missing.ogg") is None


def test_track_with_path_separator_in_file_is_rejected(catalog_path: Path) -> None:
    """カタログ側に書かれたトラバーサル値もエントリごと弾く(検証エラー→既定)。"""
    write_catalog(
        catalog_path,
        tracks=[{"key": "daily", "file": "../daily.ogg", "description": "everyday"}],
    )
    # 検証失敗はカタログ全体の破損として扱われ、組み込み既定へ倒れる
    assert adventure_bgm.get_bgm_keys() == ("daily",)
    assert adventure_bgm.resolve_bgm_audio_path("../daily.ogg") is None
