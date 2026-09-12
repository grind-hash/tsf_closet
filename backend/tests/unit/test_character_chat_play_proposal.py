"""おすすめのプレイ(案内役キャラの提案カード)のモデル・カタログ・プロンプト。"""

from __future__ import annotations

import json
import os
import time

import pytest
from pydantic import ValidationError

from gateway.models import Character
from gateway.services import character_chat_play_proposal as proposal_module
from gateway.services import custom_sessions
from gateway.services.character_chat_models import (
    CharacterChatPlan,
    CharacterChatPlayProposal,
)
from gateway.services.character_chat_play_proposal import (
    PlayCatalogEntry,
    build_play_catalog,
    catalog_names,
    catalog_prompt_items,
    grounding_plan,
    play_proposal_meta,
    self_profile_hint,
)
from gateway.services.character_chat_prompts import (
    planner_system_prompt,
    play_proposal_block,
    play_proposal_system_prompt,
    play_proposal_unavailable_block,
    play_proposal_user_prompt,
    reply_system_prompt,
)
from gateway.settings.config import settings

CONTEXT = {
    "catalog": {
        "template:char1": "カナタ",
        "template:char2": "ハルカ",
        "custom:1": "サクラ",
    },
    "self_mode_available": False,
}


def _raw(**overrides) -> str:
    data = {
        "title": "文化祭のメイド喫茶",
        "reason": "着せ替えのプレイが多いので",
        "character_ref": "template:char1",
        "self_mode": False,
        "instruction_type": "dress_up",
        "instruction": "メイド服に着替える",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def _validate(raw: str, **context) -> CharacterChatPlayProposal:
    return CharacterChatPlayProposal.model_validate_json(
        raw, context={**CONTEXT, **context}
    )


# ---------------------------------------------------------------------------
# 提案のモデル
# ---------------------------------------------------------------------------


def test_proposal_accepts_catalog_ref_and_clamps_text() -> None:
    proposal = _validate(_raw(title="あ" * 80, instruction="  メイド服に\n着替える  "))
    assert proposal.character_ref == "template:char1"
    assert len(proposal.title) == 40
    assert proposal.instruction == "メイド服に 着替える"
    assert proposal.self_mode is False


def test_proposal_maps_unique_name_to_ref() -> None:
    assert _validate(_raw(character_ref="サクラ")).character_ref == "custom:1"


@pytest.mark.parametrize("ref", ["template:char9", "custom:2", "", None])
def test_proposal_rejects_unknown_character(ref) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _validate(_raw(character_ref=ref))
    # 修復リトライで直せるよう、使える参照キーを伝える
    assert "template:char1" in str(excinfo.value)


def test_proposal_requires_catalog_context() -> None:
    with pytest.raises(ValidationError):
        CharacterChatPlayProposal.model_validate_json(_raw(), context={})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("dress_up", "dress_up"),
        ("Dress-Up", "dress_up"),
        ("現実改変", "reality_alter"),
        ("talk", "conversation"),
        ("action", "action"),
    ],
)
def test_proposal_normalizes_instruction_type(raw, expected) -> None:
    assert _validate(_raw(instruction_type=raw)).instruction_type == expected


@pytest.mark.parametrize("value", ["image_only", "transform", "", 3])
def test_proposal_rejects_unsupported_instruction_type(value) -> None:
    with pytest.raises(ValidationError):
        _validate(_raw(instruction_type=value))


@pytest.mark.parametrize("field", ["title", "reason", "instruction"])
def test_proposal_rejects_empty_text(field) -> None:
    with pytest.raises(ValidationError):
        _validate(_raw(**{field: "  "}))


def test_proposal_self_mode_only_when_profile_available() -> None:
    assert _validate(_raw(self_mode=True)).self_mode is False
    assert _validate(_raw(self_mode="true"), self_mode_available=True).self_mode is True


def test_plan_play_proposal_coerces_strings() -> None:
    assert CharacterChatPlan.model_validate({"play_proposal": "true"}).play_proposal
    assert not CharacterChatPlan.model_validate({"play_proposal": "no"}).play_proposal
    assert not CharacterChatPlan.model_validate({}).play_proposal


