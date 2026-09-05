"""持ち物システム(adventure_inventory)の純関数テスト。"""

import copy

import pytest

from gateway.consts.adventure_inventory import (
    INVENTORY_ITEMS_MAX,
    INVENTORY_LOG_CONTEXT_MAX,
    INVENTORY_LOG_MAX,
    INVENTORY_NPC_NOTES_MAX,
    INVENTORY_NPC_STATES_MAX,
    WORLD_EVENTS_MAX,
)
from gateway.schemas.adventure import AdventureTurnRequest
from gateway.services.adventure_inventory import (
    InventoryActionError,
    RealityPatch,
    WorldEvent,
    apply_item_resolution,
    apply_reality_patch,
    apply_world_events,
    coerce_reality_patch,
    coerce_world_events,
    item_resolution_narrative_suffix,
    lean_inventory_for_llm,
    npc_states_for_llm,
    public_inventory_view,
    public_npc_states,
    resolve_item_action,
    resolve_npc_name,
    worn_inventory_items,
)
from gateway.services.adventure_service import (
    AdventureResolutionOutput,
    AdventureRomanceResolutionOutput,
    _default_director_choices,
)


def make_state(**overrides) -> dict:
    state = {
        "inventory_enabled": True,
        "sim": {"partner_name": "サクラ"},
        "visual_state": {
            "main_characters": [{"name": "店員のミナ", "description": "店員"}]
        },
    }
    state.update(overrides)
    return state


def bra_event(**overrides) -> dict:
    event = {
        "type": "item_transfer",
        "from": "character:サクラ",
        "to": "player",
        "item": {"name": "黒いブラ", "category": "underwear", "tags": ["black"]},
    }
    event.update(overrides)
    return event


def give_state() -> dict:
    """黒いブラを1つ所持した状態。"""
    state = make_state()
    apply_world_events(state, [bra_event()], turn_number=1, input_kind="free_text")
    return state


def resolution_context() -> dict:
    return {"fallback_choices": _default_director_choices("ja"), "language": "ja"}


def three_choices() -> list[dict]:
    return [{"id": f"c{i}", "label": f"選択肢{i}"} for i in range(3)]


# --- validators ---------------------------------------------------------------


def test_coerce_world_events_drops_broken_entries_and_caps() -> None:
    events = coerce_world_events(
        [
            bra_event(),
            "junk",
            {"type": "nope", "item": {"name": "x"}},
            {"type": "item_transfer", "to": "player", "item": {"name": ""}},
        ]
    )
    assert len(events) == 1
    assert events[0]["from"] == "character:サクラ"
    assert events[0]["item"]["capabilities"] == ["give", "wear", "discard"]
    assert coerce_world_events("junk") == []
    many = coerce_world_events([bra_event() for _ in range(WORLD_EVENTS_MAX + 3)])
    assert len(many) == WORLD_EVENTS_MAX


def test_world_event_normalizes_aliases_and_vocabulary() -> None:
    event = WorldEvent.model_validate(
        {
            "type": "item_acquire",
            "item": {
                "name": "飴",
                "category": "sweets",
                "capabilities": ["wear", "use"],
            },
            "severity": "MAJOR",
        }
    )
    assert event.type == "item_transfer"
    assert event.to == "player"
    assert event.item is not None
    assert event.item.category == "other"
    # other は着用不可なので wear は落ち、discard は常に付く
    assert event.item.capabilities == ["use", "discard"]
    assert event.severity == "major"
    give = WorldEvent.model_validate(
        {"type": "item_give", "to": "サクラ", "item_id": "i1"}
    )
    assert give.from_ == "player" and give.to == "character:サクラ"


def test_resolution_output_accepts_world_events_and_reality_patch_leniently() -> None:
    output = AdventureResolutionOutput.model_validate(
        {"choices": three_choices(), "world_events": "junk", "reality_patch": "junk"},
        context=resolution_context(),
    )
    assert output.world_events == [] and output.reality_patch is None
    output = AdventureRomanceResolutionOutput.model_validate(
        {
            "choices": three_choices(),
            "world_events": [bra_event(), {"type": "??"}],
            "reality_patch": {
                "inventory": [{"op": "add", "item": {"name": "赤いリボン"}}],
                "npc_notes": [{"npc": "サクラ", "note": "昨日贈った"}, "junk"],
                "npc_boundary_reset": ["サクラ"],
            },
        },
        context=resolution_context(),
    )
    assert [event["type"] for event in output.world_events] == ["item_transfer"]
    assert output.reality_patch is not None
    assert output.reality_patch["inventory"][0]["op"] == "add"
    assert output.reality_patch["npc_notes"] == [
        {"npc": "サクラ", "note": "昨日贈った"}
    ]
    assert output.reality_patch["npc_boundary_reset"] == ["サクラ"]


