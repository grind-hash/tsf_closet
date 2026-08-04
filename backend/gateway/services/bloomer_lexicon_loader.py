"""TSF Bloomer 用経験シグナル辞書の読み込みと検証。

同梱辞書 (gateway/lexicons) をロードし、ユーザー辞書 (settings.bloomer_lexicon_dir)
をカテゴリ単位でマージする。マッチングはプレーン部分一致のみで、正規表現は
サポートしない (ReDoS 回避)。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..consts.bloomer_consts import (
    LEXICON_CATEGORIES,
    LEXICON_CATEGORY_CAPS,
    LEXICON_LANGUAGES,
    MAX_KEYWORD_LENGTH,
    MAX_KEYWORDS_PER_FILE,
    MAX_LEXICON_FILE_BYTES,
    MAX_LEXICON_FILES,
)
from ..settings.config import settings

logger = logging.getLogger(__name__)

BUNDLED_LEXICON_DIR = Path(__file__).resolve().parents[1] / "lexicons"


class BloomerLexiconDefinition(BaseModel):
    """辞書ファイル1件分の定義。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1, le=1)
    category: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    cap: int | None = Field(default=None, ge=1, le=1000)
    mode: Literal["extend", "replace"] = "extend"
    keywords: dict[str, list[str]]

    @field_validator("category")
    @classmethod
    def _validate_category(cls, value: str) -> str:
        if value not in LEXICON_CATEGORIES:
            raise ValueError(f"未知の辞書カテゴリです: {value}")
        return value

    @field_validator("keywords")
    @classmethod
    def _validate_keywords(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        if not value:
            raise ValueError("keywordsが空です")
        total = 0
        normalized: dict[str, list[str]] = {}
        for language, words in value.items():
            if language not in LEXICON_LANGUAGES:
                raise ValueError(f"未対応の言語です: {language}")
            cleaned: list[str] = []
            for word in words:
                stripped = word.strip()
                if not stripped:
                    continue
                if len(stripped) > MAX_KEYWORD_LENGTH:
                    raise ValueError(
                        f"キーワードが長すぎます (最大{MAX_KEYWORD_LENGTH}文字): {stripped[:32]}"
                    )
                cleaned.append(stripped.lower())
            total += len(cleaned)
            normalized[language] = cleaned
        if total > MAX_KEYWORDS_PER_FILE:
            raise ValueError(
                f"キーワード件数が上限を超えています (最大{MAX_KEYWORDS_PER_FILE}件)"
            )
        return normalized


class BloomerLexicon:
    """カテゴリごとのキーワード集合とcap値を保持する。"""

    def __init__(self, keywords: dict[str, list[str]], caps: dict[str, int]) -> None:  # noqa: D107
        self.keywords = keywords
        self.caps = caps

    def keywords_for(self, category: str) -> list[str]:
        return self.keywords.get(category, [])

    def cap_for(self, category: str) -> int:
        return self.caps.get(category, LEXICON_CATEGORY_CAPS.get(category, 30))

    def counts(self) -> dict[str, int]:
        return {category: len(words) for category, words in self.keywords.items()}


def _read_definition(path: Path) -> BloomerLexiconDefinition:
    size = path.stat().st_size
    if size > MAX_LEXICON_FILE_BYTES:
        raise ValueError(
            f"辞書ファイルが大きすぎます (最大{MAX_LEXICON_FILE_BYTES}バイト): {path.name}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return BloomerLexiconDefinition.model_validate(payload)


def _iter_json_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    files = [path for path in sorted(directory.glob("*.json")) if path.is_file()]
    return files[:MAX_LEXICON_FILES]


def _merge(
    accumulated: dict[str, list[str]],
    caps: dict[str, int],
    definition: BloomerLexiconDefinition,
) -> None:
    words: list[str] = []
    for language in LEXICON_LANGUAGES:
        words.extend(definition.keywords.get(language, []))

    if definition.mode == "replace":
        accumulated[definition.category] = []

    existing = accumulated.setdefault(definition.category, [])
    seen = set(existing)
    for word in words:
        if word not in seen:
            existing.append(word)
            seen.add(word)

    if definition.cap is not None:
        caps[definition.category] = definition.cap
    else:
        caps.setdefault(
            definition.category, LEXICON_CATEGORY_CAPS.get(definition.category, 30)
        )


def load_bloomer_lexicon(user_dir: Path | None = None) -> BloomerLexicon:
    """同梱辞書とユーザー辞書をマージして返す。

    同梱辞書の不備は起動時エラーとして送出する。ユーザー辞書の不備は該当ファイルの
    みスキップし、警告ログを出して処理を続行する。
    """
    keywords: dict[str, list[str]] = {}
    caps: dict[str, int] = {}

    for path in _iter_json_files(BUNDLED_LEXICON_DIR):
        try:
            definition = _read_definition(path)
        except Exception as exc:
            raise RuntimeError(
                f"同梱辞書の読み込みに失敗しました: {path.name}"
            ) from exc
        _merge(keywords, caps, definition)

    target_dir = user_dir if user_dir is not None else settings.bloomer_lexicon_dir
    for path in _iter_json_files(target_dir):
        # シンボリックリンク経由のパストラバーサルを避けるため実体ファイルのみ扱う
        if path.is_symlink():
            logger.warning("Bloomer辞書のシンボリックリンクを無視しました: %s", path)
            continue
        try:
            definition = _read_definition(path)
        except Exception as exc:
            logger.warning("ユーザー辞書をスキップしました (%s): %s", path.name, exc)
            continue
        _merge(keywords, caps, definition)

    return BloomerLexicon(keywords=keywords, caps=caps)


_lexicon: BloomerLexicon = load_bloomer_lexicon()


def get_bloomer_lexicon() -> BloomerLexicon:
    return _lexicon


def reload_bloomer_lexicon() -> BloomerLexicon:
    global _lexicon
    _lexicon = load_bloomer_lexicon()
    return _lexicon