# ---------------------------------------------------------------------------
# カタログ・根拠・保存形
# ---------------------------------------------------------------------------


@pytest.fixture
def history_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "history_images_dir", tmp_path / "history_images")
    return tmp_path / "history_images"


def test_build_play_catalog_lists_templates_then_newest_custom(
    history_dir, monkeypatch
) -> None:
    monkeypatch.setattr(
        proposal_module.character_manager,
        "get_all",
        lambda: [
            Character(
                id="char1",
                name="カナタ",
                image_path="char1.png",
                description="高校生",
                gender="male",
                personality="素直",
            )
        ],
    )
    custom_sessions.save_custom_character(
        "old-id", b"png", {"id": "old-id", "name": "旧", "gender": "woman"}
    )
    custom_sessions.save_custom_character("new-id", b"png", {"id": "new-id"})
    old_png = custom_sessions.custom_character_image_path("old-id")
    os.utime(old_png, (time.time() - 100, time.time() - 100))

    catalog = build_play_catalog()
    assert list(catalog) == ["template:char1", "custom:1", "custom:2"]
    assert catalog["template:char1"].gender == "man"
    assert catalog["custom:1"] == PlayCatalogEntry(
        ref="custom:1",
        source="custom",
        id="new-id",
        name="カスタムキャラクター",
        gender="other",
        personality="",
        description="",
    )
    assert catalog["custom:2"].id == "old-id"
    assert catalog_names(catalog)["custom:2"] == "旧"

    items = catalog_prompt_items(catalog)
    assert items[0] == {
        "ref": "template:char1",
        "kind": "preset",
        "name": "カナタ",
        "starting_gender": "man",
        "description": "高校生",
        "personality": "素直",
    }
    assert items[1]["kind"] == "saved custom"
    # 作成済みキャラの uuid はプロンプトに載せず、連番の参照キーだけを見せる
    assert "new-id" not in json.dumps(items, ensure_ascii=False)

    monkeypatch.setattr(proposal_module, "PLAY_PROPOSAL_CUSTOM_MAX", 1)
    assert list(build_play_catalog()) == ["template:char1", "custom:1"]


def test_grounding_plan_skips_kinds_already_run() -> None:
    plan = grounding_plan(())
    assert [lookup.kind for lookup in plan.lookups] == [
        "tendencies",
        "recent_sessions",
    ]
    assert plan.lookups[1].limit == 5
    assert [lookup.kind for lookup in grounding_plan({"tendencies"}).lookups] == [
        "recent_sessions"
    ]


def test_self_profile_hint() -> None:
    assert self_profile_hint(None) is None
    assert self_profile_hint({}) is None
    assert self_profile_hint({"display_name": "", "interests": []}) is None
    assert self_profile_hint(
        {
            "display_name": "ミナト",
            "gender": "man",
            "pronoun": "僕",
            "interests": ["コスプレ", "", "カフェ"],
        }
    ) == {
        "display_name": "ミナト",
        "gender": "man",
        "interests": ["コスプレ", "カフェ"],
    }


def test_play_proposal_meta_copies_character_from_catalog() -> None:
    proposal = _validate(
        _raw(character_ref="custom:1", instruction_type="reality_alter")
    )
    entry = PlayCatalogEntry(
        ref="custom:1",
        source="custom",
        id="uuid-1",
        name="サクラ",
        gender="woman",
        personality="",
        description="",
    )
    assert play_proposal_meta(proposal, entry) == {
        "kind": "play",
        "title": "文化祭のメイド喫茶",
        "reason": "着せ替えのプレイが多いので",
        "character": {"source": "custom", "id": "uuid-1", "name": "サクラ"},
        "self_mode": False,
        "first_instruction": {
            "instruction_type": "reality_alter",
            "text": "メイド服に着替える",
        },
    }


# ---------------------------------------------------------------------------
# プロンプト
# ---------------------------------------------------------------------------


