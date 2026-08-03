from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gateway.databases.models import (
    AdventureRun,
    AdventureTurn,
    Base,
    History,
    Session,
    User,
)
from gateway.services.adventure_service import (
    AdventureChoice,
    AdventureDirectorOutput,
    AdventureError,
    AdventureService,
    AdventureVisualState,
    PRESETS,
    SCENARIO_TEMPLATES,
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

    setup = await service.generate_setup(
        source_session_id="session-1", source_history_id=None, preset=preset
    )

    prompt = __import__("json").loads(generated.await_args.args[1])
    assert prompt["preset"] == preset
    assert (
        prompt["mission_definition"]["default_objective"]
        == PRESETS[preset]["objective"]
    )
    assert setup["objective"] == "8手以内に保管庫から青い契約書を確保して正門を出る"
    assert len(setup["constraints"]) == 2
    assert "observable end condition" in service._setup_system_prompt("ja")


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
            "title": "プリンセスにならないと出られない部屋",
            "synopsis": SCENARIO_TEMPLATES["princess_locked_room"]["synopsis"]["ja"],
            "setting": SCENARIO_TEMPLATES["princess_locked_room"]["setting"]["ja"],
            "objective": SCENARIO_TEMPLATES["princess_locked_room"]["objective"]["ja"],
            "constraints": SCENARIO_TEMPLATES["princess_locked_room"]["constraints"][
                "ja"
            ],
            "max_turns": 8,
            "content_rating": "mature",
        }
    ]


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

    await service.generate_image("run-1", redraw_from_reference=True)

    image_kwargs = generate_image.await_args.kwargs
    assert image_kwargs["image_bytes"] is None
    assert image_kwargs["size_override"] == "landscape"
    assert image_kwargs["novelai_model_override"] == "nai-diffusion-4-5-full"
    assert image_kwargs["character_references"][0]["type"] == "character"
    assert image_kwargs["character_references"][0]["strength"] == 0.45
    assert image_kwargs["character_references"][0]["fidelity"] == 0.65
    assert "navy evening dress" in image_kwargs["characters"][0]["prompt"]
    assert image_kwargs["characters"][0]["position"] == (0.55, 0.5)
    assert "security guard uniform" in image_kwargs["characters"][1]["prompt"]
    assert image_kwargs["characters"][1]["position"] == (0.18, 0.5)


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
