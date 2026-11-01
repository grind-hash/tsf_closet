"""Boundary values for the salon management mode (サロン経営モード).

Every number of the economy is decided here in Python; the LLM only writes the
customer's review. The defaults follow the user's novel (a mansion salon with
a heavy property tax, a 50,000 yen basic course, two customers per weekend
day) and are meant to be tuned while playing.
"""

from __future__ import annotations

SALON_NAME_MAX: int = 40
SALON_REVIEW_MAX: int = 160

# 1 シーズンの週数。最終週を締めた時点で決算する
SALON_TOTAL_WEEKS: int = 12

# 毎週の固定費(固定資産税・光熱費・維持費)・本業の収入(小説の年収 500 万円)。
# 毎週の赤字は 20 万円で、1 シーズンで 240 万円
SALON_WEEKLY_FIXED_COST: int = 300_000
SALON_WEEKLY_SALARY: int = 100_000

# 経営の難易度ごとの開業資金。成功の線(開業資金を上回る)は難易度によらず同じで、
# 開業資金は倒産の線だけを動かす
SALON_DIFFICULTY_INITIAL_CASH: dict[str, int] = {
    "easy": 3_000_000,  # 接客しなくても倒産しない
    "normal": 2_000_000,  # 接客を怠ると倒産する
    "hard": 1_500_000,  # 満足度 50 前後が続いても倒産する
}
SALON_DEFAULT_DIFFICULTY: str = "normal"

# 基本コースの料金と、満足度による係数
SALON_BASE_PRICE: int = 50_000
SALON_PRICE_RATE_LOW: float = 0.5  # 満足度が SALON_LOW_SATISFACTION 未満
SALON_PRICE_RATE_NORMAL: float = 1.0
SALON_PRICE_RATE_FULFILLED: float = 1.5  # 依頼達成(チップ込み)
SALON_LOW_SATISFACTION: int = 40

# 評判(0〜100)。依頼達成の線は依頼の土台(REQUEST_FULFILL_THRESHOLD)に従う
SALON_INITIAL_REPUTATION: int = 20
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
