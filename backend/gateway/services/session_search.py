"""セッション横断のフリーワード検索。

ギャラリーの検索とキャラチャットの「過去のやり取りを調べる」が共用する。
History の指示・心境・前後記述、Conversation の本文、PlaySummary の
称号・要約を LIKE で当て、セッションごとの代表スニペットを返す。
"""

from __future__ import annotations

from sqlalchemy import desc, or_, select

from ..databases.models import Conversation as ConversationORM
from ..databases.models import History as HistoryORM
from ..databases.models import PlaySummary as PlaySummaryORM


def escape_like(value: str) -> str:
    """LIKE パターン用に % / _ / \\ をエスケープする"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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


async def fetch_match_snippets(
    db_session,
    session_ids: list[str],
    query: str,
) -> dict[str, str]:
    """セッションごとの代表的なマッチ箇所を取得する（会話を優先）"""
    if not session_ids or not query:
        return {}

    pattern = f"%{escape_like(query)}%"
    snippets: dict[str, str] = {}

    conv_rows = (
        await db_session.execute(
            select(ConversationORM.session_id, ConversationORM.content)
            .where(
                ConversationORM.session_id.in_(session_ids),
                ConversationORM.content.like(pattern, escape="\\"),
            )
            .order_by(desc(ConversationORM.created_at))
        )
    ).all()
    for session_id, content in conv_rows:
        sid = str(session_id)
        if sid not in snippets and content:
            snippets[sid] = make_snippet(content, query)

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
                        HistoryORM.instruction.like(pattern, escape="\\"),
                        HistoryORM.feeling_text.like(pattern, escape="\\"),
                        HistoryORM.before_description.like(pattern, escape="\\"),
                        HistoryORM.after_description.like(pattern, escape="\\"),
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
                if field and (query.lower() in field.lower() or query in field):
                    snippets[sid] = make_snippet(field, query)
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
                        PlaySummaryORM.title.like(pattern, escape="\\"),
                        PlaySummaryORM.summary.like(pattern, escape="\\"),
                    ),
                )
            )
        ).all()
        for row in summary_rows:
            sid = str(row.session_id)
            if sid in snippets:
                continue
            for field in (row.title, row.summary):
                if field and (query.lower() in field.lower() or query in field):
                    snippets[sid] = make_snippet(field, query)
                    break

    return snippets
