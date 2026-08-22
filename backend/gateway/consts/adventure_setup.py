"""Limits for user-authored Adventure mission setups.

The setting / objective / constraints entered on the setup screen are sent to
both ``POST /adventure/setup/generate`` (as the author's draft) and
``POST /adventure/runs``. Keep the constraint count bound here so the request
models, the LLM output schema, and the frontend hint stay in sync.
"""

from __future__ import annotations

# 1 行 1 件で入力される制約の上限件数。4 件では詳細なキャラクター設定を
# 書き切れず 422 になったため、LLM プロンプトに収まる範囲で広げている
SCENARIO_CONSTRAINTS_MAX_ITEMS: int = 20

__all__ = ["SCENARIO_CONSTRAINTS_MAX_ITEMS"]
