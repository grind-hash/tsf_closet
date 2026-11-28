"""同梱の更新履歴(リリースノート)。

案内役キャラ(セレナ)の調べ物 app_updates と、いま使われている版の 1 行に使う。
backend/gateway/data/release_notes/release_notes.ja.md を版ごとに分けて読む。

- ファイルの先頭の版を「いま使われている版」とする(版番号の置き場所はこのファイルだけ)
- 日本語版だけを同梱し、英語の会話でも同じ文面を渡す(返答の言語は返答側で合わせる)
- ファイルの mtime が変わったときだけ読み直す(サーバーの再起動は不要)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .session_search import search_terms

logger = logging.getLogger(__name__)

# モジュール属性にしておくとテストから monkeypatch で差し替えられる
RELEASE_NOTES_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "release_notes"
    / "release_notes.ja.md"
)

_RELEASE_HEADING_RE = re.compile(r"^## (v\d+\.\d+\.\d+\S*) \((\d{4}-\d{2}-\d{2})\)\s*$")
_SECTION_HEADING_RE = re.compile(r"^### (.+?)\s*$")
_VERSION_PARTS_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(\S*)$")
# 判定 LLM の検索語が版番号か(v0.10.0 / 0.10 / v0.10.1_selfhost)
_VERSION_QUERY_RE = re.compile(r"^v?(\d+\.\d+(?:\.\d+)?\S*)$", re.IGNORECASE)
# 「最新の更新」を指すだけの検索語。これだけなら検索語なし(最新の版)として扱う
_LATEST_WORDS = frozenset(
    {
        "最新",
        "最新版",
        "最近",
        "アップデート",
        "更新",
        "更新内容",
        "更新履歴",
        "変更",
        "変更点",
        "新機能",
        "リリース",
        "リリースノート",
        "バージョン",
        "latest",
        "newest",
        "recent",
        "new",
        "update",
        "updates",
        "change",
        "changes",
        "changelog",
        "release",
        "releases",
        "version",
    }
)
# 最新が修正版(x.y.1 など)のとき、続けて載せる前の版の数の上限
_LATEST_CHAIN_MAX = 3
# 前の版を続けて載せる価値がある残りの文字数
_MIN_FOLLOWUP_CHARS = 300
# キーワード検索で載せる項目の最低数(判定 LLM の limit が小さくてもこれだけは載せる)
_SEARCH_ITEMS_MIN = 8
# キーワード検索で、1 項目に添える下の階層の行の数と 1 行の文字数
_SEARCH_SUBLINES_MAX = 2
_SEARCH_LINE_CHARS = 160


@dataclass(frozen=True)
class ReleaseItem:
    """箇条書きの 1 項目。head は 1 行目、lines は下の階層の行(インデントのまま)。"""

    section: str
    head: str
    lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class Release:
    version: str
    date: str
    items: tuple[ReleaseItem, ...]

    @property
    def is_patch(self) -> bool:
        """x.y.1 や x.y.z_selfhost のような修正版か。"""
        match = _VERSION_PARTS_RE.match(self.version)
        return bool(match) and (match.group(3) != "0" or bool(match.group(4)))


def parse_release_notes(text: str) -> list[Release]:
    """Markdown を版ごとに分ける。最初の「## vX.Y.Z (日付)」より前は読まない。"""
    releases: list[Release] = []
    version = date = ""
    section = ""
    items: list[ReleaseItem] = []

    def flush() -> None:
        if version:
            releases.append(Release(version=version, date=date, items=tuple(items)))

    for raw in text.splitlines():
        line = raw.rstrip()
        heading = _RELEASE_HEADING_RE.match(line)
        if heading:
            flush()
            version, date = heading.group(1), heading.group(2)
            section, items = "", []
            continue
        if not version or not line.strip():
            continue
        sub = _SECTION_HEADING_RE.match(line)
        if sub:
            section = sub.group(1)
            continue
        if line.startswith((" ", "\t")) and items:
            last = items[-1]
            items[-1] = ReleaseItem(last.section, last.head, (*last.lines, line))
            continue
        items.append(ReleaseItem(section, line.removeprefix("- ").strip()))
    flush()
    return releases


