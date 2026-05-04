"""History lookback count boundaries for spec 004.

Used by SettingsModel and prompt-building services to determine how many
recent history entries are referenced in LLM prompts.
"""

from __future__ import annotations

HISTORY_LOOKBACK_DEFAULT: int = 10
HISTORY_LOOKBACK_MIN: int = 5
HISTORY_LOOKBACK_MAX: int = 20

__all__ = [
    "HISTORY_LOOKBACK_DEFAULT",
    "HISTORY_LOOKBACK_MIN",
    "HISTORY_LOOKBACK_MAX",
]
