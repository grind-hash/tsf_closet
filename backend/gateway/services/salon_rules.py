"""Pure rules of the salon management mode (サロン経営モード).

Payments, reputation, bookings, the weekly settlement, and the season result
are all decided here from the request foundation's satisfaction; the LLM never
writes a number. The salon service applies these to the database.
"""

from __future__ import annotations

import random
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from ..consts.salon import (
    SALON_BASE_PRICE,
    SALON_BOOKINGS_MAX,
    SALON_BOOKINGS_REPUTATION_STEP,
    SALON_GOOD_SATISFACTION,
    SALON_LOW_SATISFACTION,
    SALON_PRICE_RATE_FULFILLED,
    SALON_PRICE_RATE_LOW,
    SALON_PRICE_RATE_NORMAL,
    SALON_REPUTATION_DECLINED,
    SALON_REPUTATION_FULFILLED,
    SALON_REPUTATION_GOOD,
    SALON_REPUTATION_MAX,
    SALON_REPUTATION_MIN,
    SALON_REPUTATION_POOR,
    SALON_WEEKLY_FIXED_COST,
    SALON_WEEKLY_SALARY,
)


@dataclass(frozen=True)
class Customer:
    """予約に入るお客様。

    source は template(同梱キャラ) / custom(保存済みカスタムキャラ) /
    preset(キャラクター画面で作ったキャラ)。
    """

    source: str
    id: str
    name: str


def clamp_reputation(value: int) -> int:
    return max(SALON_REPUTATION_MIN, min(SALON_REPUTATION_MAX, int(value)))


def bookings_count(reputation: int) -> int:
    """その週に入る予約の数。評判が上がるほど増える(上限あり)。"""
    return min(
        SALON_BOOKINGS_MAX,
        1 + max(0, int(reputation)) // SALON_BOOKINGS_REPUTATION_STEP,
    )


def pick_customers(
    pool: list[Customer],
    *,
    seed: int,
    week: int,
    count: int,
    exclude: Collection[tuple[str, str]] = (),
) -> list[Customer]:
    """その週のお客様を選ぶ。同じ週に同じ人は来ない。seed と週が同じなら同じ結果になる。

    exclude は (source, id) で、既に予約が決まっているお客様(前回の姿のまま来る常連)。
    """
    candidates = [item for item in pool if (item.source, item.id) not in exclude]
    if count <= 0 or not candidates:
        return []
    rng = random.Random(f"{seed}:{week}")
    return rng.sample(candidates, min(count, len(candidates)))


def keeps_look(fulfilled: bool, week: int, total_weeks: int) -> bool:
    """願いを叶えたお客様は、施術した姿のまま翌週も来店する(最終週は翌週が無い)。"""
    return fulfilled and week < total_weeks


def visit_payment(satisfaction: int, fulfilled: bool) -> int:
    """会計の支払額。依頼達成はチップ込みの割増、満足度が低いと半額。"""
    if fulfilled:
        rate = SALON_PRICE_RATE_FULFILLED
    elif satisfaction < SALON_LOW_SATISFACTION:
        rate = SALON_PRICE_RATE_LOW
    else:
        rate = SALON_PRICE_RATE_NORMAL
    return int(round(SALON_BASE_PRICE * rate))


def visit_reputation_delta(satisfaction: int, fulfilled: bool) -> int:
    """会計で変わる評判。"""
    if fulfilled:
        return SALON_REPUTATION_FULFILLED
    if satisfaction >= SALON_GOOD_SATISFACTION:
        return SALON_REPUTATION_GOOD
    if satisfaction < SALON_LOW_SATISFACTION:
        return SALON_REPUTATION_POOR
    return 0


def declined_reputation_delta() -> int:
    return SALON_REPUTATION_DECLINED


def week_summary(
    *,
    week: int,
    cash_before_close: int,
    reputation: int,
    payments: list[int],
    served: int,
    declined: int,
    extra_costs: list[int] | None = None,
) -> dict[str, Any]:
    """週を締めたときの収支の記録。

    会計の売上は会計時に現金へ入り、追加施術の代金は購入時に現金から引いている。
    """
    cash_end = cash_before_close + SALON_WEEKLY_SALARY - SALON_WEEKLY_FIXED_COST
    return {
        "week": week,
        "revenue": sum(payments),
        "extra_cost": sum(extra_costs or []),
        "salary": SALON_WEEKLY_SALARY,
        "fixed_cost": SALON_WEEKLY_FIXED_COST,
        "served": served,
        "declined": declined,
        "cash_end": cash_end,
        "reputation_end": reputation,
    }


def season_result(cash: int, initial_cash: int) -> str:
    """決算。開業資金を上回れば成功、0 以上なら部分的な成功。"""
    if cash > initial_cash:
        return "success"
    if cash >= 0:
        return "partial"
    return "bankrupt"
