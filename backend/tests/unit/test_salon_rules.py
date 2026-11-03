"""サロン経営モードの数値ルール(支払・評判・予約・週の締め・決算)。"""

from __future__ import annotations

import pytest

from gateway.consts.salon import (
    SALON_BASE_PRICE,
    SALON_BOOKINGS_MAX,
    SALON_REGULAR_FEE_MAX,
    SALON_REPUTATION_MAX,
    SALON_WEEKLY_FIXED_COST,
    SALON_WEEKLY_SALARY,
)
from gateway.services.salon_rules import (
    Customer,
    bookings_count,
    clamp_reputation,
    declined_reputation_delta,
    keeps_look,
    normalize_season_length,
    pick_customers,
    season_initial_cash,
    season_initial_reputation,
    season_result,
    season_weeks,
    visit_bill,
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


def test_pick_customers_skips_customers_already_booked() -> None:
    booked = {("template", "c0"), ("template", "c1")}
    picked = pick_customers(POOL, seed=42, week=3, count=4, exclude=booked)
    assert len(picked) == 4
    assert not booked & {(item.source, item.id) for item in picked}
    assert pick_customers(POOL[:2], seed=1, week=1, count=2, exclude=booked) == []


@pytest.mark.parametrize(
    ("fulfilled", "week", "expected"),
    [(True, 1, True), (True, 11, True), (True, 12, False), (False, 3, False)],
)
def test_customer_keeps_look_only_when_fulfilled_before_final_week(
    fulfilled, week, expected
) -> None:
    assert keeps_look(fulfilled, week, 12) is expected


def test_pick_customers_caps_at_pool_size_and_handles_empty() -> None:
    assert len(pick_customers(POOL[:2], seed=1, week=1, count=4)) == 2
    assert pick_customers([], seed=1, week=1, count=3) == []
    assert pick_customers(POOL, seed=1, week=1, count=0) == []


@pytest.mark.parametrize(
    ("satisfaction", "fulfilled", "rate"),
    [
        (100, True, 2.0),
        (99, True, 1.5),
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
    assert summary["extra_cost"] == 0
    assert summary["served"] == 2
    assert summary["declined"] == 1
    assert summary["reputation_end"] == 30


@pytest.mark.parametrize(
    ("cash", "outcome"),
    [(3_000_001, "success"), (3_000_000, "partial"), (0, "partial"), (-1, "bankrupt")],
)
def test_season_result(cash, outcome) -> None:
    assert season_result(cash, 3_000_000) == outcome


def test_visit_bill_adds_tip_and_regular_fee_only_when_fulfilled() -> None:
    bill = visit_bill(80, True, reputation=60, regular_visits=2)
    assert bill.course == 75_000
    assert bill.tip == 30_000
    assert bill.regular_fee == 20_000
    assert bill.total == 125_000
    # 指名料は上限で止まる
    assert (
        visit_bill(80, True, reputation=0, regular_visits=9).regular_fee
        == SALON_REGULAR_FEE_MAX
    )
    unmet = visit_bill(60, False, reputation=100, regular_visits=3)
    assert (unmet.course, unmet.tip, unmet.regular_fee) == (50_000, 0, 0)


@pytest.mark.parametrize(
    ("length", "weeks", "reputation", "bookings"),
    [("short", 4, 45, 2), ("standard", 12, 20, 1), ("unknown", 12, 20, 1)],
)
def test_season_length_sets_weeks_and_opening_reputation(
    length, weeks, reputation, bookings
) -> None:
    assert season_weeks(length) == weeks
    assert season_initial_reputation(length) == reputation
    assert bookings_count(season_initial_reputation(length)) == bookings
    assert normalize_season_length(length) in {"short", "standard"}


@pytest.mark.parametrize("length", ["short", "standard"])
def test_initial_cash_keeps_the_difficulty_meaning_for_each_length(length) -> None:
    """やさしいは接客しなくても倒産せず、ふつう・むずかしいは接客を怠ると倒産する。"""
    weekly_loss = SALON_WEEKLY_FIXED_COST - SALON_WEEKLY_SALARY
    season_loss = weekly_loss * season_weeks(length)
    assert season_initial_cash(length, "easy") >= season_loss
    assert season_initial_cash(length, "normal") < season_loss
    assert season_initial_cash(length, "hard") < season_initial_cash(length, "normal")


def _simulate(length: str, difficulty: str, satisfactions: list[int]) -> int | None:
    """毎回 satisfactions を順に繰り返して接客したときの期の黒字。倒産したら None。

    予約数・持ち越し・チップ・指名料・評判は本番と同じ純関数で回す(経済の回帰用)。
    """
    weeks = season_weeks(length)
    cash = start = season_initial_cash(length, difficulty)
    reputation = season_initial_reputation(length)
    kept: dict[int, int] = {}
    next_id = served = 0
    for week in range(1, weeks + 1):
        batch = list(kept.items())
        kept = {}
        for _ in range(max(0, bookings_count(reputation) - len(batch))):
            next_id += 1
            batch.append((next_id, 0))
        for customer, streak in batch:
            satisfaction = satisfactions[served % len(satisfactions)]
            served += 1
            fulfilled = satisfaction >= 70
            cash += visit_bill(
                satisfaction, fulfilled, reputation=reputation, regular_visits=streak
            ).total
            reputation = clamp_reputation(
                reputation + visit_reputation_delta(satisfaction, fulfilled)
            )
            if keeps_look(fulfilled, week, weeks):
                kept[customer] = streak + 1
        cash += SALON_WEEKLY_SALARY - SALON_WEEKLY_FIXED_COST
        if cash < 0:
            return None
    return cash - start


@pytest.mark.parametrize(
    ("length", "satisfactions", "low", "high"),
    [
        # 全員の願いを叶えると、12 週で 200 万円を超える(名店の上の実績に届く)
        ("standard", [80], 2_000_000, 4_000_000),
        # 満点・達成・未達が混ざる腕前: 100 万円台(200 万円には届かない)
        ("standard", [100, 80, 80, 60, 50], 1_000_000, 2_000_000),
        # 5 人に 2 人を叶える: 黒字だが 50 万円に届かない
        ("standard", [80, 60, 50, 80, 45], 300_000, 500_000),
        # 叶えられないと赤字
        ("standard", [60], -2_000_000, -1),
        ("short", [80], 500_000, 1_000_000),
        ("short", [80, 60, 50, 80, 45], 1, 300_000),
        ("short", [60], -1_000_000, -1),
    ],
)
def test_season_economy_regression(length, satisfactions, low, high) -> None:
    profit = _simulate(length, "normal", satisfactions)
    assert profit is not None
    assert low <= profit <= high


@pytest.mark.parametrize("length", ["short", "standard"])
def test_hard_goes_bankrupt_when_satisfaction_stays_around_fifty(length) -> None:
    assert _simulate(length, "hard", [50]) is None
    assert _simulate(length, "easy", [50]) is not None


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
    stats.salon_best_profit = 1_999_999
    assert check_achievement(ACHIEVEMENTS["salon_profit_100"], stats)
    assert not check_achievement(ACHIEVEMENTS["salon_profit_200"], stats)