def test_coerce_reality_patch_returns_none_when_empty() -> None:
    assert coerce_reality_patch({"inventory": [], "npc_notes": []}) is None
    assert coerce_reality_patch("junk") is None
    patch = RealityPatch.model_validate(
        {"inventory": [{"op": "add", "item": "手紙"}, {"op": "explode"}]}
    )
    assert len(patch.inventory) == 1
    assert patch.inventory[0].item == {"name": "手紙"}


def test_turn_request_accepts_item_action() -> None:
    request = AdventureTurnRequest(
        client_turn_id="c1",
        user_input="黒いブラをサクラに渡す",
        input_kind="item_action",
        item_action={"item_id": "i1", "action": "give", "target": "サクラ"},
    )
    assert request.item_action is not None
    assert request.item_action.action == "give"
    with pytest.raises(ValueError):
        AdventureTurnRequest(
            client_turn_id="c1",
            user_input="x",
            input_kind="item_action",
            item_action={"item_id": "i1", "action": "eat"},
        )


# --- apply_world_events -------------------------------------------------------


def test_apply_world_events_ignores_disabled_runs() -> None:
    state = make_state(inventory_enabled=False)
    before = copy.deepcopy(state)
    assert (
        apply_world_events(state, [bra_event()], turn_number=1, input_kind="free_text")
        == []
    )
    assert state == before


