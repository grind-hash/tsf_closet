"""services/cost_tracker.py: コンテキスト単位の料金集計。"""

from __future__ import annotations

import asyncio
import contextvars

from gateway.services.cost_tracker import (
    begin_cost_tracking,
    current_cost_tracker,
    record_cost,
)


async def test_record_cost_is_a_noop_without_a_tracker():
    # 未設定のコンテキストで呼んでも落ちない
    ctx = contextvars.copy_context()
    ctx.run(record_cost, 1.5)
    assert ctx.run(current_cost_tracker) is None


async def test_costs_accumulate_and_ignore_none_or_zero():
    tracker = begin_cost_tracking()
    record_cost(0.25)
    record_cost(None)
    record_cost(0)
    record_cost(0.5)
    assert tracker.total_usd == 0.75
    assert current_cost_tracker() is tracker


async def test_costs_recorded_inside_tasks_reach_the_caller():
    tracker = begin_cost_tracking()

    async def producer(amount: float) -> None:
        record_cost(amount)

    await asyncio.gather(producer(0.1), asyncio.create_task(producer(0.2)))
    assert round(tracker.total_usd, 6) == 0.3


async def test_begin_replaces_the_tracker_for_the_current_context():
    first = begin_cost_tracking()
    record_cost(1.0)
    second = begin_cost_tracking()
    record_cost(2.0)
    assert (first.total_usd, second.total_usd) == (1.0, 2.0)
