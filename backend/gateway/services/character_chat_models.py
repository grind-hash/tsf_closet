"""キャラチャットの LLM 構造化出力(Pydantic)。

判定 LLM の計画(何を調べるか / 着替え要求か / 来歴の記憶を呼ぶか)と、
着替え時の外見タグ更新の出力形。崩れた値は検証エラーにせず、adventure_models と
同じく切り詰め・既定値で受ける(修復リトライに落とさない)。
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..consts.character_chat import (
    APPEARANCE_DESCRIPTION_MAX,
    APPEARANCE_REQUEST_MAX,
    APPEARANCE_TAGS_MAX,
    LOOKUP_KINDS,
    LOOKUP_LIMIT_DEFAULT,
    LOOKUP_LIMIT_MAX,
    LOOKUP_MAX_PER_TURN,
    LOOKUP_QUERY_MAX,
)
from .session_search import search_terms

LookupKind = Literal[
    "recent_sessions",
    "session_detail",
    "search_sessions",
    "tendencies",
    "recent_adventures",
]

_NULL_WORDS = {"", "null", "none", "no", "false", "n/a"}


# 外見タグに混ざってはいけない文字(ひらがな・カタカナ・漢字・全角記号)
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")


def non_english_tag_parts(tags: str) -> list[str]:
    """カンマ区切りタグのうち、日本語(CJK)を含む要素を返す。

    着替え LLM が依頼文をそのまま写した「シフォンブラウス」のようなタグは
    画像生成器に通じないため、呼び出し側は再生成または拒否に使う。
    """
    return [
        part.strip()
        for part in str(tags or "").split(",")
        if part.strip() and _CJK_RE.search(part)
    ]


def _clean_text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if text.lower() in _NULL_WORDS:
        return None
    return text[:limit]


class CharacterChatLookup(BaseModel):
    kind: LookupKind
    query: str | None = None
    session_id: str | None = None
    limit: int = LOOKUP_LIMIT_DEFAULT

    @field_validator("query", mode="before")
    @classmethod
    def _clean_query(cls, value: Any) -> str | None:
        # 判定 LLM は検索語を引用符で包んで返すことがある。LIKE 検索と meta_json に
        # 残す検索語の両方から外す(空白区切りの各語について両端だけ)
        text = _clean_text(value, LOOKUP_QUERY_MAX)
        if text is None:
            return None
        return " ".join(search_terms(text)) or None

    @field_validator("session_id", mode="before")
    @classmethod
    def _clean_session_id(cls, value: Any) -> str | None:
        return _clean_text(value, 80)

    @field_validator("limit", mode="before")
    @classmethod
    def _clamp_limit(cls, value: Any) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return LOOKUP_LIMIT_DEFAULT
        return max(1, min(LOOKUP_LIMIT_MAX, number))


class CharacterChatPlan(BaseModel):
    lookups: list[CharacterChatLookup] = Field(default_factory=list)
    appearance_request: str | None = None
    # 案内役キャラの「別の層の記憶」を今回の返答に載せるか(base 種だけ意味を持つ)
    origin_lore: bool = False

    @field_validator("lookups", mode="before")
    @classmethod
    def _coerce_lookups(cls, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        kept: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for item in value:
            if isinstance(item, str):
                item = {"kind": item}
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip().lower()
            if kind not in LOOKUP_KINDS:
                continue
            key = (kind, item.get("query"), item.get("session_id"))
            if key in seen:
                continue
            seen.add(key)
            kept.append({**item, "kind": kind})
            if len(kept) >= LOOKUP_MAX_PER_TURN:
                break
        return kept

    @field_validator("appearance_request", mode="before")
    @classmethod
    def _clean_request(cls, value: Any) -> str | None:
        if isinstance(value, bool):
            return None
        return _clean_text(value, APPEARANCE_REQUEST_MAX)

    @field_validator("origin_lore", mode="before")
    @classmethod
    def _coerce_origin_lore(cls, value: Any) -> bool:
        # 判定 LLM は "true" / "yes" のような文字列で返すことがある。それ以外は false
        if isinstance(value, bool):
            return value
        if isinstance(value, int | float):
            return bool(value)
        return str(value or "").strip().lower() in {"true", "yes", "1"}


def empty_plan() -> CharacterChatPlan:
    return CharacterChatPlan()


class CharacterChatAppearanceOutput(BaseModel):
    identity_tags: str = ""
    clothing_tags: str = ""
    description: str = ""

    @field_validator("identity_tags", "clothing_tags", mode="before")
    @classmethod
    def _clean_tags(cls, value: Any) -> str:
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        text = _clean_text(value, APPEARANCE_TAGS_MAX) or ""
        parts = [part.strip() for part in text.split(",")]
        return ", ".join(part for part in parts if part)

    @field_validator("description", mode="before")
    @classmethod
    def _clean_description(cls, value: Any) -> str:
        return _clean_text(value, APPEARANCE_DESCRIPTION_MAX) or ""
