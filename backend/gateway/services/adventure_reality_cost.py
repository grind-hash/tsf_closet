"""Adventure reality-cost (改変の代償) option.

Pure functions used by adventure_service. On a run with
``reality_cost_enabled``, every turn that establishes a reality rule also
creates one cost: an unforeseen but logical consequence of the alteration
that the player then has to deal with.

- Non-romance runs: a cost is a complication in the story. The resolution LLM
  reports it settled only when the narrative of a non-alteration turn shows
  the player handling it, so a reality alteration never erases a cost.
- Romance runs: a cost is a bill. Python fixes the amount from the severity,
  and the player pays it from the HUD without spending a turn.
- A run that ends in success while a cost is still unresolved is downgraded
  to a partial success.

Everything mutates the run's state dict in place. The turn pipeline stores a
full state snapshot per turn, so rewinds restore the costs for free.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from ..consts.adventure_reality_cost import (
    REALITY_COST_DEFAULT_SEVERITY,
    REALITY_COST_HISTORY_MAX,
    REALITY_COST_MAX_ACTIVE,
    REALITY_COST_SEVERITIES,
    REALITY_COST_SOURCE_RULE_MAX,
    REALITY_COST_TEXT_MAX,
    ROMANCE_REALITY_BILL_AMOUNTS,
)

logger = logging.getLogger(__name__)


class RealityCostError(Exception):
    """支払いなど手番外の操作が成立しないときの例外。state は変更しない。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def reality_cost_enabled(state: dict[str, Any]) -> bool:
    return bool(state.get("reality_cost_enabled"))


def _clean_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit].strip()


def coerce_reality_cost(value: Any) -> dict[str, str] | None:
    """LLM 出力の reality_cost を {text, severity} にする。空・不正は None。"""
    if not isinstance(value, dict):
        return None
    text = _clean_text(value.get("text"), REALITY_COST_TEXT_MAX)
    if not text:
        return None
    severity = str(value.get("severity") or "").strip().lower()
    if severity not in REALITY_COST_SEVERITIES:
        severity = REALITY_COST_DEFAULT_SEVERITY
    return {"text": text, "severity": severity}


def coerce_cost_ids(value: Any) -> list[str]:
    """LLM 出力の ID 一覧を重複なしの文字列リストにする。不正な要素は捨てる。"""
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("id")
        if not isinstance(item, str | int):
            continue
        text = str(item).strip()
        if text and text not in ids:
            ids.append(text)
    return ids[:REALITY_COST_HISTORY_MAX]


def _costs(state: dict[str, Any]) -> list[dict[str, Any]]:
    """state の代償一覧。要素は state 内の dict そのものなので、書き換えは反映される。"""
    costs = state.get("reality_costs")
    if not isinstance(costs, list):
        return []
    return [item for item in costs if isinstance(item, dict) and item.get("id")]


def _is_active(cost: dict[str, Any]) -> bool:
    return cost.get("resolved_turn") is None


def _is_bill(cost: dict[str, Any]) -> bool:
    return isinstance(cost.get("amount"), int)


