"""TSF Bloomer サービス層のユニットテスト。

DB を使わずに純粋関数をテストする。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from gateway.consts.bloomer_consts import (
    AXIS_KEYS,
    INITIAL_OUTFITS,
    MAX_DAYS,
    NSFW_STAGE_TRUST_THRESHOLDS,
    REFUSAL_MIN,
    STAGE_REQUIREMENTS,
)
from gateway.services.bloomer_service import (
    BloomerService,
    _clamp,
    _determine_ending_key,
    _growth_factor,
    _load_json,
)


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _axes(
    allure=50, technique=50, depravity=50, sensitivity=50, endurance=50, composure=50
):
    return {
        "allure": allure,
        "technique": technique,
        "depravity": depravity,
        "sensitivity": sensitivity,
        "endurance": endurance,
        "composure": composure,
    }


def _make_run(
    *,
    trust=50,
    mood=60,
    stamina=100,
    stage=0,
    nsfw_stage=0,
    day=1,
    axes=None,
    growth=None,
    decisions=None,
    status="active",
    ending_key=None,
    equipped_outfit="plain_dress",
    wardrobe=None,
    actions_left=4,
):
    axes = axes or _axes()
    growth = growth or {k: 0 for k in AXIS_KEYS}
    decisions = decisions or {}
    wardrobe = wardrobe or list(INITIAL_OUTFITS)
    return SimpleNamespace(
        id="run-test",
        user_id="test-user",
        trust=trust,
        mood=mood,
        stamina=stamina,
        stage=stage,
        nsfw_stage=nsfw_stage,
        day=day,
        max_days=MAX_DAYS,
        actions_left=actions_left,
        status=status,
        ending_key=ending_key,
        equipped_outfit=equipped_outfit,
        wardrobe_json=json.dumps(wardrobe),
        axes_json=json.dumps(axes),
        growth_json=json.dumps(growth),
        decisions_json=json.dumps(decisions),
        events=[],
    )


# ---------------------------------------------------------------------------
# _clamp
# ---------------------------------------------------------------------------


def test_clamp_within_range():
    assert _clamp(50) == 50


def test_clamp_lower():
    assert _clamp(-10) == 0


def test_clamp_upper():
    assert _clamp(110) == 100


def test_clamp_custom_range():
    assert _clamp(150, 0, 200) == 150


# ---------------------------------------------------------------------------
# _growth_factor
# ---------------------------------------------------------------------------


def test_growth_factor_low_aptitude_low_current():
    # 素質 1、現在値 1 → ほぼ GROWTH_APTITUDE_FLOOR
    f = _growth_factor(1, 1)
    assert 0.4 < f < 0.7


def test_growth_factor_high_aptitude_low_current():
    # 素質 100、現在値 1 → 高め
    f = _growth_factor(100, 1)
    assert f > 1.0


def test_growth_factor_high_aptitude_high_current():
    # 素質 100、現在値 99 → 上限に近いので逓減
    f_high_current = _growth_factor(100, 99)
    f_low_current = _growth_factor(100, 1)
    assert f_high_current < f_low_current


def test_growth_factor_never_negative():
    for apt in (0, 1, 50, 100):
        for cur in (0, 50, 99, 100):
            assert _growth_factor(apt, cur) > 0


# ---------------------------------------------------------------------------
# BloomerService._check_stage_up
# ---------------------------------------------------------------------------

_service = BloomerService.__new__(BloomerService)


def test_stage_up_returns_none_when_conditions_not_met():
    run = _make_run(trust=0, stage=0, day=1, axes=_axes())
    # axis_total = 300 以下 → ステージアップしない
    assert _service._check_stage_up(run) is None


def test_stage_up_to_stage_1():
    req = STAGE_REQUIREMENTS[0]
    run = _make_run(
        trust=req["trust"],
        stage=0,
        day=req["day"],
        axes=_axes(**{k: req["axis_total"] // len(AXIS_KEYS) + 5 for k in AXIS_KEYS}),
    )
    result = _service._check_stage_up(run)
    assert result == 1


def test_stage_up_skips_already_achieved_stage():
    req = STAGE_REQUIREMENTS[0]
    run = _make_run(
        trust=req["trust"],
        stage=1,  # すでにステージ 1
        day=req["day"],
        axes=_axes(**{k: 55 for k in AXIS_KEYS}),
    )
    result = _service._check_stage_up(run)
    # ステージ 1 は飛ばして 2 以上を確認する（条件不足なら None）
    assert result != 1


# ---------------------------------------------------------------------------
# BloomerService._update_nsfw_stage
# ---------------------------------------------------------------------------


def test_nsfw_stage_0_below_first_threshold():
    run = _make_run(trust=NSFW_STAGE_TRUST_THRESHOLDS[0] - 1)
    _service._update_nsfw_stage(run)
    assert run.nsfw_stage == 0


def test_nsfw_stage_1_at_first_threshold():
    run = _make_run(trust=NSFW_STAGE_TRUST_THRESHOLDS[0])
    _service._update_nsfw_stage(run)
    assert run.nsfw_stage == 1


def test_nsfw_stage_max_at_all_thresholds():
    run = _make_run(trust=100)
    _service._update_nsfw_stage(run)
    assert run.nsfw_stage == len(NSFW_STAGE_TRUST_THRESHOLDS)


# ---------------------------------------------------------------------------
# BloomerService._roll_refusal
# ---------------------------------------------------------------------------


def _make_action_def(req_mood=0, req_trust=0, req_nsfw_stage=0):
    return {
        "kind": "care",
        "stamina": 0,
        "mood": 0,
        "trust": 0,
        "axes": {},
        "req_mood": req_mood,
        "req_trust": req_trust,
        "req_nsfw_stage": req_nsfw_stage,
        "narrate": False,
        "once_per_day": False,
    }


def test_refusal_chance_minimum_when_mood_matches():
    # mood == req_mood → gap=0 → chance = REFUSAL_BASE (最低値)
    run = _make_run(mood=30, stamina=100)
    action_def = _make_action_def(req_mood=30)
    # 100 回試行して常に [REFUSAL_MIN, REFUSAL_BASE + epsilon] の範囲内
    import random

    random.seed(42)
    refusals = sum(_service._roll_refusal(run, action_def) for _ in range(200))
    # REFUSAL_BASE=0.15 なので約 30 回 (±20) になるはず
    assert 10 <= refusals <= 60


def test_refusal_never_below_minimum():
    run = _make_run(mood=100, stamina=100)
    action_def = _make_action_def(req_mood=0)
    # chance = max(REFUSAL_MIN, ...) なので常に >= REFUSAL_MIN
    # random が REFUSAL_MIN - 0.001 を返せば < chance → 拒否 True
    with patch("gateway.services.bloomer_service.random") as mock_random:
        mock_random.random.return_value = REFUSAL_MIN - 0.001
        result = _service._roll_refusal(run, action_def)
        assert result is True


def test_refusal_always_true_at_max():
    # chance = REFUSAL_MAX → random < REFUSAL_MAX は常に True (random=0)
    run = _make_run(mood=0, stamina=0)
    action_def = _make_action_def(req_mood=100)
    with patch("gateway.services.bloomer_service.random") as mock_random:
        mock_random.random.return_value = 0.0
        result = _service._roll_refusal(run, action_def)
        assert result is True


# ---------------------------------------------------------------------------
# BloomerService._apply_effects
# ---------------------------------------------------------------------------


def test_apply_effects_basic():
    run = _make_run(mood=50, stamina=50, trust=10)
    action_def = {
        "kind": "care",
        "stamina": 20,
        "mood": 10,
        "trust": 5,
        "axes": {},
        "req_mood": 0,
        "req_trust": 0,
        "req_nsfw_stage": 0,
        "narrate": False,
        "once_per_day": False,
    }
    _service._apply_effects(run, action_def)
    assert run.stamina == 70
    assert run.mood == 60
    assert run.trust == 15


def test_apply_effects_clamped_at_100():
    run = _make_run(mood=95, stamina=90, trust=98)
    action_def = {
        "kind": "care",
        "stamina": 50,
        "mood": 20,
        "trust": 10,
        "axes": {},
        "req_mood": 0,
        "req_trust": 0,
        "req_nsfw_stage": 0,
        "narrate": False,
        "once_per_day": False,
    }
    _service._apply_effects(run, action_def)
    assert run.stamina == 100
    assert run.mood == 100
    assert run.trust == 100


def test_apply_effects_clamped_at_0():
    run = _make_run(mood=5, stamina=10, trust=3)
    action_def = {
        "kind": "care",
        "stamina": -50,
        "mood": -20,
        "trust": -10,
        "axes": {},
        "req_mood": 0,
        "req_trust": 0,
        "req_nsfw_stage": 0,
        "narrate": False,
        "once_per_day": False,
    }
    _service._apply_effects(run, action_def)
    assert run.stamina == 0
    assert run.mood == 0
    assert run.trust == 0


def test_apply_effects_axis_growth():
    run = _make_run(axes=_axes(allure=50), growth={k: 0 for k in AXIS_KEYS})
    action_def = {
        "kind": "train",
        "stamina": 0,
        "mood": 0,
        "trust": 0,
        "axes": {"allure": 6},
        "req_mood": 0,
        "req_trust": 0,
        "req_nsfw_stage": 0,
        "narrate": False,
        "once_per_day": False,
    }
    _service._apply_effects(run, action_def)
    growth = _load_json(run.growth_json, {})
    assert growth.get("allure", 0) > 0


def test_apply_effects_axis_growth_clamped():
    # 素質が 100、成長が既に 50 → allure 上限 100 を超えない
    run = _make_run(
        axes=_axes(allure=100), growth={**{k: 0 for k in AXIS_KEYS}, "allure": 0}
    )
    action_def = {
        "kind": "train",
        "stamina": 0,
        "mood": 0,
        "trust": 0,
        "axes": {"allure": 200},  # 大きな値を入れても上限を超えない
        "req_mood": 0,
        "req_trust": 0,
        "req_nsfw_stage": 0,
        "narrate": False,
        "once_per_day": False,
    }
    _service._apply_effects(run, action_def)
    growth = _load_json(run.growth_json, {})
    assert growth.get("allure", 0) <= 0  # axes=100 なので growth 余地=0


# ---------------------------------------------------------------------------
# _determine_ending_key (決定論的)
# ---------------------------------------------------------------------------


def test_ending_quiet_bloom_high_trust_stage4():
    run = _make_run(trust=80, stage=4, nsfw_stage=1, decisions={"6": "kept"})
    key = _determine_ending_key(run)
    assert key == "quiet_bloom"


def test_ending_blooming_free_freed_flag():
    run = _make_run(trust=80, stage=4, nsfw_stage=1, decisions={"6": "freed"})
    key = _determine_ending_key(run)
    assert key == "blooming_free"


def test_ending_devoted_descent_nsfw3():
    run = _make_run(trust=80, stage=4, nsfw_stage=3, decisions={"6": "descended"})
    key = _determine_ending_key(run)
    assert key == "devoted_descent"


def test_ending_unresponsive_low_trust():
    run = _make_run(trust=5, stage=0)
    key = _determine_ending_key(run)
    assert key == "unresponsive_end"


def test_ending_sheltered_bud():
    run = _make_run(trust=30, stage=2, decisions={"2": "sheltered"})
    key = _determine_ending_key(run)
    assert key == "sheltered_bud"


def test_ending_self_made_driven_technique():
    run = _make_run(
        trust=55,
        stage=3,
        decisions={"2": "driven"},
        axes=_axes(technique=80),
    )
    key = _determine_ending_key(run)
    assert key == "self_made"


def test_ending_determinism():
    # 同じ入力は常に同じキーを返す
    run1 = _make_run(trust=80, stage=4, decisions={"6": "kept"})
    run2 = _make_run(trust=80, stage=4, decisions={"6": "kept"})
    assert _determine_ending_key(run1) == _determine_ending_key(run2)


# ---------------------------------------------------------------------------
# BloomerService._check_action_requirements
# ---------------------------------------------------------------------------


def test_action_requirement_mood_too_low():
    from gateway.services.bloomer_service import BloomerError

    run = _make_run(mood=20, trust=50, nsfw_stage=0)
    action_def = _make_action_def(req_mood=40)
    with pytest.raises(BloomerError) as exc_info:
        _service._check_action_requirements(run, "some_action", action_def)
    assert exc_info.value.code == "mood_too_low"


def test_action_requirement_trust_too_low():
    from gateway.services.bloomer_service import BloomerError

    run = _make_run(mood=80, trust=5, nsfw_stage=0)
    action_def = _make_action_def(req_trust=20)
    with pytest.raises(BloomerError) as exc_info:
        _service._check_action_requirements(run, "some_action", action_def)
    assert exc_info.value.code == "trust_too_low"


def test_action_requirement_nsfw_locked():
    from gateway.services.bloomer_service import BloomerError

    run = _make_run(mood=80, trust=80, nsfw_stage=0)
    action_def = _make_action_def(req_nsfw_stage=1)
    with pytest.raises(BloomerError) as exc_info:
        _service._check_action_requirements(run, "indulge_tease", action_def)
    assert exc_info.value.code == "nsfw_locked"


def test_action_requirement_passes():
    run = _make_run(mood=60, trust=40, nsfw_stage=2)
    action_def = _make_action_def(req_mood=40, req_trust=30, req_nsfw_stage=1)
    _service._check_action_requirements(run, "indulge_devote", action_def)  # 例外なし


# ---------------------------------------------------------------------------
# BloomerService._unlock_outfits
# ---------------------------------------------------------------------------


def test_unlock_outfits_stage1():
    run = _make_run(wardrobe=list(INITIAL_OUTFITS))
    _service._unlock_outfits(run, 1)
    wardrobe = _load_json(run.wardrobe_json, [])
    assert "frilled_blouse" in wardrobe


def test_unlock_outfits_no_duplicates():
    run = _make_run(wardrobe=["frilled_blouse", *INITIAL_OUTFITS])
    _service._unlock_outfits(run, 1)
    wardrobe = _load_json(run.wardrobe_json, [])
    assert wardrobe.count("frilled_blouse") == 1


# ---------------------------------------------------------------------------
# BloomerService._images_dir 初期化
# ---------------------------------------------------------------------------


def test_service_init_creates_images_dir(tmp_path):
    with patch("gateway.services.bloomer_service.settings") as mock_settings:
        mock_settings.history_images_dir.parent = tmp_path
        BloomerService()
        assert (tmp_path / "bloomer_images").is_dir()
