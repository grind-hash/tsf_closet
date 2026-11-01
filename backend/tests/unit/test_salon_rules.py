"""サロン経営モードの数値ルール(支払・評判・予約・週の締め・決算)。"""

from __future__ import annotations

import pytest

from gateway.consts.salon import (
    SALON_BASE_PRICE,
    SALON_BOOKINGS_MAX,
    SALON_REPUTATION_MAX,
    SALON_WEEKLY_FIXED_COST,
    SALON_WEEKLY_SALARY,
)
from gateway.services.salon_rules import (
    Customer,
    bookings_count,
    clamp_reputation,
    declined_reputation_delta,
    pick_customers,
    season_result,
    visit_payment,
    visit_reputation_delta,
    week_summary,
)

POOL = [Customer("template", f"c{index}", f"客{index}") for index in range(6)]


@pytest.mark.parametrize(
    ("reputation", "expected"),
    [(0, 1), (24, 1), (25, 2), (50, 3), (75, 4), (100, SALON_BOOKINGS_MAX), (-10, 1)],
)
def test_bookings_grow_with_reputation_up_to_cap(reputation, expected) -> None:
    assert bookings_count(reputation) == expected


def test_pick_customers_is_deterministic_per_week_without_duplicates() -> None:
    first = pick_customers(POOL, seed=42, week=3, count=4)
    assert first == pick_customers(POOL, seed=42, week=3, count=4)
    assert len(first) == 4
    assert len(set(first)) == 4


def test_pick_customers_caps_at_pool_size_and_handles_empty() -> None:
    assert len(pick_customers(POOL[:2], seed=1, week=1, count=4)) == 2
    assert pick_customers([], seed=1, week=1, count=3) == []
    assert pick_customers(POOL, seed=1, week=1, count=0) == []


@pytest.mark.parametrize(
    ("satisfaction", "fulfilled", "rate"),
    [
        (100, True, 1.5),
        (70, True, 1.5),
        (60, False, 1.0),
        (40, False, 1.0),
        (39, False, 0.5),
    ],
)
def test_visit_payment_bands(satisfaction, fulfilled, rate) -> None:
    assert visit_payment(satisfaction, fulfilled) == int(SALON_BASE_PRICE * rate)


@pytest.mark.parametrize(
    ("satisfaction", "fulfilled", "delta"),
    [
        (80, True, 8),
        (60, False, 3),
        (55, False, 3),
        (54, False, 0),
        (40, False, 0),
        (39, False, -5),
    ],
)
def test_visit_reputation_delta_bands(satisfaction, fulfilled, delta) -> None:
    assert visit_reputation_delta(satisfaction, fulfilled) == delta


def test_declined_lowers_reputation() -> None:
    assert declined_reputation_delta() < 0


def test_clamp_reputation_bounds() -> None:
    assert clamp_reputation(-3) == 0
    assert clamp_reputation(SALON_REPUTATION_MAX + 5) == SALON_REPUTATION_MAX
    assert clamp_reputation(42) == 42


def test_week_summary_applies_salary_and_fixed_cost_only() -> None:
    summary = week_summary(
        week=2,
        cash_before_close=1_000_000,
        reputation=30,
        payments=[50_000, 75_000],
        served=2,
        declined=1,
    )
    # 会計の売上は会計時に現金へ入っているため、締めでは足さない
    assert summary["cash_end"] == (
        1_000_000 + SALON_WEEKLY_SALARY - SALON_WEEKLY_FIXED_COST
    )
    assert summary["revenue"] == 125_000
    assert summary["served"] == 2
    assert summary["declined"] == 1
    assert summary["reputation_end"] == 30


@pytest.mark.parametrize(
    ("cash", "outcome"),
    [(3_000_001, "success"), (3_000_000, "partial"), (0, "partial"), (-1, "bankrupt")],
)
def test_season_result(cash, outcome) -> None:
    assert season_result(cash, 3_000_000) == outcome


def test_salon_achievement_conditions() -> None:
    from gateway.services.achievements import (
        ACHIEVEMENTS,
        AchievementStats,
        check_achievement,
    )

    stats = AchievementStats(
        salon_completed_count=1, salon_success_count=1, salon_best_profit=299_999
    )
    assert check_achievement(ACHIEVEMENTS["salon_first_season"], stats)
    assert check_achievement(ACHIEVEMENTS["salon_success"], stats)
    assert not check_achievement(ACHIEVEMENTS["salon_success_hard"], stats)
    assert not check_achievement(ACHIEVEMENTS["salon_profit_30"], stats)
    stats.salon_best_profit = 300_000
    assert check_achievement(ACHIEVEMENTS["salon_profit_30"], stats)
    assert not check_achievement(ACHIEVEMENTS["salon_profit_50"], stats)