def active_reality_costs(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [cost for cost in _costs(state) if _is_active(cost)]


def _next_cost_id(state: dict[str, Any]) -> str:
    try:
        number = max(1, int(state.get("reality_cost_next_id") or 1))
    except (TypeError, ValueError):
        number = 1
    state["reality_cost_next_id"] = number + 1
    return f"cost{number}"


def _trim_history(costs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """上限を超えたら古い解決済みから落とす。未解決は落とさない。"""
    overflow = len(costs) - REALITY_COST_HISTORY_MAX
    if overflow <= 0:
        return costs
    kept: list[dict[str, Any]] = []
    for cost in costs:
        if overflow > 0 and not _is_active(cost):
            overflow -= 1
            continue
        kept.append(cost)
    return kept


def add_reality_cost(
    state: dict[str, Any],
    cost: dict[str, str] | None,
    *,
    turn_number: int,
    source_rule: str | None,
    romance: bool,
) -> dict[str, Any] | None:
    """代償を1件追加して返す。未解決が上限に達していれば追加しない。

    romance では請求額を severity から Python で決める(LLM は金額を書かない)。
    """
    if cost is None:
        return None
    costs = _costs(state)
    if sum(1 for item in costs if _is_active(item)) >= REALITY_COST_MAX_ACTIVE:
        logger.warning(
            "Reality cost skipped: active costs reached the limit (%d)",
            REALITY_COST_MAX_ACTIVE,
        )
        return None
    severity = cost.get("severity") or REALITY_COST_DEFAULT_SEVERITY
    entry: dict[str, Any] = {
        "id": _next_cost_id(state),
        "text": cost["text"],
        "severity": severity,
        "source_rule": _clean_text(source_rule, REALITY_COST_SOURCE_RULE_MAX),
        "created_turn": int(turn_number),
        "resolved_turn": None,
        "resolution": None,
    }
    if romance:
        entry["amount"] = ROMANCE_REALITY_BILL_AMOUNTS.get(
            severity, ROMANCE_REALITY_BILL_AMOUNTS[REALITY_COST_DEFAULT_SEVERITY]
        )
    costs.append(entry)
    state["reality_costs"] = _trim_history(costs)
    return entry


def resolve_reality_costs(
    state: dict[str, Any], ids: Iterable[str], *, turn_number: int
) -> list[dict[str, Any]]:
    """物語の中で解決された代償に解決手番を記録して返す。

    請求(amount あり)は支払いでしか解決しないため、ここでは対象外にする。
    """
    wanted = {str(item) for item in ids}
    resolved: list[dict[str, Any]] = []
    if not wanted:
        return resolved
    for cost in _costs(state):
        if cost["id"] in wanted and _is_active(cost) and not _is_bill(cost):
            cost["resolved_turn"] = int(turn_number)
            cost["resolution"] = "story"
            resolved.append(cost)
    return resolved


def pay_reality_bill(
    state: dict[str, Any], cost_id: str, *, turn_number: int
) -> dict[str, Any]:
    """romance の請求を所持金から支払い、解決済みにして返す。"""
    sim = state.get("sim")
    if not isinstance(sim, dict):
        raise RealityCostError(
            "reality_cost_not_bill", "支払いが必要な代償ではありません"
        )
    cost = next((item for item in _costs(state) if item["id"] == cost_id), None)
    if cost is None:
        raise RealityCostError("reality_cost_not_found", "代償が見つかりません")
    if not _is_active(cost):
        raise RealityCostError(
            "reality_cost_already_resolved", "この代償は既に解決しています"
        )
    if not _is_bill(cost):
        raise RealityCostError(
            "reality_cost_not_bill", "支払いが必要な代償ではありません"
        )
    amount = int(cost["amount"])
    money = int(sim.get("money") or 0)
    if money < amount:
        raise RealityCostError(
            "insufficient_funds", "所持金が足りず、この請求を支払えません"
        )
    sim["money"] = money - amount
    cost["resolved_turn"] = int(turn_number)
    cost["resolution"] = "paid"
    return cost


def gate_ending_status(
    state: dict[str, Any], status: str
) -> tuple[str, list[dict[str, Any]]]:
    """未解決の代償が残る success を partial に下げる。

    戻り値は (適用後の status, 格下げの原因になった代償)。格下げしなければ空。
    """
    if status != "success" or not reality_cost_enabled(state):
        return status, []
    active = active_reality_costs(state)
    if not active:
        return status, []
    return "partial", active


def gated_ending_note(costs: list[dict[str, Any]], language: str) -> str:
    """格下げした結末の要約に添える1行。"""
    if language == "ja":
        listed = "、".join(f"「{cost['text']}」" for cost in costs)
        return f"未解決の代償が残ったため、部分的な成功に留まった: {listed}"
    listed = "; ".join(f'"{cost["text"]}"' for cost in costs)
    return (
        "Unresolved reality costs remained, so this counts only as a partial "
        f"success: {listed}"
    )


def reality_costs_for_llm(state: dict[str, Any]) -> list[dict[str, Any]]:
    """LLM に渡す未解決の代償。請求は kind=bill として金額を添える。"""
    view: list[dict[str, Any]] = []
    for cost in active_reality_costs(state):
        entry: dict[str, Any] = {
            "id": cost["id"],
            "text": cost.get("text", ""),
            "kind": "bill" if _is_bill(cost) else "complication",
        }
        if _is_bill(cost):
            entry["amount"] = cost["amount"]
        view.append(entry)
    return view


def public_reality_costs(state: dict[str, Any]) -> list[dict[str, Any]]:
    """フロントへ配信する代償の一覧(解決済みを含む)。"""
    return [
        {
            "id": cost["id"],
            "text": str(cost.get("text") or ""),
            "severity": str(cost.get("severity") or REALITY_COST_DEFAULT_SEVERITY),
            "source_rule": str(cost.get("source_rule") or ""),
            "amount": cost["amount"] if _is_bill(cost) else None,
            "created_turn": cost.get("created_turn"),
            "resolved_turn": cost.get("resolved_turn"),
            "resolution": cost.get("resolution"),
        }
        for cost in _costs(state)
    ]


def applied_entry(kind: str, cost: dict[str, Any]) -> dict[str, Any]:
    """手番の表示用記録(reality_costs_applied)の1件。"""
    return {
        "type": kind,
        "id": cost["id"],
        "text": str(cost.get("text") or ""),
        "amount": cost["amount"] if _is_bill(cost) else None,
    }


REALITY_COST_NARRATIVE_INSTRUCTION = (
    "active_reality_costs lists consequences of earlier reality alterations that "
    "this world has not settled yet. Each one is a real, ongoing complication: let "
    "NPCs, institutions, and circumstances keep reacting to it where it is "
    "relevant, and never narrate it vanishing, being forgiven, or settling itself. "
    "Only an action the player actually takes can settle a complication, a bill "
    "(kind bill) is settled only through the game's payment system so never "
    "narrate it as paid, and a reality alteration never erases an existing cost. "
    "When reality_cost_due is true, this turn's alteration also sets one "
    "unforeseen but logical consequence in motion; you may foreshadow it (a "
    "notice arrives, someone notices, a demand appears) but never resolve it."
)

REALITY_COST_RESOLUTION_INSTRUCTION = (
    'Add "resolved_reality_cost_ids": the ids of active_reality_costs entries of '
    "kind complication that the narrative of this turn shows actually settled by "
    "the player's own action, normally an empty list. The player merely claiming "
    "to have handled one does not settle it, a bill is never settled here, and a "
    "reality alteration never settles a cost. Never report ending_status success "
    "while active_reality_costs is not empty."
)

REALITY_COST_DUE_INSTRUCTION = (
    "This turn established a reality alteration (reality_rule_declared_this_turn), "
    'and reality balances its books: add "reality_cost": {"text":"...",'
    '"severity":"minor|major"} describing exactly one unforeseen but logical '
    "consequence that the alteration itself causes in this world, as an "
    "observable fact in at most 80 Japanese characters or 25 English words (for "
    "example, suddenly owning a mansion brings a property tax notice that has to "
    "be dealt with). Never make it a change to anyone's feelings, consent, "
    "memories, or body, never repeat an entry of active_reality_costs, and use "
    "major only when the consequence seriously threatens the objective."
)

ROMANCE_REALITY_COST_DUE_INSTRUCTION = (
    "In this dating sim the consequence must be something that costs money to "
    "settle, such as a tax, a fine, a fee, a repair, or compensation. Never state "
    "an amount; the game decides it from the severity."
)
