"""Boundary values for request mode (依頼モード) in the normal game.

The character asks for the look they want to have: a visible wish and 2-3
hidden preferences. The LLM judges each turn only as a fit category and the
list of satisfied preferences; the satisfaction number is decided here.
"""

from __future__ import annotations

REQUEST_WISH_MAX: int = 200
REQUEST_PREFERENCES_MIN: int = 2
REQUEST_PREFERENCES_MAX: int = 3
REQUEST_PREFERENCE_TEXT_MAX: int = 80
REQUEST_PREFERENCE_HINT_MAX: int = 30
REQUEST_EVALUATION_HINT_MAX: int = 120

REQUEST_FITS: tuple[str, ...] = ("none", "partial", "good", "perfect")
# 願い全体への近さで決まる点数。好みの点数(最大 REQUEST_PREFERENCES_SCORE)と合算する
REQUEST_FIT_SCORES: dict[str, int] = {
    "none": 0,
    "partial": 20,
    "good": 40,
    "perfect": 60,
}
REQUEST_PREFERENCES_SCORE: int = 40
# この満足度に初めて達した手番で依頼達成とする
REQUEST_FULFILL_THRESHOLD: int = 80
