"""TSF Bloomer (育成モード) の定数定義。

前半は既存セッションから 6 軸の素質を決定論的に導出するための重み付け、
後半は育成ループ (日数 / アクション / 拒否判定 / ステージ / 衣装) の調整値。
"""

from __future__ import annotations

from typing import Any, Final, Literal

# =============================================================================
# 6 軸の素質 (LLM 非使用の決定論導出)
# =============================================================================

AxisKey = Literal[
    "allure", "technique", "depravity", "sensitivity", "endurance", "composure"
]

AXIS_KEYS: Final[tuple[str, ...]] = (
    "allure",
    "technique",
    "depravity",
    "sensitivity",
    "endurance",
    "composure",
)

AXIS_MIN: Final[int] = 1
AXIS_MAX: Final[int] = 100
AXIS_TOTAL_TARGET: Final[int] = 280
AXIS_TOTAL_TOLERANCE: Final[int] = 30
CORE_AXIS_FLOOR: Final[int] = 12

CORE_AXIS_WEIGHTS: Final[dict[str, dict[str, float]]] = {
    "allure": {
        "initiative": 0.28,
        "dominance": 0.17,
        "exposure_score": 0.25,
        "partner_bond": 0.15,
        "transformation_progress": 0.15,
    },
    "technique": {
        "intimacy": 0.30,
        "costume_diversity": 0.22,
        "type_diversity": 0.18,
        "history_progress": 0.30,
    },
    "depravity": {
        "received": 0.30,
        "submission": 0.20,
        "partner_variety": 0.12,
        "reality_ratio": 0.10,
        "exposure_score": 0.18,
        "deprived_costume_ratio": 0.10,
    },
    "sensitivity": {
        "climax": 0.38,
        "received": 0.22,
        "receptivity": 0.25,
        "tsf_identity": 0.15,
    },
    "endurance": {
        "transformation_progress": 0.34,
        "receptivity": 0.20,
        "resistance": 0.16,
        "history_progress": 0.18,
        "conversation_progress": 0.12,
    },
    "composure": {
        "resistance": 0.32,
        "dominance": 0.22,
        "transformation_progress": 0.26,
        "conversation_progress": 0.20,
    },
}

MODIFIER_WEIGHT: Final[float] = 0.30

EXPOSURE_WEIGHTS: Final[dict[str, int]] = {"high": 100, "medium": 55, "low": 20}

REACTION_STYLE_BIAS: Final[dict[str, dict[str, int]]] = {
    "default": {
        "allure": 60,
        "technique": 60,
        "depravity": 60,
        "sensitivity": 60,
        "endurance": 60,
        "composure": 60,
    },
    "bold": {
        "allure": 80,
        "technique": 65,
        "depravity": 65,
        "sensitivity": 50,
        "endurance": 70,
        "composure": 80,
    },
    "gentle": {
        "allure": 65,
        "technique": 60,
        "depravity": 45,
        "sensitivity": 70,
        "endurance": 70,
        "composure": 60,
    },
    "cheerful": {
        "allure": 70,
        "technique": 60,
        "depravity": 55,
        "sensitivity": 60,
        "endurance": 75,
        "composure": 70,
    },
    "shy": {
        "allure": 55,
        "technique": 50,
        "depravity": 60,
        "sensitivity": 85,
        "endurance": 50,
        "composure": 35,
    },
    "calm": {
        "allure": 55,
        "technique": 70,
        "depravity": 40,
        "sensitivity": 45,
        "endurance": 75,
        "composure": 85,
    },
    "passionate": {
        "allure": 85,
        "technique": 65,
        "depravity": 80,
        "sensitivity": 75,
        "endurance": 55,
        "composure": 45,
    },
}

DEPRAVED_COSTUME_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"swimsuit", "underwear", "cosplay"}
)

SELF_PROFILE_ATTITUDE_BONUS: Final[int] = 15
SELF_PROFILE_INTEREST_BONUS: Final[int] = 15
SELF_PROFILE_INTEREST_CAP: Final[int] = 6

ATTRIBUTE_COUNT_CAP: Final[int] = 15
CONVERSATION_COUNT_CAP: Final[int] = 60
HISTORY_COUNT_CAP: Final[int] = 30
TRANSFORMATION_COUNT_CAP: Final[int] = 40
COSTUME_CATEGORY_COUNT: Final[int] = 9
INSTRUCTION_TYPE_COUNT: Final[int] = 4

