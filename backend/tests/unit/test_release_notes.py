"""同梱の更新履歴(release_notes)の読み込みと、調べ物 app_updates の本文。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gateway.services import release_notes

_SAMPLE = """# TSF Closet 更新履歴

ここは読まない前置き。

## v0.3.1 (2026-03-10)

### 不具合修正

- 保存できない不具合を修正
  - 長い名前で保存に失敗していた

## v0.3.0 (2026-03-07)

### 新機能

- ギャラリーに「要約と称号」を追加
  - 指示の履歴をタイムラインで可視化
  - 一言で称号を生成
- 周囲状況画像を生成する機能を追加（実験的機能）

### 改善

- 長ターンで矛盾が起きにくくなるよう調整

## v0.2.0_selfhost (2026-02-25)

### 改善

- セルフホスト版のモデルを更新

## v0.2.0 (2026-02-24)

### 新機能

- 「自分自身モード」を追加（実験的機能）
"""


@pytest.fixture
def sample_notes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "release_notes.ja.md"
    path.write_text(_SAMPLE, encoding="utf-8")
    monkeypatch.setattr(release_notes, "RELEASE_NOTES_PATH", path)
    monkeypatch.setattr(release_notes, "_cache", None)
    return path


def test_parse_splits_versions_sections_and_sublines() -> None:
    releases = release_notes.parse_release_notes(_SAMPLE)

    assert [r.version for r in releases] == [
        "v0.3.1",
        "v0.3.0",
        "v0.2.0_selfhost",
        "v0.2.0",
    ]
    assert releases[1].date == "2026-03-07"
    first, second, third = releases[1].items
    assert first.section == "新機能"
    assert first.head == "ギャラリーに「要約と称号」を追加"
    assert first.lines == (
        "  - 指示の履歴をタイムラインで可視化",
        "  - 一言で称号を生成",
    )
    assert second.lines == ()
    assert third.section == "改善"
    # 最初の版の見出しより前は読まない
    assert all("前置き" not in item.head for r in releases for item in r.items)


def test_is_patch_distinguishes_fix_releases() -> None:
    releases = {r.version: r for r in release_notes.parse_release_notes(_SAMPLE)}
    assert releases["v0.3.1"].is_patch
    assert releases["v0.2.0_selfhost"].is_patch
    assert not releases["v0.3.0"].is_patch


def test_current_release_is_the_first_entry(sample_notes: Path) -> None:
    current = release_notes.current_release()
    assert current is not None
    assert (current.version, current.date) == ("v0.3.1", "2026-03-10")


def test_missing_file_disables_quietly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release_notes, "RELEASE_NOTES_PATH", tmp_path / "none.md")
    monkeypatch.setattr(release_notes, "_cache", None)
    assert release_notes.current_release() is None
    assert "読めませんでした" in release_notes.render_app_updates(None, 5, "ja", 2500)


@pytest.mark.parametrize("query", [None, "", "最新", "latest update", "アップデート"])
def test_latest_includes_previous_release_when_latest_is_a_fix(
    sample_notes: Path, query: str | None
) -> None:
    text = release_notes.render_app_updates(query, 5, "ja", 2500)

    assert text.startswith("新しい版から順に載せています。\nv0.3.1（2026-03-10 公開）")
    # 最新が修正版なら、直前の機能追加の版まで続けて載せる(それより前は載せない)
    assert "v0.3.0（2026-03-07 公開）" in text
    assert "【新機能】\n- ギャラリーに「要約と称号」を追加" in text
    assert "v0.2.0" not in text


def test_version_query_returns_that_release(sample_notes: Path) -> None:
    text = release_notes.render_app_updates("v0.3.0", 5, "ja", 2500)
    assert text.startswith("v0.3.0（2026-03-07 公開）")
    assert "v0.3.1" not in text

    # 0.2 は v0.2.0 と v0.2.0_selfhost の両方
    both = release_notes.render_app_updates("0.2", 5, "ja", 2500)
    assert "v0.2.0_selfhost（2026-02-25 公開）" in both
    assert "v0.2.0（2026-02-24 公開）" in both


def test_unknown_version_lists_known_versions(sample_notes: Path) -> None:
    text = release_notes.render_app_updates("v0.9.0", 5, "ja", 2500)
    assert text.startswith("(v0.9.0 は更新履歴にありません)")
    assert "v0.3.1（2026-03-10）" in text


def test_keyword_search_shows_version_date_and_matching_sublines(
    sample_notes: Path,
) -> None:
    text = release_notes.render_app_updates("称号", 5, "ja", 2500)

    assert text.splitlines()[0] == "「称号」を含む更新(新しい順):"
    assert "- v0.3.0（2026-03-07）【新機能】ギャラリーに「要約と称号」を追加" in text
    assert "  - 一言で称号を生成" in text
    # 検索語を含まない下の階層の行は載せない
    assert "タイムライン" not in text


def test_keyword_search_prefers_feature_names_and_keeps_the_first_mention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """説明の行にだけ出る新しい項目が多くても、機能名に出る項目と最初の記載を落とさない。"""
    sections = []
    for minor in range(12, 1, -1):
        sections.append(
            f"## v0.{minor}.0 (2026-01-{minor:02d})\n\n### 改善\n\n"
            f"- 別の機能{minor}を改善\n  - キャラチャットからも使えます"
        )
    sections.append(
        "## v0.1.0 (2026-01-01)\n\n### 新機能\n\n- キャラチャットを追加\n  - 1対1で話せます"
    )
    path = tmp_path / "release_notes.ja.md"
    path.write_text("\n\n".join(sections), encoding="utf-8")
    monkeypatch.setattr(release_notes, "RELEASE_NOTES_PATH", path)
    monkeypatch.setattr(release_notes, "_cache", None)

    text = release_notes.render_app_updates("キャラチャット", 1, "ja", 2500)

    assert "- v0.1.0（2026-01-01）【新機能】キャラチャットを追加" in text
    assert text.endswith("いちばん古い記載: v0.1.0（2026-01-01）")
    # limit が小さくても最低件数は載せる。新しい順に並べる
    items = [line for line in text.splitlines() if line.startswith("- v")]
    assert len(items) == 8
    assert items[0].startswith("- v0.12.0")
    assert items[-1].startswith("- v0.1.0")


def test_keyword_miss_says_so(sample_notes: Path) -> None:
    text = release_notes.render_app_updates("箱庭", 5, "ja", 2500)
    assert text.startswith("(「箱庭」を含む更新は更新履歴にありません)")
    assert "更新履歴にある版:" in text


def test_english_framing(sample_notes: Path) -> None:
    text = release_notes.render_app_updates("v0.3.0", 5, "en", 2500)
    assert text.startswith("v0.3.0 (released 2026-03-07)")
    missing = release_notes.render_app_updates("v0.9.0", 5, "en", 2500)
    assert missing.startswith("(v0.9.0 is not in the release notes.)")


def test_render_release_keeps_every_item_head_within_cap() -> None:
    release = release_notes.Release(
        version="v1.0.0",
        date="2026-01-01",
        items=tuple(
            release_notes.ReleaseItem(
                section="新機能",
                head=f"機能{index}を追加",
                lines=tuple(f"  - 機能{index}の説明{n}" + "あ" * 40 for n in range(5)),
            )
            for index in range(6)
        ),
    )
    text = release_notes.render_release(release, "ja", 900)

    assert len(text) <= 900
    for index in range(6):
        assert f"- 機能{index}を追加" in text
    # 説明は先頭の項目に偏らず、各項目の 1 行目から配る
    for index in range(6):
        assert f"機能{index}の説明0" in text
    assert text.endswith("(一部の項目は細かい説明を省いています)")


def test_bundled_release_notes_are_well_formed() -> None:
    """同梱ファイルそのもの。版の見出し・日付の並び・不要な節が無いこと。"""
    path = release_notes.RELEASE_NOTES_PATH
    text = path.read_text(encoding="utf-8")
    releases = release_notes.parse_release_notes(text)

    assert releases, "release notes must contain at least one version"
    headings = re.findall(r"^## (.+)$", text, flags=re.MULTILINE)
    assert len(headings) == len(releases), "every ## heading must be a version"
    versions = [r.version for r in releases]
    assert len(versions) == len(set(versions))
    dates = [r.date for r in releases]
    assert dates == sorted(dates, reverse=True), "newest version first"
    assert all(r.items for r in releases)
    for unwanted in ("Special Thanks", "Full Changelog", "素材のクレジット"):
        assert unwanted not in text
