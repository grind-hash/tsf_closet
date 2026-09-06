"""セッション横断検索(session_search)。ギャラリーとキャラチャットが共用する。"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from gateway.databases.models import Conversation as ConversationORM
from gateway.databases.models import History as HistoryORM
from gateway.databases.models import PlaySummary as PlaySummaryORM
from gateway.databases.models import Session as SessionORM
from gateway.databases.models import User
from gateway.services.session_search import (
    escape_like,
    fetch_match_snippets,
    make_snippet,
    matching_session_ids_select,
    matching_session_ids_select_terms,
    search_terms,
    strip_quotes,
)


def test_escape_like_escapes_wildcards() -> None:
    assert escape_like("50%_a\\b") == "50\\%\\_a\\\\b"


def test_search_terms_strips_quotes_and_splits() -> None:
    assert strip_quotes(' "メイド服" ') == "メイド服"
    assert strip_quotes("「元々男だったのに」") == "元々男だったのに"
    assert search_terms('"元々男だったのに"') == ["元々男だったのに"]
    assert search_terms("メイド\u3000猫耳 メイド") == ["メイド", "猫耳"]
    assert search_terms("“a”, 'b'、 c") == ["a", "b", "c"]
    assert search_terms('""  「」') == []
    assert search_terms(None) == []
    assert search_terms("1 2 3 4 5 6 7", max_terms=3) == ["1", "2", "3"]


def test_make_snippet_centers_on_query() -> None:
    text = "a" * 50 + "メイド服" + "b" * 80
    snippet = make_snippet(text, "メイド服")
    assert snippet.startswith("…")
    assert snippet.endswith("…")
    assert "メイド服" in snippet
    assert make_snippet("short text", "zzz") == "short text"


async def _seed(factory) -> None:
    async with factory() as db:
        db.add(User(id="default-user"))
        for sid in ("s-hist", "s-conv", "s-sum", "s-none"):
            db.add(
                SessionORM(id=sid, user_id="default-user", current_image_path="x.png")
            )
        db.add(
            HistoryORM(
                id="h1",
                session_id="s-hist",
                instruction="メイド服に着替える",
                image_path="x.png",
                created_at=datetime(2026, 9, 1),
            )
        )
        db.add(
            ConversationORM(
                id="c1",
                session_id="s-conv",
                role="user",
                content="メイド服は似合う？",
                created_at=datetime(2026, 9, 2),
            )
        )
        db.add(
            PlaySummaryORM(
                session_id="s-sum",
                title="メイド服の一日",
                summary="給仕をした",
                timeline_json="[]",
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_matching_union_and_snippets(isolated_db) -> None:
    await _seed(isolated_db.async_factory)
    async with isolated_db.async_factory() as db:
        matching = matching_session_ids_select(f"%{escape_like('メイド服')}%")
        ids = {str(row[0]) for row in (await db.execute(matching)).all()}
        assert ids == {"s-hist", "s-conv", "s-sum"}
        snippets = await fetch_match_snippets(db, sorted(ids), "メイド服")
        assert snippets["s-conv"] == "メイド服は似合う？"
        assert "メイド服" in snippets["s-hist"]
        assert "メイド服" in snippets["s-sum"]
        rows = (await db.execute(select(SessionORM.id))).all()
        assert len(rows) == 4


@pytest.mark.asyncio
async def test_matching_terms_all_or_any(isolated_db) -> None:
    await _seed(isolated_db.async_factory)
    async with isolated_db.async_factory() as db:

        async def ids(terms, *, match_all):
            stmt = matching_session_ids_select_terms(terms, match_all=match_all)
            return {str(row[0]) for row in (await db.execute(stmt)).all()}

        assert await ids(["メイド服"], match_all=True) == {"s-hist", "s-conv", "s-sum"}
        # 同じセッション内の別の行・列で一致してもよい
        assert await ids(["メイド服", "似合う"], match_all=True) == {"s-conv"}
        assert await ids(["メイド服", "給仕"], match_all=True) == {"s-sum"}
        assert await ids(["似合う", "給仕"], match_all=True) == set()
        assert await ids(["似合う", "給仕"], match_all=False) == {"s-conv", "s-sum"}

        snippets = await fetch_match_snippets(
            db, ["s-hist", "s-conv", "s-sum"], ["給仕", "似合う"]
        )
        assert snippets == {"s-conv": "メイド服は似合う？", "s-sum": "給仕をした"}
    with pytest.raises(ValueError):
        matching_session_ids_select_terms([])
