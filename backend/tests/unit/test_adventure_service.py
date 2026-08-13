from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gateway.consts.adventure_romance import (
    ROMANCE_AFFECTION_START,
    ROMANCE_INITIAL_MONEY,
)
from gateway.consts.adventure_turns import (
    ADVENTURE_TURNS_DEFAULT,
    ADVENTURE_TURNS_MAX,
    ADVENTURE_TURNS_MIN,
)
from gateway.databases.models import (
    AdventureRun,
    AdventureTurn,
    Base,
    History,
    Session,
    User,
)
from gateway.services.adventure_romance import (
    apply_romance_outcome,
    clamp_romance_max_turns,
)
from gateway.services.adventure_service import (
    AdventureChoice,
    AdventureDirectorOutput,
    AdventureError,
    AdventureImagePromptOutput,
    AdventureService,
    AdventureVisualState,
    PRESETS,
    SCENARIO_TEMPLATES,
    _default_ending_title,
    _apply_visual_style_to_state,
    _authored_scene_tags,
    _equipment_score_choices,
    _equipment_negative_tags,
    _equipment_wear_choice_label,
    _last_equipment_action,
    _equipment_clothing_state_tags,
    _strip_clothing_tags_for_equipment_scenario,
    _character_reference_strength,
    _compose_scene_base_tags,
    _merge_scene_tags,
    _romance_template_player_appearance,
    _sanitize_choices,
    _template_visual_style,
    clamp_generated_max_turns,
)
from gateway.services.session import DEFAULT_USER_ID


def make_image_prompt_content(*, with_guard: bool = False) -> str:
    return __import__("json").dumps(
        {
            "scene_tags": "luxury building entrance, night, warm lighting",
            "player_tags": "mature woman, navy evening dress, elegant",
            "npc_tags": ["middle-aged man, security guard uniform, white gloves"]
            if with_guard
            else [],
        }
    )


def make_output(
    *,
    completed: list[str],
    location: str = "hall",
    clothing: str = "",
    ending: str = "continue",
) -> AdventureDirectorOutput:
    return AdventureDirectorOutput(
        narrative="状況が進展した。",
        choices=[
            AdventureChoice(id="a", label="調べる"),
            AdventureChoice(id="b", label="話す"),
            AdventureChoice(id="c", label="移動する"),
        ],
        discovered_clues=["招待状"],
        completed_milestones=completed,
        visual_state=AdventureVisualState(
            location=location,
            appearance="開始時の姿",
            clothing=clothing,
            main_characters=["案内人"],
        ),
        ending_status=ending,
    )


def make_run(*, turn_count: int = 0, max_turns: int = 8) -> SimpleNamespace:
    milestones = PRESETS["infiltration"]["milestones"]
    return SimpleNamespace(
        preset="infiltration",
        state_json=(
            '{"milestones": '
            + __import__("json").dumps(milestones, ensure_ascii=False)
            + ', "completed_milestones": [], "clues": [], '
            '"visual_state": {"location": "entrance", '
            '"appearance": "開始時の姿", "main_characters": []}}'
        ),
        max_turns=max_turns,
        turn_count=turn_count,
    )


def make_romance_run(*, turn_count: int = 0, max_turns: int = 14) -> SimpleNamespace:
    state = {
        "milestones": PRESETS["romance"]["milestones"],
        "completed_milestones": [],
        "clues": [],
        "visual_state": {
            "location": "campus",
            "appearance": "開始時の姿",
            "main_characters": [],
        },
        "sim": {
            "total_days": max_turns // 2,
            "affection": 10,
            "money": 5000,
            "partner_name": "美咲",
            "job": {"name": "カフェ", "wage": 3000},
            "gift_catalog": [],
            "hidden_preferences": {
                "liked_gift_ids": [],
                "disliked_gift_ids": [],
                "likes_hint": "",
                "dislikes_hint": "",
            },
            "given_gifts": [],
            "confessed": False,
        },
    }
    return SimpleNamespace(
        preset="romance",
        state_json=__import__("json").dumps(state, ensure_ascii=False),
        max_turns=max_turns,
        turn_count=turn_count,
    )


def test_all_milestones_force_success() -> None:
    service = AdventureService()
    milestone_ids = [item["id"] for item in PRESETS["infiltration"]["milestones"]]

    state, status, visual_changed, clothing_changed = service._merge_output(
        make_run(), make_output(completed=milestone_ids), 3
    )

    assert status == "success"
    assert state["completed_milestones"] == sorted(milestone_ids)
    assert visual_changed is True
    assert clothing_changed is False


def test_turn_limit_uses_partial_and_failure_endings() -> None:
    service = AdventureService()
    partial_state, partial_status, _, _ = service._merge_output(
        make_run(turn_count=7), make_output(completed=["gain_access"]), 8
    )
    _, failure_status, _, _ = service._merge_output(
        make_run(turn_count=7), make_output(completed=[]), 8
    )

    assert partial_status == "partial"
    assert partial_state["ending_summary"] == "状況が進展した。"
    assert failure_status == "failure"


def test_explicit_failure_ends_before_turn_limit() -> None:
    service = AdventureService()
    output = make_output(completed=[], ending="failure")
    output.ending_summary = "重大な違反により任務を続行できなくなった。"

    state, status, _, _ = service._merge_output(make_run(), output, 2)

    assert status == "failure"
    assert state["ending_summary"] == output.ending_summary


def test_disguise_preset_uses_identity_without_inherited_memory() -> None:
    preset = PRESETS["disguise"]

    assert "開始時点ですでに特定人物の姿へ変身している" in preset["guidance"]
    assert "開始スナップショットと完全に同一" in preset["guidance"]
    assert "髪色、髪型、目の色、体格" in preset["guidance"]
    assert "記憶" in preset["guidance"]
    assert "観察" in preset["guidance"]
    assert preset["milestones"][0]["id"] == "learn_identity"

    system_prompt = AdventureService()._director_system_prompt("ja")
    assert "another person's memories" in system_prompt
    assert "immutable identity signature" in system_prompt
    assert "hair color, hair length, hairstyle" in system_prompt


def test_turn_output_cannot_replace_locked_starting_appearance() -> None:
    service = AdventureService()
    run = make_run()
    state = __import__("json").loads(run.state_json)
    state["appearance_lock"] = "1girl, short black hair, black eyes"
    run.state_json = __import__("json").dumps(state, ensure_ascii=False)
    output = make_output(completed=[])
    output.visual_state.appearance = "blonde hair, long hair, blue eyes"

    merged, _, _, _ = service._merge_output(run, output, 1)

    assert merged["visual_state"]["appearance"] == (
        "1girl, short black hair, black eyes"
    )
    assert output.visual_state.appearance == "1girl, short black hair, black eyes"


def test_romance_preset_defines_dating_milestones() -> None:
    preset = PRESETS["romance"]
    assert [item["id"] for item in preset["milestones"]] == [
        "become_friends",
        "mutual_interest",
        "mutual_love",
        "start_dating",
    ]
    assert "romance_resolution" in preset["guidance"]


def test_romance_prompts_carry_romance_guidance_only_when_enabled() -> None:
    service = AdventureService()
    narrative_prompt = service._narrative_system_prompt("ja", romance=True)
    assert "romance simulation" in narrative_prompt
    # スナップショットの人物は攻略対象であり、主人公とは別人として扱う
    assert "partner" in narrative_prompt
    assert "never the player" in narrative_prompt
    assert "romance simulation" not in service._narrative_system_prompt("ja")
    romance_resolution_prompt = service._resolution_system_prompt("ja", romance=True)
    assert "affection_set" in romance_resolution_prompt
    assert "affection_set" not in service._resolution_system_prompt("ja")
    # 会話の採点基準と、交際宣言の機械可読フィールド
    assert "rubric" in romance_resolution_prompt
    assert "start_dating" in romance_resolution_prompt
    # 専用ボタン(バイト/ギフト/属性付与/告白)と重複する選択肢の抑止
    assert "never duplicate the dedicated action buttons" in romance_resolution_prompt
    assert "never duplicate the dedicated action buttons" in narrative_prompt
    romance_visual_prompt = service._visual_system_prompt("ja", romance=True)
    assert "partner is an NPC" in romance_visual_prompt
    assert "partner is an NPC" not in service._visual_system_prompt("ja")
    # 主人公が別性別で描かれないよう、player_tags へ性別トークンの復唱を要求する
    assert "sex tokens" in romance_visual_prompt


def test_romance_template_player_appearance_adds_gender_tags() -> None:
    boy = SimpleNamespace(
        base_tags="short black hair, black eyes, white t-shirt, black shorts",
        description="普通の男の子。",
        gender="man",
    )
    girl = SimpleNamespace(
        base_tags="brown hair, medium hair, shorts",
        description="",
        gender="woman",
    )
    already_tagged = SimpleNamespace(
        base_tags="1girl, twin tails",
        description="",
        gender="man",
    )
    unknown_gender = SimpleNamespace(
        base_tags="silver hair",
        description="",
        gender="",
    )

    assert _romance_template_player_appearance(boy) == (
        "male, 1boy, short black hair, black eyes, white t-shirt, black shorts"
    )
    assert _romance_template_player_appearance(girl) == (
        "female, 1girl, brown hair, medium hair, shorts"
    )
    # 既に性別トークンを含む場合は二重に足さない
    assert _romance_template_player_appearance(already_tagged) == "1girl, twin tails"
    assert _romance_template_player_appearance(unknown_gender) == "silver hair"


def test_romance_overrides_llm_milestone_and_ending_claims() -> None:
    service = AdventureService()
    run = make_romance_run()
    state = __import__("json").loads(run.state_json)
    # LLM が架空の達成と即クリアを申告しても Python 算出値で置き換える
    output = make_output(completed=["start_dating"], ending="success")
    apply_romance_outcome(
        state,
        output,
        {"kind": "talk", "money_delta": 0, "affection_delta": 0},
        SimpleNamespace(
            affection_delta=2,
            affection_set=100,
            updated_liked_gift_ids=[],
            updated_disliked_gift_ids=[],
        ),
    )
    merged, status, _, _ = service._merge_output(run, output, 1, state_override=state)

    assert merged["sim"]["affection"] == 12
    assert merged["completed_milestones"] == []
    assert status == "continue"


def test_romance_confession_success_ends_run_with_all_milestones() -> None:
    run = make_romance_run(turn_count=5)
    state = __import__("json").loads(run.state_json)
    state["sim"]["affection"] = 80
    output = make_output(completed=[])
    apply_romance_outcome(
        state,
        output,
        {"kind": "confess", "success": True, "money_delta": 0, "affection_delta": 0},
        None,
    )
    merged, status, _, _ = AdventureService()._merge_output(
        run, output, 6, state_override=state
    )

    assert status == "success"
    assert merged["sim"]["confessed"] is True
    assert set(merged["completed_milestones"]) == {
        "become_friends",
        "mutual_interest",
        "mutual_love",
        "start_dating",
    }


def test_romance_turn_limit_ends_partial_with_romance_titles() -> None:
    run = make_romance_run(turn_count=13)
    state = __import__("json").loads(run.state_json)
    state["sim"]["affection"] = 30
    output = make_output(completed=[])
    apply_romance_outcome(
        state,
        output,
        {"kind": "talk", "money_delta": 0, "affection_delta": 0},
        SimpleNamespace(
            affection_delta=0,
            affection_set=None,
            updated_liked_gift_ids=[],
            updated_disliked_gift_ids=[],
        ),
    )
    _, status, _, _ = AdventureService()._merge_output(
        run, output, 14, state_override=state
    )

    assert status == "partial"
    assert _default_ending_title("romance", "success") == "交際成立"
    assert _default_ending_title("romance", "partial") == "想いは届きかけた"
    assert _default_ending_title("romance", "failure") == "恋は実らなかった"
    assert _default_ending_title("infiltration", "failure") == "ミッション失敗"


