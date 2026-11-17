"""Boundary values for the salon management mode (サロン経営モード).

Every number of the economy is decided here in Python; the LLM only writes the
customer's review. The defaults follow the user's novel (a mansion salon with
a heavy property tax, a 50,000 yen basic course, two customers per weekend
day) and are meant to be tuned while playing.
"""

from __future__ import annotations

SALON_NAME_MAX: int = 40

# 来客の種類(開店画面とオーナー室で選ぶ)。お客様の性別(元の性別)で予約を絞り、
# 願う体で依頼の向きを決める。any は絞らない(願う体は TSF への態度から生成が選ぶ)。
# 性別は次の週の予約から、願う体は次に接客を始めるお客様から効く
SALON_CUSTOMER_GENDERS: tuple[str, ...] = ("any", "man", "woman")
SALON_DESIRED_BODIES: tuple[str, ...] = ("any", "female", "male")
SALON_DEFAULT_CUSTOMER_GENDER: str = "any"
SALON_DEFAULT_DESIRED_BODY: str = "any"
SALON_REVIEW_MAX: int = 160

# 1 期の長さ。開店時に選び、期の最終週を締めた時点で決算する。決算のあとは同じ長さの
# 次の期へ進める(現金と評判を持ち越す)。短い期は初週から来店が多く、開業資金も小さい
SALON_SEASON_LENGTHS: dict[str, int] = {"short": 4, "standard": 12}
SALON_DEFAULT_SEASON_LENGTH: str = "standard"
# 標準の期の週数(以前の固定値。互換のため残す)
SALON_TOTAL_WEEKS: int = SALON_SEASON_LENGTHS["standard"]

# 毎週の固定費(固定資産税・光熱費・維持費)・本業の収入(小説の年収 500 万円)。
# 毎週の赤字は 20 万円で、1 シーズンで 240 万円
SALON_WEEKLY_FIXED_COST: int = 300_000
SALON_WEEKLY_SALARY: int = 100_000

# 経営の難易度ごとの開業資金(期の長さごと)。成功の線(期首の現金を上回る)は難易度によらず
# 同じで、開業資金は倒産の線だけを動かす。短い期も同じ考え方にそろえる(4 週の赤字は 80 万円)
SALON_INITIAL_CASH: dict[str, dict[str, int]] = {
    "standard": {
        "easy": 3_000_000,  # 接客しなくても倒産しない
        "normal": 2_000_000,  # 接客を怠ると倒産する
        "hard": 1_500_000,  # 満足度 50 前後が続いても倒産する
    },
    "short": {
        "easy": 1_000_000,
        "normal": 600_000,
        "hard": 300_000,
    },
}
# 標準の期の開業資金(以前の名前。互換のため残す)
SALON_DIFFICULTY_INITIAL_CASH: dict[str, int] = SALON_INITIAL_CASH["standard"]
SALON_DEFAULT_DIFFICULTY: str = "normal"
# 施術中の心境で、まだ叶っていない好みをほのめかす一文を強調する難易度。
# むずかしいでは強調せず、文中に紛れたヒントを読み取らせる
SALON_HINT_EMPHASIS_DIFFICULTIES: frozenset[str] = frozenset({"easy", "normal"})
# カウンセリングの答えの手掛かりの強さ(依頼の土台の REQUEST_CLUE_LEVELS)
SALON_CLUE_LEVELS: dict[str, str] = {
    "easy": "plain",
    "normal": "normal",
    "hard": "subtle",
}

# 基本コースの料金と、満足度による係数
SALON_BASE_PRICE: int = 50_000
SALON_PRICE_RATE_LOW: float = 0.5  # 満足度が SALON_LOW_SATISFACTION 未満
SALON_PRICE_RATE_NORMAL: float = 1.0
SALON_PRICE_RATE_FULFILLED: float = 1.5  # 依頼達成
SALON_PRICE_RATE_PERFECT: float = (
    2.0  # 満足度 SALON_PERFECT_SATISFACTION(満点の仕上がり)
)
SALON_PERFECT_SATISFACTION: int = 100
SALON_LOW_SATISFACTION: int = 40

# 依頼を達成したお客様の上乗せ。評判が高いほどチップが増え、姿を持ち越して続けて来る
# 常連ほど指名料が増える。評判が予約数だけでなく、1 人あたりの売上にも効くようにする
SALON_TIP_PER_REPUTATION: int = 500  # 会計前の評判 1 点あたり(評判 80 で 4 万円)
SALON_REGULAR_FEE_PER_VISIT: int = 10_000  # 続けて来た回数 1 回あたり
SALON_REGULAR_FEE_MAX: int = 30_000

# 評判(0〜100)。依頼達成の線は依頼の土台(REQUEST_FULFILL_THRESHOLD)に従う。
# 開店時の評判は期の長さで変える(短い期は初週から 2 名)
SALON_INITIAL_REPUTATION_BY_LENGTH: dict[str, int] = {"standard": 20, "short": 45}
SALON_INITIAL_REPUTATION: int = SALON_INITIAL_REPUTATION_BY_LENGTH["standard"]
SALON_REPUTATION_MIN: int = 0
SALON_REPUTATION_MAX: int = 100
SALON_REPUTATION_FULFILLED: int = 8
SALON_REPUTATION_GOOD: int = 3  # 満足度 SALON_GOOD_SATISFACTION 以上(未達成)
SALON_GOOD_SATISFACTION: int = 55
SALON_REPUTATION_POOR: int = -5  # 満足度 SALON_LOW_SATISFACTION 未満
SALON_REPUTATION_DECLINED: int = -3  # 予約を断る・週を締めるまで接客しなかった

# 翌週の予約数 = 1 + 評判 ÷ SALON_BOOKINGS_REPUTATION_STEP(上限あり)。
# 上限は小説の「週末2日 × 2名」
SALON_BOOKINGS_REPUTATION_STEP: int = 25
SALON_BOOKINGS_MAX: int = 4

# 接客の依頼は、施術3手・カウンセリングの質問2回(小説の3時間コース)
SALON_TURN_LIMIT: int = 3
SALON_QUESTION_LIMIT: int = 2

# 資金を払って足せる施術(手数を使い切った後、来店1回につき SALON_EXTRA_TURNS_MAX 手まで)。
# 値段は基本料金と同じ: 成功すれば翌週の来店まで含めて得をし、失敗すれば損をする賭けにする
SALON_EXTRA_TURN_PRICE: int = 50_000
SALON_EXTRA_TURNS_MAX: int = 1
