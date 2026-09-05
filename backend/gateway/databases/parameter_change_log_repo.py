"""ORM helpers for the parameter_change_log table (spec 004).

These helpers are intentionally low-level and do NOT commit; the caller
is responsible for committing the surrounding transaction.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ParameterChangeLog

# Public type alias used by callers.
StatChange = tuple[str, int, int, int]
"""(stat_name, delta, prev_value, new_value)."""


async def insert_change_logs(
    db: AsyncSession,
    *,
    session_id: str,
    history_id: str,
    stat_changes: Iterable[StatChange],
    reason: str | None,
) -> int:
    """Insert one row per non-zero delta.

    Args:
        db: Active AsyncSession (caller commits).
        session_id: Owning session id (FK).
        history_id: Owning history id (FK).
        stat_changes: Iterable of (stat_name, delta, prev_value, new_value).
        reason: Action type label (e.g. ``dress_up``, ``reality_alter``,
            ``action``) or None.

    Returns:
        Number of rows inserted (delta=0 entries are skipped).
    """
    rows: list[ParameterChangeLog] = []
    for stat_name, delta, prev_value, new_value in stat_changes:
        if delta == 0:
            continue
        rows.append(
            ParameterChangeLog(
                session_id=session_id,
                history_id=history_id,
                stat_name=stat_name,
                delta=int(delta),
                prev_value=int(prev_value),
                new_value=int(new_value),
                reason=reason,
            )
        )
    if not rows:
        return 0
    db.add_all(rows)
    await db.flush()
    return len(rows)


async def fetch_change_logs_by_history(
    db: AsyncSession,
    history_id: str,
) -> Sequence[ParameterChangeLog]:
    """Return all change-log rows for ``history_id`` ordered by created_at ASC."""
    stmt = (
        select(ParameterChangeLog)
        .where(ParameterChangeLog.history_id == history_id)
        .order_by(
            ParameterChangeLog.created_at.asc(),
            ParameterChangeLog.id.asc(),
        )
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def fetch_change_logs_by_session(
    db: AsyncSession,
    session_id: str,
) -> Sequence[ParameterChangeLog]:
    """Return all change-log rows for ``session_id`` ordered by created_at ASC."""
    stmt = (
        select(ParameterChangeLog)
        .where(ParameterChangeLog.session_id == session_id)
        .order_by(
            ParameterChangeLog.created_at.asc(),
            ParameterChangeLog.id.asc(),
        )
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def delete_change_logs_by_history(
    db: AsyncSession,
    history_id: str,
) -> int:
    """Delete all change-log rows for ``history_id``.

    Returns:
        Number of rows deleted.
    """
    stmt = sa_delete(ParameterChangeLog).where(
        ParameterChangeLog.history_id == history_id
    )
    result = await db.execute(stmt)
    return result.rowcount or 0


__all__ = [
    "StatChange",
    "delete_change_logs_by_history",
    "fetch_change_logs_by_history",
    "fetch_change_logs_by_session",
    "insert_change_logs",
]
