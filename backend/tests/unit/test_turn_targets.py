"""複数人表示で「指示の対象人物」「立ち位置」「人物ごとのパラメータ」を扱う処理のテスト。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from gateway.services.character_service import (
    CharacterLook,
    TurnTargets,
    apply_stage_positions,
    build_character_states,
    build_novelai_characters_section,
    build_session_characters_prompt_section,
    build_stage_roster,
    default_effect_targets,
    keep_bystander_looks,
    parse_character_states,
    parse_declared_targets,
    resolve_turn_targets,
)
from gateway.services.prompts import build_observer_feeling_prompt


def _rec(
    record_id: str,
    slot_index: int,
    *,
    name: str | None = None,
    tags: str = "",
    position: str = "center",
    is_protagonist: bool = False,
    lock: bool = False,
    exclude: bool = False,
):
    return SimpleNamespace(
        id=record_id,
        slot_index=slot_index,
        name=name or record_id,
        position=position,
        appearance_tags=tags,
        appearance_natural="",
        is_protagonist=is_protagonist,
        on_stage=True,
        negative_tags="",
        profile_json=None,
        appearance_lock=lock,
        exclude_from_effects=exclude,
        appearance_spec_rev=0,
    )


def _trio(*, protagonist_excluded: bool = True, ryo_excluded: bool = True):
    """主人公エミ（左）・リョウ（右）・アヤ（中央）。登録順はエミ→リョウ→アヤ。"""
    return [
        _rec(
            "emi",
            0,
            name="エミ",
            tags="1girl, brown hair, bob cut, white t-shirt",
            position="left",
            is_protagonist=True,
            exclude=protagonist_excluded,
        ),
        _rec(
            "ryo",
            1,
            name="リョウ",
            tags="1boy, black hair, blue suit",
            position="right",
            exclude=ryo_excluded,
        ),
        _rec(
            "aya",
            2,
            name="アヤ",
            tags="1girl, blonde hair, yellow long dress",
            position="center",
        ),
    ]


# ---------------------------------------------------------------------------
# 対象人物の判定
# ---------------------------------------------------------------------------


def test_default_target_is_protagonist_when_it_receives_effects() -> None:
    stage = build_stage_roster(_trio(protagonist_excluded=False))
    assert [m.name for m in default_effect_targets(stage)] == ["エミ"]


def test_default_targets_move_to_everyone_eligible_when_protagonist_excluded() -> None:
    stage = build_stage_roster(_trio(ryo_excluded=False))
    assert [m.name for m in default_effect_targets(stage)] == ["リョウ", "アヤ"]
    stage = build_stage_roster(_trio())
    assert [m.name for m in default_effect_targets(stage)] == ["アヤ"]


def test_fixed_look_does_not_receive_effects() -> None:
    records = _trio(protagonist_excluded=False)
    records[0].appearance_lock = True
    records[0].exclude_from_effects = False
    stage = build_stage_roster(records)
    assert [m.name for m in default_effect_targets(stage)] == ["アヤ"]


def test_parse_declared_targets_accepts_refs_and_names() -> None:
    stage = build_stage_roster(_trio())
    raw = "```json\n" + json.dumps({"targets": ["C3", "リョウ", "C3"]}) + "\n```"
    assert parse_declared_targets(raw, stage) == [2, 1]
    assert parse_declared_targets(json.dumps({"targets": "C3"}), stage) == [2]


def test_parse_declared_targets_none_when_missing_or_unknown() -> None:
    stage = build_stage_roster(_trio())
    assert parse_declared_targets(json.dumps({"characters": []}), stage) is None
    assert parse_declared_targets(json.dumps({"targets": []}), stage) is None
    assert parse_declared_targets(json.dumps({"targets": ["誰か"]}), stage) is None
    assert parse_declared_targets("1girl, solo", stage) is None
    assert parse_declared_targets(None, stage) is None


def test_resolve_targets_follows_declaration_without_bystanders() -> None:
    stage = build_stage_roster(_trio())
    targets = resolve_turn_targets(stage, [0, 2])
    assert [m.name for m in targets.members] == ["アヤ"]
    assert targets.protagonist is False
    assert [m.name for m in targets.others] == ["アヤ"]


def test_resolve_targets_named_character_even_when_protagonist_eligible() -> None:
    stage = build_stage_roster(_trio(protagonist_excluded=False))
    targets = resolve_turn_targets(stage, [2])
    assert targets.protagonist is False
    assert [m.name for m in targets.members] == ["アヤ"]


def test_resolve_targets_without_declaration_uses_default() -> None:
    stage = build_stage_roster(_trio())
    targets = resolve_turn_targets(stage, None)
    assert [m.name for m in targets.members] == ["アヤ"]
    assert targets.protagonist is False

    stage = build_stage_roster(_trio(protagonist_excluded=False))
    targets = resolve_turn_targets(stage, None)
    assert [m.name for m in targets.members] == ["エミ"]
    assert targets.protagonist is True


def test_resolve_targets_without_stage_keeps_legacy_protagonist() -> None:
    assert resolve_turn_targets((), None) == TurnTargets()
    assert TurnTargets().protagonist is True


# ---------------------------------------------------------------------------
# プロンプトの規則
# ---------------------------------------------------------------------------


def test_image_section_routes_subjectless_instruction_when_protagonist_excluded() -> (
    None
):
    section = build_novelai_characters_section(_trio())
    assert "refer to C1 (the protagonist), who does not receive" in section
    assert "Sentences without a subject" in section
    assert "are about C3: apply them to that character, never to C1." in section
    assert '"targets"' in section
    assert "set to its listed position" in section


def test_image_section_keeps_protagonist_default_when_eligible() -> None:
    section = build_novelai_characters_section(_trio(protagonist_excluded=False))
    assert "sentences without a subject refer to C1 (the protagonist)." in section


def test_image_section_without_anyone_eligible() -> None:
    records = _trio()
    records[2].exclude_from_effects = True
    section = build_novelai_characters_section(records)
    assert "No listed character can receive instruction effects" in section


def test_text_section_names_default_targets_when_protagonist_excluded() -> None:
    section = build_session_characters_prompt_section(_trio(ryo_excluded=False))
    assert "主語のない指示（服装だけの指示など）はリョウ、アヤへの指示" in section
    section = build_session_characters_prompt_section(_trio(protagonist_excluded=False))
    assert "主語のない指示" not in section


# ---------------------------------------------------------------------------
# 指示対象外の姿の維持・立ち位置
# ---------------------------------------------------------------------------


def test_keep_bystander_looks_restores_excluded_characters() -> None:
    looks = {"emi": CharacterLook(tags="1girl, brown hair, red dress", spec_rev=0)}
    stage = build_stage_roster(_trio(), looks=looks)
    characters = [
        {"prompt": "1girl, brown hair, green dress", "stage_index": 0},
        {"prompt": "1boy, black hair, blue suit, waving", "stage_index": 1},
        {"prompt": "1girl, blonde hair, green dress", "stage_index": 2},
        {"prompt": "1girl, waitress", "stage_index": None},
    ]
    result = keep_bystander_looks(characters, stage)
    assert [c["prompt"] for c in result] == [
        "1girl, brown hair, red dress",
        "1boy, black hair, blue suit",
        "1girl, blonde hair, green dress",
        "1girl, waitress",
    ]
    # 元の配列は書き換えない
    assert characters[0]["prompt"] == "1girl, brown hair, green dress"


def test_positions_follow_registered_order_and_enable_coords() -> None:
    stage = build_stage_roster(_trio())
    characters = [
        {"prompt": "emi", "position": (0.5, 0.5), "stage_index": 0},
        {"prompt": "ryo", "position": (0.5, 0.5), "stage_index": 1},
        {"prompt": "aya", "position": (0.7, 0.5), "stage_index": 2},
    ]
    result = apply_stage_positions(characters, stage)
    assert [c["prompt"] for c in result] == ["emi", "aya", "ryo"]
    assert [c["position"] for c in result] == [(0.1, 0.5), (0.5, 0.5), (0.9, 0.5)]
    assert all(c["fixed_position"] for c in result)


def test_positions_without_coords_when_overlapping_or_unlisted() -> None:
    records = _trio()
    records[2].position = "left"
    stage = build_stage_roster(records)
    characters = [
        {"prompt": "emi", "stage_index": 0},
        {"prompt": "ryo", "stage_index": 1},
        {"prompt": "aya", "stage_index": 2},
    ]
    result = apply_stage_positions(characters, stage)
    # 同じ立ち位置どうしは今の順のまま、左から並べる
    assert [c["prompt"] for c in result] == ["emi", "aya", "ryo"]
    assert not any(c.get("fixed_position") for c in result)

    stage = build_stage_roster(_trio())
    result = apply_stage_positions(
        [
            {"prompt": "emi", "stage_index": 0},
            {"prompt": "guest", "position": (0.7, 0.5), "stage_index": None},
        ],
        stage,
    )
    assert not any(c.get("fixed_position") for c in result)


def test_positions_untouched_without_stage() -> None:
    characters = [
        {"prompt": "a", "position": (0.7, 0.5)},
        {"prompt": "b", "position": (0.3, 0.5)},
    ]
    assert apply_stage_positions(characters, ()) == characters


# ---------------------------------------------------------------------------
# 人物ごとのパラメータ
# ---------------------------------------------------------------------------


def test_states_store_stats_for_character_without_recorded_look() -> None:
    stage = build_stage_roster(_trio())
    states = build_character_states(
        [],
        stage,
        None,
        ["emi", "ryo", "aya"],
        stats_updates={
            "aya": {
                "bloom": 3,
                "shame": 45,
                "adaptation": 2,
                "transformation_count": 1,
            }
        },
    )
    assert states == [
        {
            "character_id": "aya",
            "tags": "",
            "spec_rev": 0,
            "stats": {
                "bloom": 3,
                "shame": 45,
                "adaptation": 2,
                "transformation_count": 1,
            },
        }
    ]


def test_states_keep_stats_when_look_is_rewritten() -> None:
    stage = build_stage_roster(_trio())
    stats = {"bloom": 5, "shame": 40, "adaptation": 1, "transformation_count": 2}
    previous = [
        {"character_id": "aya", "tags": "1girl, yellow", "spec_rev": 0, "stats": stats}
    ]
    states = build_character_states(
        previous,
        stage,
        [{"prompt": "1girl, purple dress", "stage_index": 2}],
        ["emi", "ryo", "aya"],
    )
    assert states == [
        {
            "character_id": "aya",
            "tags": "1girl, purple dress",
            "spec_rev": 0,
            "stats": stats,
        }
    ]


def test_parse_states_keeps_and_normalizes_stats() -> None:
    raw = json.dumps(
        [
            {
                "character_id": "aya",
                "tags": "1girl",
                "spec_rev": 0,
                "stats": {"bloom": 7, "shame": "x", "transformation_count": 1},
            },
            {"character_id": "ryo", "tags": "1boy", "spec_rev": 0},
        ]
    )
    entries = parse_character_states(raw)
    assert entries[0]["stats"] == {
        "bloom": 7,
        "shame": 50,
        "adaptation": 0,
        "transformation_count": 1,
    }
    assert "stats" not in entries[1]


# ---------------------------------------------------------------------------
# 主人公が見た反応の心境
# ---------------------------------------------------------------------------


def test_observer_feeling_prompt_describes_others_change() -> None:
    system, user = build_observer_feeling_prompt(
        instruction="アヤを紫のロングワンピースに着せ替える",
        pronoun="僕",
        changes=(("アヤ", "1girl, yellow long dress", "1girl, purple long dress"),),
        protagonist_look="1girl, brown hair, red dress",
        personality="穏やか",
    )
    assert "姿が変わったのは主人公ではなく" in system
    assert "主人公自身が着替えた・着ている・姿が変わったという表現" in system
    assert "【このキャラクターの性格】" in system
    assert "という指示でアヤの衣装が変更された" in user
    assert "「僕」" in user
    assert "- アヤ：1girl, yellow long dress → 1girl, purple long dress" in user
    assert "主人公の今の姿（今回は変化なし）：1girl, brown hair, red dress" in user


def test_observer_feeling_prompt_for_reality_and_unknown_after() -> None:
    _system, user = build_observer_feeling_prompt(
        instruction="アヤに猫耳が生える",
        pronoun="私",
        changes=(("アヤ", "1girl, blonde hair", ""),),
        protagonist_look="",
        is_reality=True,
    )
    assert "という現実改変でアヤが変化した" in user
    assert "- アヤ：1girl, blonde hair（この指示で変化）" in user
