import random
from types import SimpleNamespace

import pytest

from gateway.consts.adventure_romance import (
    ROMANCE_AFFECTION_START,
    ROMANCE_CONFESSION_FAIL_PENALTY,
    ROMANCE_GIFT_POINTS,
    ROMANCE_INITIAL_MONEY,
    ROMANCE_MILESTONES,
    ROMANCE_WORK_ENCOUNTER_BONUS,
    ROMANCE_WORK_WAGE,
)
from gateway.services.adventure_romance import (
    RomanceActionError,
    RomanceGift,
    RomanceSetupOutput,
    apply_romance_outcome,
    clamp_romance_max_turns,
    init_romance_state,
    public_sim_view,
    resolve_romance_action,
    romance_day_slot,
    romance_stage,
)


def make_setup(**overrides) -> RomanceSetupOutput:
    payload = {
        "partner_name": "美咲",
        "partner_profile": "書店でよく会う穏やかな同級生。",
        "relationship_origin": "顔見知りの常連同士。",
        "job_name": "カフェ",
        "gift_catalog": [
            {"name": "花束", "price": 1500, "tier": "budget"},
            {"name": "文庫本", "price": 800, "tier": "budget"},
            {"name": "紅茶セット", "price": 3000, "tier": "standard"},
            {"name": "マフラー", "price": 4500, "tier": "standard"},
            {"name": "万年筆", "price": 5500, "tier": "standard"},
            {"name": "ぬいぐるみ", "price": 2500, "tier": "standard"},
            {"name": "香水", "price": 8000, "tier": "luxury"},
            {"name": "ネックレス", "price": 12000, "tier": "luxury"},
        ],
        "liked_gift_names": ["文庫本", "紅茶セット"],
        "disliked_gift_names": ["香水"],
        "likes_hint": "静かな時間の過ごし方に関心がある。",
        "dislikes_hint": "強い匂いは少し苦手らしい。",
    }
    payload.update(overrides)
    return RomanceSetupOutput.model_validate(payload)


def make_sim(**overrides) -> dict:
    sim = init_romance_state(make_setup(), 14, rng=random.Random(0))
    sim.update(overrides)
    return sim


def make_output() -> SimpleNamespace:
    return SimpleNamespace(
        completed_milestones=["fake_milestone"],
        ending_status="failure",
    )


