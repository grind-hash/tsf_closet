"""Boundary values for the romance (dating-sim) Adventure preset.

Money, days, affection, gift scoring, and confession outcomes are decided
deterministically in Python; the LLM never writes these numbers. Day and
slot are derived from turn_number, so none of these values are stored
per-turn. Applies only to preset="romance" runs.
"""

from __future__ import annotations

ROMANCE_DAYS_DEFAULT: int = 7
ROMANCE_DAYS_MIN: int = 5
ROMANCE_DAYS_MAX: int = 30
ROMANCE_SLOTS_PER_DAY: int = 2

# 現実改変宣言によるタイムリミット(日数)変更で許す上限。
# 作成時の上限(30日)より広く取り、宣言で延長するプレイを許容する
ROMANCE_ALTER_DAYS_MAX: int = 60

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
# 告白ラインを日数へスケールさせる1手あたりの想定獲得ペース。
# 短いランでも正攻法で告白に届くようにし、THRESHOLD は最長ラン用の上限とする
ROMANCE_CONFESSION_PACE: float = 2.2

# 会話系ターン(choice/free_text)で LLM の affection_delta を収める幅
ROMANCE_TALK_DELTA_LIMIT: int = 3
# 属性付与(reality_alter)ターンで LLM の affection_delta を収める幅
ROMANCE_ALTER_DELTA_LIMIT: int = 20
# resolution 生成に失敗した会話ターンへ与える既定の好感度。
# 生成失敗をプレイヤーへの減点にしないための下駄
ROMANCE_TALK_FALLBACK_DELTA: int = 1

ROMANCE_INITIAL_MONEY: int = 5000
# 所持金の下限・上限。現実改変で書き換えられるが、桁あふれと負値だけは防ぐ
ROMANCE_MONEY_MIN: int = 0
ROMANCE_MONEY_MAX: int = 999_999_999
# 属性付与(reality_alter)ターンで LLM の money_delta を収める幅
ROMANCE_ALTER_MONEY_LIMIT: int = 999_999_999
ROMANCE_WORK_WAGE: int = 3000
ROMANCE_WORK_ENCOUNTER_RATE: float = 0.25
ROMANCE_WORK_ENCOUNTER_BONUS: int = 2

# 背景は (現在地, 時間帯) ごとに1枚生成してキャッシュする。
# 生成回数が青天井にならないよう1ラン内の総枚数を制限する
ROMANCE_BACKGROUND_CACHE_MAX: int = 12

# 時間帯ごとに scene_tags へ前置する照明タグ
ROMANCE_SLOT_SCENE_TAGS: dict[str, str] = {
    "day": "daytime, daylight, bright natural lighting",
    "night": "night, nighttime, dark sky, artificial lighting",
}

# 反対の時間帯を示すタグ。previous_image_tags 経由で引き継がれるため、
# 前置する前に取り除いて矛盾したタグが並ばないようにする
ROMANCE_SLOT_CONFLICT_TAGS: dict[str, tuple[str, ...]] = {
    "day": (
        "night",
        "nighttime",
        "at night",
        "moonlight",
        "moonlit",
        "starry sky",
        "night sky",
        "sunset",
        "dusk",
        "twilight",
        "dark sky",
        "artificial lighting",
    ),
    "night": (
        "daytime",
        "daylight",
        "sunlight",
        "sunny",
        "noon",
        "midday",
        "blue sky",
        "bright natural lighting",
        "bright sunlight",
    ),
}

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

# 専用の行動ボタンで扱う操作。LLM が同じ内容を選択肢として出しても、
# 選んだ時に機械処理が走らず空振りするため、サーバ側で除去する
ROMANCE_RESERVED_CHOICE_PATTERNS: tuple[str, ...] = (
    r"告白|想いを告げる|愛の告白|交際を申し込",
    r"(プレゼント|贈り物|ギフト).*(贈|買|購入|渡)",
    r"(贈|買|購入).*(プレゼント|贈り物|ギフト)",
    r"バイト|アルバイト|働きに|仕事に出|勤務に",
    r"属性を付与|現実改変",
    r"\bconfess\b|confession",
    r"\bgift\b|\bpresent\b",
    r"part-?time|work shift|go to work",
    r"grant an attribute|alter reality",
)