@pytest.mark.asyncio
@pytest.mark.parametrize("preset", list(PRESETS))
async def test_generate_setup_uses_selected_mission_preset(
    monkeypatch, tmp_path, preset
) -> None:
    service = AdventureService()
    generated = AsyncMock(
        return_value=SimpleNamespace(
            content=__import__("json").dumps(
                {
                    "setting": "閉館後の企業資料館",
                    "objective": "8手以内に保管庫から青い契約書を確保して正門を出る",
                    "constraints": ["警備員が巡回している", "社員証は使用できない"],
                },
                ensure_ascii=False,
            )
        )
    )
    monkeypatch.setattr(
        service,
        "_build_snapshot",
        AsyncMock(
            return_value=(
                {"attributes": ["変身後の姿"], "character_name": "水瀬ユウヤ"},
                tmp_path / "source.png",
                "変身後の姿",
                False,
            )
        ),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_user_settings",
        AsyncMock(return_value={"language": "ja", "novelai_text_model": "glm-4-6"}),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.llm_service.generate_text", generated
    )

    setup = await service.generate_setup(
        source_session_id="session-1", source_history_id=None, preset=preset
    )

    prompt = __import__("json").loads(generated.await_args.args[1])
    assert prompt["preset"] == preset
    if preset == "romance":
        # 変身前の主人公名(character_name)を攻略対象の名前として流用させない
        assert "character_name" not in prompt["source_snapshot"]
    else:
        assert prompt["source_snapshot"]["character_name"] == "水瀬ユウヤ"
    assert (
        prompt["mission_definition"]["default_objective"]
        == PRESETS[preset]["objective"]
    )
    assert setup["objective"] == "8手以内に保管庫から青い契約書を確保して正門を出る"
    assert len(setup["constraints"]) == 2
    assert "observable end condition" in service._setup_system_prompt("ja")
    # romance は日数×2 の偶数ターンへ丸めるため既定 15 は 14 になる
    expected_budget = (
        clamp_romance_max_turns(ADVENTURE_TURNS_DEFAULT)
        if preset == "romance"
        else ADVENTURE_TURNS_DEFAULT
    )
    assert prompt["max_turns"] == expected_budget


@pytest.mark.asyncio
async def test_generate_setup_passes_requested_turn_budget(
    monkeypatch, tmp_path
) -> None:
    service = AdventureService()
    generated = AsyncMock(
        return_value=SimpleNamespace(
            content=__import__("json").dumps(
                {
                    "setting": "閉館後の企業資料館",
                    "objective": "25手以内に保管庫から青い契約書を確保して正門を出る",
                    "constraints": ["警備員が巡回している"],
                },
                ensure_ascii=False,
            )
        )
    )
    monkeypatch.setattr(
        service,
        "_build_snapshot",
        AsyncMock(
            return_value=(
                {"attributes": ["変身後の姿"]},
                tmp_path / "source.png",
                "変身後の姿",
                False,
            )
        ),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_user_settings",
        AsyncMock(return_value={"language": "ja", "novelai_text_model": "glm-4-6"}),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.llm_service.generate_text", generated
    )

    await service.generate_setup(
        source_session_id="session-1",
        source_history_id=None,
        preset="infiltration",
        max_turns=25,
    )

    prompt = __import__("json").loads(generated.await_args.args[1])
    system_prompt = generated.await_args.args[0]
    assert prompt["max_turns"] == 25
    assert "a 25-turn objective-based adventure game" in system_prompt
    assert "within 25 turns" in system_prompt
    assert "eight" not in system_prompt


def test_generated_turn_budget_is_clamped_to_supported_range() -> None:
    assert clamp_generated_max_turns(99) == ADVENTURE_TURNS_MAX
    assert clamp_generated_max_turns(1) == ADVENTURE_TURNS_MIN
    assert clamp_generated_max_turns(ADVENTURE_TURNS_DEFAULT) == ADVENTURE_TURNS_DEFAULT


@pytest.mark.asyncio
async def test_authored_template_list_uses_current_language(monkeypatch) -> None:
    service = AdventureService()
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_user_settings",
        AsyncMock(return_value={"language": "ja"}),
    )

    templates = await service.list_templates()

    template_definition = SCENARIO_TEMPLATES["princess_locked_room"]
    assert template_definition["start_state"] == {
        "clothing": "none",
        "allow_clothing_changes": True,
        "appearance_policy": "preserve_until_rule_event",
    }
    assert template_definition["rule"]["type"] == "equipment_score"
    assert (
        next(
            item["labels"]["ja"]
            for item in template_definition["rule"]["items"]
            if item["id"] == "dress"
        )
        == "エレガントなプリンセスドレス"
    )

    assert templates == [
        {
            "id": "princess_locked_room",
            "preset": "escape",
            "title": "女装してプリンセスにならないと出られない部屋",
            "synopsis": SCENARIO_TEMPLATES["princess_locked_room"]["synopsis"]["ja"],
            "setting": SCENARIO_TEMPLATES["princess_locked_room"]["setting"]["ja"],
            "objective": SCENARIO_TEMPLATES["princess_locked_room"]["objective"]["ja"],
            "constraints": SCENARIO_TEMPLATES["princess_locked_room"]["constraints"][
                "ja"
            ],
            "max_turns": SCENARIO_TEMPLATES["princess_locked_room"]["max_turns"],
            "content_rating": "mature",
        }
    ]


def test_princess_room_template_defines_luxurious_visual_style() -> None:
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    visual_style = _template_visual_style(template)

    assert visual_style is not None
    assert "豪邸" in template["setting"]["ja"]
    assert "密室" not in template["setting"]["ja"]
    assert "luxurious mansion dressing room" in template["setting"]["en"].lower()
    assert visual_style["location"]["ja"] == "豪邸の豪華な衣装部屋"
    assert "chandelier" in visual_style["scene_tags"].lower()
    assert "ball gown" in visual_style["scene_tags"].lower()
    assert "basement" not in visual_style["scene_tags"].lower()
    assert "locker" not in visual_style["scene_tags"].lower()
    assert "luxurious palace dressing room" in _authored_scene_tags(template=template)


def test_merge_scene_tags_prefers_authored_base() -> None:
    authored = "luxurious palace dressing room, crystal chandelier"
    generated = "dim cold room, fluorescent lights"
    merged = _merge_scene_tags(authored, generated)

    assert merged.startswith(authored)
    assert "dim cold room" in merged
    assert _merge_scene_tags(authored, authored + ", open door") == (
        authored + ", open door"
    )


def test_apply_visual_style_overrides_location_and_surroundings() -> None:
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    visual_state = AdventureVisualState(
        location="寒い密室",
        appearance="1girl",
        surroundings="コンクリートの壁",
    )

    _apply_visual_style_to_state(visual_state, _template_visual_style(template), "ja")

    assert visual_state.location == "豪邸の豪華な衣装部屋"
    assert "シャンデリア" in visual_state.surroundings
    assert "ドレス" in visual_state.surroundings


def test_enforce_template_visual_corrects_only_drab_rooms() -> None:
    service = AdventureService()
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    state = {
        "appearance_lock": "1girl, short black hair, black eyes",
        "template_state": {"worn_items": ["panties", "bra"], "transformed": False},
    }
    drab = AdventureVisualState(
        location="地下室",
        appearance="1girl",
        clothing="",
        surroundings="暗い倉庫",
    )
    service._enforce_template_visual(
        template,
        state,
        drab,
        {
            "worn_items": ["panties", "bra"],
            "event": "almost_complete",
        },
        "ja",
    )
    assert drab.location == "豪邸の豪華な衣装部屋"
    assert "シャンデリア" in drab.surroundings

    kept = AdventureVisualState(
        location="衣装部屋の全身鏡の前",
        appearance="1girl",
        clothing="",
        surroundings="きらびやかなドレスが左右に並ぶ",
    )
    service._enforce_template_visual(
        template,
        state,
        kept,
        {
            "worn_items": ["panties", "bra"],
            "event": "almost_complete",
        },
        "ja",
    )
    assert kept.location == "衣装部屋の全身鏡の前"
    assert kept.surroundings == "きらびやかなドレスが左右に並ぶ"


def test_lean_state_for_llm_strips_image_fields() -> None:
    from gateway.services.adventure_service import _lean_state_for_llm

    lean = _lean_state_for_llm(
        {
            "setting": "豪邸",
            "authored_scene_tags": "luxurious palace dressing room",
            "last_image_prompt": {"scene_tags": "x"},
            "opening_image_path": "/tmp/a.png",
            "visual_state": {"location": "部屋"},
        }
    )
    assert "setting" in lean
    assert "visual_state" in lean
    assert "authored_scene_tags" not in lean
    assert "last_image_prompt" not in lean
    assert "opening_image_path" not in lean


def test_detect_reality_declaration_accepts_player_notation() -> None:
    from gateway.services.adventure_service import _detect_reality_declaration

    rule = _detect_reality_declaration(
        "現実改変：僕のあらゆる行動（わいせつ行為も含む）は、"
        "あらゆる人に疑問に思われなくなる"
    )
    assert (
        rule
        == (
            "現実改変：僕のあらゆる行動（わいせつ行為も含む）は、"
            "あらゆる人に疑問に思われなくなる"
        ).split("：", 1)[1]
    )
    assert _detect_reality_declaration("[現実改変] 誰も咎めない") == "誰も咎めない"
    assert _detect_reality_declaration("reality: nobody objects") == "nobody objects"


def test_detect_reality_declaration_ignores_plain_actions() -> None:
    from gateway.services.adventure_service import _detect_reality_declaration

    assert _detect_reality_declaration("受付を観察する") is None
    assert _detect_reality_declaration("現実改変について尋ねる") is None
    assert _detect_reality_declaration("現実改変：   ") is None
    assert _detect_reality_declaration("") is None


def test_append_reality_rule_dedupes_and_caps() -> None:
    from gateway.services.adventure_service import (
        _MAX_REALITY_RULES,
        _append_reality_rule,
    )

    state: dict[str, object] = {}
    _append_reality_rule(state, "誰も咎めない")
    _append_reality_rule(state, "誰も咎めない")
    assert state["reality_rules"] == ["誰も咎めない"]

    for index in range(_MAX_REALITY_RULES + 3):
        _append_reality_rule(state, f"ルール{index}")
    rules = state["reality_rules"]
    assert isinstance(rules, list)
    assert len(rules) == _MAX_REALITY_RULES
    assert "誰も咎めない" not in rules
    assert rules[-1] == f"ルール{_MAX_REALITY_RULES + 2}"


def test_turn_judgement_prompts_carry_reality_rule_policy() -> None:
    service = AdventureService()

    prompts = (
        service._director_system_prompt("ja"),
        service._narrative_system_prompt("ja"),
        service._resolution_system_prompt("ja"),
    )
    for prompt in prompts:
        assert "reality_rules" in prompt
        # ルールが覆う行動だけでBadEndにしない、という判定方針が載っていること
        assert "must never by itself set ending_status to failure" in prompt


def _narration_prompts(service: AdventureService, **kwargs: str) -> tuple[str, ...]:
    return (
        service._director_system_prompt("ja", **kwargs),
        service._narrative_system_prompt("ja", **kwargs),
        service._resolution_system_prompt("ja", **kwargs),
    )


def test_narration_voice_defaults_to_second_person() -> None:
    service = AdventureService()
    for prompt in _narration_prompts(service):
        assert "NARRATION VOICE:" in prompt
        assert "in the second person" in prompt


@pytest.mark.parametrize(
    ("voice", "marker"),
    [
        ("second_person", "in the second person"),
        ("third_person", "in the third person"),
        ("first_person", "in the first person"),
    ],
)
def test_narration_voice_switches_grammatical_person(voice: str, marker: str) -> None:
    service = AdventureService()
    for prompt in _narration_prompts(service, narration_voice=voice):
        assert marker in prompt


def test_first_person_narration_pins_the_configured_pronoun() -> None:
    service = AdventureService()
    for prompt in _narration_prompts(
        service, narration_voice="first_person", narration_pronoun="俺"
    ):
        assert "「俺」" in prompt
        assert "never substituting a different first-person pronoun" in prompt


def test_unknown_narration_voice_falls_back_to_second_person() -> None:
    service = AdventureService()
    assert "in the second person" in service._narrative_system_prompt(
        "ja", narration_voice="bogus"
    )


def test_narration_voice_keeps_agency_guard_in_every_mode() -> None:
    """人称を変えても同意・主体性のガードを弱めないこと。"""
    service = AdventureService()
    for voice in ("second_person", "third_person", "first_person"):
        for prompt in _narration_prompts(service, narration_voice=voice):
            assert "consent" in prompt
            assert "any voluntary action that the" in prompt


def test_resolution_prompt_keeps_choice_labels_voice_free() -> None:
    service = AdventureService()
    prompt = service._resolution_system_prompt("ja", narration_voice="first_person")
    assert "choices[].label must remain a short neutral action phrase" in prompt


@pytest.mark.parametrize(
    ("voice", "pronoun", "expected"),
    [
        ("second_person", "僕", "君は赤いドレスを着用した。"),
        ("first_person", "俺", "俺は赤いドレスを着用した。"),
        # 変身で性別が変わりうるため三人称では主語を補わない
        ("third_person", "僕", "赤いドレスを着用した。"),
    ],
)
def test_clothing_narrative_suffix_follows_narration_voice(
    voice: str, pronoun: str, expected: str
) -> None:
    service = AdventureService()
    suffix = service._clothing_narrative_suffix(
        "赤いドレス",
        "",
        "ja",
        narration_voice=voice,
        narration_pronoun=pronoun,
    )
    assert suffix == expected