MAX_TEXT_LENGTH_PER_ROW: Final[int] = 4000
MAX_HISTORY_SCAN: Final[int] = 300
MAX_CONVERSATION_SCAN: Final[int] = 800

# =============================================================================
# キーワード辞書
# =============================================================================

LexiconCategory = Literal[
    "intimacy",
    "climax",
    "received",
    "initiative",
    "receptivity",
    "resistance",
    "dominance",
    "submission",
    "partner",
    "tsf_identity",
    "attitude_positive",
    "attitude_negative",
]

LEXICON_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "intimacy",
        "climax",
        "received",
        "initiative",
        "receptivity",
        "resistance",
        "dominance",
        "submission",
        "partner",
        "tsf_identity",
        "attitude_positive",
        "attitude_negative",
    }
)

LEXICON_CATEGORY_CAPS: Final[dict[str, int]] = {
    "intimacy": 40,
    "climax": 60,
    "received": 40,
    "initiative": 30,
    "receptivity": 40,
    "resistance": 30,
    "dominance": 25,
    "submission": 30,
    "partner": 24,
    "tsf_identity": 50,
    "attitude_positive": 6,
    "attitude_negative": 6,
}

LEXICON_LANGUAGES: Final[tuple[str, ...]] = ("ja", "en")
ATTITUDE_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"attitude_positive", "attitude_negative"}
)

MAX_LEXICON_FILES: Final[int] = 50
MAX_LEXICON_FILE_BYTES: Final[int] = 256 * 1024
MAX_KEYWORDS_PER_FILE: Final[int] = 2000
MAX_KEYWORD_LENGTH: Final[int] = 64

# =============================================================================
# 育成ループ
# =============================================================================

MAX_DAYS: Final[int] = 7
ACTIONS_PER_DAY: Final[int] = 4
MILESTONE_DAYS: Final[tuple[int, ...]] = (2, 4, 6)

STAMINA_MAX: Final[int] = 100
MOOD_MAX: Final[int] = 100
TRUST_MAX: Final[int] = 100

INITIAL_MOOD: Final[int] = 60
INITIAL_TRUST: Final[int] = 10

# 夜を越えたときの持ち越し。機嫌はゆっくり平常値へ戻る
MOOD_NIGHTLY_DRIFT: Final[int] = 4
MOOD_NEUTRAL: Final[int] = 50

RunOrigin = Literal["session", "preset"]
RunStatus = Literal["active", "ended"]
EventKind = Literal["action", "refusal", "milestone", "stage_up", "ending"]

# =============================================================================
# アクション
# =============================================================================

ActionKind = Literal["care", "talk", "train", "outing", "indulge"]

# narrate=True のアクションのみ LLM で反応文を生成する (テンポ優先)
ACTION_CATALOG: Final[dict[str, dict[str, Any]]] = {
    "rest": {
        "kind": "care",
        "stamina": 30,
        "mood": 5,
        "trust": 0,
        "axes": {},
        "req_mood": 0,
        "req_trust": 0,
        "req_nsfw_stage": 0,
        "narrate": False,
        "once_per_day": False,
    },
    "groom": {
        "kind": "care",
        "stamina": -10,
        "mood": 8,
        "trust": 2,
        "axes": {"composure": 2, "allure": 2},
        "req_mood": 15,
        "req_trust": 0,
        "req_nsfw_stage": 0,
        "narrate": False,
        "once_per_day": False,
    },
    "talk": {
        "kind": "talk",
        "stamina": -5,
        "mood": 3,
        "trust": 7,
        "axes": {},
        "req_mood": 10,
        "req_trust": 0,
        "req_nsfw_stage": 0,
        "narrate": True,
        "once_per_day": False,
    },
    "outing": {
        "kind": "outing",
        "stamina": -20,
        "mood": 12,
        "trust": 4,
        "axes": {"allure": 1, "endurance": 1},
        "req_mood": 25,
        "req_trust": 10,
        "req_nsfw_stage": 0,
        "narrate": True,
        "once_per_day": True,
    },
    "indulge_tease": {
        "kind": "indulge",
        "stamina": -20,
        "mood": 15,
        "trust": -3,
        "axes": {"sensitivity": 5, "depravity": 4},
        "req_mood": 40,
        "req_trust": 30,
        "req_nsfw_stage": 1,
        "narrate": True,
        "once_per_day": False,
    },
    "indulge_devote": {
        "kind": "indulge",
        "stamina": -25,
        "mood": 18,
        "trust": -5,
        "axes": {"depravity": 6, "sensitivity": 3, "composure": -2},
        "req_mood": 55,
        "req_trust": 55,
        "req_nsfw_stage": 2,
        "narrate": True,
        "once_per_day": False,
    },
}

