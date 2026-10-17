"""お気に入りプロンプトのインポート / エクスポート用ファイル（JSON / CSV）。"""

from __future__ import annotations

import json

import pytest

from gateway.schemas.favorite_prompts import (
    FavoritePromptFile,
    FavoritePromptFileCategory,
    FavoritePromptFilePrompt,
)
from gateway.services.favorite_prompt_file import (
    EXPORT_FORMAT,
    EXPORT_VERSION,
    FavoritePromptFileError,
    parse_file,
    render_csv,
    render_json,
)


def _sample() -> FavoritePromptFile:
    return FavoritePromptFile(
        format=EXPORT_FORMAT,
        version=EXPORT_VERSION,
        categories=[
            FavoritePromptFileCategory(label="衣装", color="#3B82F6"),
            FavoritePromptFileCategory(label="空", color="#10B981"),
        ],
        prompts=[
            FavoritePromptFilePrompt(
                category="衣装",
                label="白ワンピース",
                content="white dress,\nsun hat, ",
                color="#6B7280",
            ),
            FavoritePromptFilePrompt(
                category=None, label="弱め", content="-1::smile::", color="#EF4444"
            ),
        ],
    )


def test_json_round_trip():
    entries = parse_file("favorites.json", render_json(_sample()).encode("utf-8"))

    assert [(c.label, c.color) for c in entries.categories] == [
        ("衣装", "#3B82F6"),
        ("空", "#10B981"),
    ]
    assert [(p.category, p.label, p.content) for p in entries.prompts] == [
        ("衣装", "白ワンピース", "white dress,\nsun hat, "),
        (None, "弱め", "-1::smile::"),
    ]
    assert entries.prompts[0].position == "お気に入りプロンプトの1件目"


def test_csv_round_trip_keeps_empty_category_and_formula_like_text():
    text = render_csv(_sample())
    assert text.startswith("﻿カテゴリー,名前,内容,色,カテゴリーの色\r\n")
    # Excel に数式として解釈させない
    assert "'-1::smile::" in text

    entries = parse_file("favorites.csv", text.encode("utf-8"))

    # 一覧画面と同じく未分類が先、空のカテゴリーは名前・内容が空の行で残る
    assert [(p.category, p.label, p.content, p.color) for p in entries.prompts] == [
        (None, "弱め", "-1::smile::", "#EF4444"),
        ("衣装", "白ワンピース", "white dress,\nsun hat, ", "#6B7280"),
    ]
    assert [(c.label, c.color) for c in entries.categories] == [
        ("衣装", "#3B82F6"),
        ("空", "#10B981"),
    ]


def test_csv_accepts_shift_jis_english_headers_and_bare_colors():
    text = "Name,Content,Category,Color\r\n笑顔,smile,表情,ff0000\r\n"
    entries = parse_file("export.csv", text.encode("cp932"))

    assert [(p.category, p.label, p.content, p.color) for p in entries.prompts] == [
        ("表情", "笑顔", "smile", "#ff0000"),
    ]
    assert entries.categories == []


def test_csv_positions_follow_spreadsheet_rows():
    text = "カテゴリ,名前,内容\n\n衣装,,white dress\n"
    entries = parse_file("a.csv", text.encode("utf-8"))

    assert entries.prompts[0].position == "3行目"


def test_csv_requires_label_and_content_columns():
    with pytest.raises(FavoritePromptFileError) as exc:
        parse_file("a.csv", "カテゴリー,名前\n衣装,a\n".encode())
    assert exc.value.code == "invalid_import_file"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ("not json", "invalid_import_file"),
        (json.dumps({"format": "other", "version": 1}), "invalid_import_file"),
        (
            json.dumps({"format": EXPORT_FORMAT, "version": 99}),
            "unsupported_import_version",
        ),
    ],
)
def test_json_rejects_foreign_files(payload: str, code: str):
    with pytest.raises(FavoritePromptFileError) as exc:
        parse_file("a.json", payload.encode("utf-8"))
    assert exc.value.code == code


def test_json_reports_position_of_malformed_item():
    payload = {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "prompts": [{"label": "a", "content": "b"}, {"label": "c"}],
    }
    with pytest.raises(FavoritePromptFileError) as exc:
        parse_file("a.json", json.dumps(payload).encode("utf-8"))
    assert exc.value.message.startswith("お気に入りプロンプトの2件目")


def test_empty_file_is_rejected():
    with pytest.raises(FavoritePromptFileError) as exc:
        parse_file("a.csv", b"\xef\xbb\xbf\r\n")
    assert exc.value.code == "empty_file"