# (mtime, 版の一覧)
_cache: tuple[float, list[Release]] | None = None


def load_releases() -> list[Release]:
    """同梱の更新履歴を新しい順に返す。読めなければ空(機能は静かに無効になる)。"""
    global _cache
    path = RELEASE_NOTES_PATH
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _cache = None
        return []
    if _cache is not None and _cache[0] == mtime:
        return _cache[1]
    try:
        releases = parse_release_notes(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        logger.warning("release notes %s are unreadable: %s", path, error)
        return _cache[1] if _cache is not None else []
    _cache = (mtime, releases)
    return releases


def current_release() -> Release | None:
    """いま使われている版(更新履歴の先頭の版)。履歴が無ければ None。"""
    releases = load_releases()
    return releases[0] if releases else None


def _lang(language: str) -> str:
    return "en" if language == "en" else "ja"


def _clip(text: str, cap: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= cap else text[: cap - 1].rstrip() + "…"


def _release_heading(release: Release, language: str) -> str:
    if _lang(language) == "en":
        return f"{release.version} (released {release.date})"
    return f"{release.version}（{release.date} 公開）"


def _compose(release: Release, language: str, shown: list[int] | None) -> str:
    """版の本文。shown は項目ごとに載せる下の階層の行数(None なら全部)。"""
    lines = [_release_heading(release, language)]
    section = None
    omitted = False
    for index, item in enumerate(release.items):
        if item.section and item.section != section:
            section = item.section
            lines.append(f"【{section}】")
        lines.append(f"- {item.head}")
        count = len(item.lines) if shown is None else shown[index]
        lines.extend(item.lines[:count])
        omitted = omitted or count < len(item.lines)
    if omitted:
        lines.append(
            "(Some details are omitted.)"
            if _lang(language) == "en"
            else "(一部の項目は細かい説明を省いています)"
        )
    return "\n".join(lines)


def render_release(release: Release, language: str, cap: int) -> str:
    """1 つの版を上限内で描く。

    収まらなければ見出しと各項目の 1 行目を残し、下の階層の行は全項目に 1 行ずつ
    順に配って入るだけ載せる(先頭の項目だけが詳しくならないようにする)。
    """
    full = _compose(release, language, None)
    if len(full) <= cap:
        return full
    shown = [0] * len(release.items)
    budget = cap - len(_compose(release, language, shown))
    depth_max = max((len(item.lines) for item in release.items), default=0)
    for depth in range(depth_max):
        for index, item in enumerate(release.items):
            if shown[index] != depth or depth >= len(item.lines):
                continue
            cost = len(item.lines[depth]) + 1
            if cost <= budget:
                shown[index] += 1
                budget -= cost
    return _clip(_compose(release, language, shown), cap)


def _version_list(releases: list[Release], language: str) -> str:
    if _lang(language) == "en":
        listed = ", ".join(f"{r.version} ({r.date})" for r in releases)
        return f"Versions in the release notes: {listed}"
    listed = "、".join(f"{r.version}（{r.date}）" for r in releases)
    return f"更新履歴にある版: {listed}"


def _render_sequence(releases: list[Release], language: str, cap: int) -> str:
    """版を順に、残りの文字数に入るだけ描く(先頭は必ず載せる)。"""
    parts: list[str] = []
    remaining = cap
    for release in releases:
        if parts and remaining < _MIN_FOLLOWUP_CHARS:
            break
        text = render_release(release, language, remaining)
        parts.append(text)
        remaining -= len(text) + 2
    return "\n\n".join(parts)


def _render_latest(releases: list[Release], language: str, cap: int) -> str:
    # 最新が修正版なら、直前の機能追加の版(x.y.0)まで続けて載せる
    chain = [releases[0]]
    for release in releases[1:_LATEST_CHAIN_MAX]:
        if not chain[-1].is_patch:
            break
        chain.append(release)
    intro = (
        "Newest first." if _lang(language) == "en" else "新しい版から順に載せています。"
    )
    body = _render_sequence(chain, language, cap - len(intro) - 1)
    return f"{intro}\n{body}"


def _match_version(releases: list[Release], query: str) -> list[Release] | None:
    """版番号の検索語なら、当てはまる版(無ければ空)。版番号でなければ None。"""
    match = _VERSION_QUERY_RE.match(query.strip())
    if not match:
        return None
    wanted = match.group(1).lower()
    return [
        release
        for release in releases
        if release.version[1:].lower() == wanted
        or release.version[1:].lower().startswith(f"{wanted}.")
        or release.version[1:].lower().startswith(f"{wanted}_")
    ]


def _render_search(
    releases: list[Release], terms: list[str], limit: int, language: str, cap: int
) -> str | None:
    """キーワードを含む項目を、版と日付つきで新しい順に。当てはまる項目が無ければ None。

    1 行目(機能名)に語を含む項目を、説明の行にだけ含む項目より優先する。
    「いつ追加されたか」に答えられるよう、最も古い一致は件数の上限を超えても必ず載せる。
    """
    lowered = [term.lower() for term in terms]
    scored: list[tuple[int, int, Release, ReleaseItem]] = []
    order = 0
    for release in releases:
        for item in release.items:
            head = item.head.lower()
            body = "\n".join(item.lines).lower()
            score = sum(
                2 if term in head else 1 if term in body else 0 for term in lowered
            )
            if score:
                scored.append((-score, order, release, item))
            order += 1
    if not scored:
        return None
    oldest = max(scored, key=lambda entry: entry[1])
    scored.sort(key=lambda entry: (entry[0], entry[1]))
    picked = scored[: max(limit, _SEARCH_ITEMS_MIN)]
    if oldest not in picked:
        picked[-1] = oldest
    picked.sort(key=lambda entry: entry[1])
    lines: list[str] = []
    for _, _, release, item in picked:
        section = f"【{item.section}】" if item.section else ""
        lines.append(f"- {release.version}（{release.date}）{section}{item.head}")
        sublines = [
            line for line in item.lines if any(term in line.lower() for term in lowered)
        ][:_SEARCH_SUBLINES_MAX]
        lines.extend(
            f"  - {_clip(line.strip().removeprefix('- '), _SEARCH_LINE_CHARS)}"
            for line in sublines
        )
    joined = "、".join(terms)
    _, _, first_release, _ = oldest
    if _lang(language) == "en":
        intro = f"Release-note items mentioning {joined} (newest first):"
        earliest = f"Earliest mention: {first_release.version} ({first_release.date})"
    else:
        intro = f"「{joined}」を含む更新(新しい順):"
        earliest = f"いちばん古い記載: {first_release.version}（{first_release.date}）"
    return _clip("\n".join((intro, *lines, earliest)), cap)


def render_app_updates(query: str | None, limit: int, language: str, cap: int) -> str:
    """調べ物 app_updates の本文。

    検索語なし(または「最新」だけ) → 最新の版、版番号 → その版、それ以外 → キーワードを
    含む項目。当てはまる版・項目が無ければ、その旨と更新履歴にある版の一覧を返す。
    """
    releases = load_releases()
    if not releases:
        return (
            "(The release notes are not available.)"
            if _lang(language) == "en"
            else "(更新履歴を読めませんでした)"
        )
    terms = search_terms(query)
    if not terms or all(term.lower() in _LATEST_WORDS for term in terms):
        return _render_latest(releases, language, cap)
    for term in terms:
        matched = _match_version(releases, term)
        if matched is None:
            continue
        if matched:
            return _render_sequence(matched, language, cap)
        missing = (
            f"({term} is not in the release notes.)"
            if _lang(language) == "en"
            else f"({term} は更新履歴にありません)"
        )
        return _clip(f"{missing}\n{_version_list(releases, language)}", cap)
    keywords = [term for term in terms if term.lower() not in _LATEST_WORDS] or terms
    found = _render_search(releases, keywords, limit, language, cap)
    if found is not None:
        return found
    joined = "、".join(keywords)
    missing = (
        f"(Nothing in the release notes mentions {joined}.)"
        if _lang(language) == "en"
        else f"(「{joined}」を含む更新は更新履歴にありません)"
    )
    return _clip(f"{missing}\n{_version_list(releases, language)}", cap)