def make_romance_output(**overrides) -> SimpleNamespace:
    payload = {
        "affection_delta": 0,
        "affection_set": None,
        "updated_liked_gift_ids": [],
        "updated_disliked_gift_ids": [],
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_day_slot_derivation_boundaries() -> None:
    assert romance_day_slot(1) == (1, "day")
    assert romance_day_slot(2) == (1, "night")
    assert romance_day_slot(3) == (2, "day")
    assert romance_day_slot(14) == (7, "night")


def test_clamp_romance_max_turns_bounds_and_evenness() -> None:
    assert clamp_romance_max_turns(9) == 10
    assert clamp_romance_max_turns(14) == 14
    assert clamp_romance_max_turns(15) == 14
    assert clamp_romance_max_turns(99) == 30


def test_stage_thresholds() -> None:
    assert romance_stage(24) == "stranger"
    assert romance_stage(25) == "friend"
    assert romance_stage(50) == "aware"
    assert romance_stage(74) == "aware"
    assert romance_stage(75) == "mutual"


def test_init_state_assigns_ids_and_matches_named_preferences() -> None:
    sim = make_sim()
    ids = [item["id"] for item in sim["gift_catalog"]]
    assert ids == [f"g{index}" for index in range(1, 9)]
    hidden = sim["hidden_preferences"]
    assert set(hidden["liked_gift_ids"]) == {"g2", "g3"}
    assert set(hidden["disliked_gift_ids"]) == {"g7"}
    assert sim["affection"] == ROMANCE_AFFECTION_START
    assert sim["money"] == ROMANCE_INITIAL_MONEY


def test_init_state_backfills_unmatched_preferences() -> None:
    setup = make_setup(liked_gift_names=["存在しない品"], disliked_gift_names=[])
    sim = init_romance_state(setup, 14, rng=random.Random(1))
    hidden = sim["hidden_preferences"]
    assert len(hidden["liked_gift_ids"]) == 2
    assert len(hidden["disliked_gift_ids"]) == 2
    assert not set(hidden["liked_gift_ids"]) & set(hidden["disliked_gift_ids"])


def test_init_state_keeps_partner_and_player_separated() -> None:
    sim = init_romance_state(
        make_setup(),
        14,
        rng=random.Random(0),
        partner_appearance="brown hair, school uniform",
        player_name="水瀬ユウヤ",
        player_character_id="char1",
    )
    assert sim["partner_appearance"] == "brown hair, school uniform"
    assert sim["player_name"] == "水瀬ユウヤ"
    assert sim["player_character_id"] == "char1"
    view = public_sim_view(sim, turn_count=0)
    assert view["player_name"] == "水瀬ユウヤ"
    assert view["player_character_id"] == "char1"
    # 隠し情報と内部プロフィールは公開ビューへ出さない
    assert "hidden_preferences" not in view
    assert "partner_profile" not in view


def test_work_resolution_pays_wage_and_seeds_encounter() -> None:
    sim = make_sim()
    hit = resolve_romance_action(
        sim,
        user_input="バイトに出る",
        input_kind="work",
        turn_number=1,
        total_turns=14,
        rng=random.Random(1),
    )
    assert hit["kind"] == "work"
    assert hit["money_delta"] == ROMANCE_WORK_WAGE
    assert hit["partner_encountered"] is True
    assert hit["affection_delta"] == ROMANCE_WORK_ENCOUNTER_BONUS
    miss = resolve_romance_action(
        sim,
        user_input="バイトに出る",
        input_kind="work",
        turn_number=2,
        total_turns=14,
        rng=random.Random(2),
    )
    assert miss["partner_encountered"] is False
    assert miss["affection_delta"] == 0


def test_gift_resolution_scores_by_tier_and_preference() -> None:
    sim = make_sim()
    liked = resolve_romance_action(
        sim,
        user_input="紅茶セットを贈る",
        input_kind="gift",
        gift_id="g3",
        turn_number=1,
        total_turns=14,
    )
    assert liked["preference_match"] == "liked"
    assert liked["affection_delta"] == ROMANCE_GIFT_POINTS["standard"]["liked"]
    assert liked["money_delta"] == -3000
    disliked = resolve_romance_action(
        make_sim(money=20000),
        user_input="香水を贈る",
        input_kind="gift",
        gift_id="g7",
        turn_number=1,
        total_turns=14,
    )
    assert disliked["preference_match"] == "disliked"
    assert disliked["affection_delta"] == ROMANCE_GIFT_POINTS["luxury"]["disliked"]


def test_gift_resolution_rejects_unknown_and_unaffordable() -> None:
    sim = make_sim()
    with pytest.raises(RomanceActionError) as unknown:
        resolve_romance_action(
            sim,
            user_input="謎の品を贈る",
            input_kind="gift",
            gift_id="g99",
            turn_number=1,
            total_turns=14,
        )
    assert unknown.value.code == "invalid_gift"
    with pytest.raises(RomanceActionError) as broke:
        resolve_romance_action(
            make_sim(money=100),
            user_input="ネックレスを贈る",
            input_kind="gift",
            gift_id="g8",
            turn_number=1,
            total_turns=14,
        )
    assert broke.value.code == "insufficient_funds"


def test_repeated_gift_decays_to_neutral() -> None:
    sim = make_sim(given_gifts=["g3"])
    repeated = resolve_romance_action(
        sim,
        user_input="また紅茶セットを贈る",
        input_kind="gift",
        gift_id="g3",
        turn_number=3,
        total_turns=14,
    )
    assert repeated["repeated_gift"] is True
    assert repeated["preference_match"] == "neutral"
    assert repeated["affection_delta"] == ROMANCE_GIFT_POINTS["standard"]["neutral"]


def test_confession_outcome_follows_threshold() -> None:
    success = resolve_romance_action(
        make_sim(affection=75),
        user_input="想いを告げる",
        input_kind="confess",
        turn_number=5,
        total_turns=14,
    )
    assert success["success"] is True
    assert success["affection_delta"] == 0
    failure = resolve_romance_action(
        make_sim(affection=74),
        user_input="想いを告げる",
        input_kind="confess",
        turn_number=5,
        total_turns=14,
    )
    assert failure["success"] is False
    assert failure["affection_delta"] == ROMANCE_CONFESSION_FAIL_PENALTY


def test_talk_turn_clamps_llm_delta_and_overrides_llm_claims() -> None:
    state = {"sim": make_sim(), "completed_milestones": []}
    output = make_output()
    apply_romance_outcome(
        state,
        output,
        {"kind": "talk", "money_delta": 0, "affection_delta": 0},
        make_romance_output(affection_delta=10, affection_set=100),
    )
    # クランプ ±3、affection_set は talk では無効、LLM 申告の milestone/ending は破棄
    assert state["sim"]["affection"] == ROMANCE_AFFECTION_START + 3
    assert output.completed_milestones == []
    assert output.ending_status == "continue"


def test_alter_turn_honors_affection_set_and_updates_preferences() -> None:
    state = {"sim": make_sim(), "completed_milestones": []}
    output = make_output()
    apply_romance_outcome(
        state,
        output,
        {"kind": "alter", "money_delta": 0, "affection_delta": 0},
        make_romance_output(
            affection_set=100,
            updated_liked_gift_ids=["g7", "g99"],
            updated_disliked_gift_ids=["g2", "g7"],
        ),
    )
    sim = state["sim"]
    assert sim["affection"] == 100
    hidden = sim["hidden_preferences"]
    # g7 は liked 優先で移動、g2 は disliked へ移動、未知 g99 は破棄
    assert "g7" in hidden["liked_gift_ids"]
    assert "g2" in hidden["disliked_gift_ids"]
    assert "g99" not in hidden["liked_gift_ids"]
    # 好感度 100 で段階マイルストーン3件が Python 算出で立つ
    assert set(output.completed_milestones) == {
        "become_friends",
        "mutual_interest",
        "mutual_love",
    }
    assert output.ending_status == "continue"


def test_alter_turn_without_set_clamps_wide_delta() -> None:
    state = {"sim": make_sim(), "completed_milestones": []}
    apply_romance_outcome(
        state,
        make_output(),
        {"kind": "alter", "money_delta": 0, "affection_delta": 0},
        make_romance_output(affection_delta=50),
    )
    assert state["sim"]["affection"] == ROMANCE_AFFECTION_START + 20


def test_gift_and_work_turns_apply_only_engine_numbers() -> None:
    state = {"sim": make_sim(), "completed_milestones": []}
    apply_romance_outcome(
        state,
        make_output(),
        {
            "kind": "gift",
            "money_delta": -3000,
            "affection_delta": 12,
            "gift": {"id": "g3"},
        },
        make_romance_output(affection_delta=3, affection_set=100),
    )
    sim = state["sim"]
    assert sim["affection"] == ROMANCE_AFFECTION_START + 12
    assert sim["money"] == ROMANCE_INITIAL_MONEY - 3000
    assert sim["given_gifts"] == ["g3"]


def test_successful_confession_completes_all_milestones() -> None:
    state = {"sim": make_sim(affection=80), "completed_milestones": []}
    output = make_output()
    apply_romance_outcome(
        state,
        output,
        {"kind": "confess", "success": True, "money_delta": 0, "affection_delta": 0},
        make_romance_output(),
    )
    assert state["sim"]["confessed"] is True
    assert output.completed_milestones == [item["id"] for item in ROMANCE_MILESTONES]
    assert output.ending_status == "success"


def test_public_view_hides_preferences_and_reports_next_slot() -> None:
    sim = make_sim(affection=80)
    view = public_sim_view(sim, turn_count=2)
    assert "hidden_preferences" not in view
    assert view["day"] == 2
    assert view["slot"] == "day"
    assert view["stage"] == "mutual"
    assert view["confession_available"] is True
    confessed = public_sim_view(make_sim(affection=80, confessed=True), turn_count=3)
    assert confessed["confession_available"] is False


def test_gift_price_clamped_into_tier_band() -> None:
    gift = RomanceGift.model_validate(
        {"name": "花束", "price": 30000, "tier": "budget"}
    )
    assert gift.price == 2000
    floor = RomanceGift.model_validate({"name": "香水", "price": 100, "tier": "luxury"})
    assert floor.price == 6001