# 予約語で選択肢が消えたときに補充する会話ビート
ROMANCE_FALLBACK_CHOICES: dict[str, list[dict[str, str]]] = {
    "ja": [
        {"id": "romance_small_talk", "label": "他愛ない話をする"},
        {"id": "romance_walk_together", "label": "一緒に少し歩く"},
        {"id": "romance_observe", "label": "相手の様子をうかがう"},
    ],
    "en": [
        {"id": "romance_small_talk", "label": "Make small talk"},
        {"id": "romance_walk_together", "label": "Walk together for a while"},
        {"id": "romance_observe", "label": "Watch how they are doing"},
    ],
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

# トークモード(手番を消費しない会話)。ログは run の state_json["talk_log"] に
# 保持し、件数上限を超えた分は古い順に捨てる
ROMANCE_TALK_LOG_MAX: int = 40
# 1メッセージの入力上限と、LLM 返答を切り詰める長さ
ROMANCE_TALK_INPUT_MAX: int = 500
ROMANCE_TALK_REPLY_MAX: int = 400
# 次の手番へ文脈として渡す直近件数(手番をまたいで最新から数える)
ROMANCE_TALK_CONTEXT_MAX: int = 12
# トークの LLM 呼び出しへチャット履歴(user/assistant メッセージ)として渡す
# 直近件数。手番をまたいで最新から数える
ROMANCE_TALK_HISTORY_MAX: int = 24
# トークの LLM 呼び出しへ渡す直近の場面(手番)数。好感度の推移も併せて渡す
ROMANCE_TALK_SCENE_CONTEXT_MAX: int = 5

# 対面会話モードの台本形式やトークで主人公名が無いときの呼称
ROMANCE_PLAYER_NAME_FALLBACK: dict[str, str] = {"ja": "主人公", "en": "You"}

__all__ = [
    "ROMANCE_DAYS_DEFAULT",
    "ROMANCE_DAYS_MIN",
    "ROMANCE_DAYS_MAX",
    "ROMANCE_ALTER_DAYS_MAX",
    "ROMANCE_SLOTS_PER_DAY",
    "ROMANCE_AFFECTION_START",
    "ROMANCE_AFFECTION_MIN",
    "ROMANCE_AFFECTION_MAX",
    "ROMANCE_STAGE_THRESHOLDS",
    "ROMANCE_STAGE_MILESTONE_IDS",
    "ROMANCE_CONFESSION_THRESHOLD",
    "ROMANCE_CONFESSION_FAIL_PENALTY",
    "ROMANCE_CONFESSION_PACE",
    "ROMANCE_TALK_DELTA_LIMIT",
    "ROMANCE_TALK_FALLBACK_DELTA",
    "ROMANCE_ALTER_DELTA_LIMIT",
    "ROMANCE_INITIAL_MONEY",
    "ROMANCE_MONEY_MIN",
    "ROMANCE_MONEY_MAX",
    "ROMANCE_ALTER_MONEY_LIMIT",
    "ROMANCE_WORK_WAGE",
    "ROMANCE_WORK_ENCOUNTER_RATE",
    "ROMANCE_WORK_ENCOUNTER_BONUS",
    "ROMANCE_BACKGROUND_CACHE_MAX",
    "ROMANCE_SLOT_SCENE_TAGS",
    "ROMANCE_SLOT_CONFLICT_TAGS",
    "ROMANCE_GIFT_TIER_PRICES",
    "ROMANCE_GIFT_POINTS",
    "ROMANCE_RESERVED_CHOICE_PATTERNS",
    "ROMANCE_FALLBACK_CHOICES",
    "ROMANCE_MILESTONES",
    "ROMANCE_DATING_MILESTONE_ID",
    "ROMANCE_PLAYER_DEFAULT_CHARACTER_ID",
    "ROMANCE_TALK_LOG_MAX",
    "ROMANCE_TALK_INPUT_MAX",
    "ROMANCE_TALK_REPLY_MAX",
    "ROMANCE_TALK_CONTEXT_MAX",
    "ROMANCE_TALK_HISTORY_MAX",
    "ROMANCE_TALK_SCENE_CONTEXT_MAX",
    "ROMANCE_PLAYER_NAME_FALLBACK",
]
