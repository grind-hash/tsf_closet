"""Tests for parameter_change_log_repo helpers (spec 004 T011)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from gateway.databases.models import (
    History,
    ParameterChangeLog,
    User,
)
from gateway.databases.models import (
    Session as SessionORM,
)
from gateway.databases.parameter_change_log_repo import (
    fetch_change_logs_by_history,
    fetch_change_logs_by_session,
    insert_change_logs,
)


async def _seed_session_history(factory, *, session_id: str, history_id: str) -> None:
    async with factory() as db:
        db.add(User(id="user-1"))
        db.add(
            SessionORM(
                id=session_id,
                user_id="user-1",
                current_image_path="img/start.png",
                character_id="char-1",
            )
        )
        db.add(
            History(
                id=history_id,
                session_id=session_id,
                instruction="dress up",
                image_path="img/h1.png",
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_insert_change_logs_skips_zero_delta(isolated_db):
    factory = isolated_db.async_factory
    await _seed_session_history(factory, session_id="s1", history_id="h1")

    async with factory() as db:
        inserted = await insert_change_logs(
            db,
            session_id="s1",
            history_id="h1",
            stat_changes=[
                ("bloom", 0, 10, 10),
                ("shame", -3, 50, 47),
                ("adaptation", 0, 0, 0),
            ],
            reason="dress_up",
        )
        await db.commit()

    assert inserted == 1
    async with factory() as db:
        rows = (await db.execute(select(ParameterChangeLog))).scalars().all()
        assert len(rows) == 1
        assert rows[0].stat_name == "shame"
        assert rows[0].delta == -3
        assert rows[0].prev_value == 50
        assert rows[0].new_value == 47
        assert rows[0].reason == "dress_up"


@pytest.mark.asyncio
async def test_insert_change_logs_three_rows_when_all_nonzero(isolated_db):
    factory = isolated_db.async_factory
    await _seed_session_history(factory, session_id="s2", history_id="h2")

    async with factory() as db:
        inserted = await insert_change_logs(
            db,
            session_id="s2",
            history_id="h2",
            stat_changes=[
                ("bloom", 5, 10, 15),
                ("shame", -2, 50, 48),
                ("adaptation", 1, 0, 1),
            ],
            reason="action",
        )
        await db.commit()

    assert inserted == 3
    async with factory() as db:
        rows = await fetch_change_logs_by_history(db, "h2")
        assert [r.stat_name for r in rows] == ["bloom", "shame", "adaptation"]
        assert all(r.reason == "action" for r in rows)


@pytest.mark.asyncio
async def test_fetch_change_logs_ordered_by_created_at_then_id(isolated_db):
    factory = isolated_db.async_factory
    await _seed_session_history(factory, session_id="s3", history_id="h3")

    async with factory() as db:
        await insert_change_logs(
            db,
            session_id="s3",
            history_id="h3",
            stat_changes=[
                ("bloom", 1, 0, 1),
                ("shame", 2, 0, 2),
                ("adaptation", 3, 0, 3),
            ],
            reason="action",
        )
        await db.commit()

    async with factory() as db:
        by_history = await fetch_change_logs_by_history(db, "h3")
        by_session = await fetch_change_logs_by_session(db, "s3")

    history_ids = [r.id for r in by_history]
    assert history_ids == sorted(history_ids), "history fetch must be ASC"
    session_ids = [r.id for r in by_session]
    assert session_ids == sorted(session_ids), "session fetch must be ASC"
