"""Audit tests for parameter_change_log records (spec 004 T021, US3).

`(session_id, history_id)` 単位で監査クエリが期待通り動作することを検証する。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gateway.databases.base import Base
from gateway.databases.models import (
    History as HistoryORM,
    Session as SessionORM,
    User,
)
from gateway.databases.parameter_change_log_repo import (
    fetch_change_logs_by_history,
    insert_change_logs,
)


async def _setup(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'audit.db'}", future=True
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(User(id="u-audit"))
        db.add(
            SessionORM(
                id="s-audit",
                user_id="u-audit",
                current_image_path="img/x.png",
                character_id="c-audit",
            )
        )
        db.add(
            HistoryORM(
                id="h-audit",
                session_id="s-audit",
                instruction="audit",
                image_path="img/h.png",
            )
        )
        await db.commit()
    return factory


@pytest.mark.asyncio
async def test_audit_log_contains_all_fields_per_action(tmp_path: Path):
    factory = await _setup(tmp_path)

    async with factory() as db:
        await insert_change_logs(
            db,
            session_id="s-audit",
            history_id="h-audit",
            stat_changes=[
                ("bloom", 4, 10, 14),
                ("shame", -2, 50, 48),
                ("adaptation", 1, 0, 1),
            ],
            reason="reality_alter",
        )
        await db.commit()

    async with factory() as db:
        rows = await fetch_change_logs_by_history(db, "h-audit")

    assert len(rows) == 3
    for row in rows:
        # 全フィールドが揃っていること (FR-001)
        assert row.session_id == "s-audit"
        assert row.history_id == "h-audit"
        assert row.stat_name in {"bloom", "shame", "adaptation"}
        assert row.delta != 0  # delta=0 はそもそも記録されない
        assert isinstance(row.prev_value, int)
        assert isinstance(row.new_value, int)
        assert row.new_value - row.prev_value == row.delta
        assert row.reason == "reality_alter"
        assert row.created_at is not None