def test_transfer_to_player_adds_and_merges_items() -> None:
    state = make_state()
    applied = apply_world_events(
        state, [bra_event()], turn_number=3, input_kind="free_text"
    )
    assert applied[0]["type"] == "item_transfer" and applied[0]["origin"] == "event"
    items = state["inventory"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == "i1"
    assert items[0]["obtained_from"] == "character:サクラ"
    assert items[0]["obtained_turn"] == 3
    assert items[0]["worn"] is False
    # 同名・同分類・未着用は数量を合算し、入手元の敬称は攻略対象名へ寄せる
    apply_world_events(
        state,
        [
            bra_event(
                **{
                    "from": "サクラさん",
                    "item": {
                        "name": "黒いブラ",
                        "category": "underwear",
                        "quantity": 2,
                    },
                }
            )
        ],
        turn_number=4,
        input_kind="free_text",
    )
    assert len(items) == 1 and items[0]["quantity"] == 3
    assert state["inventory"]["log"][-1]["from"] == "character:サクラ"


def test_transfer_from_player_requires_ownership_and_quantity() -> None:
    state = give_state()
    dropped = apply_world_events(
        state,
        [
            {
                "type": "item_transfer",
                "from": "player",
                "to": "character:サクラ",
                "item": {"name": "赤いリボン"},
            },
            {
                "type": "item_transfer",
                "from": "player",
                "to": "character:サクラ",
                "item_id": "i1",
                "quantity": 5,
            },
            {
                "type": "item_transfer",
                "from": "character:サクラ",
                "to": "character:ミナ",
                "item": {"name": "黒いブラ"},
            },
        ],
        turn_number=2,
        input_kind="free_text",
    )
    assert dropped == []
    assert state["inventory"]["items"][0]["quantity"] == 1
    applied = apply_world_events(
        state,
        [
            {
                "type": "item_transfer",
                "from": "player",
                "to": "店員のミナさん",
                "item_id": "i1",
            }
        ],
        turn_number=2,
        input_kind="free_text",
    )
    assert applied[0]["to"] == "character:店員のミナ"
    assert state["inventory"]["items"] == []


def test_use_consumes_only_consumables() -> None:
    state = make_state()
    apply_world_events(
        state,
        [
            {
                "type": "item_transfer",
                "from": "world",
                "to": "player",
                "item": {"name": "飴", "category": "consumable", "quantity": 2},
            },
            {
                "type": "item_transfer",
                "from": "world",
                "to": "player",
                "item": {"name": "鍵", "category": "key"},
            },
        ],
        turn_number=1,
        input_kind="free_text",
    )
    applied = apply_world_events(
        state,
        [
            {"type": "item_use", "item_id": "i1"},
            {"type": "item_use", "item": {"name": "鍵"}},
            {"type": "item_use", "item_id": "i1", "quantity": 9},
        ],
        turn_number=2,
        input_kind="free_text",
    )
    assert [entry["item"] for entry in applied] == ["飴", "鍵"]
    items = {item["name"]: item for item in state["inventory"]["items"]}
    assert items["飴"]["quantity"] == 1
    assert items["鍵"]["quantity"] == 1


def test_discard_wear_and_unwear_rules() -> None:
    state = give_state()
    apply_world_events(
        state,
        [
            {
                "type": "item_transfer",
                "from": "world",
                "to": "player",
                "item": {"name": "石", "category": "other"},
            }
        ],
        turn_number=1,
        input_kind="free_text",
    )
    applied = apply_world_events(
        state,
        [
            {"type": "item_wear", "item": {"name": "石"}},
            {"type": "item_unwear", "item_id": "i1"},
            {"type": "item_wear", "item_id": "i1"},
            {"type": "item_wear", "item_id": "i1"},
        ],
        turn_number=2,
        input_kind="free_text",
    )
    assert [entry["type"] for entry in applied] == ["item_wear"]
    assert state["inventory"]["items"][0]["worn"] is True
    applied = apply_world_events(
        state,
        [
            {"type": "item_unwear", "item_id": "i1"},
            {"type": "item_discard", "item_id": "i2", "quantity": 3},
            {"type": "item_discard", "item_id": "i2"},
        ],
        turn_number=3,
        input_kind="free_text",
    )
    assert [entry["type"] for entry in applied] == ["item_unwear", "item_discard"]
    assert [item["name"] for item in state["inventory"]["items"]] == ["黒いブラ"]
    assert state["inventory"]["items"][0]["worn"] is False


def test_boundary_violation_counts_per_npc_and_skips_reality_turns() -> None:
    state = make_state()
    for turn in range(1, 12):
        apply_world_events(
            state,
            [
                {
                    "type": "boundary_violation",
                    "npc": "サクラさん",
                    "reason": "下着を要求",
                    "severity": "major",
                }
            ],
            turn_number=turn,
            input_kind="free_text",
        )
    entry = state["npc_states"]["サクラ"]
    assert entry["boundary_violations"] == 9
    assert entry["last_violation_turn"] == 11
    assert entry["last_violation_severity"] == "major"
    assert (
        apply_world_events(
            state,
            [{"type": "boundary_violation", "npc": "サクラ"}],
            turn_number=12,
            input_kind="reality_alter",
        )
        == []
    )
    assert (
        apply_world_events(
            state,
            [{"type": "boundary_violation"}],
            turn_number=12,
            input_kind="free_text",
        )
        == []
    )


def test_caps_for_items_log_and_npc_states() -> None:
    state = make_state()
    for index in range(INVENTORY_ITEMS_MAX + 2):
        apply_world_events(
            state,
            [
                {
                    "type": "item_transfer",
                    "from": "world",
                    "to": "player",
                    "item": {"name": f"品{index}"},
                }
            ],
            turn_number=index,
            input_kind="free_text",
        )
    assert len(state["inventory"]["items"]) == INVENTORY_ITEMS_MAX
    # 上限で弾かれた追加はログにも残らない
    assert len(state["inventory"]["log"]) == INVENTORY_ITEMS_MAX
    for index in range(INVENTORY_NPC_STATES_MAX + 3):
        apply_world_events(
            state,
            [{"type": "boundary_violation", "npc": f"通行人{index}"}],
            turn_number=index,
            input_kind="free_text",
        )
    assert len(state["npc_states"]) == INVENTORY_NPC_STATES_MAX
    assert "通行人0" not in state["npc_states"]
    assert len(state["inventory"]["log"]) == INVENTORY_LOG_MAX


def test_resolve_npc_name_matches_partner_scene_and_existing_keys() -> None:
    state = make_state()
    assert resolve_npc_name("サクラさん", state) == "サクラ"
    assert resolve_npc_name("character:ミナ", state) == "店員のミナ"
    assert resolve_npc_name("新しい人", state) == "新しい人"
    assert resolve_npc_name("", state) == ""


# --- apply_reality_patch ------------------------------------------------------


def test_reality_patch_add_transfer_and_notes() -> None:
    state = make_state()
    applied = apply_reality_patch(
        state,
        {
            "inventory": [
                {
                    "op": "add",
                    "item": {"name": "黒いブラ", "category": "underwear"},
                    "from": "サクラ",
                    "obtained_when": "昨日",
                },
                {
                    "op": "transfer",
                    "to": "player",
                    "from": "character:ミナ",
                    "name": "領収書",
                },
            ],
            "npc_notes": [
                {"npc": "サクラさん", "note": "昨日、自分の黒いブラを贈った"}
            ],
        },
        turn_number=5,
    )
    assert [entry["origin"] for entry in applied] == ["reality", "reality"]
    items = {item["name"]: item for item in state["inventory"]["items"]}
    assert items["黒いブラ"]["obtained_from"] == "character:サクラ"
    assert items["黒いブラ"]["metadata"] == {"obtained_when": "昨日"}
    assert items["領収書"]["obtained_from"] == "character:店員のミナ"
    assert state["npc_states"]["サクラ"]["notes"] == ["昨日、自分の黒いブラを贈った"]
    assert (
        apply_reality_patch(
            make_state(inventory_enabled=False),
            {"inventory": [{"op": "add", "item": "x"}]},
            turn_number=1,
        )
        == []
    )


def test_reality_patch_remove_replace_set_quantity_update_and_reset() -> None:
    state = give_state()
    apply_world_events(
        state,
        [{"type": "boundary_violation", "npc": "サクラ"}],
        turn_number=1,
        input_kind="free_text",
    )
    applied = apply_reality_patch(
        state,
        {
            "inventory": [
                {"op": "set_quantity", "item_id": "i1", "quantity": 3},
                {
                    "op": "update",
                    "name": "黒いブラ",
                    "item": {"name": "レースのブラ", "tags": ["lace"]},
                    "worn": True,
                    "from": "world",
                },
                {
                    "op": "replace",
                    "item_id": "i1",
                    "item": {"name": "白いブラ", "category": "underwear"},
                },
                {"op": "remove", "name": "白いブラ", "quantity": 1},
                {"op": "remove", "name": "存在しない"},
            ],
            "npc_boundary_reset": ["サクラ"],
        },
        turn_number=6,
    )
    types = [entry["type"] for entry in applied]
    assert types == ["item_update", "item_update", "item_update", "item_discard"]
    items = state["inventory"]["items"]
    assert len(items) == 1
    assert items[0]["name"] == "白いブラ" and items[0]["quantity"] == 2
    # replace は入手元・入手手番を引き継ぐ
    assert items[0]["obtained_from"] == "world" and items[0]["obtained_turn"] == 1
    assert state["npc_states"]["サクラ"]["boundary_violations"] == 0
    notes_state = make_state()
    apply_reality_patch(
        notes_state,
        {
            "npc_notes": [
                {"npc": "サクラ", "note": f"記憶{i}"}
                for i in range(INVENTORY_NPC_NOTES_MAX + 4)
            ]
        },
        turn_number=1,
    )
    # LLM 出力側で上限に切られる
    assert len(notes_state["npc_states"]["サクラ"]["notes"]) == INVENTORY_NPC_NOTES_MAX


# --- item actions -------------------------------------------------------------


def test_resolve_item_action_validates_without_mutating_state() -> None:
    state = give_state()
    before = copy.deepcopy(state)
    wear = resolve_item_action(state, {"item_id": "i1", "action": "wear"})
    assert wear["resolved"] is True and wear["outcome"] == "worn"
    assert wear["item"]["name"] == "黒いブラ"
    give = resolve_item_action(state, {"item_id": "i1", "action": "give"})
    assert give["resolved"] is False and give["target"] == "character:サクラ"
    give_to = resolve_item_action(
        state, {"item_id": "i1", "action": "give", "target": "ミナさん"}
    )
    assert give_to["target"] == "character:店員のミナ"
    assert state == before
    with pytest.raises(InventoryActionError) as missing:
        resolve_item_action(state, {"item_id": "i9", "action": "wear"})
    assert missing.value.code == "invalid_item"
    with pytest.raises(InventoryActionError) as unwear:
        resolve_item_action(state, {"item_id": "i1", "action": "unwear"})
    assert unwear.value.code == "item_action_unavailable"
    with pytest.raises(InventoryActionError):
        resolve_item_action(state, {"item_id": "i1", "action": "use"})
    with pytest.raises(InventoryActionError):
        resolve_item_action(state, {"item_id": "i1", "action": "eat"})


def test_apply_item_resolution_is_idempotent_with_llm_events() -> None:
    state = give_state()
    wear = resolve_item_action(state, {"item_id": "i1", "action": "wear"})
    applied = apply_item_resolution(state, wear, turn_number=2)
    assert [entry["origin"] for entry in applied] == ["action"]
    assert state["inventory"]["items"][0]["worn"] is True
    assert apply_item_resolution(state, wear, turn_number=2) == []
    discard = resolve_item_action(state, {"item_id": "i1", "action": "discard"})
    apply_world_events(
        state,
        [{"type": "item_discard", "item_id": "i1"}],
        turn_number=3,
        input_kind="item_action",
    )
    assert apply_item_resolution(state, discard, turn_number=3) == []
    assert state["inventory"]["items"] == []
    pending = resolve_item_action(give_state(), {"item_id": "i1", "action": "give"})
    assert apply_item_resolution(give_state(), pending, turn_number=1) == []


def test_item_resolution_narrative_suffix_follows_voice() -> None:
    state = give_state()
    wear = resolve_item_action(state, {"item_id": "i1", "action": "wear"})
    assert (
        item_resolution_narrative_suffix(wear, "", "ja") == "君は黒いブラを身につけた。"
    )
    assert item_resolution_narrative_suffix(wear, "黒いブラを胸に当てた。", "ja") == ""
    assert (
        item_resolution_narrative_suffix(
            wear, "", "ja", narration_voice="first_person", narration_pronoun="僕"
        )
        == "僕は黒いブラを身につけた。"
    )
    assert (
        item_resolution_narrative_suffix(wear, "", "ja", narration_voice="third_person")
        == "黒いブラを身につけた。"
    )
    assert item_resolution_narrative_suffix(wear, "", "en") == "You put on 黒いブラ."
    give = resolve_item_action(state, {"item_id": "i1", "action": "give"})
    assert item_resolution_narrative_suffix(give, "", "ja") == ""


# --- views --------------------------------------------------------------------


def test_worn_items_apply_pending_resolution_virtually() -> None:
    state = give_state()
    assert worn_inventory_items(state) == []
    wear = resolve_item_action(state, {"item_id": "i1", "action": "wear"})
    assert worn_inventory_items(state, pending=wear) == [
        {"name": "黒いブラ", "category": "underwear", "tags": ["black"]}
    ]
    state["inventory"]["items"][0]["worn"] = True
    assert worn_inventory_items(state) != []
    unwear = resolve_item_action(state, {"item_id": "i1", "action": "unwear"})
    assert worn_inventory_items(state, pending=unwear) == []
    assert worn_inventory_items(make_state(inventory_enabled=False)) == []


def test_lean_and_public_views() -> None:
    state = give_state()
    for index in range(INVENTORY_LOG_CONTEXT_MAX + 3):
        apply_world_events(
            state,
            [{"type": "boundary_violation", "npc": "サクラ", "reason": f"r{index}"}],
            turn_number=index,
            input_kind="free_text",
        )
    apply_reality_patch(
        state, {"npc_notes": [{"npc": "サクラ", "note": "秘密"}]}, turn_number=9
    )
    lean = lean_inventory_for_llm(state)
    assert lean is not None
    assert len(lean["recent_log"]) == INVENTORY_LOG_CONTEXT_MAX
    assert set(lean["items"][0]) == {
        "id",
        "name",
        "category",
        "tags",
        "quantity",
        "worn",
        "capabilities",
        "obtained_from",
        "obtained_turn",
    }
    assert lean_inventory_for_llm(make_state(inventory_enabled=False)) is None
    llm_npcs = npc_states_for_llm(state)
    assert llm_npcs["サクラ"]["notes"] == ["秘密"]
    assert npc_states_for_llm(make_state()) == {}
    public = public_inventory_view(state)
    assert public["items"][0]["id"] == "i1"
    assert len(public["log"]) <= INVENTORY_LOG_MAX
    assert public_npc_states(state) == {
        "サクラ": {
            "boundary_violations": 9,
            "last_violation_turn": INVENTORY_LOG_CONTEXT_MAX + 2,
        }
    }