def test_planner_prompt_offers_play_proposal_for_base_only() -> None:
    prompt = planner_system_prompt("ja")
    assert '"play_proposal": <true|false>' in prompt
    assert '- play_proposal: true ONLY when character_kind is "base"' in prompt


def test_play_proposal_system_prompt_rules() -> None:
    safe = play_proposal_system_prompt("ja", nsfw_mode=False, self_mode_available=False)
    assert safe.startswith("You are the play proposal planner")
    # テストの LLM 差し替えが判定 LLM・着替え LLM と取り違えない
    assert "retrieval planner" not in safe
    assert "appearance tags" not in safe
    assert "non-explicit" in safe
    assert "minors" in safe
    assert "self_mode: always false" in safe
    assert "in Japanese" in safe

    adult = play_proposal_system_prompt("en", nsfw_mode=True, self_mode_available=True)
    assert "non-explicit" not in adult
    assert "minors" in adult
    assert "self_profile" in adult
    assert "self_mode: always false" not in adult
    assert "in English" in adult


def test_play_proposal_user_prompt_payload() -> None:
    payload = json.loads(
        play_proposal_user_prompt(
            characters=[{"ref": "template:char1", "name": "カナタ"}],
            self_profile=None,
            play_records="",
            memory_text="メイド服を好む",
            recent_messages=[{"role": "user", "content": "やあ"}],
            message="おすすめある？",
        )
    )
    assert payload["characters"][0]["ref"] == "template:char1"
    assert payload["self_mode_available"] is False
    assert "self_profile" not in payload
    assert payload["play_records"] == "(no records)"
    assert payload["user_memory"] == "メイド服を好む"
    assert payload["recent_messages"] == [{"role": "user", "content": "やあ"}]
    assert payload["latest_user_message"] == "おすすめある？"

    with_profile = json.loads(
        play_proposal_user_prompt(
            characters=[],
            self_profile={"display_name": "ミナト"},
            play_records="セッション総数: 3",
            memory_text=None,
            recent_messages=[],
            message="おすすめ",
        )
    )
    assert with_profile["self_mode_available"] is True
    assert with_profile["self_profile"] == {"display_name": "ミナト"}
    assert with_profile["play_records"] == "セッション総数: 3"
    assert "user_memory" not in with_profile


def test_play_proposal_blocks() -> None:
    meta = {
        "kind": "play",
        "title": "もしも最初から女の子だったら",
        "reason": "現実改変を試したことが無いので",
        "character": {"source": "custom", "id": "uuid-1", "name": "サクラ"},
        "self_mode": True,
        "first_instruction": {
            "instruction_type": "reality_alter",
            "text": "生まれたときから女の子だったことにする",
        },
    }
    block = play_proposal_block(meta, "ja")
    assert block.startswith("[おすすめのプレイ(提案カード)]")
    assert "サクラ(自分自身モード)" in block
    assert "最初の指示(現実改変): 生まれたときから女の子だったことにする" in block
    assert "現実改変を試したことが無いので" in block

    english = play_proposal_block(meta, "en")
    assert english.startswith("[Recommended play card]")
    assert "reality alteration" in english
    assert "self mode" in english

    failed = play_proposal_unavailable_block("ja")
    assert "用意できませんでした" in failed
    assert "ボタンで始められる" in failed
    assert "no proposal card" in play_proposal_unavailable_block("en")


def test_reply_system_prompt_places_proposal_before_rules() -> None:
    block = play_proposal_unavailable_block("ja")
    prompt = reply_system_prompt(
        "ja",
        name="セレナ",
        pronoun="私",
        persona_block="persona",
        memory_block_text="",
        summary_text=None,
        lookup_block_text="",
        appearance_description="",
        appearance_change_request=None,
        play_proposal_text=block,
    )
    assert block in prompt
    assert prompt.index("[おすすめのプレイ]") < prompt.index("会話のルール")
    assert "[おすすめのプレイ" not in reply_system_prompt(
        "ja",
        name="セレナ",
        pronoun="私",
        persona_block="persona",
        memory_block_text="",
        summary_text=None,
        lookup_block_text="",
        appearance_description="",
        appearance_change_request=None,
    )
