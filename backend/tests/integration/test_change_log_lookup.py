"""Index lookup verification for parameter_change_log (spec 004 T022, US3).

`PRAGMA index_list` および `EXPLAIN QUERY PLAN` で
`idx_pcl_history_id` がヒットすることを aiosqlite 経由で確認する統合テスト。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from gateway.databases.models import (
    History as HistoryORM,
)
from gateway.databases.models import (
    Session as SessionORM,
)
from gateway.databases.models import (
    User,
)
from gateway.databases.parameter_change_log_repo import (
    fetch_change_logs_by_history,
    fetch_change_logs_by_session,
    insert_change_logs,
)


async def _setup(factory):
    async with factory() as db:
        db.add(User(id="u-idx"))
        db.add(
            SessionORM(
                id="s-idx",
                user_id="u-idx",
                current_image_path="img/x.png",
                character_id="c-idx",
            )
        )
        db.add(
            HistoryORM(
                id="h-idx",
                session_id="s-idx",
                instruction="idx",
                image_path="img/h.png",
            )
        )
        await db.commit()

    async with factory() as db:
        await insert_change_logs(
            db,
            session_id="s-idx",
            history_id="h-idx",
            stat_changes=[("bloom", 1, 0, 1)],
            reason="action",
        )
        await db.commit()
    return factory


@pytest.mark.asyncio
async def test_pragma_index_list_contains_pcl_indexes(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        result = await db.execute(text("PRAGMA index_list('parameter_change_log')"))
        indexes = {row[1] for row in result.all()}
    assert "idx_pcl_history_id" in indexes
    assert "idx_pcl_session_id" in indexes


@pytest.mark.asyncio
async def test_query_plan_uses_history_index(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        plan = await db.execute(
            text(
                "EXPLAIN QUERY PLAN "
                "SELECT * FROM parameter_change_log WHERE history_id = 'h-idx'"
            )
        )
        plan_text = " ".join(str(row) for row in plan.all())
    assert "idx_pcl_history_id" in plan_text


@pytest.mark.asyncio
async def test_fetch_by_session_and_by_history_return_same_row(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        by_history = await fetch_change_logs_by_history(db, "h-idx")
        by_session = await fetch_change_logs_by_session(db, "s-idx")
    assert len(by_history) == 1
    assert len(by_session) == 1
    assert by_history[0].id == by_session[0].id