def test_equipment_image_tags_include_worn_dress() -> None:
    from gateway.services.adventure_service import _equipment_image_tags

    template = SCENARIO_TEMPLATES["princess_locked_room"]
    tags = _equipment_image_tags(template, ["panties", "bra", "dress", "sanitary_pad"])
    assert "wearing dress" in tags or "princess" in tags.lower()
    assert "bra" in tags.lower()
    assert "tiara" not in tags.lower()


def test_equipment_image_tags_hide_underwear_under_dress_when_layers_respected() -> (
    None
):
    from gateway.services.adventure_service import _equipment_image_tags

    template = SCENARIO_TEMPLATES["princess_locked_room"]
    worn = ["panties", "bra", "dress", "sanitary_pad"]
    tags = _equipment_image_tags(template, worn, respect_clothing_layers=True)
    assert "dress" in tags.lower()
    assert "bra" not in tags.lower()
    assert "panties" not in tags.lower()
    assert "sanitary" not in tags.lower()


def test_equipment_image_tags_keep_underwear_without_outer_garment() -> None:
    from gateway.services.adventure_service import _equipment_image_tags

    template = SCENARIO_TEMPLATES["princess_locked_room"]
    tags = _equipment_image_tags(
        template, ["panties", "bra"], respect_clothing_layers=True
    )
    assert "bra" in tags.lower()
    assert "panties" in tags.lower()


def test_covered_underwear_is_peeled_from_player_tags_with_negative() -> None:
    from gateway.services.adventure_service import (
        _apply_clothing_layers_to_player_tags,
        _equipment_layers_covered,
    )

    covered = _equipment_layers_covered(["panties", "bra", "dress"], True)
    assert covered is True
    tags, negative = _apply_clothing_layers_to_player_tags(
        "1girl, white bra, white panties, princess dress, tiara", covered=covered
    )
    assert "bra" not in tags.lower()
    assert "panties" not in tags.lower()
    assert "princess dress" in tags
    assert negative is not None
    assert "visible bra" in negative


def test_clothing_layers_are_ignored_when_setting_is_off() -> None:
    from gateway.services.adventure_service import (
        _apply_clothing_layers_to_player_tags,
        _equipment_layers_covered,
    )

    covered = _equipment_layers_covered(["panties", "bra", "dress"], False)
    assert covered is False
    tags, negative = _apply_clothing_layers_to_player_tags(
        "1girl, white bra, princess dress", covered=covered
    )
    assert "white bra" in tags
    assert negative is None


def test_door_check_without_tiara_stays_incomplete_and_lists_missing() -> None:
    service = AdventureService()
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    state = {
        "scenario_template_id": "princess_locked_room",
        "appearance_lock": "1girl, short black hair, black eyes",
        "milestones": template["milestones"]["ja"],
        "completed_milestones": ["read_rule"],
        "template_state": {
            "worn_items": ["panties", "bra", "dress", "sanitary_pad"],
            "rule_read": True,
            "door_score": 0,
            "transformed": False,
        },
    }
    resolution = service._resolve_template_action(template, state, "扉の採点を確認する")
    assert resolution["event"] == "incomplete"
    assert resolution["score"] == 0
    assert "tiara" not in resolution["worn_items"]

    output = make_output(completed=[])
    service._enforce_template_output(template, state, output, resolution, "ja")
    assert any("ティアラ" in clue for clue in output.discovered_clues)
    assert "ティアラ" in output.narrative
    assert output.ending_status == "continue"


def test_tiara_aliases_include_headdress() -> None:
    service = AdventureService()
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    state = {
        "template_state": {
            "worn_items": ["panties", "bra", "dress", "sanitary_pad"],
            "flags": {},
            "score": 0,
            "transformed": False,
        },
        "completed_milestones": ["read_rule"],
        "milestones": template["milestones"]["ja"],
    }
    resolution = service._resolve_template_action(
        template, state, "ヘッドドレスを身につける"
    )
    assert "tiara" in resolution["worn_items"]
    door = service._resolve_template_action(template, state, "扉の採点を確認する")
    assert door["event"] == "perfect_score"
    assert door["score"] == 100


def test_equipment_negative_tags_target_only_unworn_items() -> None:
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    negative = _equipment_negative_tags(template, ["bra"])
    # 未装備の下着・ドレス・ティアラは打ち消す
    assert "panties" in negative
    assert "gown" in negative
    assert "tiara" in negative
    # 装備中のブラは打ち消さない。総称語も混ぜない
    assert "bra" not in negative.split(", ")
    assert "underwear" not in negative
    assert "lingerie" not in negative


def test_equipment_negative_tags_skip_underwear_under_outer_garment() -> None:
    """外衣を着ているときは下着 negative を出さない。

    CLOTHING_LAYER_COVERED_NEGATIVE が `no panties` を含むため、
    同じプロンプトに `panties` を足すと自己矛盾になる。
    """
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    negative = _equipment_negative_tags(template, ["bra", "dress"])
    assert "panties" not in negative
    assert "tiara" in negative


def test_equipment_negative_tags_ignore_non_equipment_templates() -> None:
    assert _equipment_negative_tags(None, ["bra"]) == ""


def test_equipment_scenario_drops_llm_clothing_tags() -> None:
    """装備採点シナリオでは LLM が書いた服装タグを残さない。

    元セッションの私服がそのまま画像へ出てしまうため。
    """
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    stripped = _strip_clothing_tags_for_equipment_scenario(
        template,
        "1girl, black bob hair, white shirt, blue jacket, black pants, panties",
    )
    tokens = stripped.split(", ")
    assert tokens == ["1girl", "black bob hair"]


def test_equipment_scenario_clothing_strip_ignores_other_scenarios() -> None:
    tags = "1girl, white shirt"
    assert _strip_clothing_tags_for_equipment_scenario(None, tags) == tags


def test_equipment_scenario_clothing_strip_keeps_original_when_all_removed() -> None:
    """player_tags は min_length=1。全消しになる入力では元を返す。"""
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    assert (
        _strip_clothing_tags_for_equipment_scenario(template, "panties, bra")
        == "panties, bra"
    )


def test_equipment_scenario_states_exposure_with_danbooru_tags() -> None:
    """「ブラだけ」は分布外なので、bottomless で状態そのものを指示する。"""
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    assert "nude" in _equipment_clothing_state_tags(template, [])
    assert "bottomless" in _equipment_clothing_state_tags(template, ["bra"])
    assert "topless" in _equipment_clothing_state_tags(template, ["panties"])
    # 上下そろっていれば露出指示は不要
    assert _equipment_clothing_state_tags(template, ["bra", "panties"]) == ""
    # 外衣で覆われていれば露出指示は出さない
    assert _equipment_clothing_state_tags(template, ["bra", "dress"]) == ""
    assert _equipment_clothing_state_tags(None, []) == ""


def test_equipment_scenario_drops_previous_exposure_state_tags() -> None:
    """前ターンの露出状態タグを引き継いだ player_tags から除去する。

    previous_image_tags 経由で LLM が topless 等を再利用してくるため、
    残すと上下そろった装備でも wearing bra が打ち消される。
    """
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    stripped = _strip_clothing_tags_for_equipment_scenario(
        template,
        "1girl, black bob hair, 1.4::topless::, no bra, bare chest, "
        "bottomless, bare hips, completely nude, braless, wearing panties",
    )
    assert stripped.split(", ") == ["1girl", "black bob hair"]


@pytest.mark.asyncio
async def test_prepare_image_prompt_keeps_override_unmutated(monkeypatch) -> None:
    """prompt_override は last_image_prompt として保存されるため書き換えない。

    変換後を保存すると次ターンの previous_image_tags 経由で
    露出状態タグが LLM 出力へ再入し、装備タグを打ち消してしまう。
    """
    service = AdventureService()
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_user_settings",
        AsyncMock(return_value={}),
    )
    run = SimpleNamespace(text_model=None, nsfw_mode=False)
    state = {
        "scenario_template_id": "princess_locked_room",
        "template_state": {"worn_items": ["bra"]},
        "visual_state": {},
    }
    original_player_tags = "1girl, black bob hair, 1.4::topless::, bare chest"
    override = AdventureImagePromptOutput(
        scene_tags="castle room",
        player_tags=original_player_tags,
    )

    (
        image_prompt,
        _outfit_changed,
        _nsfw_mode,
        _use_precise_reference,
        _extra_negative,
        raw_image_prompt,
    ) = await service._prepare_image_prompt(
        run,
        state,
        redraw_from_reference=False,
        prompt_override=override,
        worn_items_override=["bra", "panties"],
    )

    # 保存用の raw は override そのもので、変換の影響を受けない
    assert raw_image_prompt is override
    assert override.player_tags == original_player_tags
    # 変換後は前ターンの露出タグが落ち、確定した装備タグへ置き換わる
    assert "topless" not in image_prompt.player_tags
    assert "bare chest" not in image_prompt.player_tags
    assert "wearing bra" in image_prompt.player_tags
    assert "wearing panties" in image_prompt.player_tags


def _resolve_equipment_actions(text: str) -> dict[str, str]:
    """princess_locked_room の全アイテムに対する着脱判定をまとめて返す。"""
    items = SCENARIO_TEMPLATES["princess_locked_room"]["rule"]["items"]
    alias_by_item = {item["id"]: tuple(item["aliases"]) for item in items}
    actions: dict[str, str] = {}
    for item_id, aliases in alias_by_item.items():
        own = set(aliases)
        other = tuple(
            alias
            for other_id, other_aliases in alias_by_item.items()
            if other_id != item_id
            for alias in other_aliases
            if alias not in own
        )
        action = _last_equipment_action(text, aliases, other_aliases=other)
        if action:
            actions[item_id] = action
    return actions


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 選んだ衣類だけが装備される
        ("ブラジャーをつける", {"bra": "wear"}),
        ("ショーツを履く", {"panties": "wear"}),
        # 動詞は最も近いエイリアスへ帰属する（以前は「脱いで」が無視されていた）
        ("ショーツを脱いでブラジャーをつける", {"panties": "remove", "bra": "wear"}),
        # 他アイテムの語を越えて動詞を拾わない
        ("ショーツは後回しにして、まずブラジャーをつける", {"bra": "wear"}),
        # 英語は動詞が名詞の前に来る
        ("Put on bra", {"bra": "wear"}),
        ("Put on panties", {"panties": "wear"}),
        ("Put on tiara", {"tiara": "wear"}),
        # 長い語に内包されただけの一致は数えない（ヘッドドレスの「ドレス」）
        ("ヘッドドレスを身につける", {"tiara": "wear"}),
        # 修飾・場所として言及された衣類は着脱対象ではない
        ("ドレスの上からティアラをつける", {"tiara": "wear"}),
        # 並列表現は動詞を共有する
        (
            "ショーツとブラジャーを身につけ、ドレスを着用してティアラをかぶる",
            {
                "panties": "wear",
                "bra": "wear",
                "dress": "wear",
                "tiara": "wear",
            },
        ),
        # 共有エイリアス「下着」は両方に効く（意図した挙動）
        ("下着をつける", {"panties": "wear", "bra": "wear"}),
        ("扉の文章をもう一度読む", {}),
    ],
)
def test_equipment_action_attribution(text: str, expected: dict[str, str]) -> None:
    assert _resolve_equipment_actions(text) == expected


def test_equipment_wear_labels_do_not_match_other_items() -> None:
    """着用選択肢ラベルが、自分以外のアイテムを装備させないこと。"""
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    for language in ("ja", "en"):
        for item in template["rule"]["items"]:
            item_id = item["id"]
            label = item["labels"][language]
            choice_label = _equipment_wear_choice_label(item_id, label, language)
            actions = _resolve_equipment_actions(choice_label)
            assert actions == {item_id: "wear"}, (language, choice_label, actions)


