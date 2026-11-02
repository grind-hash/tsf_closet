"""Boundary values for the Adventure reality-cost (改変の代償) option.

Each reality alteration on a run with ``reality_cost_enabled`` creates one
cost: an unforeseen but logical consequence of the declaration, stored in
``AdventureRun.state_json["reality_costs"]``. The LLM writes only the text and
the severity; limits, bill amounts, and the ending gate are decided in Python.
"""

from __future__ import annotations

from .adventure_romance import ROMANCE_WORK_WAGE

REALITY_COST_SEVERITIES: tuple[str, ...] = ("minor", "major")
REALITY_COST_DEFAULT_SEVERITY: str = "minor"

REALITY_COST_TEXT_MAX: int = 120
REALITY_COST_SOURCE_RULE_MAX: int = 200

# 未解決のまま同時に抱えられる上限。超えた手番は代償を発生させない
# (HUD とプロンプトの肥大を防ぐ)
REALITY_COST_MAX_ACTIVE: int = 5
# 解決済みを含めて state に残す件数の上限。超えたら古い解決済みから落とす
REALITY_COST_HISTORY_MAX: int = 20

# romance の請求額。バイト1枠の賃金を単位にし、major は2枠分
ROMANCE_REALITY_BILL_AMOUNTS: dict[str, int] = {
    "minor": ROMANCE_WORK_WAGE,
    "major": ROMANCE_WORK_WAGE * 2,
}
