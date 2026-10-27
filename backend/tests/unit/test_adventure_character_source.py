"""Adventure の開始素材・主人公にキャラクターメイクのキャラクターを使う経路のテスト。"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from gateway.consts.adventure_speech import SPEECH_STYLE_DEFAULT
from gateway.schemas.adventure import (
    AdventureCreateRequest,
    AdventureSetupGenerateRequest,
)
from gateway.services import character_preset_portrait as portrait
from gateway.services import source_snapshot as snap
from gateway.services.adventure_service import (
    _PLAYER_PERSONA_INSTRUCTION,
    AdventureError,
    AdventureService,
    CreateRunRequest,
    _lean_state_for_llm,
    _preset_guidance,
    _preset_objective,
    _prompt_snapshot,
    _turn_style_rules,
    _with_persona_speech,
)

PERSONA_PROFILE = {
    "personality": "負けず嫌いで面倒見がいい",
    "reaction_style": "cheerful",
    "pronoun": "あたし",
    "gender": "woman",
    "interests": ["料理", "ランニング"],
    "tsf_attitude": "",
    "memo": "自動生成の種",
    "speech_style": "砕けた口調で語尾に「〜じゃん」",
    "sample_lines": "やるじゃん！\nまあ、任せときなって。",
    "knowledge": "商店街の定食屋の娘",
    "greeting": "よっ、来たね",
}


def _preset(**overrides):
    values = {
        "id": "preset-1",
        "name": "サクラ",
        "appearance_tags": "long hair, pink hair, school uniform, standing",
        "profile_json": json.dumps(PERSONA_PROFILE, ensure_ascii=False),
        "portrait_path": "portrait.png",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def preset_source(tmp_path: Path, monkeypatch):
    image = tmp_path / "portrait.png"
    image.write_bytes(b"png")

    @asynccontextmanager
    async def _fake_factory():
        yield object()

    monkeypatch.setattr(snap, "async_session_factory", _fake_factory)
    fetch = AsyncMock(return_value=_preset())
    monkeypatch.setattr(snap, "fetch_character_preset", fetch)
    monkeypatch.setattr(portrait, "preset_portrait_file", lambda preset: image)
    return fetch, image


@pytest.mark.asyncio
async def test_build_snapshot_from_character_preset(preset_source):
    _, image = preset_source
    snapshot, image_path, appearance, nsfw = await AdventureService()._build_snapshot(
        None, None, source_character_preset_id="preset-1"
    )
    assert image_path == image
    # 性別トークンを補い、服装と情景のタグは外見から外す
    assert appearance == "1girl, long hair, pink hair"
    assert snapshot["clothing"] == "school uniform"
    assert snapshot["character_name"] == "サクラ"
    assert snapshot["source_character_preset_id"] == "preset-1"
    assert snapshot["source_session_id"] is None
    assert nsfw is False
    persona = snapshot["persona"]
    assert persona["name"] == "サクラ"
    assert persona["pronoun"] == "あたし"
    assert persona["gender"] == "female"
    assert persona["reaction_style"] == "cheerful"
    assert persona["speech_style"] == "砕けた口調で語尾に「〜じゃん」"
    # 自動生成の種と挨拶は物語に使わない。空の項目は省く
    assert "memo" not in persona
    assert "greeting" not in persona
    assert "tsf_attitude" not in persona


@pytest.mark.asyncio
async def test_character_source_takes_priority(preset_source):
    fetch, _ = preset_source
    snapshot, *_ = await AdventureService()._build_snapshot(
        "sess",
        None,
        source_prompt_expander_entry_id="pe-1",
        source_character_preset_id="preset-1",
    )
    assert snapshot["source_character_preset_id"] == "preset-1"
    assert fetch.await_args.args[1] == "preset-1"


@pytest.mark.asyncio
async def test_build_character_snapshot_errors(preset_source, monkeypatch):
    service = AdventureService()
    monkeypatch.setattr(portrait, "preset_portrait_file", lambda preset: None)
    with pytest.raises(AdventureError) as exc:
        await service._build_snapshot(None, None, source_character_preset_id="x")
    assert exc.value.code == "image_not_found"

    monkeypatch.setattr(snap, "fetch_character_preset", AsyncMock(return_value=None))
    with pytest.raises(AdventureError) as exc:
        await service._build_snapshot(None, None, source_character_preset_id="x")
    assert exc.value.code == "source_not_found"


def test_request_models_accept_character_source():
    ok = AdventureCreateRequest(preset="escape", source_character_preset_id="p-1")
    assert ok.source_character_preset_id == "p-1"
    assert (
        AdventureSetupGenerateRequest(
            preset="romance", source_character_preset_id="p-1"
        ).source_character_preset_id
        == "p-1"
    )
    player = AdventureCreateRequest(
        preset="romance",
        source_session_id="sess",
        romance_player_character_preset_id="p-2",
    )
    assert player.romance_player_character_preset_id == "p-2"
    # 主人公の指定だけでは開始素材にならない
    with pytest.raises(ValidationError):
        AdventureCreateRequest(
            preset="romance", romance_player_character_preset_id="p-2"
        )


def test_prompt_snapshot_moves_persona_out_of_source_snapshot():
    snapshot = {"character_name": "サクラ", "appearance": "1girl", "persona": {"a": 1}}
    assert _prompt_snapshot(snapshot, romance=False) == {
        "character_name": "サクラ",
        "appearance": "1girl",
    }
    assert _prompt_snapshot(snapshot, romance=True) == {"appearance": "1girl"}


def test_disguise_switches_to_persona_guidance():
    plain = _preset_guidance("disguise", player_persona=False)
    persona = _preset_guidance("disguise", player_persona=True)
    assert "すでに特定人物の姿へ変身している" in plain
    assert "身体は変身していない" in persona
    assert "player_persona" in persona
    assert "変身後の人物として" in _preset_objective("disguise", player_persona=False)
    assert "なりすます立場" in _preset_objective("disguise", player_persona=True)
    # 専用の指針が無いプリセットは従来どおり
    assert _preset_guidance("escape", player_persona=True) == _preset_guidance(
        "escape", player_persona=False
    )


def test_turn_style_rules_add_persona_only_when_present():
    base = {"player_speech_style": "casual"}
    assert _PLAYER_PERSONA_INSTRUCTION not in _turn_style_rules(base)
    with_persona = _turn_style_rules({**base, "player_persona": {"name": "サクラ"}})
    assert with_persona.startswith("SPEECH REGISTER:")
    assert with_persona.endswith(_PLAYER_PERSONA_INSTRUCTION)
    # 人物設定は毎ターン user prompt の state にも載る
    assert "player_persona" in _lean_state_for_llm({"player_persona": {"a": 1}})


def test_persona_speech_fills_only_default_register():
    persona = {"speech_style": "砕けた口調"}
    request = CreateRunRequest(
        source_session_id=None, source_history_id=None, preset="escape"
    )
    assert request.player_speech_style == SPEECH_STYLE_DEFAULT
    seeded = _with_persona_speech(request, persona)
    assert seeded.player_speech_style == "custom"
    assert seeded.player_speech_custom == "砕けた口調"
    chosen = CreateRunRequest(
        source_session_id=None,
        source_history_id=None,
        preset="escape",
        player_speech_style="formal",
    )
    assert _with_persona_speech(chosen, persona) is chosen
    assert _with_persona_speech(request, {"pronoun": "僕"}) is request


def test_setup_system_prompt_handles_character_sources():
    service = AdventureService()
    romance = service._setup_system_prompt("ja", 20, "romance", partner_character=True)
    assert "use partner_character.name verbatim" in romance
    assert "invent a fitting new name" not in romance
    plain_romance = service._setup_system_prompt("ja", 20, "romance")
    assert "invent a fitting new name" in plain_romance

    persona = service._setup_system_prompt("ja", 20, "disguise", player_persona=True)
    assert "the player IS this person" in persona
    assert "the player has not transformed" in persona
    plain = service._setup_system_prompt("ja", 20, "disguise")
    assert "generate the transformed person's name" in plain
    assert "player_persona" not in plain


def _romance_source(**overrides):
    values = {
        "romance_player_prompt_expander_entry_id": None,
        "romance_player_session_id": None,
        "romance_player_history_id": None,
        "romance_player_character_id": None,
        "romance_player_character_preset_id": None,
        "player_name_override": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _romance_output(**overrides):
    from gateway.services.adventure_romance import RomanceSetupOutput

    values = {
        "partner_name": "LLMが考えた名前",
        "partner_profile": "駅前の花屋で働いている",
        "partner_speech_style": "丁寧語",
        "relationship_origin": "常連客",
        "job_name": "花屋",
        "gift_catalog": [
            {"name": f"品{index}", "price": 1000, "tier": "budget"}
            for index in range(8)
        ],
    }
    values.update(overrides)
    return RomanceSetupOutput.model_validate(values)


@pytest.mark.asyncio
async def test_setup_romance_uses_character_as_player(monkeypatch, tmp_path):
    service = AdventureService()
    persona = {"name": "ユウ", "pronoun": "僕", "personality": "穏やか"}
    build_snapshot = AsyncMock(
        return_value=(
            {"character_name": "ユウ", "clothing": "hoodie", "persona": persona},
            tmp_path / "yu.png",
            "1boy, black hair",
            False,
        )
    )
    monkeypatch.setattr(service, "_build_snapshot", build_snapshot)
    generate = AsyncMock(return_value=_romance_output())
    monkeypatch.setattr(service, "_generate_structured_output", generate)

    romance = await service._setup_romance(
        _romance_source(romance_player_character_preset_id="preset-yu"),
        SimpleNamespace(companion_mode=False, romance_partner_speech_style=""),
        SimpleNamespace(max_turns=20, setting="", objective="", constraints=[]),
        snapshot={"appearance": "1girl"},
        partner_appearance="1girl",
        partner_image=tmp_path / "partner.png",
        text_model="glm-4-6",
        language="ja",
    )

    assert build_snapshot.await_args.kwargs == {
        "source_character_preset_id": "preset-yu"
    }
    assert romance.player_ref == "character:preset-yu"
    assert romance.player_name == "ユウ"
    assert romance.player_clothing == "hoodie"
    assert romance.player_persona == persona
    payload = json.loads(generate.await_args.kwargs["user_prompt"])
    assert payload["player_persona"] == persona
    assert "partner_character" not in payload
    # 攻略対象はセッション素材のままなので、LLM が考えた名前を使う
    assert romance.setup.partner_name == "LLMが考えた名前"


@pytest.mark.asyncio
async def test_setup_romance_fixes_character_partner(monkeypatch, tmp_path):
    service = AdventureService()
    generate = AsyncMock(return_value=_romance_output())
    monkeypatch.setattr(service, "_generate_structured_output", generate)
    persona = {
        "name": "サクラ",
        "pronoun": "あたし",
        "personality": "負けず嫌い",
        "speech_style": "砕けた口調",
        "sample_lines": "やるじゃん！",
    }
    snapshot = {
        "character_name": "サクラ",
        "appearance": "1girl, pink hair",
        "persona": persona,
        "source_character_preset_id": "preset-1",
    }

    async def run(partner_speech: str):
        return await service._setup_romance(
            _romance_source(),
            SimpleNamespace(
                companion_mode=False, romance_partner_speech_style=partner_speech
            ),
            SimpleNamespace(max_turns=20, setting="", objective="", constraints=[]),
            snapshot=snapshot,
            partner_appearance="1girl, pink hair",
            partner_image=tmp_path / "partner.png",
            text_model="glm-4-6",
            language="ja",
        )

    romance = await run("")
    # 名前とプロフィール先頭の人物設定は LLM 出力によらずキャラクターのもの
    assert romance.setup.partner_name == "サクラ"
    assert romance.setup.partner_profile.startswith("性格=負けず嫌い")
    assert "駅前の花屋で働いている" in romance.setup.partner_profile
    # 口調はキャラクターのものを使い、書かれていない一人称を補う
    assert romance.partner_speech_style == "一人称は「あたし」。砕けた口調"
    assert romance.partner_sample_lines == "やるじゃん！"
    payload = json.loads(generate.await_args.kwargs["user_prompt"])
    assert payload["partner_character"] == {"name": "サクラ", "persona": persona}
    assert "persona" not in payload["source_snapshot"]
    assert "character_name" not in payload["source_snapshot"]
    assert (
        "partner_character.name exactly" in generate.await_args.kwargs["system_prompt"]
    )

    # セットアップで書いた口調はキャラクターの口調より優先する
    overridden = await run("敬語で話す")
    assert overridden.partner_speech_style == "敬語で話す"


@pytest.mark.asyncio
async def test_romance_replay_restores_character_partner(monkeypatch):
    service = AdventureService()
    replay_run = SimpleNamespace(
        state_json=json.dumps({"sim": {"player_character_id": "character:preset-yu"}}),
        snapshot_json=json.dumps({"source_character_preset_id": "preset-1"}),
        preset="romance",
        source_prompt_expander_entry_id=None,
        source_session_id=None,
        source_history_id=None,
    )
    monkeypatch.setattr(service, "get_run_orm", AsyncMock(return_value=replay_run))
    source = await service._resolve_scenario_source(
        CreateRunRequest(
            source_session_id="current-sess",
            source_history_id=None,
            preset="romance",
            replay_run_id="run-1",
        )
    )
    assert source.source_character_preset_id == "preset-1"
    assert source.source_session_id is None
    assert source.romance_player_character_preset_id == "preset-yu"


@pytest.mark.asyncio
async def test_create_run_applies_character_persona(monkeypatch, tmp_path):
    """恋愛以外でキャラクターを開始素材にすると、主人公がその人物本人になる。"""
    from gateway.services import adventure_service as module

    service = AdventureService()
    persona = {"name": "サクラ", "pronoun": "あたし", "speech_style": "砕けた口調"}
    snapshot = {
        "character_name": "サクラ",
        "appearance": "1girl, pink hair",
        "clothing": "school uniform",
        "persona": persona,
        "source_character_preset_id": "preset-1",
    }
    monkeypatch.setattr(
        service,
        "_build_snapshot",
        AsyncMock(return_value=(snapshot, tmp_path / "p.png", "1girl", False)),
    )
    monkeypatch.setattr(
        module.session_store, "get_user_settings", AsyncMock(return_value={})
    )
    director = AsyncMock(
        return_value=SimpleNamespace(
            visual_state=SimpleNamespace(appearance="", clothing="")
        )
    )
    monkeypatch.setattr(service, "_generate_director_output", director)
    monkeypatch.setattr(
        service, "_copy_opening_images", lambda *args: (tmp_path / "i.png", None)
    )
    captured: dict = {}

    def build_state(*args, **kwargs):
        captured["request"] = args[1]
        captured["definition"] = args[2]
        captured["persona"] = kwargs["player_persona"]
        return {}

    monkeypatch.setattr(service, "_build_initial_state", build_state)
    monkeypatch.setattr(service, "_persist_new_run", AsyncMock())
    monkeypatch.setattr(service, "_generate_opening_visuals", AsyncMock())
    monkeypatch.setattr(service, "get_run", AsyncMock(return_value={"id": "r"}))

    await service.create_run(
        source_session_id=None,
        source_history_id=None,
        preset="disguise",
        source_character_preset_id="preset-1",
    )

    assert captured["persona"] == persona
    # 口調が既定のままなので、キャラクターの口調を自由入力として使う
    assert captured["request"].player_speech_style == "custom"
    assert captured["request"].player_speech_custom == "砕けた口調"
    assert "身体は変身していない" in captured["definition"].scenario_guidance
    assert "なりすます立場" in captured["definition"].objective
    kwargs = director.await_args.kwargs
    assert kwargs["speech_rule"].endswith(_PLAYER_PERSONA_INSTRUCTION)
    prompt = json.loads(kwargs["prompt"])
    assert prompt["player_persona"] == persona
    assert "persona" not in prompt["source_snapshot"]
    assert prompt["source_snapshot"]["character_name"] == "サクラ"