def test_princess_room_requires_hidden_item_before_transformation() -> None:
    service = AdventureService()
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    state = {
        "scenario_template_id": "princess_locked_room",
        "appearance_lock": "1girl, short black hair, black eyes",
        "milestones": template["milestones"]["ja"],
        "completed_milestones": [],
        "template_state": {
            "worn_items": [],
            "rule_read": False,
            "door_score": 0,
            "transformed": False,
        },
    }

    service._resolve_template_action(template, state, "扉の文章を読んで条件を確認する")
    service._resolve_template_action(
        template,
        state,
        "ショーツとブラジャーを身につけ、ドレスを着用してティアラをかぶる",
    )
    almost = service._resolve_template_action(
        template, state, "衣装を整えて扉の前へ向かい、採点を確認する"
    )
    almost_output = make_output(completed=[])
    service._enforce_template_output(template, state, almost_output, almost, "ja")

    assert almost["event"] == "almost_complete"
    assert almost["door_score"] == 90
    assert state["completed_milestones"] == ["read_rule", "complete_outfit"]
    assert "90点" in almost_output.narrative
    assert almost_output.ending_status == "continue"
    assert any("ナプキン" in clue for clue in almost_output.discovered_clues)

    perfect = service._resolve_template_action(
        template,
        state,
        "ナプキンをショーツの内側に貼り、ドレスを着用して扉の前へ向かう",
    )
    perfect_output = make_output(completed=[])
    service._enforce_template_output(template, state, perfect_output, perfect, "ja")

    assert perfect["event"] == "perfect_score"
    assert perfect["door_score"] == 100
    assert state["completed_milestones"] == [
        "read_rule",
        "complete_outfit",
        "perfect_score",
    ]
    assert state["template_state"]["transformed"] is True
    assert perfect_output.ending_status == "success"
    assert "100点満点" in perfect_output.narrative
    assert "long black hair" in perfect_output.visual_state.appearance
    assert "月経" not in perfect_output.narrative


def test_clothing_change_requests_reference_redraw() -> None:
    service = AdventureService()
    run = make_run()

    _, _, visual_changed, clothing_changed = service._merge_output(
        run,
        make_output(completed=[], location="entrance", clothing="紺色のドレス"),
        1,
    )

    assert visual_changed is True
    assert clothing_changed is True


def test_explicit_clothing_action_overrides_deferred_director_output() -> None:
    service = AdventureService()
    output = make_output(
        completed=[], location="ブティック", clothing="白いTシャツ、黒い半ズボン"
    )
    output.narrative = "君は棚に掛かったドレスを指さした。"

    changed = service._enforce_explicit_clothing_action(
        output, "エレガントなドレスを着る", "ja"
    )

    assert changed is True
    assert output.visual_state.clothing == "エレガントなドレス"
    assert output.narrative.endswith("君はエレガントなドレスを着用した。")


def test_non_clothing_action_does_not_override_visual_state() -> None:
    service = AdventureService()
    output = make_output(completed=[], clothing="白いTシャツ、黒い半ズボン")

    changed = service._enforce_explicit_clothing_action(
        output, "店員にドレスについて尋ねる", "ja"
    )

    assert changed is False
    assert output.visual_state.clothing == "白いTシャツ、黒い半ズボン"


def test_visual_characters_accept_objects_and_legacy_strings() -> None:
    visual_state = AdventureVisualState(
        location="婦人服売り場",
        appearance="ドレス姿",
        main_characters=[
            {
                "name": "店員",
                "description": "デパートの制服を着た店員",
                "clothing": "制服",
                "gesture": "声をかけている",
            },
            "買い物客",
        ],
    )

    assert visual_state.main_characters[0].description == "デパートの制服を着た店員"
    assert visual_state.main_characters[0].model_extra == {"gesture": "声をかけている"}
    assert visual_state.main_characters[1].description == "買い物客"


@pytest.mark.asyncio
async def test_empty_director_appearance_uses_starting_appearance(monkeypatch) -> None:
    service = AdventureService()
    generated = AsyncMock(
        return_value=SimpleNamespace(
            content=__import__("json").dumps(
                {
                    "narrative": "寒い部屋で目を覚ました。",
                    "choices": [
                        {"id": "a", "label": "扉を調べる"},
                        {"id": "b", "label": "衣装を見る"},
                        {"id": "c", "label": "周囲を確認する"},
                    ],
                    "discovered_clues": [],
                    "completed_milestones": [],
                    "visual_state": {
                        "location": "寒い密室",
                        "appearance": "",
                        "main_characters": [],
                    },
                    "ending_status": "continue",
                    "ending_title": None,
                    "ending_summary": None,
                },
                ensure_ascii=False,
            )
        )
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.llm_service.generate_text", generated
    )

    output = await service._generate_director_output(
        prompt="開始場面",
        language="ja",
        text_model="glm-4-6",
        fallback_appearance="1girl, short black hair, black eyes",
    )

    assert output.visual_state.appearance == "1girl, short black hair, black eyes"
    assert generated.await_count == 1


@pytest.mark.asyncio
async def test_empty_director_choices_use_language_fallback(monkeypatch) -> None:
    service = AdventureService()
    generated = AsyncMock(
        return_value=SimpleNamespace(
            content=__import__("json").dumps(
                {
                    "narrative": "廊下の先に扉が見える。",
                    "choices": [],
                    "discovered_clues": [],
                    "completed_milestones": [],
                    "visual_state": {
                        "location": "廊下",
                        "appearance": "1girl, short black hair, black eyes",
                        "main_characters": [],
                    },
                    "ending_status": "continue",
                    "ending_title": None,
                    "ending_summary": None,
                },
                ensure_ascii=False,
            )
        )
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.llm_service.generate_text", generated
    )

    output = await service._generate_director_output(
        prompt="次の展開",
        language="ja",
        text_model="glm-4-6",
    )

    assert [choice.label for choice in output.choices] == [
        "周囲を詳しく観察する",
        "近くの人物に話しかける",
        "目的に向かって移動する",
    ]
    assert generated.await_count == 1


@pytest.mark.asyncio
async def test_whitespace_director_choices_use_language_fallback(monkeypatch) -> None:
    service = AdventureService()
    generated = AsyncMock(
        return_value=SimpleNamespace(
            content=__import__("json").dumps(
                {
                    "narrative": "壁の衣装を眺めた。",
                    "choices": [
                        {"id": "a", "label": " "},
                        {"id": "b", "label": "  "},
                        {"id": "c", "label": "\t"},
                    ],
                    "discovered_clues": [],
                    "completed_milestones": [],
                    "visual_state": {
                        "location": "密室",
                        "appearance": "1girl, short black hair, black eyes",
                        "main_characters": [],
                    },
                    "ending_status": "continue",
                    "ending_title": None,
                    "ending_summary": None,
                },
                ensure_ascii=False,
            )
        )
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.llm_service.generate_text", generated
    )

    output = await service._generate_director_output(
        prompt="次の展開",
        language="ja",
        text_model="glm-4-6",
    )

    assert [choice.label for choice in output.choices] == [
        "周囲を詳しく観察する",
        "近くの人物に話しかける",
        "目的に向かって移動する",
    ]
    assert generated.await_count == 1


def test_sanitize_choices_rejects_partial_blank_labels(caplog) -> None:
    import logging

    with caplog.at_level(logging.WARNING, logger="gateway.services.adventure_service"):
        sanitized = _sanitize_choices(
            [
                {"id": "1", "label": " "},
                {"id": "2", "label": "非常階段を上る"},
                {"id": "3", "label": "周囲を調べる"},
            ],
            language="ja",
            source="unit_test.blank_label",
        )
    assert sanitized == [
        {"id": "observe", "label": "周囲を詳しく観察する"},
        {"id": "talk", "label": "近くの人物に話しかける"},
        {"id": "advance", "label": "目的に向かって移動する"},
    ]
    assert any(
        "Adventure choices fallback applied" in record.message
        and "unit_test.blank_label" in record.message
        and "empty_label" in record.message
        for record in caplog.records
    )


def test_sanitize_choices_does_not_log_empty_authored_probe(caplog) -> None:
    import logging

    with caplog.at_level(logging.WARNING, logger="gateway.services.adventure_service"):
        sanitized = _sanitize_choices(
            [],
            language="ja",
            fallback=[],
            source="regenerate_choices.authored_template",
        )
    assert sanitized == []
    assert not any(
        "Adventure choices fallback applied" in record.message
        for record in caplog.records
    )


def test_sanitize_choices_keeps_valid_labels() -> None:
    source = [
        {"id": "look", "label": "衣装を調べる"},
        {"id": "door", "label": "扉を読む"},
        {"id": "pad", "label": "棚を確認する"},
    ]
    assert _sanitize_choices(source, language="ja") == source


def test_sanitize_choices_accepts_adventure_choice_models() -> None:
    source = [
        AdventureChoice(id="look", label="衣装を調べる"),
        AdventureChoice(id="door", label="扉を読む"),
        AdventureChoice(id="pad", label="棚を確認する"),
    ]
    assert _sanitize_choices(source, language="ja") == [
        {"id": "look", "label": "衣装を調べる"},
        {"id": "door", "label": "扉を読む"},
        {"id": "pad", "label": "棚を確認する"},
    ]


def test_director_output_preserves_resolution_choice_models() -> None:
    choices = [
        AdventureChoice(id="look", label="衣装を調べる"),
        AdventureChoice(id="door", label="扉を読む"),
        AdventureChoice(id="pad", label="棚を確認する"),
    ]
    output = AdventureDirectorOutput(
        narrative="部屋を見渡した。",
        choices=choices,
        visual_state=AdventureVisualState(
            location="豪邸の衣装部屋",
            appearance="1girl",
        ),
    )
    assert [choice.model_dump() for choice in output.choices] == [
        {"id": "look", "label": "衣装を調べる"},
        {"id": "door", "label": "扉を読む"},
        {"id": "pad", "label": "棚を確認する"},
    ]


def make_serializable_turn(state_delta: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id="turn-1",
        run_id="run-1",
        turn_number=1,
        client_turn_id="c1",
        user_input="話しかける",
        input_kind="choice",
        narrative="彼女は微笑んだ。",
        choices_json=__import__("json").dumps(
            [
                {"id": "a", "label": "続ける"},
                {"id": "b", "label": "様子を見る"},
                {"id": "c", "label": "移動する"},
            ],
            ensure_ascii=False,
        ),
        image_path=None,
        image_status="not_requested",
        portrait_image_path=None,
        portrait_status="not_requested",
        state_delta_json=__import__("json").dumps(state_delta, ensure_ascii=False),
        created_at=None,
    )


def test_serialize_turn_exposes_romance_sim_and_partner_note(tmp_path) -> None:
    service = AdventureService()
    partner_file = tmp_path / "partner-1-abcd1234.png"
    partner_file.write_bytes(b"png")
    turn = make_serializable_turn(
        {
            "partner_portrait_path": str(partner_file),
            "visual_state": {
                "location": "ロビーカフェ",
                "appearance": "主人公の姿",
                "main_characters": [
                    {
                        "name": "アリシア",
                        "description": "グラスを受け取り微笑んでいる",
                        "clothing": "競泳水着",
                    }
                ],
            },
            "sim": {
                "total_days": 7,
                "affection": 12,
                "money": 5000,
                "partner_name": "アリシア",
                "job": {"name": "カフェ", "wage": 3000},
                "gift_catalog": [],
                "hidden_preferences": {
                    "liked_gift_ids": ["g1"],
                    "disliked_gift_ids": [],
                    "likes_hint": "甘いもの",
                    "dislikes_hint": "辛いもの",
                },
                "given_gifts": [],
                "confessed": False,
            },
        }
    )

    payload = service._serialize_turn(turn)

    assert payload["sim"]["partner_name"] == "アリシア"
    assert payload["sim"]["affection"] == 12
    assert payload["sim"]["stage"] == "stranger"
    assert "hidden_preferences" not in payload["sim"]
    assert payload["partner_note"] == "グラスを受け取り微笑んでいる"
    # ターン確定時点の攻略対象立ち絵URL(過去フレーム表示用)
    assert payload["partner_portrait_url"] == (
        f"/adventure/images/run-1/{partner_file.name}"
    )


def test_serialize_turn_omits_sim_for_mission_turns() -> None:
    service = AdventureService()
    turn = make_serializable_turn(
        {
            "visual_state": {
                "location": "倉庫",
                "appearance": "変装した姿",
                "main_characters": [],
            }
        }
    )

    payload = service._serialize_turn(turn)

    assert "sim" not in payload
    assert "partner_note" not in payload


