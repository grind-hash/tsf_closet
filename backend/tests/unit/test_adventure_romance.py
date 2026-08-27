import random
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from gateway.consts.adventure_romance import (
    ROMANCE_AFFECTION_START,
    ROMANCE_ALTER_MONEY_LIMIT,
    ROMANCE_CONFESSION_FAIL_PENALTY,
    ROMANCE_DAYS_MAX,
    ROMANCE_GIFT_POINTS,
    ROMANCE_INITIAL_MONEY,
    ROMANCE_MILESTONES,
    ROMANCE_MONEY_MAX,
    ROMANCE_SLOTS_PER_DAY,
    ROMANCE_WORK_ENCOUNTER_BONUS,
    ROMANCE_WORK_WAGE,
)
from gateway.routes.adventure_router import (
    AdventureCreateRequest,
    AdventureSetupGenerateRequest,
)
from gateway.services.adventure_romance import (
    ROMANCE_NARRATIVE_GUIDANCE,
    ROMANCE_RESOLUTION_GUIDANCE,
    ROMANCE_VISUAL_GUIDANCE,
    RomanceActionError,
    RomanceAlteredGift,
    RomanceGift,
    RomanceSetupOutput,
    apply_romance_outcome,
    apply_romance_time_of_day,
    clamp_romance_max_turns,
    init_romance_state,
    public_sim_view,
    resolve_romance_action,
    romance_confession_threshold,
    romance_day_slot,
    romance_stage,
    strip_duplicate_action_choices,
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
        "money_delta": 0,
        "money_set": None,
        "start_dating": False,
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
    assert clamp_romance_max_turns(99) == ROMANCE_DAYS_MAX * ROMANCE_SLOTS_PER_DAY
    assert clamp_romance_max_turns(ROMANCE_DAYS_MAX * ROMANCE_SLOTS_PER_DAY) == 60


def test_request_models_accept_max_romance_days_as_turns() -> None:
    # 恋愛シミュレーションは日数×2 を scenario_max_turns として送るため、
    # 最大日数(30日=60手)がルーターのバリデーションを通る必要がある
    max_turns = ROMANCE_DAYS_MAX * ROMANCE_SLOTS_PER_DAY
    assert max_turns == 60
    create = AdventureCreateRequest(
        preset="romance",
        source_session_id="session-1",
        scenario_max_turns=max_turns,
    )
    assert create.scenario_max_turns == max_turns
    setup = AdventureSetupGenerateRequest(
        preset="romance",
        source_session_id="session-1",
        scenario_max_turns=max_turns,
    )
    assert setup.scenario_max_turns == max_turns
    with pytest.raises(ValidationError):
        AdventureCreateRequest(
            preset="romance",
            source_session_id="session-1",
            scenario_max_turns=max_turns + 1,
        )


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


def test_init_state_takes_partner_speech_style_from_the_generated_setup() -> None:
    sim = init_romance_state(
        make_setup(partner_speech_style="ため口。語尾を伸ばすギャル口調。"),
        14,
        rng=random.Random(0),
    )
    assert sim["partner_speech_style"] == "ため口。語尾を伸ばすギャル口調。"
    # 主人公の口調表示と対にして並べるため、公開ビューへは出す
    assert (
        public_sim_view(sim, turn_count=0)["partner_speech_style"]
        == "ため口。語尾を伸ばすギャル口調。"
    )


def test_user_written_partner_speech_style_wins_over_the_generated_one() -> None:
    sim = init_romance_state(
        make_setup(partner_speech_style="丁寧語で話す。"),
        14,
        rng=random.Random(0),
        partner_speech_style="ため口で話す。",
    )
    assert sim["partner_speech_style"] == "ため口で話す。"


def test_partner_speech_style_is_optional_for_legacy_setups() -> None:
    sim = init_romance_state(make_setup(), 14, rng=random.Random(0))
    assert sim["partner_speech_style"] == ""


def test_narrative_guidance_pins_the_partner_register() -> None:
    from gateway.services.adventure_romance import ROMANCE_NARRATIVE_GUIDANCE

    assert "state.sim.partner_speech_style" in ROMANCE_NARRATIVE_GUIDANCE
    assert "never drifts toward the player's" in ROMANCE_NARRATIVE_GUIDANCE


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
    assert hit["next_slot"] == "night"
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


def test_resolution_reports_next_slot_including_epilogue_rollover() -> None:
    sim = make_sim()

    def resolve(turn_number: int) -> dict:
        return resolve_romance_action(
            sim,
            user_input="挨拶する",
            input_kind="free_text",
            turn_number=turn_number,
            total_turns=14,
            rng=random.Random(0),
        )

    first = resolve(1)
    assert (first["day"], first["slot"]) == (1, "day")
    assert (first["next_day"], first["next_slot"]) == (1, "night")
    second = resolve(2)
    assert (second["next_day"], second["next_slot"]) == (2, "day")
    # 最終ターンの次はエピローグ初枠(total_days+1 日目の昼)へロールオーバーする
    final = resolve(14)
    assert (final["day"], final["slot"]) == (7, "night")
    assert (final["next_day"], final["next_slot"]) == (8, "day")
    epilogue = resolve(15)
    assert (epilogue["day"], epilogue["slot"]) == (8, "day")
    assert (epilogue["next_day"], epilogue["next_slot"]) == (8, "night")


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


def test_repeated_gift_is_rejected_before_consuming_a_turn() -> None:
    sim = make_sim(given_gifts=["g3"])
    with pytest.raises(RomanceActionError) as error:
        resolve_romance_action(
            sim,
            user_input="また紅茶セットを贈る",
            input_kind="gift",
            gift_id="g3",
            turn_number=3,
            total_turns=14,
        )
    assert error.value.code == "gift_already_given"


def test_confession_threshold_scales_with_days() -> None:
    # 15日以上=75(上限で飽和)、7日=41、5日=32。日数不明の旧データは従来の75に倒す
    assert romance_confession_threshold(15) == 75
    assert romance_confession_threshold(7) == 41
    assert romance_confession_threshold(5) == 32
    assert romance_confession_threshold(0) == 75


def test_confession_outcome_follows_threshold() -> None:
    # make_sim は7日設定のため、スケール後の閾値41で判定される
    success = resolve_romance_action(
        make_sim(affection=41),
        user_input="想いを告げる",
        input_kind="confess",
        turn_number=5,
        total_turns=14,
    )
    assert success["success"] is True
    assert success["affection_delta"] == 0
    failure = resolve_romance_action(
        make_sim(affection=40),
        user_input="想いを告げる",
        input_kind="confess",
        turn_number=5,
        total_turns=14,
    )
    assert failure["success"] is False
    assert failure["affection_delta"] == ROMANCE_CONFESSION_FAIL_PENALTY
    # 15日設定では従来どおり75がライン
    long_run = resolve_romance_action(
        make_sim(total_days=15, affection=74),
        user_input="想いを告げる",
        input_kind="confess",
        turn_number=5,
        total_turns=30,
    )
    assert long_run["success"] is False


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


def test_alter_turn_start_dating_completes_run() -> None:
    # 「交際を始める」宣言は reality_alter ターンで告白成功と同じ扱いになる
    state = {"sim": make_sim(affection=48), "completed_milestones": []}
    output = make_output()
    apply_romance_outcome(
        state,
        output,
        {"kind": "alter", "money_delta": 0, "affection_delta": 0},
        make_romance_output(affection_set=100, start_dating=True),
    )
    assert state["sim"]["confessed"] is True
    assert state["sim"]["affection"] == 100
    assert output.completed_milestones == [item["id"] for item in ROMANCE_MILESTONES]
    assert output.ending_status == "success"


def test_talk_turn_ignores_start_dating() -> None:
    state = {"sim": make_sim(), "completed_milestones": []}
    output = make_output()
    apply_romance_outcome(
        state,
        output,
        {"kind": "talk", "money_delta": 0, "affection_delta": 0},
        make_romance_output(affection_delta=2, start_dating=True),
    )
    assert bool(state["sim"].get("confessed")) is False
    assert output.ending_status == "continue"


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
    # 7日設定ならスケール後の閾値41で告白ボタンが出る
    scaled = public_sim_view(make_sim(affection=45), turn_count=3)
    assert scaled["confession_available"] is True


def test_gift_price_clamped_into_tier_band() -> None:
    gift = RomanceGift.model_validate(
        {"name": "花束", "price": 30000, "tier": "budget"}
    )
    assert gift.price == 2000
    floor = RomanceGift.model_validate({"name": "香水", "price": 100, "tier": "luxury"})
    assert floor.price == 6001


def test_public_view_reports_the_slot_of_the_resolved_turn() -> None:
    # day/slot は次に行動する枠、scene_day/scene_slot は今映っている場面の枠
    view = public_sim_view(make_sim(), turn_count=6)
    assert (view["day"], view["slot"]) == (4, "day")
    assert (view["scene_day"], view["scene_slot"]) == (3, "night")
    opening = public_sim_view(make_sim(), turn_count=0)
    assert opening["scene_day"] is None
    assert opening["scene_slot"] is None
    # 最終手番を超えても枠は最後のスロットで止める
    last = public_sim_view(make_sim(), turn_count=99)
    assert (last["scene_day"], last["scene_slot"]) == (7, "night")


def test_alter_turn_honors_money_set() -> None:
    state = {"sim": make_sim(), "completed_milestones": []}
    apply_romance_outcome(
        state,
        make_output(),
        {"kind": "alter", "money_delta": 0, "affection_delta": 0},
        make_romance_output(money_set=65536),
    )
    assert state["sim"]["money"] == 65536


def test_alter_turn_clamps_money_to_bounds() -> None:
    over = {"sim": make_sim(), "completed_milestones": []}
    apply_romance_outcome(
        over,
        make_output(),
        {"kind": "alter", "money_delta": 0, "affection_delta": 0},
        make_romance_output(money_set=ROMANCE_MONEY_MAX * 10),
    )
    assert over["sim"]["money"] == ROMANCE_MONEY_MAX
    under = {"sim": make_sim(), "completed_milestones": []}
    apply_romance_outcome(
        under,
        make_output(),
        {"kind": "alter", "money_delta": 0, "affection_delta": 0},
        make_romance_output(money_delta=-ROMANCE_ALTER_MONEY_LIMIT),
    )
    assert under["sim"]["money"] == 0


def test_talk_and_gift_turns_ignore_llm_money_fields() -> None:
    talk = {"sim": make_sim(), "completed_milestones": []}
    apply_romance_outcome(
        talk,
        make_output(),
        {"kind": "talk", "money_delta": 0, "affection_delta": 0},
        make_romance_output(money_set=999_999, money_delta=999_999),
    )
    assert talk["sim"]["money"] == ROMANCE_INITIAL_MONEY
    gift = {"sim": make_sim(), "completed_milestones": []}
    apply_romance_outcome(
        gift,
        make_output(),
        {
            "kind": "gift",
            "money_delta": -3000,
            "affection_delta": 12,
            "gift": {"id": "g3", "name": "紅茶セット", "price": 3000},
        },
        make_romance_output(money_set=999_999),
    )
    assert gift["sim"]["money"] == ROMANCE_INITIAL_MONEY - 3000


def test_time_of_day_replaces_conflicting_lighting_tags() -> None:
    night = apply_romance_time_of_day(
        "resort beach, daylight, sunny, blue sky, two people talking", "night"
    )
    assert night.startswith("night, nighttime, dark sky, artificial lighting")
    assert "daylight" not in night
    assert "sunny" not in night
    assert "resort beach" in night
    assert "two people talking" in night


def test_time_of_day_does_not_duplicate_existing_tags() -> None:
    tags = apply_romance_time_of_day("daytime, cafe interior", "day")
    assert tags.count("daytime") == 1
    assert tags.endswith("cafe interior")


def test_time_of_day_clamps_to_scene_tag_limit() -> None:
    long_tags = ", ".join(f"tag{index}" for index in range(1000))
    assert len(apply_romance_time_of_day(long_tags, "day")) <= 1800


def test_strip_duplicate_action_choices_removes_reserved_actions() -> None:
    sim = make_sim()
    kept = strip_duplicate_action_choices(
        [
            {"id": "c1", "label": "美咲に告白する"},
            {"id": "c2", "label": "紅茶セットを買って贈る"},
            {"id": "c3", "label": "カフェのバイトに出る"},
            {"id": "c4", "label": "美咲と一緒に本の話をする"},
        ],
        sim,
        "ja",
    )
    labels = [item["label"] for item in kept]
    assert "美咲と一緒に本の話をする" in labels
    assert not any(
        label in labels
        for label in (
            "美咲に告白する",
            "紅茶セットを買って贈る",
            "カフェのバイトに出る",
        )
    )


def test_strip_duplicate_action_choices_refills_to_three() -> None:
    kept = strip_duplicate_action_choices(
        [
            {"id": "c1", "label": "美咲に告白する"},
            {"id": "c2", "label": "プレゼントを贈る"},
            {"id": "c3", "label": "属性を付与する"},
        ],
        make_sim(),
        "ja",
    )
    assert len(kept) == 3
    assert all("告白" not in item["label"] for item in kept)


def test_strip_duplicate_action_choices_keeps_untouched_lists_intact() -> None:
    choices = [
        {"id": "c1", "label": "海辺を歩く"},
        {"id": "c2", "label": "好きな本の話をする"},
    ]
    assert strip_duplicate_action_choices(choices, make_sim(), "ja") == choices


def test_alter_turn_cannot_restart_dating_when_already_confessed() -> None:
    state = {"sim": make_sim(confessed=True, affection=61), "completed_milestones": []}
    output = make_output()
    apply_romance_outcome(
        state,
        output,
        {"kind": "alter", "money_delta": 0, "affection_delta": 0},
        make_romance_output(start_dating=True),
    )
    # 既に交際中なら成立イベントは再発火せず、マイルストーンも据え置き
    assert output.ending_status == "continue"
    assert "start_dating" not in output.completed_milestones


def test_confess_is_rejected_after_dating_started() -> None:
    with pytest.raises(RomanceActionError) as error:
        resolve_romance_action(
            make_sim(confessed=True, affection=90),
            user_input="もう一度告白する",
            input_kind="confess",
            turn_number=5,
            total_turns=14,
        )
    assert error.value.code == "already_dating"


def test_failure_epilogue_can_still_reach_dating() -> None:
    # 失敗End後のエピローグ想定: confessed=False のまま好感度が閾値に到達
    sim = make_sim(affection=80)
    view = public_sim_view(sim, turn_count=15, epilogue=True)
    assert view["confession_available"] is True
    state = {"sim": sim, "completed_milestones": []}
    output = make_output()
    resolution = resolve_romance_action(
        sim,
        user_input="想いを告げる",
        input_kind="confess",
        turn_number=15,
        total_turns=14,
    )
    apply_romance_outcome(state, output, resolution, make_romance_output())
    # 逆転経路: 告白成功で全マイルストーン + success
    assert output.ending_status == "success"
    assert set(output.completed_milestones) == {
        item["id"] for item in ROMANCE_MILESTONES
    }
    assert sim["confessed"] is True


def test_public_view_epilogue_lifts_day_clamp() -> None:
    # total_days=7 (total_turns=14)。通常はクランプ、エピローグでは素通し
    clamped = public_sim_view(make_sim(), turn_count=20)
    assert (clamped["day"], clamped["scene_day"]) == (7, 7)
    assert clamped["epilogue"] is False
    open_view = public_sim_view(make_sim(), turn_count=20, epilogue=True)
    assert open_view["scene_day"] == 10
    assert open_view["scene_slot"] == "night"
    assert open_view["day"] == 11
    assert open_view["epilogue"] is True


def test_narrative_guidance_covers_established_couple() -> None:
    assert "state.sim.confessed" in ROMANCE_NARRATIVE_GUIDANCE
    assert "already dating" in ROMANCE_NARRATIVE_GUIDANCE
    assert "state.sim.confessed" in ROMANCE_RESOLUTION_GUIDANCE


def test_guidance_defines_half_day_granularity() -> None:
    # 1ターン=半日の粒度指示と、同意ガード・ミクロ動作禁止の維持を固定する
    assert "half-day slot" in ROMANCE_NARRATIVE_GUIDANCE
    assert "morning to late afternoon" in ROMANCE_NARRATIVE_GUIDANCE
    assert "opening beat" in ROMANCE_NARRATIVE_GUIDANCE
    assert "never invent a new voluntary decision" in ROMANCE_NARRATIVE_GUIDANCE
    assert "shaking hands" in ROMANCE_NARRATIVE_GUIDANCE
    assert "next_slot" in ROMANCE_RESOLUTION_GUIDANCE
    assert "romance_next_slot" in ROMANCE_RESOLUTION_GUIDANCE
    assert "shaking hands" in ROMANCE_RESOLUTION_GUIDANCE


def test_init_state_stores_player_history_id() -> None:
    sim = init_romance_state(
        make_setup(),
        14,
        rng=random.Random(0),
        player_character_id="session:abc",
        player_history_id="42",
    )
    assert sim["player_history_id"] == "42"
    # リプレイ用の内部データであり、公開ビューには載せない
    assert "player_history_id" not in public_sim_view(sim, turn_count=0)


def test_alter_turn_updates_partner_appearance_only_on_alter() -> None:
    sim = make_sim(partner_appearance="brown hair, school uniform")
    apply_romance_outcome(
        {"sim": sim},
        make_output(),
        {"kind": "alter"},
        make_romance_output(updated_partner_appearance=" cat ears, silver hair "),
    )
    assert sim["partner_appearance"] == "cat ears, silver hair"

    # 非alterターンの申告は無視される
    apply_romance_outcome(
        {"sim": sim},
        make_output(),
        {"kind": "talk"},
        make_romance_output(updated_partner_appearance="blonde hair"),
    )
    assert sim["partner_appearance"] == "cat ears, silver hair"

    # alterターンでも空白のみの申告は採用しない
    apply_romance_outcome(
        {"sim": sim},
        make_output(),
        {"kind": "alter"},
        make_romance_output(updated_partner_appearance=" "),
    )
    assert sim["partner_appearance"] == "cat ears, silver hair"


def test_resolution_guidance_mentions_partner_appearance_field() -> None:
    assert "updated_partner_appearance" in ROMANCE_RESOLUTION_GUIDANCE
    # 「入れ替わり」も相手の外見変更として申告させる
    assert "swap, exchange, or transfer of bodies" in ROMANCE_RESOLUTION_GUIDANCE
    # 画像タグとして使うため英語タグ・性別トークン開始・服装なしを要求する
    assert "English comma-separated tags" in ROMANCE_RESOLUTION_GUIDANCE
    assert "never clothing" in ROMANCE_RESOLUTION_GUIDANCE


def test_visual_guidance_requires_sex_tokens_for_both_characters() -> None:
    """性別トークンが無いと画像モデルが女性寄りに描くため双方へ明示させる。"""
    assert "female, 1girl or male, 1boy" in ROMANCE_VISUAL_GUIDANCE
    assert "The partner's entry in npc_tags" in ROMANCE_VISUAL_GUIDANCE
    assert "never drawn female" in ROMANCE_VISUAL_GUIDANCE
    # 宣言ターンは主人公も新しい体の性別を名乗る
    assert "sex tokens of the player's new body" in ROMANCE_VISUAL_GUIDANCE


def test_narrative_and_visual_guidance_allow_declared_body_swap() -> None:
    """「相手の特徴を主人公へ混ぜるな」は入れ替わり宣言と衝突するため例外が要る。"""
    for guidance in (ROMANCE_NARRATIVE_GUIDANCE, ROMANCE_VISUAL_GUIDANCE):
        assert "exchanged bodies or identities" in guidance
        assert "the clothing that body was already wearing" in guidance


def test_public_sim_view_exposes_partner_appearance() -> None:
    """攻略対象の外見は現実改変で変わるので、主人公の外見表示と対にして配信する。"""
    sim = init_romance_state(
        make_setup(),
        14,
        partner_appearance="female, 1girl, long blonde hair",
        player_name="僕",
        player_character_id="char1",
    )
    assert public_sim_view(sim, 1)["partner_appearance"] == (
        "female, 1girl, long blonde hair"
    )
    sim["partner_appearance"] = "male, 1boy, black hair"
    assert public_sim_view(sim, 1)["partner_appearance"] == "male, 1boy, black hair"


def test_alter_turn_rewrites_gift_catalog_and_preserves_ids() -> None:
    """現実改変のカタログ書換。既存品はIDを引き継ぎ、好みと贈答記録を掃除する。"""
    state = {
        "sim": make_sim(given_gifts=["g1", "g2"]),
        "completed_milestones": [],
    }
    new_catalog = [
        RomanceAlteredGift(name="文庫本", price=0, tier="budget"),
        RomanceAlteredGift(
            name="魔法の指輪", price=100, tier="luxury", preference="liked"
        ),
        RomanceAlteredGift(
            name="香水", price=8000, tier="luxury", preference="neutral"
        ),
    ]
    apply_romance_outcome(
        state,
        make_output(),
        {"kind": "alter", "money_delta": 0, "affection_delta": 0},
        make_romance_output(updated_gift_catalog=new_catalog),
    )
    sim = state["sim"]
    catalog = {item["name"]: item for item in sim["gift_catalog"]}
    assert set(catalog) == {"文庫本", "魔法の指輪", "香水"}
    # 既存品はIDを引き継ぎ、新規品は未使用の連番を得る
    assert catalog["文庫本"]["id"] == "g2"
    assert catalog["香水"]["id"] == "g7"
    assert catalog["魔法の指輪"]["id"] not in {"g2", "g7"}
    # 価格はtier帯へクランプされない(無料化の宣言を許す)
    assert catalog["文庫本"]["price"] == 0
    hidden = sim["hidden_preferences"]
    # 消えた品(紅茶セット=g3)の好みは掃除し、preference指定を反映する
    assert catalog["魔法の指輪"]["id"] in hidden["liked_gift_ids"]
    assert "g3" not in hidden["liked_gift_ids"]
    assert "g7" not in hidden["disliked_gift_ids"]
    assert "g2" in hidden["liked_gift_ids"]
    # 贈答済み記録は存続する品だけ残る
    assert sim["given_gifts"] == ["g2"]


def test_alter_turn_empty_gift_catalog_is_noop() -> None:
    state = {"sim": make_sim(), "completed_milestones": []}
    before = [dict(item) for item in state["sim"]["gift_catalog"]]
    apply_romance_outcome(
        state,
        make_output(),
        {"kind": "alter", "money_delta": 0, "affection_delta": 0},
        make_romance_output(updated_gift_catalog=[]),
    )
    assert state["sim"]["gift_catalog"] == before


def test_strip_romance_time_of_day_removes_day_and_night_tags() -> None:
    from gateway.services.adventure_romance import strip_romance_time_of_day

    stripped = strip_romance_time_of_day(
        "night, school rooftop, Nighttime, dark sky, wide shot, daytime, sunset"
    )
    assert stripped == "school rooftop, wide shot"
    assert strip_romance_time_of_day("") == ""


def test_romance_location_key_normalizes_case_and_whitespace() -> None:
    from gateway.services.adventure_romance import romance_location_key

    assert romance_location_key("  School Rooftop ") == "school rooftop"
    assert romance_location_key("") == ""
    assert len(romance_location_key("x" * 200)) == 80


def test_talk_log_helpers_bound_and_filter_by_turn() -> None:
    from gateway.consts.adventure_romance import ROMANCE_TALK_LOG_MAX
    from gateway.services.adventure_romance import (
        append_talk_entry,
        public_talk_log,
        recent_talk_entries,
    )

    state: dict = {}
    for index in range(ROMANCE_TALK_LOG_MAX + 6):
        append_talk_entry(
            state,
            role="user" if index % 2 == 0 else "partner",
            text=f"  line {index}  ",
            after_turn=index // 10,
        )
    assert len(state["talk_log"]) == ROMANCE_TALK_LOG_MAX
    # 古い分から捨てられる
    assert state["talk_log"][0]["text"] == "line 6"
    recent = recent_talk_entries(state, 4)
    assert recent and all(
        item["role"] in {"user", "partner"} and item["text"].startswith("line 4")
        for item in recent
    )
    assert recent_talk_entries(state, 99) == []
    public = public_talk_log(state)
    assert public[0]["id"] and public[0]["after_turn"] == 0
    assert {"id", "role", "text", "after_turn"} == set(public[0])


def test_normalize_talk_reply_strips_name_prefix_and_brackets() -> None:
    from gateway.consts.adventure_romance import ROMANCE_TALK_REPLY_MAX
    from gateway.services.adventure_romance import normalize_talk_reply

    assert (
        normalize_talk_reply("美咲「やっほー、元気？」", "美咲") == "やっほー、元気？"
    )
    assert (
        normalize_talk_reply("美咲：「（笑って）そうだね」", "美咲")
        == "（笑って）そうだね"
    )
    assert normalize_talk_reply("```\nそうだね\n```", "美咲") == "そうだね"
    assert normalize_talk_reply("うん、「好き」", "美咲") == "うん、「好き」"
    assert len(normalize_talk_reply("あ" * 1000, "美咲")) == ROMANCE_TALK_REPLY_MAX


def test_romance_script_and_talk_prompts_include_names() -> None:
    from gateway.services.adventure_romance import (
        ROMANCE_RECENT_TALK_GUIDANCE,
        ROMANCE_VISUAL_GUIDANCE,
        romance_script_format_guidance,
        romance_script_names,
        romance_talk_system_prompt,
    )

    assert romance_script_names({"partner_name": "美咲"}, "ja") == ("美咲", "主人公")
    assert romance_script_names(
        {"partner_name": "Misaki", "player_name": "Ken"}, "en"
    ) == (
        "Misaki",
        "Ken",
    )
    guidance = romance_script_format_guidance("美咲", "主人公")
    assert "美咲「...」" in guidance and "主人公「...」" in guidance
    prompt = romance_talk_system_prompt(
        "ja",
        partner_name="美咲",
        player_name="主人公",
        speech_rule="SPEECH REGISTER: x",
    )
    assert "You are 美咲" in prompt and "Japanese" in prompt
    assert prompt.endswith("SPEECH REGISTER: x")
    assert "hidden_preferences" in prompt
    # 現在地の固定ルールは全 romance run の visual プロンプトに載る
    assert "previous_visual_state.location verbatim" in ROMANCE_VISUAL_GUIDANCE
    assert "affection_delta" in ROMANCE_RECENT_TALK_GUIDANCE
