"""お気に入りプロンプトのインポート / エクスポート用ファイル（JSON / CSV）の読み書き。

ファイルの形式だけを扱う。名前や色の検証、既存データとの照合は
favorite_prompt_service で行う。

CSV は Excel での編集を想定して次のように扱う。

- 書き出しは BOM 付き UTF-8（Excel で開いても文字化けしない）
- 読み込みは UTF-8 と Shift_JIS（Excel の「CSV (コンマ区切り)」保存）の両方を受け付ける
- 列見出しは日本語・英語のどちらでもよく、列の並び順も問わない
- カテゴリーだけを書いて名前と内容を空にした行は、空のカテゴリーとして扱う
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import ValidationError

from ..schemas.favorite_prompts import FavoritePromptFile, FavoritePromptFilePrompt

EXPORT_FORMAT = "tsf-closet-favorite-prompts"
EXPORT_VERSION = 1
MAX_FILE_BYTES = 5 * 1024 * 1024

FileKind = Literal["json", "csv"]
CsvLanguage = Literal["ja", "en"]

_CSV_COLUMNS = ("category", "label", "content", "color", "category_color")
_CSV_HEADERS: dict[CsvLanguage, dict[str, str]] = {
    "ja": {
        "category": "カテゴリー",
        "label": "名前",
        "content": "内容",
        "color": "色",
        "category_color": "カテゴリーの色",
    },
    "en": {
        "category": "Category",
        "label": "Name",
        "content": "Content",
        "color": "Color",
        "category_color": "Category Color",
    },
}
# 読み込み時に受け付ける見出し（空白を除き小文字にして比較する）
_CSV_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "category": ("カテゴリー", "カテゴリ", "category"),
    "label": ("名前", "名称", "name", "label"),
    "content": ("内容", "content"),
    "color": ("色", "color"),
    "category_color": (
        "カテゴリーの色",
        "カテゴリの色",
        "カテゴリー色",
        "カテゴリ色",
        "categorycolor",
        "category_color",
    ),
}
_CSV_HEADER_LOOKUP = {
    alias: key for key, aliases in _CSV_HEADER_ALIASES.items() for alias in aliases
}
# Excel が数式として解釈する先頭文字。書き出し時に ' を前置し、読み込み時に外す
# （NovelAI の "-1::tag::" のような記法を Excel で壊さないため）
_FORMULA_PREFIXES = ("=", "+", "-", "@")
_BARE_HEX_COLOR = re.compile(r"^[0-9A-Fa-f]{6}$")


class FavoritePromptFileError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class FileCategoryEntry:
    # エラー表示で使う位置（「カテゴリーの2件目」「3行目のカテゴリー」など）
    position: str
    label: str
    color: str | None


@dataclass(frozen=True)
class FilePromptEntry:
    position: str
    category: str | None
    label: str
    content: str
    color: str | None


@dataclass
class FavoritePromptFileEntries:
    """ファイルから読み取った未検証の項目。"""

    categories: list[FileCategoryEntry] = field(default_factory=list)
    prompts: list[FilePromptEntry] = field(default_factory=list)


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp932")
    except UnicodeDecodeError as exc:
        raise FavoritePromptFileError(
            "invalid_encoding",
            "文字コードを読み取れませんでした。UTF-8 で保存し直してください",
        ) from exc


def _detect_kind(filename: str | None, text: str) -> FileKind:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return "csv"
    if name.endswith(".json"):
        return "json"
    return "json" if text.lstrip().startswith("{") else "csv"


def parse_file(filename: str | None, raw: bytes) -> FavoritePromptFileEntries:
    """アップロードされたファイルを読み取る。形式は拡張子（無ければ中身）で判断する。"""
    if len(raw) > MAX_FILE_BYTES:
        raise FavoritePromptFileError(
            "file_too_large",
            f"ファイルが大きすぎます（上限 {MAX_FILE_BYTES // (1024 * 1024)} MiB）",
        )
    text = _decode(raw)
    if not text.strip():
        raise FavoritePromptFileError("empty_file", "ファイルが空です")
    if _detect_kind(filename, text) == "csv":
        return _parse_csv(text)
    return _parse_json(text)


def _validation_position(exc: ValidationError) -> str:
    errors = exc.errors()
    loc = errors[0].get("loc", ()) if errors else ()
    if len(loc) >= 2 and isinstance(loc[1], int):
        if loc[0] == "categories":
            return f"カテゴリーの{loc[1] + 1}件目: "
        if loc[0] == "prompts":
            return f"お気に入りプロンプトの{loc[1] + 1}件目: "
    return ""


def _parse_json(text: str) -> FavoritePromptFileEntries:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FavoritePromptFileError(
            "invalid_import_file", "JSON として読み込めませんでした"
        ) from exc
    if not isinstance(payload, dict) or payload.get("format") != EXPORT_FORMAT:
        raise FavoritePromptFileError(
            "invalid_import_file",
            "TSF Closet のお気に入りプロンプトのファイルではありません",
        )
    if payload.get("version") != EXPORT_VERSION:
        raise FavoritePromptFileError(
            "unsupported_import_version",
            "対応していないファイル形式のバージョンです",
        )
    try:
        data = FavoritePromptFile.model_validate(payload)
    except ValidationError as exc:
        raise FavoritePromptFileError(
            "invalid_import_file",
            f"{_validation_position(exc)}ファイルの中身の形式が正しくありません",
        ) from exc
    return FavoritePromptFileEntries(
        categories=[
            FileCategoryEntry(f"カテゴリーの{i}件目", c.label, c.color)
            for i, c in enumerate(data.categories, start=1)
        ],
        prompts=[
            FilePromptEntry(
                f"お気に入りプロンプトの{i}件目",
                p.category,
                p.label,
                p.content,
                p.color,
            )
            for i, p in enumerate(data.prompts, start=1)
        ],
    )


def _header_key(title: str) -> str | None:
    return _CSV_HEADER_LOOKUP.get(re.sub(r"\s+", "", title).lower())


def _read_csv_header(row: list[str]) -> dict[str, int]:
    columns: dict[str, int] = {}
    for index, title in enumerate(row):
        key = _header_key(title)
        if key is not None and key not in columns:
            columns[key] = index
    if "label" not in columns or "content" not in columns:
        headers = _CSV_HEADERS["ja"]
        raise FavoritePromptFileError(
            "invalid_import_file",
            f"CSV の見出し行に「{headers['label']}」と「{headers['content']}」の列が必要です",
        )
    return columns


def _from_csv_cell(value: str) -> str:
    if value.startswith("'") and value[1:2] in _FORMULA_PREFIXES:
        return value[1:]
    return value


def _to_csv_cell(value: str) -> str:
    if value.startswith(_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def _csv_cell(row: list[str], columns: dict[str, int], key: str) -> str:
    index = columns.get(key)
    if index is None or index >= len(row):
        return ""
    return _from_csv_cell(row[index])


def _csv_color(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    # Excel で # を付け忘れた色コードも受け付ける
    if _BARE_HEX_COLOR.match(text):
        return f"#{text}"
    return text


def _parse_csv(text: str) -> FavoritePromptFileEntries:
    entries = FavoritePromptFileEntries()
    columns: dict[str, int] | None = None
    try:
        # 行番号は Excel の行番号と揃える（セル内改行があっても 1 行と数える）
        for row_number, row in enumerate(
            csv.reader(io.StringIO(text, newline="")), start=1
        ):
            if not any(cell.strip() for cell in row):
                continue
            if columns is None:
                columns = _read_csv_header(row)
                continue

            category = _csv_cell(row, columns, "category")
            label = _csv_cell(row, columns, "label")
            content = _csv_cell(row, columns, "content").replace("\r\n", "\n")
            category_color = _csv_color(_csv_cell(row, columns, "category_color"))
            is_category_only = not label.strip() and not content.strip()
            if category.strip() and (category_color or is_category_only):
                entries.categories.append(
                    FileCategoryEntry(
                        f"{row_number}行目のカテゴリー", category, category_color
                    )
                )
            if is_category_only:
                continue
            entries.prompts.append(
                FilePromptEntry(
                    f"{row_number}行目",
                    category or None,
                    label,
                    content,
                    _csv_color(_csv_cell(row, columns, "color")),
                )
            )
    except csv.Error as exc:
        raise FavoritePromptFileError(
            "invalid_import_file", "CSV として読み込めませんでした"
        ) from exc
    if columns is None:
        raise FavoritePromptFileError("empty_file", "ファイルが空です")
    return entries


def render_json(data: FavoritePromptFile) -> str:
    return json.dumps(data.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


def render_csv(data: FavoritePromptFile, language: CsvLanguage = "ja") -> str:
    """一覧画面と同じ順（未分類 → カテゴリー順）で 1 行 1 プロンプトにして書き出す。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    headers = _CSV_HEADERS[language]
    writer.writerow([headers[key] for key in _CSV_COLUMNS])

    category_colors = {c.label: c.color or "" for c in data.categories}
    grouped: dict[str | None, list[FavoritePromptFilePrompt]] = {None: []}
    for category in data.categories:
        grouped.setdefault(category.label, [])
    for prompt in data.prompts:
        grouped.setdefault(prompt.category, []).append(prompt)

    for category_label, prompts in grouped.items():
        category_cell = _to_csv_cell(category_label or "")
        category_color = category_colors.get(category_label or "", "")
        if category_label is not None and not prompts:
            # 空のカテゴリーは名前・内容を空にした行で残す
            writer.writerow([category_cell, "", "", "", category_color])
        for prompt in prompts:
            writer.writerow(
                [
                    category_cell,
                    _to_csv_cell(prompt.label),
                    _to_csv_cell(prompt.content),
                    prompt.color or "",
                    category_color if category_label else "",
                ]
            )
    return "﻿" + buffer.getvalue()