def test_serialize_run_includes_romance_opening_sim(tmp_path) -> None:
    service = AdventureService()
    opening_partner_file = tmp_path / "partner-0-abcd1234.png"
    opening_partner_file.write_bytes(b"png")
    run = SimpleNamespace(
        id="run-romance",
        source_session_id=None,
        source_history_id=None,
        preset="romance",
        title="恋愛シミュレーション",
        objective="交際を始める",
        constraints_json="[]",
        status="active",
        turn_count=3,
        max_turns=14,
        ending_title=None,
        ending_summary=None,
        language="ja",
        current_image_path="current.png",
        initial_image_path="initial.png",
        snapshot_json="{}",
        created_at=None,
        updated_at=None,
        state_json=__import__("json").dumps(
            {
                "opening_narrative": "書店で出会った。",
                "opening_image_path": "initial.png",
                "opening_partner_portrait_path": str(opening_partner_file),
                "choices": [
                    {"id": "a", "label": "話しかける"},
                    {"id": "b", "label": "本棚を眺める"},
                    {"id": "c", "label": "店を出る"},
                ],
                "clues": [],
                "milestones": [],
                "completed_milestones": [],
                "sim": {
                    "total_days": 7,
                    "affection": 40,
                    "money": 12000,
                    "partner_name": "美咲",
                    "job": {"name": "カフェ", "wage": 3000},
                    "gift_catalog": [],
                    "hidden_preferences": {
                        "liked_gift_ids": [],
                        "disliked_gift_ids": [],
                    },
                    "given_gifts": ["g1"],
                    "confessed": False,
                },
            },
            ensure_ascii=False,
        ),
    )

    payload = service._serialize_run(run, [], include_snapshot=False)

    # 現在値はそのまま、開幕ビューは開始定数から再構成される
    assert payload["sim"]["affection"] == 40
    assert payload["opening_sim"]["affection"] == ROMANCE_AFFECTION_START
    assert payload["opening_sim"]["money"] == ROMANCE_INITIAL_MONEY
    assert payload["opening_sim"]["day"] == 1
    assert payload["opening_sim"]["slot"] == "day"
    assert payload["opening_sim"]["given_gift_ids"] == []
    assert "hidden_preferences" not in payload["opening_sim"]
    # 開幕フレーム表示用の攻略対象立ち絵URL
    assert payload["opening_partner_portrait_url"] == (
        f"/adventure/images/run-romance/{opening_partner_file.name}"
    )


def test_serialize_run_repairs_blank_choice_labels() -> None:
    service = AdventureService()
    run = SimpleNamespace(
        id="run-blank",
        source_session_id=None,
        source_history_id=None,
        preset="escape",
        title="テスト",
        objective="脱出する",
        constraints_json="[]",
        status="active",
        turn_count=1,
        max_turns=8,
        ending_title=None,
        ending_summary=None,
        language="ja",
        current_image_path="current.png",
        initial_image_path="initial.png",
        snapshot_json="{}",
        created_at=None,
        updated_at=None,
        state_json=__import__("json").dumps(
            {
                "opening_narrative": "部屋で目を覚ました。",
                "opening_image_path": "initial.png",
                "choices": [
                    {"id": "a", "label": " "},
                    {"id": "b", "label": " "},
                    {"id": "c", "label": " "},
                ],
                "clues": [],
                "milestones": [],
                "completed_milestones": [],
            },
            ensure_ascii=False,
        ),
    )
    turn = SimpleNamespace(
        id="turn-1",
        run_id="run-blank",
        turn_number=1,
        client_turn_id="c1",
        user_input="周囲を見る",
        input_kind="choice",
        narrative="壁に衣装が並んでいる。",
        choices_json=__import__("json").dumps(
            [
                {"id": "a", "label": " "},
                {"id": "b", "label": " "},
                {"id": "c", "label": " "},
            ],
            ensure_ascii=False,
        ),
        image_path=None,
        image_status="not_requested",
        portrait_image_path=None,
        portrait_status="not_requested",
        state_delta_json="{}",
        created_at=None,
    )

    payload = service._serialize_run(run, [turn], include_snapshot=False)

    assert [item["label"] for item in payload["choices"]] == [
        "周囲を詳しく観察する",
        "近くの人物に話しかける",
        "目的に向かって移動する",
    ]
    assert [item["label"] for item in payload["turns"][0]["choices"]] == [
        "周囲を詳しく観察する",
        "近くの人物に話しかける",
        "目的に向かって移動する",
    ]


@pytest.mark.asyncio
async def test_regenerate_choices_updates_only_choices(monkeypatch) -> None:
    service = AdventureService()
    turn = SimpleNamespace(
        id="turn-1",
        run_id="run-1",
        turn_number=1,
        client_turn_id="c1",
        user_input="衣服や装身具を調べる",
        input_kind="choice",
        narrative="壁にかけられた衣類が並んでいる。",
        choices_json=__import__("json").dumps(
            [
                {"id": "a", "label": " "},
                {"id": "b", "label": " "},
                {"id": "c", "label": " "},
            ],
            ensure_ascii=False,
        ),
        image_path=None,
        image_status="not_requested",
        portrait_image_path=None,
        portrait_status="not_requested",
        created_at=None,
    )
    state = {
        "opening_narrative": "部屋で目を覚ました。",
        "choices": [
            {"id": "a", "label": " "},
            {"id": "b", "label": " "},
            {"id": "c", "label": " "},
        ],
        "clues": ["特等席の衣装がある"],
        "milestones": [],
        "completed_milestones": [],
        "scenario_template_id": None,
        "visual_state": {"location": "密室", "appearance": "1girl"},
    }
    run = SimpleNamespace(
        id="run-1",
        status="active",
        language="ja",
        preset="escape",
        objective="脱出する",
        max_turns=8,
        turn_count=1,
        text_model="glm-4-6",
        state_json=__import__("json").dumps(state, ensure_ascii=False),
        turns=[turn],
    )
    persisted_run = SimpleNamespace(
        id="run-1",
        state_json=run.state_json,
        updated_at=None,
    )
    persisted_turn = SimpleNamespace(
        id="turn-1",
        choices_json=turn.choices_json,
    )

    class FakeDatabase:
        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return None

        async def get(self, model, record_id):
            if model is AdventureRun and record_id == "run-1":
                return persisted_run
            if model is AdventureTurn and record_id == "turn-1":
                return persisted_turn
            return None

        async def commit(self):
            return None

    monkeypatch.setattr(service, "get_run_orm", AsyncMock(return_value=run))
    monkeypatch.setattr(
        service,
        "_generate_resolution_output",
        AsyncMock(
            return_value=SimpleNamespace(
                choices=[
                    AdventureChoice(id="look", label="特等席の衣装を調べる"),
                    AdventureChoice(id="door", label="扉の文章を読む"),
                    AdventureChoice(id="shelf", label="棚の品を確認する"),
                ]
            )
        ),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.async_session_factory", FakeDatabase
    )

    result = await service.regenerate_choices("run-1")

    assert [item["label"] for item in result["choices"]] == [
        "特等席の衣装を調べる",
        "扉の文章を読む",
        "棚の品を確認する",
    ]
    saved_state = __import__("json").loads(persisted_run.state_json)
    assert saved_state["choices"] == result["choices"]
    assert saved_state["clues"] == ["特等席の衣装がある"]
    assert run.turn_count == 1
    assert __import__("json").loads(persisted_turn.choices_json) == result["choices"]


@pytest.mark.asyncio
async def test_invalid_director_json_is_repaired_once(monkeypatch) -> None:
    service = AdventureService()
    repaired_json = __import__("json").dumps(
        {
            "narrative": "扉が開いた。",
            "choices": [
                {"id": "a", "label": "中を見る"},
                {"id": "b", "label": "周囲を調べる"},
                {"id": "c", "label": "引き返す"},
            ],
            "discovered_clues": [],
            "completed_milestones": [{"id": "gain_access", "label": "侵入経路を確保"}],
            "visual_state": {
                "location": "入口",
                "appearance": "開始時の姿",
                "main_characters": [],
            },
            "ending_status": "continue",
            "ending_title": None,
            "ending_summary": None,
        },
        ensure_ascii=False,
    )
    generate = AsyncMock(
        side_effect=[
            SimpleNamespace(content='{"narrative":"途中で切れた出力"'),
            SimpleNamespace(content=repaired_json),
        ]
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.llm_service.generate_text", generate
    )

    output = await service._generate_director_output(
        prompt="開始場面", language="ja", text_model="glm-4-6"
    )

    assert output.narrative == "扉が開いた。"
    assert output.completed_milestones == ["gain_access"]
    assert generate.await_count == 2
    repair_call = generate.await_args_list[1]
    assert "compact JSON" in repair_call.args[0]
    assert "under 1200 characters" in repair_call.args[0]
    assert repair_call.args[1].startswith("Invalid source output:")


@pytest.mark.asyncio
async def test_clothing_redraw_does_not_reuse_previous_outfit_image(
    monkeypatch, tmp_path
) -> None:
    service = AdventureService()
    service._images_dir = tmp_path
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    current_path = run_dir / "current.png"
    initial_path = run_dir / "initial.png"
    current_path.write_bytes(b"current")
    initial_path.write_bytes(b"initial")
    run = SimpleNamespace(
        id="run-1",
        state_json=(
            '{"visual_state":{"location":"売り場","appearance":"黒髪",'
            '"clothing":"紺色のドレス","surroundings":"婦人服売り場",'
            '"main_characters":[{"name":"警備員","description":"中年男性",'
            '"clothing":"警備員の制服","action":"招待状を確認する"}]}}'
        ),
        current_image_path=str(current_path),
        initial_image_path=str(initial_path),
        text_model="glm-4-6",
        image_model="nai-diffusion-4-5-full",
        nsfw_mode=False,
        turn_count=1,
    )
    persisted_run = SimpleNamespace(
        id="run-1",
        current_image_path=str(current_path),
        updated_at=None,
        state_json="{}",
    )

    class FakeDatabase:
        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return None

        async def get(self, model, _record_id):
            return persisted_run if model is AdventureRun else None

        async def scalar(self, _statement):
            return None

        async def commit(self):
            return None

    generate_image = AsyncMock(return_value=SimpleNamespace(images=[b"generated"]))
    monkeypatch.setattr(service, "get_run_orm", AsyncMock(return_value=run))
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_user_settings",
        AsyncMock(return_value={"nsfw_mode": False, "language": "ja"}),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.llm_service.generate_text",
        AsyncMock(
            return_value=SimpleNamespace(
                content=make_image_prompt_content(with_guard=True)
            )
        ),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.image_service.generate_image",
        generate_image,
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.async_session_factory", FakeDatabase
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.settings.novelai_model",
        "nai-diffusion-4-5-full",
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.settings.novelai_curated_model",
        "nai-diffusion-4-5-curated",
    )

    await service.generate_image("run-1", redraw_from_reference=True)

    image_kwargs = generate_image.await_args.kwargs
    assert image_kwargs["image_bytes"] is None
    assert image_kwargs["size_override"] == "landscape"
    assert image_kwargs["nsfw_mode"] is False
    assert image_kwargs["novelai_model_override"] == "nai-diffusion-4-5-curated"
    # 既定は精密参照OFF。character_references を付けない
    assert image_kwargs["character_references"] is None
    assert "navy evening dress" in image_kwargs["characters"][0]["prompt"]
    assert image_kwargs["characters"][0]["position"] == (0.55, 0.5)
    assert "security guard uniform" in image_kwargs["characters"][1]["prompt"]
    assert image_kwargs["characters"][1]["position"] == (0.18, 0.5)


@pytest.mark.asyncio
async def test_adventure_image_generation_uses_precise_reference_when_enabled(
    monkeypatch, tmp_path
) -> None:
    service = AdventureService()
    service._images_dir = tmp_path
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    current_path = run_dir / "current.png"
    initial_path = run_dir / "initial.png"
    current_path.write_bytes(b"current")
    initial_path.write_bytes(b"initial")
    run = SimpleNamespace(
        id="run-1",
        state_json=(
            '{"use_precise_reference": true, "visual_state":{"location":"売り場",'
            '"appearance":"黒髪","clothing":"紺色のドレス","surroundings":"婦人服売り場",'
            '"main_characters":[]}}'
        ),
        current_image_path=str(current_path),
        initial_image_path=str(initial_path),
        text_model="glm-4-6",
        image_model="nai-diffusion-4-5-full",
        nsfw_mode=False,
        turn_count=1,
    )
    persisted_run = SimpleNamespace(
        id="run-1",
        current_image_path=str(current_path),
        updated_at=None,
        state_json="{}",
    )

    class FakeDatabase:
        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return None

        async def get(self, model, _record_id):
            return persisted_run if model is AdventureRun else None

        async def scalar(self, _statement):
            return None

        async def commit(self):
            return None

    generate_image = AsyncMock(return_value=SimpleNamespace(images=[b"generated"]))
    monkeypatch.setattr(service, "get_run_orm", AsyncMock(return_value=run))
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_user_settings",
        AsyncMock(return_value={"nsfw_mode": False, "language": "ja"}),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.llm_service.generate_text",
        AsyncMock(
            return_value=SimpleNamespace(
                content=make_image_prompt_content(with_guard=False)
            )
        ),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.image_service.generate_image",
        generate_image,
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.async_session_factory", FakeDatabase
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.settings.novelai_model",
        "nai-diffusion-4-5-full",
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.settings.novelai_curated_model",
        "nai-diffusion-4-5-curated",
    )

    await service.generate_image("run-1", redraw_from_reference=True)

    image_kwargs = generate_image.await_args.kwargs
    assert image_kwargs["character_references"] is not None
    assert image_kwargs["character_references"][0]["type"] == "character"
    assert image_kwargs["character_references"][0]["strength"] == 0.35
    assert image_kwargs["character_references"][0]["fidelity"] == 0.55
    assert image_kwargs["character_references"][0]["image"] == b"initial"


