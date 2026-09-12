"""キャラチャットの LLM 構造化出力(Pydantic)。

判定 LLM の計画(何を調べるか / 着替え要求か / 来歴の記憶を呼ぶか)と、
着替え時の外見タグ更新の出力形。崩れた値は検証エラーにせず、adventure_models と
同じく切り詰め・既定値で受ける(修復リトライに落とさない)。
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from ..consts.character_chat import (
    APPEARANCE_DESCRIPTION_MAX,
    APPEARANCE_REQUEST_MAX,
    APPEARANCE_TAGS_MAX,
    LOOKUP_KINDS,
    LOOKUP_LIMIT_DEFAULT,
    LOOKUP_LIMIT_MAX,
    LOOKUP_MAX_PER_TURN,
    LOOKUP_QUERY_MAX,
    PAST_PLAY_LOOKUP_KINDS,
    REAL_WORLD_LOOKUP_KINDS,
    WEB_SEARCH_QUERY_MAX,
    WEB_SEARCH_TERMS_MAX,
)
from .session_search import SEARCH_TERMS_MAX, search_terms

LookupKind = Literal[
    "recent_sessions",
    "session_detail",
    "search_sessions",
    "tendencies",
    "recent_adventures",
    "web_search",
    "weather",
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


def _truthy(value: Any) -> bool:
    # 判定 LLM は "true" / "yes" のような文字列で返すことがある。それ以外は false
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    return str(value or "").strip().lower() in {"true", "yes", "1"}


def _search_query(value: Any, *, limit: int, max_terms: int) -> str | None:
    # 判定 LLM は検索語を引用符で包んで返すことがある。検索に渡す語と meta_json に
    # 残す語の両方から外す(空白区切りの各語について両端だけ)
    text = _clean_text(value, limit)
    if text is None:
        return None
    return " ".join(search_terms(text, max_terms=max_terms)) or None


def _web_search_query(value: Any) -> str | None:
    return _search_query(
        value, limit=WEB_SEARCH_QUERY_MAX, max_terms=WEB_SEARCH_TERMS_MAX
    )


class CharacterChatLookup(BaseModel):
    kind: LookupKind
    query: str | None = None
    session_id: str | None = None
    limit: int = LOOKUP_LIMIT_DEFAULT
    # web_search のうち、話題が検索サービスの利用規約で禁止されている(性的に露骨)と
    # 判定 LLM が見なしたもの。検索は送らず、見送った理由を返答で伝える
    refused: bool = False

    @field_validator("query", mode="before")
    @classmethod
    def _clean_query(cls, value: Any, info: ValidationInfo) -> str | None:
        kind = info.data.get("kind")
        if kind == "weather":
            return None
        if kind == "web_search":
            return _web_search_query(value)
        return _search_query(value, limit=LOOKUP_QUERY_MAX, max_terms=SEARCH_TERMS_MAX)

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

    @field_validator("refused", mode="before")
    @classmethod
    def _coerce_refused(cls, value: Any, info: ValidationInfo) -> bool:
        return info.data.get("kind") == "web_search" and _truthy(value)


class CharacterChatPlan(BaseModel):
    lookups: list[CharacterChatLookup] = Field(default_factory=list)
    appearance_request: str | None = None
    # 案内役キャラの「別の層の記憶」を今回の返答に載せるか(base 種だけ意味を持つ)
    origin_lore: bool = False

    @field_validator("lookups", mode="before")
    @classmethod
    def _coerce_lookups(cls, value: Any, info: ValidationInfo) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        # 使ってよい種類は呼び出し側が検証 context で渡す。無ければ過去プレイの調べ物だけ。
        # 上限件数で切る前に落とし、使えない種類が枠を埋めないようにする
        context = info.context if isinstance(info.context, dict) else {}
        allowed = set(context.get("allowed_kinds", PAST_PLAY_LOOKUP_KINDS))
        kept: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for item in value:
            if isinstance(item, str):
                item = {"kind": item}
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip().lower()
            if kind not in LOOKUP_KINDS or kind not in allowed:
                continue
            # 検索語の無い web_search は捨てる。利用規約で見送る印があれば、理由を
            # 伝えるために検索語が無くても残す
            if (
                kind == "web_search"
                and _web_search_query(item.get("query")) is None
                and not _truthy(item.get("refused"))
            ):
                continue
            # 現実世界の調べ物は 1 手番に種類ごと 1 件まで
            key = (
                (kind,)
                if kind in REAL_WORLD_LOOKUP_KINDS
                else (kind, item.get("query"), item.get("session_id"))
            )
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
        return _truthy(value)


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
