"""Boundary values for request mode (依頼モード) in the normal game.

The character asks for the look they want to have: a visible wish and 2-3
hidden preferences. The LLM judges each turn only as a fit category and the
list of satisfied preferences; the satisfaction number is decided here.
"""

from __future__ import annotations

REQUEST_WISH_MAX: int = 200
# 成人向けの依頼で、願いの姿でしたいこと(お披露目の体験の場面の指示)の長さ
REQUEST_EXPERIENCE_MAX: int = 200
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
# この満足度に初めて達した手番で依頼達成とする。LLM の判定は曖昧なので、好みを全部
# 満たさなくても、ヒアリングを活かせば届く水準にする
REQUEST_FULFILL_THRESHOLD: int = 70
# 成人向けの依頼で、お披露目の体験の場面まで描けたときの満足度への加点。
# 施術が「良い」帯(55)まで届いていれば、体験で依頼達成(70)に届く大きさにする
REQUEST_EXPERIENCE_BONUS: int = 15
# ヒアリングの反映: カウンセリングの答えを汲んだ姿への加点(1件ごと・上限)
REQUEST_LISTENING_BONUS_PER_ANSWER: int = 10
REQUEST_LISTENING_BONUS_MAX: int = 20

# 施術の手数の上限。None(上限なし)のほか、この範囲で依頼ごとに決める
REQUEST_TURN_LIMIT_MAX: int = 20
# カウンセリングで質問できる回数(既定と上限)と、質問・答えの長さ
REQUEST_QUESTION_LIMIT_DEFAULT: int = 2
REQUEST_QUESTION_LIMIT_MAX: int = 5
REQUEST_QUESTION_MAX: int = 200
REQUEST_ANSWER_MAX: int = 200

# ヒントの強調(サロンのやさしい・ふつう)。心境の中で、まだ満たされていない好みを
# ほのめかす一文をこの記号で囲ませ、接客画面が強調表示する。他の画面では取り除く
REQUEST_HINT_MARK_OPEN: str = "〔"
REQUEST_HINT_MARK_CLOSE: str = "〕"

# 評価に失敗した手番も手数として数えるため、履歴へこの印を残す(満足度には使わない)
REQUEST_EVALUATION_FAILED: dict[str, bool] = {"failed": True}