@pytest.mark.asyncio
async def test_update_run_settings_toggles_precise_reference(monkeypatch) -> None:
    service = AdventureService()
    state = {
        "use_precise_reference": False,
        "choices": [
            {"id": "a", "label": "調べる"},
            {"id": "b", "label": "話す"},
            {"id": "c", "label": "進む"},
        ],
        "clues": [],
        "milestones": [],
        "completed_milestones": [],
        "opening_narrative": "開始",
        "visual_state": {"location": "room", "appearance": "1girl"},
    }
    run = SimpleNamespace(
        id="run-1",
        source_session_id=None,
        source_history_id=None,
        preset="escape",
        title="テスト",
        objective="脱出",
        constraints_json="[]",
        status="active",
        turn_count=0,
        max_turns=8,
        ending_title=None,
        ending_summary=None,
        language="ja",
        current_image_path="current.png",
        initial_image_path="initial.png",
        snapshot_json="{}",
        created_at=None,
        updated_at=None,
        state_json=__import__("json").dumps(state, ensure_ascii=False),
        turns=[],
    )
    persisted = SimpleNamespace(
        id="run-1",
        state_json=run.state_json,
        updated_at=None,
    )

    class FakeDatabase:
        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return None

        async def get(self, model, record_id):
            if model is AdventureRun and record_id == "run-1":
                return persisted
            return None

        async def commit(self):
            return None

    monkeypatch.setattr(service, "get_run_orm", AsyncMock(return_value=run))
    monkeypatch.setattr(
        "gateway.services.adventure_service.async_session_factory", FakeDatabase
    )

    result = await service.update_run_settings(
        "run-1", use_precise_reference=True, enable_composite_scene=True
    )

    assert result["use_precise_reference"] is True
    assert result["enable_composite_scene"] is True
    saved = __import__("json").loads(persisted.state_json)
    assert saved["use_precise_reference"] is True
    assert saved["enable_composite_scene"] is True


@pytest.mark.asyncio
async def test_generate_portrait_uses_portrait_size_and_no_characters(
    monkeypatch, tmp_path
) -> None:
    service = AdventureService()
    service._images_dir = tmp_path
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    initial_path = run_dir / "initial.png"
    initial_path.write_bytes(b"initial")
    run = SimpleNamespace(
        id="run-1",
        state_json=(
            '{"use_precise_reference": false, "visual_state":{"location":"売り場",'
            '"appearance":"黒髪","clothing":"紺色のドレス","surroundings":"婦人服売り場",'
            '"main_characters":[]}}'
        ),
        current_image_path=str(initial_path),
        initial_image_path=str(initial_path),
        text_model="glm-4-6",
        image_model="nai-diffusion-4-5-full",
        nsfw_mode=False,
        turn_count=1,
    )
    persisted_run = SimpleNamespace(
        id="run-1",
        portrait_image_path=None,
        updated_at=None,
        state_json="{}",
    )

    class FakeDatabase:
        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return None

        async def get(self, model, _record_id):
            return persisted_run if model is AdventureRun else None

        async def scalar(self, _statement):
            return None

        async def commit(self):
            return None

    generate_image = AsyncMock(return_value=SimpleNamespace(images=[b"portrait"]))
    monkeypatch.setattr(service, "get_run_orm", AsyncMock(return_value=run))
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_user_settings",
        AsyncMock(return_value={"nsfw_mode": False, "language": "ja"}),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.llm_service.generate_text",
        AsyncMock(
            return_value=SimpleNamespace(
                content=make_image_prompt_content(with_guard=True)
            )
        ),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.image_service.generate_image",
        generate_image,
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.async_session_factory", FakeDatabase
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.settings.novelai_model",
        "nai-diffusion-4-5-full",
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.settings.novelai_curated_model",
        "nai-diffusion-4-5-curated",
    )

    portrait_path, _ = await service._generate_portrait_unlocked(
        "run-1", None, redraw_from_reference=True, turn_number=1
    )

    image_kwargs = generate_image.await_args.kwargs
    assert image_kwargs["image_bytes"] is None
    assert image_kwargs["characters"] is None
    assert image_kwargs["size_override"] == "portrait"
    assert image_kwargs["character_references"] is None
    assert portrait_path.name.startswith("portrait-1-")
    assert persisted_run.portrait_image_path == str(portrait_path)


@pytest.mark.asyncio
async def test_generate_portrait_uses_precise_reference_when_enabled(
    monkeypatch, tmp_path
) -> None:
    service = AdventureService()
    service._images_dir = tmp_path
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    initial_path = run_dir / "initial.png"
    initial_path.write_bytes(b"initial")
    run = SimpleNamespace(
        id="run-1",
        state_json=(
            '{"use_precise_reference": true, "visual_state":{"location":"売り場",'
            '"appearance":"黒髪","clothing":"紺色のドレス","surroundings":"婦人服売り場",'
            '"main_characters":[]}}'
        ),
        current_image_path=str(initial_path),
        initial_image_path=str(initial_path),
        text_model="glm-4-6",
        image_model="nai-diffusion-4-5-full",
        nsfw_mode=False,
        turn_count=1,
    )
    persisted_run = SimpleNamespace(
        id="run-1",
        portrait_image_path=None,
        updated_at=None,
        state_json="{}",
    )

    class FakeDatabase:
        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return None

        async def get(self, model, _record_id):
            return persisted_run if model is AdventureRun else None

        async def scalar(self, _statement):
            return None

        async def commit(self):
            return None

    generate_image = AsyncMock(return_value=SimpleNamespace(images=[b"portrait"]))
    monkeypatch.setattr(service, "get_run_orm", AsyncMock(return_value=run))
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_user_settings",
        AsyncMock(return_value={"nsfw_mode": False, "language": "ja"}),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.llm_service.generate_text",
        AsyncMock(
            return_value=SimpleNamespace(
                content=make_image_prompt_content(with_guard=False)
            )
        ),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.image_service.generate_image",
        generate_image,
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.async_session_factory", FakeDatabase
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.settings.novelai_model",
        "nai-diffusion-4-5-full",
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.settings.novelai_curated_model",
        "nai-diffusion-4-5-curated",
    )

    await service._generate_portrait_unlocked(
        "run-1", None, redraw_from_reference=True, turn_number=1
    )

    image_kwargs = generate_image.await_args.kwargs
    assert image_kwargs["character_references"] is not None
    assert image_kwargs["character_references"][0]["image"] == b"initial"
    assert image_kwargs["character_references"][0]["strength"] == 0.35


@pytest.mark.asyncio
async def test_generate_background_image_persists_path_once(
    monkeypatch, tmp_path
) -> None:
    service = AdventureService()
    service._images_dir = tmp_path
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    run = SimpleNamespace(id="run-1")
    persisted_run = SimpleNamespace(
        id="run-1", background_image_path=None, updated_at=None
    )

    class FakeDatabase:
        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return None

        async def get(self, model, _record_id):
            return persisted_run if model is AdventureRun else None

        async def commit(self):
            return None

    generate_scenery = AsyncMock(return_value=SimpleNamespace(images=[b"bg"]))
    monkeypatch.setattr(service, "get_run_orm", AsyncMock(return_value=run))
    monkeypatch.setattr(
        "gateway.services.adventure_service.image_service.generate_scenery",
        generate_scenery,
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.async_session_factory", FakeDatabase
    )

    background_path = await service._generate_background_image_unlocked(
        "run-1", scene_tags="scenery tags", nsfw_mode=False
    )

    scenery_kwargs = generate_scenery.await_args.kwargs
    assert scenery_kwargs["provider_override"] == "novelai"
    assert scenery_kwargs["include_people"] is False
    assert background_path.name == "background.png"
    assert persisted_run.background_image_path == str(background_path)


def test_serialize_run_defaults_enable_composite_scene_true_for_legacy_runs() -> None:
    """state_json に enable_composite_scene が無い旧runは合成モード扱いとする。"""
    service = AdventureService()
    run = SimpleNamespace(
        id="run-legacy",
        source_session_id=None,
        source_history_id=None,
        preset="escape",
        title="テスト",
        objective="脱出する",
        constraints_json="[]",
        status="active",
        turn_count=0,
        max_turns=8,
        ending_title=None,
        ending_summary=None,
        language="ja",
        current_image_path="current.png",
        initial_image_path="initial.png",
        snapshot_json="{}",
        created_at=None,
        updated_at=None,
        state_json="{}",
    )

    payload = service._serialize_run(run, [], include_snapshot=False)

    assert payload["enable_composite_scene"] is True
    assert payload["background_image_url"] is None
    assert payload["portrait_image_url"] is None
    # 人称も旧runでは従来どおりの二人称へ倒す
    assert payload["narration_voice"] == "second_person"
    assert payload["narration_pronoun"] == "僕"


@pytest.mark.asyncio
async def test_princess_room_image_generation_merges_authored_scene_tags(
    monkeypatch, tmp_path
) -> None:
    service = AdventureService()
    service._images_dir = tmp_path
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    current_path = run_dir / "current.png"
    initial_path = run_dir / "initial.png"
    current_path.write_bytes(b"current")
    initial_path.write_bytes(b"initial")
    authored = SCENARIO_TEMPLATES["princess_locked_room"]["visual_style"]["scene_tags"]
    run = SimpleNamespace(
        id="run-1",
        state_json=__import__("json").dumps(
            {
                "scenario_template_id": "princess_locked_room",
                "authored_scene_tags": authored,
                "visual_state": {
                    "location": "豪邸の豪華な衣装部屋",
                    "appearance": "黒髪",
                    "clothing": "衣服を身につけていない",
                    "surroundings": "ドレスが並ぶ",
                    "main_characters": [],
                },
            },
            ensure_ascii=False,
        ),
        current_image_path=str(current_path),
        initial_image_path=str(initial_path),
        text_model="glm-4-6",
        image_model="nai-diffusion-4-5-full",
        nsfw_mode=False,
        turn_count=0,
    )
    persisted_run = SimpleNamespace(
        id="run-1",
        current_image_path=str(current_path),
        updated_at=None,
        state_json=run.state_json,
    )

    class FakeDatabase:
        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return None

        async def get(self, model, _record_id):
            return persisted_run if model is AdventureRun else None

        async def scalar(self, _statement):
            return None

        async def commit(self):
            return None

    generate_image = AsyncMock(return_value=SimpleNamespace(images=[b"generated"]))
    monkeypatch.setattr(service, "get_run_orm", AsyncMock(return_value=run))
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_user_settings",
        AsyncMock(return_value={"nsfw_mode": True, "language": "ja"}),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.llm_service.generate_text",
        AsyncMock(
            return_value=SimpleNamespace(
                content=__import__("json").dumps(
                    {
                        "scene_tags": "cold sealed room, fluorescent light",
                        "player_tags": "1girl, nude, embarrassed",
                        "npc_tags": [],
                    }
                )
            )
        ),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.image_service.generate_image",
        generate_image,
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.async_session_factory", FakeDatabase
    )

    await service.generate_image("run-1", redraw_from_reference=True)

    scene_prompt = generate_image.await_args.args[0]
    assert "luxurious palace dressing room" in scene_prompt
    assert "crystal chandelier" in scene_prompt
    # solo シーンでは主人公タグが base プロンプト先頭に来て、
    # authored シーンタグはその後ろに保持される
    assert scene_prompt.startswith("1girl")
    assert scene_prompt.index("1girl") < scene_prompt.index(authored.split(",")[0])
    assert generate_image.await_args.kwargs["nsfw_mode"] is True
    negative = generate_image.await_args.kwargs["negative_prompt"] or ""
    # 未装備アイテムを打ち消す negative が載ること
    assert "panties" in negative
    # 追加 negative を渡してもプロバイダ既定の品質UCが消えないこと
    assert "lowres" in negative