TRAIN_ACTION_BASE: Final[dict[str, Any]] = {
    "kind": "train",
    "stamina": -25,
    "mood": -8,
    "trust": 1,
    "req_mood": 30,
    "req_trust": 5,
    "req_nsfw_stage": 0,
    "narrate": False,
    "once_per_day": False,
}

# 主軸の伸び幅と、同時に少しだけ動く副軸
TRAIN_AXIS_GAIN: Final[int] = 6
TRAIN_SUB_AXIS: Final[dict[str, dict[str, int]]] = {
    "allure": {"composure": 1},
    "technique": {"composure": 1},
    "depravity": {"sensitivity": 1, "composure": -1},
    "sensitivity": {"endurance": -1},
    "endurance": {"technique": 1},
    "composure": {"depravity": -1},
}


def build_train_actions() -> dict[str, dict[str, Any]]:
    """train_<axis> を 6 軸ぶん展開する。"""
    actions: dict[str, dict[str, Any]] = {}
    for axis in AXIS_KEYS:
        entry = dict(TRAIN_ACTION_BASE)
        entry["axes"] = {axis: TRAIN_AXIS_GAIN, **TRAIN_SUB_AXIS.get(axis, {})}
        actions[f"train_{axis}"] = entry
    return actions


ALL_ACTIONS: Final[dict[str, dict[str, Any]]] = {
    **ACTION_CATALOG,
    **build_train_actions(),
}

# =============================================================================
# 拒否判定
# =============================================================================

REFUSAL_BASE: Final[float] = 0.15
REFUSAL_SCALE: Final[float] = 0.02
REFUSAL_MIN: Final[float] = 0.15
REFUSAL_MAX: Final[float] = 0.85
REFUSAL_STAMINA_RATIO: Final[float] = 0.5
REFUSAL_MOOD_PENALTY: Final[int] = 5

# =============================================================================
# 成長
# =============================================================================

# 素質が高い軸ほど伸びやすい。倍率は 0.5 (素質1) 〜 1.5 (素質100)
GROWTH_APTITUDE_FLOOR: Final[float] = 0.5
GROWTH_APTITUDE_RANGE: Final[float] = 1.0
# 現在値が高いほど伸びにくくする逓減 (上限に貼り付くのを防ぐ)
GROWTH_CEILING_SOFTNESS: Final[float] = 0.35

# =============================================================================
# ステージ / NSFW 解禁
# =============================================================================

STAGE_MAX: Final[int] = 4

# 各ステージへ上がるための下限。すべて満たした夜に進化する
STAGE_REQUIREMENTS: Final[tuple[dict[str, int], ...]] = (
    {"stage": 1, "trust": 20, "axis_total": 300, "day": 2},
    {"stage": 2, "trust": 40, "axis_total": 340, "day": 3},
    {"stage": 3, "trust": 60, "axis_total": 380, "day": 5},
    {"stage": 4, "trust": 80, "axis_total": 420, "day": 6},
)

# 信頼度がこの値を超えるごとに nsfw_stage が 1 段上がる
NSFW_STAGE_TRUST_THRESHOLDS: Final[tuple[int, ...]] = (25, 50, 75)
NSFW_STAGE_MAX: Final[int] = 3

# =============================================================================
# ワードローブ
# =============================================================================

