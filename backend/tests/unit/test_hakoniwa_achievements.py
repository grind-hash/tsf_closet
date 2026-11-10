"""AI箱庭の観察記録(実績): 観測の事実の記録と、すべての世界を通した判定。"""

from __future__ import annotations

import random

from gateway.services import hakoniwa_logic as logic
from gateway.services import hakoniwa_play as play
from gateway.services.achievements import (
    ACHIEVEMENTS,
    HAKONIWA_ACHIEVEMENTS,
    AchievementStats,
    check_achievement,
)


def _world(ids=("aoi", "ren")):
    return logic.new_world_state([logic.preset_resident(pid) for pid in ids])


def test_observations_keep_what_was_seen_after_the_state_changes():
    state = _world()
    state = play.observe(logic.set_rule(state, "dress", True, random.Random(0)))
    state = play.observe(logic.set_rule(state, "swap", True, random.Random(0)))
    state = play.observe({**state, "dissonance": 35})
    state = logic.set_rule(state, "dress", False, random.Random(0))
    state = logic.set_rule(state, "swap", False, random.Random(0))
    state = play.observe({**state, "dissonance": 10})
    observed = state["observations"]
    assert observed["rules_seen"] == ["dress", "swap"]
    assert observed["dress_seen"] == ["aoi", "ren"]
    assert observed["swap_seen"] is True
    assert observed["dissonance_max"] == 35
    # 正規化しても残る
    assert logic.normalize_state(state)["observations"] == observed


def test_hakoniwa_achievements_are_seventeen_without_id_clashes():
    assert len(HAKONIWA_ACHIEVEMENTS) == 17
    assert all(item.id.startswith("hakoniwa_") for item in HAKONIWA_ACHIEVEMENTS)
    assert all(ACHIEVEMENTS[item.id] is item for item in HAKONIWA_ACHIEVEMENTS)
    # 既存の実績(通常プレイの「初めての変身」)は上書きしない
    assert ACHIEVEMENTS["first_transform"].category == "transform"


def test_hakoniwa_conditions():
    stats = AchievementStats(
        hakoniwa_max_day=7,
        hakoniwa_event_count=12,
        hakoniwa_transform_count=1,
        hakoniwa_max_affinity=30,
        hakoniwa_max_dissonance=49,
        hakoniwa_world_count=1,
        hakoniwa_swap=True,
    )
    unlocked = {
        item.id for item in HAKONIWA_ACHIEVEMENTS if check_achievement(item, stats)
    }
    assert unlocked == {
        "hakoniwa_first_day",
        "hakoniwa_day_7",
        "hakoniwa_events_10",
        "hakoniwa_first_transform",
        "hakoniwa_affinity_close",
        "hakoniwa_dissonance_stirring",
        "hakoniwa_swap",
    }


def test_stats_read_current_state_of_worlds_saved_before_observations(isolated_db):
    import json
    from datetime import datetime

    from gateway.databases.models import HakoniwaWorld, User
    from gateway.services.achievement_service import achievement_service
    from gateway.services.session import DEFAULT_USER_ID

    state = logic.set_rule(_world(), "swap", True, random.Random(0))
    state.pop("observations", None)
    with isolated_db.sync_factory() as db:
        db.add(User(id=DEFAULT_USER_ID))
        db.commit()
        db.add(
            HakoniwaWorld(
                id="old-world",
                user_id=DEFAULT_USER_ID,
                name="古い世界",
                day=3,
                state_json=json.dumps({**state, "day": 3}, ensure_ascii=False),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
        db.commit()
        stats = achievement_service._hakoniwa_stats(db)
    assert stats["hakoniwa_swap"] is True
    assert stats["hakoniwa_max_day"] == 3
    assert stats["hakoniwa_world_count"] == 1