@pytest.mark.asyncio
async def test_image_provider_failure_is_retryable_adventure_error(
    monkeypatch, tmp_path
) -> None:
    service = AdventureService()
    current_path = tmp_path / "current.png"
    initial_path = tmp_path / "initial.png"
    current_path.write_bytes(b"current")
    initial_path.write_bytes(b"initial")
    run = SimpleNamespace(
        id="run-1",
        state_json='{"visual_state":{"location":"売り場"}}',
        current_image_path=str(current_path),
        initial_image_path=str(initial_path),
        text_model="glm-4-6",
        image_model="nai-diffusion-4-5-full",
        nsfw_mode=False,
        turn_count=1,
    )
    mark_failed = AsyncMock()
    monkeypatch.setattr(service, "get_run_orm", AsyncMock(return_value=run))
    monkeypatch.setattr(service, "_mark_image_failed", mark_failed)
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_user_settings",
        AsyncMock(return_value={"nsfw_mode": False, "language": "ja"}),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.llm_service.generate_text",
        AsyncMock(return_value=SimpleNamespace(content=make_image_prompt_content())),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.image_service.generate_image",
        AsyncMock(side_effect=RuntimeError("Server error: 500")),
    )

    with pytest.raises(AdventureError) as caught:
        await service.generate_image("run-1", "turn-1")

    assert caught.value.code == "image_generation_failed"
    mark_failed.assert_awaited_once_with("run-1", "turn-1")


@pytest.mark.asyncio
async def test_current_snapshot_uses_current_image_history_appearance(
    monkeypatch, tmp_path
) -> None:
    service = AdventureService()
    image_path = tmp_path / "current.png"
    image_path.write_bytes(b"image")
    history = SimpleNamespace(
        image_path=str(image_path),
        after_description=(
            '```json\n{"character":"1girl, short black hair, black eyes, red dress",'
            '"scene":"closet"}\n```'
        ),
        before_description="",
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_session_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                id="session-1",
                user_id=DEFAULT_USER_ID,
                current_image_path=str(image_path),
            )
        ),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_history",
        AsyncMock(return_value=[history]),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_session_timeline_until",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_session_attributes",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_session_stats",
        AsyncMock(return_value=None),
    )

    snapshot, resolved_image, appearance, _ = await service._build_snapshot(
        "session-1", None
    )

    assert resolved_image == image_path
    assert appearance == "1girl, short black hair, black eyes"
    assert snapshot["appearance"] == appearance
    assert snapshot["clothing"] == "red dress"


@pytest.mark.asyncio
async def test_history_snapshot_excludes_future_attributes(
    monkeypatch, tmp_path
) -> None:
    service = AdventureService()
    image_path = tmp_path / "source.png"
    image_path.write_bytes(b"image")
    branch_at = datetime.now()
    stats = SimpleNamespace(
        bloom=10,
        shame=20,
        adaptation=5,
        difficulty="normal",
        nsfw_mode=False,
    )
    history = SimpleNamespace(
        id="history-1",
        session_id="session-1",
        created_at=branch_at,
        after_description="青い制服姿",
        before_description="",
    )

    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_session_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                id="session-1",
                user_id=DEFAULT_USER_ID,
                current_image_path=str(image_path),
            )
        ),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_history_by_id",
        AsyncMock(return_value=history),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.resolve_history_image_file",
        lambda _history: image_path,
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_session_timeline_until",
        AsyncMock(return_value=[("action", "扉を調べる")]),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_session_attributes",
        AsyncMock(
            return_value=[
                {
                    "attribute_text": "青い制服",
                    "created_at": (branch_at - timedelta(seconds=1)).isoformat(),
                },
                {
                    "attribute_text": "未来の属性",
                    "created_at": (branch_at + timedelta(seconds=1)).isoformat(),
                },
            ]
        ),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.get_session_stats",
        AsyncMock(return_value=stats),
    )
    monkeypatch.setattr(
        "gateway.services.adventure_service.session_store.reconstruct_stats_at_history",
        AsyncMock(return_value=stats),
    )

    snapshot, resolved_image, appearance, nsfw_mode = await service._build_snapshot(
        "session-1", "history-1"
    )

    assert resolved_image == image_path
    assert appearance == "青い制服姿"
    assert snapshot["attributes"] == ["青い制服"]
    assert snapshot["timeline"] == [{"type": "action", "text": "扉を調べる"}]
    assert "feeling_text" not in snapshot
    assert nsfw_mode is False


@pytest.mark.asyncio
async def test_source_deletion_keeps_adventure_run_and_run_deletion_removes_turn(
    tmp_path,
) -> None:
    database_path = tmp_path / "adventure.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as database:
        database.add_all(
            [
                User(id="user-1"),
                Session(
                    id="session-1",
                    user_id="user-1",
                    current_image_path="source.png",
                ),
            ]
        )
        await database.flush()
        database.add(
            History(
                id="history-1",
                session_id="session-1",
                instruction="開始地点",
                image_path="source.png",
            )
        )
        await database.flush()
        database.add(
            AdventureRun(
                id="run-1",
                user_id="user-1",
                source_session_id="session-1",
                source_history_id="history-1",
                preset="infiltration",
                title="潜入",
                objective="目的地へ入る",
                constraints_json="[]",
                snapshot_json="{}",
                state_json="{}",
                current_image_path="adventure/current.png",
                initial_image_path="adventure/initial.png",
                text_model="glm-4-6",
                image_provider="novelai",
                image_model="nai-diffusion-4-5-full",
            )
        )
        await database.flush()
        database.add(
            AdventureTurn(
                id="turn-1",
                run_id="run-1",
                client_turn_id="client-turn-1",
                turn_number=1,
                user_input="進む",
                input_kind="free_text",
                narrative="扉の前へ進んだ。",
            )
        )
        await database.commit()

        await database.execute(delete(Session).where(Session.id == "session-1"))
        await database.commit()
        database.expire_all()

        saved_run = await database.scalar(
            select(AdventureRun).where(AdventureRun.id == "run-1")
        )
        saved_turn = await database.scalar(
            select(AdventureTurn).where(AdventureTurn.id == "turn-1")
        )
        assert saved_run is not None
        assert saved_run.source_session_id is None
        assert saved_run.source_history_id is None
        assert saved_run.initial_image_path == "adventure/initial.png"
        assert saved_turn is not None

        await database.execute(delete(AdventureRun).where(AdventureRun.id == "run-1"))
        await database.commit()
        assert (
            await database.scalar(
                select(AdventureTurn).where(AdventureTurn.id == "turn-1")
            )
            is None
        )

    await engine.dispose()


def test_equipment_score_choices_initial_prefers_wear_and_explore() -> None:
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    state = {
        "template_state": {
            "worn_items": [],
            "flags": {},
            "score": 0,
            "rule_read": False,
        }
    }
    choices = _equipment_score_choices(template, state, "ja")
    assert choices is not None
    assert len(choices) == 3
    assert choices[0]["label"] == "ショーツを履く"
    assert choices[1]["label"] == "ブラジャーをつける"
    assert choices[2]["label"] == "扉の文章を読む"
    assert all("調べる" not in item["label"] for item in choices[:2])


def test_equipment_score_choices_after_rule_read_uses_look_around() -> None:
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    state = {
        "template_state": {
            "worn_items": ["panties", "bra"],
            "flags": {"rule_read": True},
            "score": 0,
            "rule_read": True,
        }
    }
    choices = _equipment_score_choices(template, state, "ja")
    assert choices is not None
    labels = [item["label"] for item in choices]
    assert labels[0] == "エレガントなプリンセスドレスを着る"
    assert labels[1] == "ティアラをつける"
    assert labels[2] == "部屋を見回す"


def test_equipment_score_choices_almost_complete_offers_pad_and_door() -> None:
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    state = {
        "template_state": {
            "worn_items": ["panties", "bra", "dress", "tiara"],
            "flags": {"rule_read": True},
            "score": 90,
            "rule_read": True,
        }
    }
    choices = _equipment_score_choices(template, state, "ja")
    assert choices is not None
    labels = [item["label"] for item in choices]
    assert labels[0] == "ナプキンをつける"
    assert "扉" in labels[1] and "採点" in labels[1]
    assert labels[2] == "部屋を見回す"


def test_equipment_wear_labels_match_equipment_action_parser() -> None:
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    for item in template["rule"]["items"]:
        item_id = item["id"]
        label = item["labels"]["ja"]
        choice_label = _equipment_wear_choice_label(item_id, label, "ja")
        aliases = tuple(item["aliases"])
        assert _last_equipment_action(choice_label, aliases) == "wear", choice_label


def test_enforce_template_output_keeps_authored_event_choices() -> None:
    service = AdventureService()
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    state = {
        "template_state": {
            "worn_items": ["panties", "bra", "dress", "tiara"],
            "flags": {"rule_read": True},
            "score": 90,
            "rule_read": True,
        },
        "appearance_lock": "1boy, short hair",
    }
    output = AdventureDirectorOutput(
        narrative="扉が反応した。",
        choices=[
            AdventureChoice(id="a", label="LLMの選択肢A"),
            AdventureChoice(id="b", label="LLMの選択肢B"),
            AdventureChoice(id="c", label="LLMの選択肢C"),
        ],
        visual_state=AdventureVisualState(
            location="豪邸の衣装部屋",
            appearance="1boy, short hair",
            clothing="ドレス",
        ),
    )
    resolution = {
        "event": "almost_complete",
        "goal_checked": True,
        "worn_items": ["panties", "bra", "dress", "tiara"],
        "score": 90,
    }
    service._enforce_template_output(template, state, output, resolution, "ja")
    labels = [choice.label for choice in output.choices]
    assert labels == [
        "扉の文章をもう一度読む",
        "生理用品の棚を詳しく調べる",
        "身につけた品を確認する",
    ]


def test_enforce_template_output_overrides_llm_with_equipment_choices() -> None:
    service = AdventureService()
    template = SCENARIO_TEMPLATES["princess_locked_room"]
    state = {
        "template_state": {
            "worn_items": [],
            "flags": {},
            "score": 0,
            "rule_read": False,
        },
        "appearance_lock": "1boy, short hair",
    }
    output = AdventureDirectorOutput(
        narrative="部屋で目を覚ました。",
        choices=[
            AdventureChoice(id="a", label="ドレスを調べる"),
            AdventureChoice(id="b", label="下着を調べる"),
            AdventureChoice(id="c", label="鏡を見る"),
        ],
        visual_state=AdventureVisualState(
            location="豪邸の衣装部屋",
            appearance="1boy, short hair",
            clothing="衣服を身につけていない",
        ),
    )
    resolution = {
        "event": "continue",
        "goal_checked": False,
        "worn_items": [],
        "score": 0,
    }
    service._enforce_template_output(template, state, output, resolution, "ja")
    labels = [choice.label for choice in output.choices]
    assert labels == [
        "ショーツを履く",
        "ブラジャーをつける",
        "扉の文章を読む",
    ]


def test_character_reference_strength_keeps_fresh_portrait_strong() -> None:
    # このターンの新衣装で描いた立ち絵を参照する場合は衣装変更でも弱めない
    assert _character_reference_strength(
        outfit_changed=True, has_fresh_portrait=True
    ) == (0.85, 1.0)


def test_character_reference_strength_weakens_only_initial_reference() -> None:
    # 旧衣装の初期画像を参照する場合のみ、衣装変更時に弱参照へ落とす
    assert _character_reference_strength(
        outfit_changed=True, has_fresh_portrait=False
    ) == (0.35, 0.55)
    assert _character_reference_strength(
        outfit_changed=False, has_fresh_portrait=False
    ) == (0.85, 1.0)


def test_scene_base_tags_merge_player_outfit_only_when_solo() -> None:
    solo_prompt = AdventureImagePromptOutput(
        scene_tags="luxury hall, night, warm lighting",
        player_tags="mature woman, navy evening dress",
        npc_tags=[],
    )
    merged = _compose_scene_base_tags(solo_prompt)
    assert merged.startswith("mature woman, navy evening dress")
    assert "luxury hall, night, warm lighting" in merged

    with_npc = AdventureImagePromptOutput(
        scene_tags="luxury hall, night, warm lighting",
        player_tags="mature woman, navy evening dress",
        npc_tags=["security guard uniform"],
    )
    assert _compose_scene_base_tags(with_npc) == "luxury hall, night, warm lighting"


def test_visual_state_clamps_overlong_appearance_instead_of_failing() -> None:
    # LLMが上限超過の文字列を返しても検証エラーでターンを失わず、切り詰めて通す
    long_appearance = ", ".join(f"tag{i:03d}" for i in range(300))
    state = AdventureVisualState(location="部屋", appearance=long_appearance)
    assert 0 < len(state.appearance) <= 1200
    assert state.appearance.startswith("tag000")
    assert not state.appearance.endswith(",")


def test_visual_state_keeps_text_within_limit_unchanged() -> None:
    state = AdventureVisualState(location="部屋", appearance="1girl, short hair")
    assert state.appearance == "1girl, short hair"


def test_image_prompt_output_clamps_overlong_player_tags() -> None:
    long_tags = ", ".join(f"tag{i:03d}" for i in range(300))
    prompt = AdventureImagePromptOutput(scene_tags="room", player_tags=long_tags)
    assert 0 < len(prompt.player_tags) <= 1200
    assert prompt.player_tags.startswith("tag000")


