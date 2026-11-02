import pytest

from gateway.consts.adventure_reality_cost import (
    REALITY_COST_HISTORY_MAX,
    REALITY_COST_MAX_ACTIVE,
    ROMANCE_REALITY_BILL_AMOUNTS,
)
from gateway.services.adventure_models import AdventureResolutionOutput
from gateway.services.adventure_reality_cost import (
    RealityCostError,
    active_reality_costs,
    add_reality_cost,
    coerce_cost_ids,
    coerce_reality_cost,
    gate_ending_status,
    gated_ending_note,
    pay_reality_bill,
    public_reality_costs,
    reality_costs_for_llm,
    resolve_reality_costs,
)


def _state(**extra) -> dict:
    return {"reality_cost_enabled": True, **extra}


def test_coerce_reality_cost_normalizes_text_and_severity() -> None:
    assert coerce_reality_cost(None) is None
    assert coerce_reality_cost({"text": "   "}) is None
    assert coerce_reality_cost(
        {"text": " 固定資産税の\n納付書が届く ", "severity": "MAJOR"}
    ) == {
        "text": "固定資産税の 納付書が届く",
        "severity": "major",
    }
    # 語彙外の深刻度は minor に倒す
    assert (
        coerce_reality_cost({"text": "噂", "severity": "huge"})["severity"] == "minor"
    )
    assert coerce_cost_ids(["cost1", {"id": "cost2"}, "cost1", None, ""]) == [
        "cost1",
        "cost2",
    ]
    assert coerce_cost_ids("cost1") == []


def test_resolution_output_accepts_reality_cost_fields_leniently() -> None:
    output = AdventureResolutionOutput.model_validate(
        {
            "choices": [{"id": str(i), "label": f"行動{i}"} for i in range(3)],
            "reality_cost": {"text": "", "severity": "minor"},
            "resolved_reality_cost_ids": "cost1",
        }
    )
    assert output.reality_cost is None
    assert output.resolved_reality_cost_ids == []


def test_add_reality_cost_numbers_ids_and_prices_romance_bills() -> None:
    state = _state()
    first = add_reality_cost(
        state,
        {"text": "固定資産税の納付書が届く", "severity": "major"},
        turn_number=2,
        source_rule="主人公は豪邸の主である",
        romance=True,
    )
    second = add_reality_cost(
        state,
        {"text": "近所で噂になる", "severity": "minor"},
        turn_number=3,
        source_rule="主人公はお嬢様である",
        romance=False,
    )
    assert first["id"] == "cost1" and second["id"] == "cost2"
    # 金額は LLM ではなく深刻度から決まる
    assert first["amount"] == ROMANCE_REALITY_BILL_AMOUNTS["major"]
    assert "amount" not in second
    assert first["created_turn"] == 2 and first["resolved_turn"] is None
    assert (
        add_reality_cost(state, None, turn_number=4, source_rule="", romance=False)
        is None
    )


def test_add_reality_cost_skips_when_active_limit_reached() -> None:
    state = _state()
    for index in range(REALITY_COST_MAX_ACTIVE):
        add_reality_cost(
            state,
            {"text": f"代償{index}", "severity": "minor"},
            turn_number=index + 1,
            source_rule="",
            romance=False,
        )
    assert (
        add_reality_cost(
            state,
            {"text": "溢れた代償", "severity": "minor"},
            turn_number=99,
            source_rule="",
            romance=False,
        )
        is None
    )
    assert len(active_reality_costs(state)) == REALITY_COST_MAX_ACTIVE


def test_history_trim_drops_oldest_resolved_first() -> None:
    state = _state(
        reality_costs=[
            {"id": f"cost{index}", "text": "済", "resolved_turn": 1}
            for index in range(REALITY_COST_HISTORY_MAX)
        ],
        reality_cost_next_id=REALITY_COST_HISTORY_MAX,
    )
    created = add_reality_cost(
        state,
        {"text": "新しい代償", "severity": "minor"},
        turn_number=5,
        source_rule="",
        romance=False,
    )
    ids = [cost["id"] for cost in state["reality_costs"]]
    assert len(ids) == REALITY_COST_HISTORY_MAX
    assert "cost0" not in ids
    assert ids[-1] == created["id"]


