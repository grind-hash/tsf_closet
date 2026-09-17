"""セッション横断のフリーワード検索。

ギャラリーの検索とキャラチャットの「過去のやり取りを調べる」が共用する。
History の指示・心境・前後記述、Conversation の本文、PlaySummary の
称号・要約を LIKE で当て、セッションごとの代表スニペットを返す。
検索語は空白区切りの複数語にも対応し、全語一致(AND)といずれか一致(OR)を選べる。
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import desc, intersect, or_, select, union

from ..databases.models import Conversation as ConversationORM
from ..databases.models import History as HistoryORM
from ..databases.models import PlaySummary as PlaySummaryORM

# 検索語の両端から取り除く引用符・かぎ括弧・区切り記号
_TERM_EDGE_CHARS = "\"'“”‘’「」『』«»`,、。"
SEARCH_TERMS_MAX = 5


def escape_like(value: str) -> str:
    """LIKE パターン用に % / _ / \\ をエスケープする"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def strip_quotes(text: str) -> str:
    """両端の引用符・かぎ括弧・区切り記号を取り除く。"""
    return str(text or "").strip().strip(_TERM_EDGE_CHARS).strip()


def search_terms(query: str | None, max_terms: int = SEARCH_TERMS_MAX) -> list[str]:
    """フリーワードを空白で区切り、各語の両端の引用符を外した検索語の一覧にする。

    判定 LLM が「"元々男だったのに"」のように引用符ごと返しても LIKE で空振り
    しないための正規化。重複は除き、先頭から max_terms 語まで。
    """
    terms: list[str] = []
    for token in str(query or "").split():
        term = strip_quotes(token)
        if term and term not in terms:
            terms.append(term)
            if len(terms) >= max_terms:
                break
    return terms


def _terms(query: str | Sequence[str]) -> list[str]:
    if isinstance(query, str):
        return [query] if query else []
    return [str(term) for term in query if term]


def find_term(text: str, terms: Sequence[str]) -> str | None:
    """本文に含まれる最初の検索語を返す(大文字小文字は区別しない)。"""
    if not text:
        return None
    lowered = text.lower()
    for term in terms:
        if term.lower() in lowered or term in text:
            return term
    return None


def make_snippet(text: str, query: str, max_len: int = 80) -> str:
    """検索語周辺を切り出したスニペットを返す"""
    if not text:
        return ""

    idx = text.lower().find(query.lower())
    if idx < 0:
        idx = text.find(query)
    if idx < 0:
        snippet = text[:max_len]
        return snippet + ("…" if len(text) > max_len else "")

    start = max(0, idx - 20)
    end = min(len(text), idx + len(query) + 40)
    snippet = text[start:end]
    if start > 0:
        snippet = f"…{snippet}"
    if end < len(text):
        snippet = f"{snippet}…"
    return snippet


def _like_any(column, terms: Sequence[str]):
    """列がいずれかの検索語を含む条件"""
    return or_(*[column.like(f"%{escape_like(term)}%", escape="\\") for term in terms])


def matching_session_ids_select(pattern: str):
    """指示・会話・要約のいずれかに一致する session_id を返す SELECT"""
    history_match = select(HistoryORM.session_id.label("session_id")).where(
        or_(
            HistoryORM.instruction.like(pattern, escape="\\"),
            HistoryORM.feeling_text.like(pattern, escape="\\"),
            HistoryORM.before_description.like(pattern, escape="\\"),
            HistoryORM.after_description.like(pattern, escape="\\"),
        )
    )
    conversation_match = select(ConversationORM.session_id.label("session_id")).where(
        ConversationORM.content.like(pattern, escape="\\")
    )
    summary_match = select(PlaySummaryORM.session_id.label("session_id")).where(
        or_(
            PlaySummaryORM.title.like(pattern, escape="\\"),
            PlaySummaryORM.summary.like(pattern, escape="\\"),
        )
    )
    return history_match.union(conversation_match, summary_match)


def matching_session_ids_select_terms(terms: Sequence[str], *, match_all: bool = True):
    """複数の検索語に一致する session_id を返す SELECT。

    match_all=True なら全語に(セッション内のどこかの行・列で)一致するもの、
    False ならいずれかの語に一致するもの。語ごとの一致集合を INTERSECT / UNION で
    合成する。1 語なら matching_session_ids_select と同じ結果になる。
    """
    selects = [
        select(
            matching_session_ids_select(f"%{escape_like(term)}%")
            .subquery()
            .c.session_id
        )
        for term in _terms(terms)
    ]
    if not selects:
        raise ValueError("terms must not be empty")
    if len(selects) == 1:
        return selects[0]
    return intersect(*selects) if match_all else union(*selects)


async def fetch_match_snippets(
    db_session,
    session_ids: list[str],
    query: str | Sequence[str],
) -> dict[str, str]:
    """セッションごとの代表的なマッチ箇所を取得する（会話を優先）

    query は 1 語の文字列か検索語の一覧。複数語のときは、いずれかの語を含む
    本文から最初に見つかった語の周辺を切り出す。
    """
    terms = _terms(query)
    if not session_ids or not terms:
        return {}

    snippets: dict[str, str] = {}

    conv_rows = (
        await db_session.execute(
            select(ConversationORM.session_id, ConversationORM.content)
            .where(
                ConversationORM.session_id.in_(session_ids),
                _like_any(ConversationORM.content, terms),
            )
            .order_by(desc(ConversationORM.created_at))
        )
    ).all()
    for session_id, content in conv_rows:
        sid = str(session_id)
        if sid not in snippets and content:
            snippets[sid] = make_snippet(content, find_term(content, terms) or terms[0])

    remaining = [sid for sid in session_ids if sid not in snippets]
    if remaining:
        history_rows = (
            await db_session.execute(
                select(
                    HistoryORM.session_id,
                    HistoryORM.instruction,
                    HistoryORM.feeling_text,
                    HistoryORM.before_description,
                    HistoryORM.after_description,
                )
                .where(
                    HistoryORM.session_id.in_(remaining),
                    or_(
                        _like_any(HistoryORM.instruction, terms),
                        _like_any(HistoryORM.feeling_text, terms),
                        _like_any(HistoryORM.before_description, terms),
                        _like_any(HistoryORM.after_description, terms),
                    ),
                )
                .order_by(desc(HistoryORM.created_at))
            )
        ).all()
        for row in history_rows:
            sid = str(row.session_id)
            if sid in snippets:
                continue
            for field in (
                row.instruction,
                row.feeling_text,
                row.before_description,
                row.after_description,
            ):
                term = find_term(field or "", terms)
                if term:
                    snippets[sid] = make_snippet(field, term)
                    break

    remaining = [sid for sid in session_ids if sid not in snippets]
    if remaining:
        summary_rows = (
            await db_session.execute(
                select(
                    PlaySummaryORM.session_id,
                    PlaySummaryORM.title,
                    PlaySummaryORM.summary,
                ).where(
                    PlaySummaryORM.session_id.in_(remaining),
                    or_(
                        _like_any(PlaySummaryORM.title, terms),
                        _like_any(PlaySummaryORM.summary, terms),
                    ),
                )
            )
        ).all()
        for row in summary_rows:
            sid = str(row.session_id)
            if sid in snippets:
                continue
            for field in (row.title, row.summary):
                term = find_term(field or "", terms)
                if term:
                    snippets[sid] = make_snippet(field, term)
                    break

    return snippets