# ---------------------------------------------------------------------------
# 巻き戻しとエピローグ


def test_merge_output_epilogue_ignores_llm_and_turn_limit_endings() -> None:
    service = AdventureService()
    run = make_run(turn_count=7)
    # LLM の failure 申告もターン上限到達も continue に倒す
    _, status, _, _ = service._merge_output(
        run, make_output(completed=[], ending="failure"), 8, epilogue=True
    )
    assert status == "continue"


def test_merge_output_epilogue_keeps_existing_ending_summary() -> None:
    service = AdventureService()
    run = make_run(turn_count=9)
    state = __import__("json").loads(run.state_json)
    state["completed_milestones"] = [
        item["id"] for item in PRESETS["infiltration"]["milestones"]
    ]
    state["ending_summary"] = "確定済みのリザルト"
    _, status, _, _ = service._merge_output(
        run,
        make_output(
            completed=[item["id"] for item in PRESETS["infiltration"]["milestones"]]
        ),
        10,
        state_override=state,
        epilogue=True,
    )
    # 全達成が継続しているだけでは再エンディングせず、リザルトも消さない
    assert status == "continue"
    assert state["ending_summary"] == "確定済みのリザルト"


def test_merge_output_epilogue_reverses_only_on_new_completion() -> None:
    service = AdventureService()
    run = make_run(turn_count=9)
    milestone_ids = [item["id"] for item in PRESETS["infiltration"]["milestones"]]
    state = __import__("json").loads(run.state_json)
    state["completed_milestones"] = milestone_ids[:1]
    _, status, _, _ = service._merge_output(
        run,
        make_output(completed=milestone_ids),
        10,
        state_override=state,
        epilogue=True,
    )
    # エピローグ中に新規で全達成へ遷移したときだけ成功へ逆転する
    assert status == "success"


def _adventure_db_env(tmp_path):
    """一時SQLiteに紐づく engine と sessionmaker を返す。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'adventure.db'}")
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _turn_state(marker: str, **extra) -> dict:
    state = {
        "milestones": PRESETS["infiltration"]["milestones"],
        "completed_milestones": [],
        "clues": [marker],
        "visual_state": {
            "location": marker,
            "appearance": "開始時の姿",
            "clothing": "",
            "surroundings": "",
            "main_characters": [],
        },
        "choices": [
            {"id": f"c-{marker}", "label": f"{marker}を調べる"},
            {"id": f"c-{marker}-2", "label": f"{marker}で話す"},
            {"id": f"c-{marker}-3", "label": f"{marker}から移動する"},
        ],
        "opening_narrative": "開幕",
        "use_precise_reference": False,
        "enable_composite_scene": True,
    }
    state.update(extra)
    return state


async def _seed_rewind_run(session_factory, tmp_path, *, opening_state=None) -> None:
    json = __import__("json")
    async with session_factory() as db:
        db.add(User(id=DEFAULT_USER_ID))
        await db.flush()
        db.add(
            AdventureRun(
                id="run-1",
                user_id=DEFAULT_USER_ID,
                preset="infiltration",
                title="潜入",
                objective="目的地へ入る",
                constraints_json="[]",
                snapshot_json="{}",
                state_json=json.dumps(
                    _turn_state("t3", use_precise_reference=True),
                    ensure_ascii=False,
                ),
                opening_state_json=(
                    json.dumps(opening_state, ensure_ascii=False)
                    if opening_state
                    else None
                ),
                current_image_path=str(tmp_path / "run-1" / "turn-3-c3.png"),
                initial_image_path=str(tmp_path / "run-1" / "initial.png"),
                status="active",
                turn_count=3,
                max_turns=8,
                text_model="glm-4-6",
                image_provider="novelai",
                image_model="nai-diffusion-4-5-full",
            )
        )
        await db.flush()
        for number in (1, 2, 3):
            db.add(
                AdventureTurn(
                    id=f"turn-{number}",
                    run_id="run-1",
                    client_turn_id=f"client-{number}",
                    turn_number=number,
                    user_input=f"行動{number}",
                    input_kind="free_text",
                    narrative=f"ターン{number}の物語",
                    state_delta_json=json.dumps(
                        _turn_state(f"t{number}"), ensure_ascii=False
                    ),
                    image_path=str(tmp_path / "run-1" / f"turn-{number}-c{number}.png"),
                    portrait_image_path=(
                        str(tmp_path / "run-1" / f"portrait-{number}-c{number}.png")
                        if number != 2
                        else None
                    ),
                )
            )
        await db.commit()
    run_dir = tmp_path / "run-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "initial.png",
        "turn-0-open.png",
        "background-abc.png",
        "turn-1-c1.png",
        "turn-2-c2.png",
        "turn-3-c3.png",
        "portrait-1-c1.png",
        "portrait-3-c3.png",
        "partner-3-c3.png",
    ):
        (run_dir / name).write_bytes(b"png")


def _patched_service(monkeypatch, session_factory, tmp_path) -> AdventureService:
    async def _make_tables():
        return None

    monkeypatch.setattr(
        "gateway.services.adventure_service.async_session_factory", session_factory
    )
    service = AdventureService.__new__(AdventureService)
    service._run_locks = __import__("collections").defaultdict(
        __import__("asyncio").Lock
    )
    service._images_dir = tmp_path
    return service


@pytest.mark.asyncio
async def test_rewind_restores_state_and_deletes_later_turns(
    tmp_path, monkeypatch
) -> None:
    engine, session_factory = _adventure_db_env(tmp_path)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await _seed_rewind_run(session_factory, tmp_path)
    service = _patched_service(monkeypatch, session_factory, tmp_path)

    result = await service.rewind_to_turn("run-1", 1)

    assert result["turn_count"] == 1
    assert [turn["turn_number"] for turn in result["turns"]] == [1]
    assert result["clues"] == ["t1"]
    assert result["visual_state"]["location"] == "t1"
    assert result["choices"][0]["id"] == "c-t1"
    # 画像設定は現在値(use_precise_reference=True)を引き継ぐ
    assert result["use_precise_reference"] is True
    assert result["status"] == "active"
    # 画像は対象手番のものへ戻り、以降の画像だけが消える
    assert result["current_image_url"].endswith("turn-1-c1.png")
    assert (tmp_path / "run-1" / "turn-1-c1.png").exists()
    assert not (tmp_path / "run-1" / "turn-2-c2.png").exists()
    assert not (tmp_path / "run-1" / "turn-3-c3.png").exists()
    assert not (tmp_path / "run-1" / "portrait-3-c3.png").exists()
    assert not (tmp_path / "run-1" / "partner-3-c3.png").exists()
    # 開幕・初期・背景ファイルは保護される
    assert (tmp_path / "run-1" / "turn-0-open.png").exists()
    assert (tmp_path / "run-1" / "initial.png").exists()
    assert (tmp_path / "run-1" / "background-abc.png").exists()
    await engine.dispose()


@pytest.mark.asyncio
async def test_rewind_recovers_missing_portrait_from_earlier_turn(
    tmp_path, monkeypatch
) -> None:
    engine, session_factory = _adventure_db_env(tmp_path)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await _seed_rewind_run(session_factory, tmp_path)
    service = _patched_service(monkeypatch, session_factory, tmp_path)

    # turn 2 は portrait 欠落 → turn 1 の立ち絵で補う
    result = await service.rewind_to_turn("run-1", 2)

    assert result["turn_count"] == 2
    assert result["portrait_image_url"].endswith("portrait-1-c1.png")
    await engine.dispose()


@pytest.mark.asyncio
async def test_rewind_restores_ended_run_to_active(tmp_path, monkeypatch) -> None:
    json = __import__("json")
    engine, session_factory = _adventure_db_env(tmp_path)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await _seed_rewind_run(session_factory, tmp_path)
    async with session_factory() as db:
        run = await db.get(AdventureRun, "run-1")
        run.status = "failure"
        run.ending_title = "ミッション失敗"
        run.ending_summary = "捕まった"
        state = json.loads(run.state_json)
        state["ending_summary"] = "捕まった"
        state["final_status"] = "failure"
        state["epilogue"] = True
        run.state_json = json.dumps(state, ensure_ascii=False)
        await db.commit()
    service = _patched_service(monkeypatch, session_factory, tmp_path)

    result = await service.rewind_to_turn("run-1", 2)

    assert result["status"] == "active"
    assert result["ending_title"] is None
    assert result["ending_summary"] is None
    assert result["epilogue"] is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_rewind_keeps_final_status_recorded_in_target_turn(
    tmp_path, monkeypatch
) -> None:
    json = __import__("json")
    engine, session_factory = _adventure_db_env(tmp_path)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await _seed_rewind_run(session_factory, tmp_path)
    async with session_factory() as db:
        # turn 2 をエンディング(failure)確定後のエピローグターンに見立てる
        turn = await db.get(AdventureTurn, "turn-2")
        state = json.loads(turn.state_delta_json)
        state["final_status"] = "failure"
        state["final_ending_title"] = "ミッション失敗"
        state["ending_summary"] = "捕まった"
        state["epilogue"] = True
        turn.state_delta_json = json.dumps(state, ensure_ascii=False)
        run = await db.get(AdventureRun, "run-1")
        run.status = "failure"
        await db.commit()
    service = _patched_service(monkeypatch, session_factory, tmp_path)

    result = await service.rewind_to_turn("run-1", 2)

    assert result["status"] == "failure"
    assert result["ending_title"] == "ミッション失敗"
    assert result["ending_summary"] == "捕まった"
    assert result["epilogue"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_rewind_noop_and_invalid_turn_numbers(tmp_path, monkeypatch) -> None:
    engine, session_factory = _adventure_db_env(tmp_path)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await _seed_rewind_run(session_factory, tmp_path)
    service = _patched_service(monkeypatch, session_factory, tmp_path)

    noop = await service.rewind_to_turn("run-1", 3)
    assert noop["turn_count"] == 3
    assert len(noop["turns"]) == 3

    with pytest.raises(AdventureError) as negative:
        await service.rewind_to_turn("run-1", -1)
    assert negative.value.code == "invalid_turn_number"
    with pytest.raises(AdventureError) as beyond:
        await service.rewind_to_turn("run-1", 4)
    assert beyond.value.code == "invalid_turn_number"
    await engine.dispose()


@pytest.mark.asyncio
async def test_rewind_to_opening_requires_snapshot(tmp_path, monkeypatch) -> None:
    engine, session_factory = _adventure_db_env(tmp_path)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await _seed_rewind_run(session_factory, tmp_path)
    service = _patched_service(monkeypatch, session_factory, tmp_path)

    listed = await service.rewind_to_turn("run-1", 3)
    assert listed["can_rewind_to_opening"] is False
    with pytest.raises(AdventureError) as error:
        await service.rewind_to_turn("run-1", 0)
    assert error.value.code == "opening_state_unavailable"
    await engine.dispose()


@pytest.mark.asyncio
async def test_rewind_to_opening_restores_snapshot(tmp_path, monkeypatch) -> None:
    engine, session_factory = _adventure_db_env(tmp_path)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    opening = {
        "state": _turn_state("opening"),
        "current_image_path": str(tmp_path / "run-1" / "turn-0-open.png"),
        "portrait_image_path": None,
        "background_image_path": None,
    }
    await _seed_rewind_run(session_factory, tmp_path, opening_state=opening)
    service = _patched_service(monkeypatch, session_factory, tmp_path)

    result = await service.rewind_to_turn("run-1", 0)

    assert result["can_rewind_to_opening"] is True
    assert result["turn_count"] == 0
    assert result["turns"] == []
    assert result["visual_state"]["location"] == "opening"
    assert result["current_image_url"].endswith("turn-0-open.png")
    await engine.dispose()


@pytest.mark.asyncio
async def test_start_epilogue_validation_and_idempotency(tmp_path, monkeypatch) -> None:
    engine, session_factory = _adventure_db_env(tmp_path)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await _seed_rewind_run(session_factory, tmp_path)
    service = _patched_service(monkeypatch, session_factory, tmp_path)

    # 進行中の run には付与できない
    with pytest.raises(AdventureError) as active:
        await service.start_epilogue("run-1")
    assert active.value.code == "run_not_completed"

    async with session_factory() as db:
        run = await db.get(AdventureRun, "run-1")
        run.status = "failure"
        run.ending_title = "ミッション失敗"
        await db.commit()

    first = await service.start_epilogue("run-1")
    assert first["epilogue"] is True
    assert first["status"] == "failure"
    assert first["ending_title"] == "ミッション失敗"
    # 二重付与は no-op 成功
    second = await service.start_epilogue("run-1")
    assert second["epilogue"] is True
    await engine.dispose()