OUTFIT_CATALOG: Final[dict[str, dict[str, Any]]] = {
    "plain_dress": {
        "required_stage": 0,
        "axis_bonus": {"composure": 3},
        "fit_axis": "composure",
        "tags": "simple dress, modest",
    },
    "school_uniform": {
        "required_stage": 0,
        "axis_bonus": {"technique": 3},
        "fit_axis": "technique",
        "tags": "school uniform, pleated skirt",
    },
    "casual_knit": {
        "required_stage": 0,
        "axis_bonus": {"endurance": 3},
        "fit_axis": "endurance",
        "tags": "knit sweater, casual",
    },
    "frilled_blouse": {
        "required_stage": 1,
        "axis_bonus": {"allure": 4, "composure": 2},
        "fit_axis": "allure",
        "tags": "frilled blouse, ribbon",
    },
    "evening_gown": {
        "required_stage": 2,
        "axis_bonus": {"allure": 6, "composure": 3},
        "fit_axis": "allure",
        "tags": "evening gown, elegant",
    },
    "lace_lingerie": {
        "required_stage": 2,
        "axis_bonus": {"sensitivity": 6, "depravity": 4},
        "fit_axis": "sensitivity",
        "required_nsfw_stage": 2,
        "tags": "lace lingerie",
    },
    "bloom_regalia": {
        "required_stage": 4,
        "axis_bonus": {"allure": 8, "technique": 4, "composure": 4},
        "fit_axis": "allure",
        "tags": "ornate flowing dress, floral motif",
    },
}

INITIAL_OUTFITS: Final[tuple[str, ...]] = (
    "plain_dress",
    "school_uniform",
    "casual_knit",
)

# ステージ進化で解禁される衣装
STAGE_UNLOCK_OUTFITS: Final[dict[int, tuple[str, ...]]] = {
    1: ("frilled_blouse",),
    2: ("evening_gown", "lace_lingerie"),
    4: ("bloom_regalia",),
}

# 着せた衣装が素質と噛み合っていれば機嫌が上がる
OUTFIT_FIT_MOOD_HIGH: Final[int] = 10
OUTFIT_FIT_MOOD_LOW: Final[int] = -8
OUTFIT_FIT_THRESHOLD: Final[int] = 55

# =============================================================================
# 節目イベント (不可逆)
# =============================================================================

MILESTONE_CATALOG: Final[dict[int, dict[str, Any]]] = {
    2: {
        "id": "first_promise",
        "choices": {
            "shelter": {
                "axes": {"composure": 6, "endurance": 4},
                "mood": 8,
                "trust": 10,
                "flag": "sheltered",
            },
            "challenge": {
                "axes": {"technique": 6, "allure": 4},
                "mood": -6,
                "trust": 2,
                "flag": "driven",
            },
            "indulge": {
                "axes": {"sensitivity": 6, "depravity": 4},
                "mood": 12,
                "trust": -4,
                "flag": "indulged",
            },
        },
    },
    4: {
        "id": "turning_point",
        "choices": {
            "restrain": {
                "axes": {"composure": 8, "endurance": 5, "depravity": -4},
                "mood": -8,
                "trust": 6,
                "flag": "restrained",
            },
            "encourage": {
                "axes": {"allure": 8, "technique": 5},
                "mood": 6,
                "trust": 8,
                "flag": "encouraged",
            },
            "release": {
                "axes": {"depravity": 10, "sensitivity": 6, "composure": -5},
                "mood": 14,
                "trust": -6,
                "flag": "released",
            },
        },
    },
    6: {
        "id": "final_wish",
        "choices": {
            "keep": {
                "axes": {"composure": 6, "endurance": 6},
                "mood": 6,
                "trust": 12,
                "flag": "kept",
            },
            "release_free": {
                "axes": {"allure": 8, "technique": 8},
                "mood": 10,
                "trust": 6,
                "flag": "freed",
            },
            "descend": {
                "axes": {"depravity": 12, "sensitivity": 8},
                "mood": 16,
                "trust": -8,
                "flag": "descended",
            },
        },
    },
}

# =============================================================================
# エンディング
# =============================================================================

MAX_ENDING_FILES: Final[int] = 50
MAX_ENDING_FILE_BYTES: Final[int] = 128 * 1024
ENDING_SCHEMA_VERSION: Final[int] = 1
FALLBACK_ENDING_KEY: Final[str] = "quiet_bloom"

# =============================================================================
# 入力制限
# =============================================================================

MAX_NAME_LENGTH: Final[int] = 40
MAX_RUNS_PER_USER: Final[int] = 50
MAX_NARRATION_LENGTH: Final[int] = 400
