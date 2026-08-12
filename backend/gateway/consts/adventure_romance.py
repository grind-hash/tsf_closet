"""Boundary values for the romance (dating-sim) Adventure preset.

Money, days, affection, gift scoring, and confession outcomes are decided
deterministically in Python; the LLM never writes these numbers. Day and
slot are derived from turn_number, so none of these values are stored
per-turn. Applies only to preset="romance" runs.
"""

from __future__ import annotations

ROMANCE_DAYS_DEFAULT: int = 7
ROMANCE_DAYS_MIN: int = 5
ROMANCE_DAYS_MAX: int = 15
ROMANCE_SLOTS_PER_DAY: int = 2

ROMANCE_AFFECTION_START: int = 10
ROMANCE_AFFECTION_MIN: int = 0
ROMANCE_AFFECTION_MAX: int = 100

# 関係段階の閾値。affection がこの値以上で当該段階に到達する
ROMANCE_STAGE_THRESHOLDS: dict[str, int] = {
    "friend": 25,
    "aware": 50,
    "mutual": 75,
}

# 段階到達で自動達成するマイルストーンの対応
ROMANCE_STAGE_MILESTONE_IDS: dict[str, str] = {
    "friend": "become_friends",
    "aware": "mutual_interest",
    "mutual": "mutual_love",
}

ROMANCE_CONFESSION_THRESHOLD: int = 75
ROMANCE_CONFESSION_FAIL_PENALTY: int = -10

# 会話系ターン(choice/free_text)で LLM の affection_delta を収める幅
ROMANCE_TALK_DELTA_LIMIT: int = 3
# 属性付与(reality_alter)ターンで LLM の affection_delta を収める幅
ROMANCE_ALTER_DELTA_LIMIT: int = 20

ROMANCE_INITIAL_MONEY: int = 5000
ROMANCE_WORK_WAGE: int = 3000
ROMANCE_WORK_ENCOUNTER_RATE: float = 0.25
ROMANCE_WORK_ENCOUNTER_BONUS: int = 2

# ギフト tier ごとの価格帯 (下限, 上限)
ROMANCE_GIFT_TIER_PRICES: dict[str, tuple[int, int]] = {
    "budget": (500, 2000),
    "standard": (2001, 6000),
    "luxury": (6001, 15000),
}

# ギフト tier × 好み一致による好感度加点
ROMANCE_GIFT_POINTS: dict[str, dict[str, int]] = {
    "budget": {"liked": 8, "neutral": 2, "disliked": -4},
    "standard": {"liked": 12, "neutral": 3, "disliked": -6},
    "luxury": {"liked": 16, "neutral": 4, "disliked": -8},
}

ROMANCE_MILESTONES: list[dict[str, str]] = [
    {"id": "become_friends", "label": "友人になる"},
    {"id": "mutual_interest", "label": "意識し合う"},
    {"id": "mutual_love", "label": "両想いになる"},
    {"id": "start_dating", "label": "交際を始める"},
]

ROMANCE_DATING_MILESTONE_ID: str = "start_dating"

# 主人公(自分)の既定テンプレートキャラクター。開始セッションの人物は攻略対象になる
ROMANCE_PLAYER_DEFAULT_CHARACTER_ID: str = "char1"

__all__ = [
    "ROMANCE_DAYS_DEFAULT",
    "ROMANCE_DAYS_MIN",
    "ROMANCE_DAYS_MAX",
    "ROMANCE_SLOTS_PER_DAY",
    "ROMANCE_AFFECTION_START",
    "ROMANCE_AFFECTION_MIN",
    "ROMANCE_AFFECTION_MAX",
    "ROMANCE_STAGE_THRESHOLDS",
    "ROMANCE_STAGE_MILESTONE_IDS",
    "ROMANCE_CONFESSION_THRESHOLD",
    "ROMANCE_CONFESSION_FAIL_PENALTY",
    "ROMANCE_TALK_DELTA_LIMIT",
    "ROMANCE_ALTER_DELTA_LIMIT",
    "ROMANCE_INITIAL_MONEY",
    "ROMANCE_WORK_WAGE",
    "ROMANCE_WORK_ENCOUNTER_RATE",
    "ROMANCE_WORK_ENCOUNTER_BONUS",
    "ROMANCE_GIFT_TIER_PRICES",
    "ROMANCE_GIFT_POINTS",
    "ROMANCE_MILESTONES",
    "ROMANCE_DATING_MILESTONE_ID",
    "ROMANCE_PLAYER_DEFAULT_CHARACTER_ID",
]