def test_resolve_reality_costs_never_settles_bills() -> None:
    state = _state()
    trouble = add_reality_cost(
        state,
        {"text": "噂", "severity": "minor"},
        turn_number=1,
        source_rule="",
        romance=False,
    )
    bill = add_reality_cost(
        state,
        {"text": "罰金", "severity": "minor"},
        turn_number=1,
        source_rule="",
        romance=True,
    )
    resolved = resolve_reality_costs(
        state, [trouble["id"], bill["id"], "cost99"], turn_number=3
    )
    assert [cost["id"] for cost in resolved] == [trouble["id"]]
    assert trouble["resolved_turn"] == 3 and trouble["resolution"] == "story"
    assert bill["resolved_turn"] is None
    # 解決済みを再度申告しても解決手番は変わらない
    assert resolve_reality_costs(state, [trouble["id"]], turn_number=5) == []
    assert trouble["resolved_turn"] == 3


def test_pay_reality_bill_deducts_money_and_validates() -> None:
    state = _state(sim={"money": 5000})
    bill = add_reality_cost(
        state,
        {"text": "修繕費", "severity": "minor"},
        turn_number=1,
        source_rule="",
        romance=True,
    )
    big = add_reality_cost(
        state,
        {"text": "固定資産税", "severity": "major"},
        turn_number=1,
        source_rule="",
        romance=True,
    )
    trouble = add_reality_cost(
        state,
        {"text": "噂", "severity": "minor"},
        turn_number=1,
        source_rule="",
        romance=False,
    )

    paid = pay_reality_bill(state, bill["id"], turn_number=2)
    assert paid["resolution"] == "paid" and paid["resolved_turn"] == 2
    assert state["sim"]["money"] == 5000 - bill["amount"]

    with pytest.raises(RealityCostError) as shortage:
        pay_reality_bill(state, big["id"], turn_number=2)
    assert shortage.value.code == "insufficient_funds"
    assert state["sim"]["money"] == 5000 - bill["amount"]
    with pytest.raises(RealityCostError) as again:
        pay_reality_bill(state, bill["id"], turn_number=3)
    assert again.value.code == "reality_cost_already_resolved"
    with pytest.raises(RealityCostError) as not_bill:
        pay_reality_bill(state, trouble["id"], turn_number=3)
    assert not_bill.value.code == "reality_cost_not_bill"
    with pytest.raises(RealityCostError) as missing:
        pay_reality_bill(state, "cost99", turn_number=3)
    assert missing.value.code == "reality_cost_not_found"
    with pytest.raises(RealityCostError) as no_sim:
        pay_reality_bill(
            {"reality_costs": state["reality_costs"]}, big["id"], turn_number=3
        )
    assert no_sim.value.code == "reality_cost_not_bill"


def test_gate_ending_status_downgrades_only_success_with_active_costs() -> None:
    state = _state()
    assert gate_ending_status(state, "success") == ("success", [])
    cost = add_reality_cost(
        state,
        {"text": "噂", "severity": "minor"},
        turn_number=1,
        source_rule="",
        romance=False,
    )
    status, blocking = gate_ending_status(state, "success")
    assert status == "partial" and [item["id"] for item in blocking] == [cost["id"]]
    assert gate_ending_status(state, "failure") == ("failure", [])
    assert gate_ending_status(state, "continue") == ("continue", [])
    # OFF の間は結末に影響しない
    state["reality_cost_enabled"] = False
    assert gate_ending_status(state, "success") == ("success", [])

    assert "「噂」" in gated_ending_note(blocking, "ja")
    assert '"噂"' in gated_ending_note(blocking, "en")


def test_llm_and_public_views() -> None:
    state = _state(sim={"money": 0})
    bill = add_reality_cost(
        state,
        {"text": "罰金", "severity": "major"},
        turn_number=1,
        source_rule="宣言",
        romance=True,
    )
    trouble = add_reality_cost(
        state,
        {"text": "噂", "severity": "minor"},
        turn_number=2,
        source_rule="宣言",
        romance=False,
    )
    resolve_reality_costs(state, [trouble["id"]], turn_number=3)

    assert reality_costs_for_llm(state) == [
        {"id": bill["id"], "text": "罰金", "kind": "bill", "amount": bill["amount"]}
    ]
    public = public_reality_costs(state)
    assert [item["id"] for item in public] == [bill["id"], trouble["id"]]
    assert public[0]["amount"] == bill["amount"]
    assert public[1]["amount"] is None and public[1]["resolution"] == "story"
    assert public_reality_costs({}) == []
