"""キャラチャットの「調べ物」(LLM を使わない参照)。

判定 LLM が返した計画(CharacterChatPlan)を実行し、返答プロンプトへ載せる
テキストへ整形する。過去プレイの調べ物は DB 参照、現実世界の調べ物(Web 検索・天気)は
real_world_lookup 経由の外部 API で、返答プロンプトでは別の枠に載せる。
各項目は失敗しても会話を止めず「(取得できませんでした)」に落とし、文字数の上限で切る。
実行した明細(種類・検索語・本文・関係するセッション・出典)は返答メッセージの
meta_json に保存し、UI の「参照した記録」(引用表示)に使う。
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select

from ..consts.character_chat import (
    LOOKUP_LIMIT_DEFAULT,
    LOOKUP_RENDER_CAP,
    LOOKUP_TOTAL_CAP,
    PAST_PLAY_LOOKUP_KINDS,
    REAL_WORLD_LOOKUP_KINDS,
    REAL_WORLD_RENDER_CAP,
    REAL_WORLD_TOTAL_CAP,
    SESSION_CANDIDATES,
)
from ..databases.base import async_session_factory
from ..databases.models import History as HistoryORM
from ..databases.models import Session as SessionORM
from ..databases.models import TransformationTag as TransformationTagORM
from . import real_world_lookup
from .achievements import get_global_stats
from .character_chat_models import CharacterChatLookup, CharacterChatPlan
from .conversation import get_stage_display_name, get_stage_name
from .session import DEFAULT_USER_ID, session_store
from .session_search import (
    fetch_match_snippets,
    matching_session_ids_select_terms,
    search_terms,
)
from .source_snapshot import resolve_session_identity
from .summary_service import summary_service

logger = logging.getLogger(__name__)

_TITLES = {
    "recent_sessions": {"ja": "最近のセッション", "en": "Recent sessions"},
    "session_detail": {"ja": "セッションの詳細", "en": "Session detail"},
    "search_sessions": {"ja": "検索結果", "en": "Search results"},
    "tendencies": {"ja": "傾向・統計", "en": "Tendencies and statistics"},
    "recent_adventures": {"ja": "最近のTSFシナリオ", "en": "Recent TSF scenarios"},
    "web_search": {"ja": "Web検索", "en": "Web search"},
    "weather": {"ja": "天気", "en": "Weather"},
}
_INSTRUCTION_LABELS = {
    "ja": {
        "dress_up": "着替え",
        "reality_alter": "現実改変",
        "action": "行動",
        "conversation": "会話",
        "image_only": "画像のみ",
    },
    "en": {
        "dress_up": "dress-up",
        "reality_alter": "reality alteration",
        "action": "action",
        "conversation": "conversation",
        "image_only": "image only",
    },
}


@dataclass(frozen=True)
class LookupResult:
    """調べ物 1 件の結果。

    text はプロンプトに載せる整形済み本文、session_ids は本文に含めたセッションの
    ID(引用表示で「[先頭8桁]」からギャラリーへ飛ぶための対応表)。
    """

    text: str
    session_ids: tuple[str, ...] = ()
    # Web 検索の出典({title, url})。引用表示のリンクに使い、プロンプトには載せない
    sources: tuple[dict[str, str], ...] = ()


def _lang(language: str) -> str:
    return "en" if language == "en" else "ja"


def _clip(text: str, cap: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= cap else text[: cap - 1].rstrip() + "…"


def _date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    text = str(value or "")
    return text[:10] if len(text) >= 10 else text


def _short(text: Any, limit: int = 60) -> str:
    return _clip(" ".join(str(text or "").split()), limit)


def _unavailable(language: str) -> str:
    return (
        "(could not be retrieved)"
        if _lang(language) == "en"
        else "(取得できませんでした)"
    )


def _empty(language: str) -> str:
    return "(no records)" if _lang(language) == "en" else "(記録はありません)"


async def _session_name(session_id: str, language: str) -> str:
    session = await session_store.get_session_by_id(session_id)
    if session is None:
        return "?" if _lang(language) == "en" else "不明"
    name, _ = await resolve_session_identity(session)
    if bool(getattr(session, "self_mode", False)):
        return (
            f"{name} ({'self mode' if _lang(language) == 'en' else '自分自身モード'})"
        )
    return name


async def session_candidates(
    language: str, limit: int = SESSION_CANDIDATES
) -> list[dict[str, str]]:
    """判定 LLM が session_detail の session_id を選べるよう、直近セッションの id と短い説明を返す。"""
    rows, _ = await session_store.get_all_sessions(limit=limit)
    candidates: list[dict[str, str]] = []
    for row in rows:
        session_id = str(row.get("session_id") or "")
        if not session_id:
            continue
        name = await _session_name(session_id, language)
        label = f"{_date(row.get('updated_at'))} {name}"
        last = _short(row.get("last_instruction"), 30)
        if last:
            label = f"{label}: {last}"
        candidates.append({"id": session_id, "label": label})
    return candidates


async def render_recent_sessions(limit: int, language: str) -> LookupResult:
    rows, total = await session_store.get_all_sessions(limit=limit)
    if not rows:
        return LookupResult(_empty(language))
    lang = _lang(language)
    lines = [f"Total sessions: {total}" if lang == "en" else f"セッション総数: {total}"]
    session_ids: list[str] = []
    for row in rows:
        session_id = str(row.get("session_id") or "")
        session_ids.append(session_id)
        name = await _session_name(session_id, language)
        summary = await summary_service.get_summary(session_id)
        title = _short(summary.get("title"), 40) if summary else ""
        count = int(row.get("transformation_count") or 0)
        last = _short(row.get("last_instruction"), 60)
        if lang == "en":
            line = f"- [{session_id[:8]}] {_date(row.get('updated_at'))} {name}, {count} transformations"
            if title:
                line += f', title "{title}"'
            if last:
                line += f", last instruction: {last}"
        else:
            line = f"- [{session_id[:8]}] {_date(row.get('updated_at'))} {name}、変身{count}回"
            if title:
                line += f"、称号「{title}」"
            if last:
                line += f"、最後の指示: {last}"
        lines.append(line)
    return LookupResult("\n".join(lines), tuple(session_ids))


async def render_session_detail(
    session_id: str | None, limit: int, language: str
) -> LookupResult:
    lang = _lang(language)
    if not session_id:
        return LookupResult(_unavailable(language))
    session = await session_store.get_session_by_id(session_id)
    if session is None or session.user_id != DEFAULT_USER_ID:
        return LookupResult(_empty(language))
    name = await _session_name(session_id, language)
    lines = [
        f"Session {session_id[:8]} ({_date(session.updated_at)}) with {name}"
        if lang == "en"
        else f"セッション {session_id[:8]}({_date(session.updated_at)})、相手: {name}"
    ]
    summary = await summary_service.get_summary(session_id)
    if summary:
        title = _short(summary.get("title"), 40)
        body = _clip(str(summary.get("summary") or ""), 600)
        if title:
            lines.append(f"Title: {title}" if lang == "en" else f"称号: {title}")
        if body:
            lines.append(f"Summary: {body}" if lang == "en" else f"要約: {body}")
    if bool(getattr(session, "self_mode", False)):
        # 自分自身モードは stats を追跡しないので、開花度由来の段階を出さない
        lines.append(
            f"Transformations: {session.transformation_count} (self mode: no "
            "parameters or mental stage are tracked)"
            if lang == "en"
            else f"変身{session.transformation_count}回"
            "(自分自身モード: パラメータ・心理段階は追跡していません)"
        )
    else:
        stats = await session_store.get_session_stats(session_id)
        if stats is not None:
            stage = get_stage_name(int(stats.bloom))
            stage_label = stage if lang == "en" else get_stage_display_name(stage)
            lines.append(
                f"Transformations: {session.transformation_count}, stage: {stage_label} "
                f"(bloom {stats.bloom}, shame {stats.shame}, adaptation {stats.adaptation})"
                if lang == "en"
                else f"変身{session.transformation_count}回、心理段階: {stage_label}"
                f"(開花{stats.bloom} / 羞恥{stats.shame} / 適応{stats.adaptation})"
            )
    attributes = await session_store.get_session_attribute_texts(session_id)
    if attributes:
        joined = " / ".join(_short(item, 40) for item in attributes[:8])
        lines.append(
            f"Attributes: {joined}" if lang == "en" else f"付与された属性: {joined}"
        )
    timeline = await session_store.get_session_timeline(
        session_id, limit=max(limit, 10) * 2
    )
    if timeline:
        lines.append("Timeline (oldest first):" if lang == "en" else "経緯(古い順):")
        labels = _INSTRUCTION_LABELS[lang]
        for event_type, text in timeline[-(max(limit, 10) * 2) :]:
            lines.append(f"- [{labels.get(event_type, event_type)}] {_short(text, 80)}")
    return LookupResult("\n".join(lines), (session_id,))


def _quoted_terms(terms: list[str], lang: str) -> str:
    if lang == "en":
        return ", ".join(f'"{term}"' for term in terms)
    return "".join(f"「{term}」" for term in terms)


async def _search_session_rows(db, terms: list[str], *, match_all: bool, limit: int):
    matching = matching_session_ids_select_terms(terms, match_all=match_all).subquery()
    stmt = (
        select(SessionORM.id, SessionORM.updated_at)
        .where(
            SessionORM.user_id == DEFAULT_USER_ID,
            SessionORM.id.in_(select(matching.c.session_id)),
        )
        .order_by(desc(SessionORM.updated_at))
        .limit(limit)
    )
    return (await db.execute(stmt)).all()


async def render_search_sessions(
    query: str | None, limit: int, language: str
) -> LookupResult:
    """空白区切りの検索語で過去のやり取りを探す。

    まず全語に一致するセッションを探し、無ければいずれかの語に一致するものへ広げる
    (判定 LLM が語を並べ過ぎても空振りで終わらせない)。
    """
    lang = _lang(language)
    terms = search_terms(query)
    if not terms:
        return LookupResult(_unavailable(language))
    async with async_session_factory() as db:
        matched_all = True
        rows = await _search_session_rows(db, terms, match_all=True, limit=limit)
        if not rows and len(terms) > 1:
            matched_all = False
            rows = await _search_session_rows(db, terms, match_all=False, limit=limit)
        session_ids = [str(row.id) for row in rows]
        snippets = await fetch_match_snippets(db, session_ids, terms)
    quoted = _quoted_terms(terms, lang)
    if not rows:
        return LookupResult(
            f"No records match {quoted}."
            if lang == "en"
            else f"{quoted}に一致する記録はありません。"
        )
    if len(terms) == 1:
        header = (
            f"Sessions matching {quoted} (newest first):"
            if lang == "en"
            else f"{quoted}に一致するセッション(新しい順):"
        )
    elif matched_all:
        header = (
            f"Sessions matching all of {quoted} (newest first):"
            if lang == "en"
            else f"{quoted}のすべてに一致するセッション(新しい順):"
        )
    else:
        header = (
            f"No session matches all of {quoted}; sessions matching any of them "
            "(newest first):"
            if lang == "en"
            else f"{quoted}のすべてに一致する記録はありません。"
            "いずれかに一致するセッション(新しい順):"
        )
    lines = [header]
    for row in rows:
        session_id = str(row.id)
        name = await _session_name(session_id, language)
        snippet = _short(snippets.get(session_id, ""), 90)
        line = f"- [{session_id[:8]}] {_date(row.updated_at)} {name}"
        if snippet:
            line += f": {snippet}"
        lines.append(line)
    return LookupResult("\n".join(lines), tuple(session_ids))


async def render_tendencies(language: str) -> LookupResult:
    lang = _lang(language)
    labels = _INSTRUCTION_LABELS[lang]
    async with async_session_factory() as db:
        total_sessions = (
            await db.execute(
                select(func.count())
                .select_from(SessionORM)
                .where(SessionORM.user_id == DEFAULT_USER_ID)
            )
        ).scalar_one() or 0
        type_rows = (
            await db.execute(
                select(HistoryORM.instruction_type, func.count())
                .join(SessionORM, SessionORM.id == HistoryORM.session_id)
                .where(SessionORM.user_id == DEFAULT_USER_ID)
                .group_by(HistoryORM.instruction_type)
                .order_by(desc(func.count()))
            )
        ).all()
        costume_rows = (
            await db.execute(
                select(TransformationTagORM.costume_category, func.count())
                .join(HistoryORM, HistoryORM.id == TransformationTagORM.history_id)
                .join(SessionORM, SessionORM.id == HistoryORM.session_id)
                .where(SessionORM.user_id == DEFAULT_USER_ID)
                .group_by(TransformationTagORM.costume_category)
                .order_by(desc(func.count()))
                .limit(5)
            )
        ).all()
    lines = [
        f"Total sessions: {total_sessions}"
        if lang == "en"
        else f"セッション総数: {total_sessions}"
    ]
    if type_rows:
        parts = [
            f"{labels.get(str(kind or ''), str(kind or 'other'))} {count}"
            for kind, count in type_rows
        ]
        lines.append(
            "Instructions by type: " + ", ".join(parts)
            if lang == "en"
            else "指示の内訳: " + "、".join(parts)
        )
    if costume_rows:
        parts = [f"{category} {count}" for category, count in costume_rows]
        lines.append(
            "Frequent costume categories: " + ", ".join(parts)
            if lang == "en"
            else "よく選ぶ衣装カテゴリ: " + "、".join(parts)
        )
    try:
        stats = get_global_stats()
        lines.append(
            f"Cumulative: {stats.transform_count} transformations, "
            f"{stats.crossdress_count} cross-dressing, {stats.reality_alter_count} "
            f"reality alterations, {stats.gallery_count} images"
            + (", gender change experienced" if stats.has_gender_change else "")
            if lang == "en"
            else f"累計: 変身{stats.transform_count}回、女装{stats.crossdress_count}回、"
            f"現実改変{stats.reality_alter_count}回、画像{stats.gallery_count}枚"
            + ("、性転換の経験あり" if stats.has_gender_change else "")
        )
    except Exception as exc:  # pragma: no cover - 統計取得は補助情報
        logger.warning(
            "character chat tendencies stats failed: %s: %s", type(exc).__name__, exc
        )
    try:
        ending_ids = await session_store.get_achieved_ending_ids()
        if ending_ids:
            lines.append(
                f"Endings reached: {len(ending_ids)}"
                if lang == "en"
                else f"到達したエンディング: {len(ending_ids)}種"
            )
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "character chat endings lookup failed: %s: %s", type(exc).__name__, exc
        )
    return LookupResult("\n".join(lines))


async def render_recent_adventures(limit: int, language: str) -> LookupResult:
    from .adventure_service import adventure_service

    lang = _lang(language)
    runs = await adventure_service.list_runs()
    if not runs:
        return LookupResult(_empty(language))
    lines = []
    for run in runs[:limit]:
        title = _short(run.get("title"), 40)
        preset = str(run.get("preset") or "")
        status = str(run.get("status") or "")
        turn_count = int(run.get("turn_count") or 0)
        max_turns = int(run.get("max_turns") or 0)
        ending = _short(run.get("ending_title"), 40)
        if lang == "en":
            line = (
                f"- {title} (preset {preset}, {status}, turn {turn_count}/{max_turns})"
            )
            if ending:
                line += f", ending: {ending}"
        else:
            line = (
                f"- {title}(プリセット {preset}、{status}、{turn_count}/{max_turns}手)"
            )
            if ending:
                line += f"、エンディング: {ending}"
        lines.append(line)
    return LookupResult("\n".join(lines))


async def render_web_search(query: str | None, language: str) -> LookupResult:
    if not query:
        return LookupResult(_unavailable(language))
    lang = _lang(language)
    info = await real_world_lookup.tavily_search(query, language=lang)
    return LookupResult(
        real_world_lookup.format_search(info, lang),
        sources=tuple(
            {"title": source.title, "url": source.url}
            for source in info.sources
            if source.url
        ),
    )


async def render_weather(language: str) -> LookupResult:
    info = await real_world_lookup.fetch_weather()
    if info is None:
        return LookupResult(_unavailable(language))
    return LookupResult(real_world_lookup.format_weather(info, _lang(language)))


async def _dispatch(lookup: CharacterChatLookup, language: str) -> LookupResult:
    limit = int(lookup.limit or LOOKUP_LIMIT_DEFAULT)
    if lookup.kind == "recent_sessions":
        return await render_recent_sessions(limit, language)
    if lookup.kind == "session_detail":
        return await render_session_detail(lookup.session_id, limit, language)
    if lookup.kind == "search_sessions":
        return await render_search_sessions(lookup.query, limit, language)
    if lookup.kind == "tendencies":
        return await render_tendencies(language)
    if lookup.kind == "recent_adventures":
        return await render_recent_adventures(limit, language)
    if lookup.kind == "web_search":
        return await render_web_search(lookup.query, language)
    if lookup.kind == "weather":
        return await render_weather(language)
    return LookupResult(_unavailable(language))


def is_policy_refused(lookup: CharacterChatLookup, *, message: str = "") -> bool:
    """Web 検索のうち、検索サービスの利用規約で禁止されている内容として送らないもの。

    判定 LLM の印(refused)、検索語、元の発言のいずれかが明白な性的語に当たれば送らない。
    判定 LLM が検索語を当たり障りのない形に言い換えても、発言が当たれば止める。
    """
    return lookup.kind == "web_search" and (
        lookup.refused
        or real_world_lookup.violates_search_policy(lookup.query or "")
        or real_world_lookup.violates_search_policy(message)
    )


def _policy_refused(language: str) -> str:
    return (
        "(Not searched: the acceptable use policy of the search service Tavily "
        "forbids this content)"
        if _lang(language) == "en"
        else "(検索サービス Tavily の利用規約で禁止されている内容のため、検索しませんでした)"
    )


def available_real_world_kinds(
    *, use_web_search: bool, use_weather: bool
) -> frozenset[str]:
    """設定で ON にし、サーバーにもキー・地点がある現実世界の調べ物。

    案内役キャラに限る判断は呼び出し側で行う。
    """
    kinds: set[str] = set()
    if use_web_search and real_world_lookup.web_search_configured():
        kinds.add("web_search")
    if use_weather and real_world_lookup.weather_configured():
        kinds.add("weather")
    return frozenset(kinds)


@dataclass(frozen=True)
class LookupRun:
    """run_lookups の結果。

    text は過去プレイの調べ物、real_world_text は Web 検索・天気の本文(返答プロンプトでは
    別の枠に載せる)。details は引用表示用の明細。web_search_refused は Web 検索を
    利用規約で見送ったか(返答で理由を伝える)。
    """

    text: str = ""
    real_world_text: str = ""
    details: list[dict[str, Any]] = field(default_factory=list)
    web_search_refused: bool = False


async def run_lookups(
    plan: CharacterChatPlan,
    *,
    language: str,
    allowed_kinds: Collection[str] = PAST_PLAY_LOOKUP_KINDS,
    message: str = "",
) -> LookupRun:
    """計画の調べ物を順に実行する。

    allowed_kinds に無い種類は実行しない(判定 LLM の計画の検証と二重の防御)。
    利用規約で禁止されている Web 検索(is_policy_refused。message は相手の今回の発言)は
    送らず、見送った検索語と理由だけを明細に残す。
    明細は 1 件ごとに kind / query / session_id / text / session_ids を持ち、Web 検索は
    sources も持つ。text はプロンプトに載せたものと同じ整形済み本文で、返答メッセージの
    meta_json に保存して UI の「参照した記録」に使う。
    """
    lang = _lang(language)
    past_blocks: list[str] = []
    real_world_blocks: list[str] = []
    details: list[dict[str, Any]] = []
    web_search_refused = False
    for lookup in plan.lookups:
        if lookup.kind not in allowed_kinds:
            logger.info("character chat lookup %s is not allowed; skipped", lookup.kind)
            continue
        if is_policy_refused(lookup, message=message):
            logger.info(
                "character chat web search refused by the search service policy: "
                "query=%s",
                lookup.query,
            )
            web_search_refused = True
            details.append(
                {
                    "kind": lookup.kind,
                    "query": lookup.query,
                    "session_id": None,
                    "text": _policy_refused(language),
                    "session_ids": [],
                    "sources": [],
                    "refused": "search_policy",
                }
            )
            continue
        if lookup.kind == "web_search" and not lookup.query:
            continue
        real_world = lookup.kind in REAL_WORLD_LOOKUP_KINDS
        try:
            result = await _dispatch(lookup, language)
        except Exception as exc:
            logger.warning(
                "character chat lookup %s failed: %s: %s",
                lookup.kind,
                type(exc).__name__,
                exc,
            )
            result = LookupResult(_unavailable(language))
        text = _clip(
            result.text, REAL_WORLD_RENDER_CAP if real_world else LOOKUP_RENDER_CAP
        )
        title = _TITLES.get(lookup.kind, {}).get(lang, lookup.kind)
        if lookup.kind == "web_search":
            title = (
                f'{title}: "{lookup.query}"'
                if lang == "en"
                else f"{title}「{lookup.query}」"
            )
        (real_world_blocks if real_world else past_blocks).append(f"## {title}\n{text}")
        detail: dict[str, Any] = {
            "kind": lookup.kind,
            "query": lookup.query,
            "session_id": lookup.session_id,
            "text": text,
            "session_ids": list(result.session_ids),
        }
        if lookup.kind == "web_search":
            detail["sources"] = [dict(source) for source in result.sources]
        details.append(detail)
    return LookupRun(
        text=_clip("\n\n".join(past_blocks), LOOKUP_TOTAL_CAP),
        real_world_text=_clip("\n\n".join(real_world_blocks), REAL_WORLD_TOTAL_CAP),
        details=details,
        web_search_refused=web_search_refused,
    )
