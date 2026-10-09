"""登場人物（SessionCharacter）まわりの長さと人数の上限。

- 外見の上限は、プロンプトへ載せる・姿のソースから取り込むときの切り詰めに使う。
- 値は文字数（Python str の文字単位）。
"""

from __future__ import annotations

from typing import Final

# 外見・自然文の上限（文字数）。
APPEARANCE_NATURAL_MAX_LEN: Final[int] = 200

# 外見タグの上限（文字数）。NovelAI 形式タグの数十個分を許容する想定。
APPEARANCE_TAGS_MAX_LEN: Final[int] = 400

# 人物ごとのネガティブタグの上限（文字数）。
NEGATIVE_TAGS_MAX_LEN: Final[int] = 400

# 1 セッションに登録できる人物数（主人公を含む）。NovelAI V5 のキャラクター
# プロンプト上限（22）に合わせる。登場させられる人数は画像モデルごとに別途絞る。
MAX_REGISTERED_CHARACTERS: Final[int] = 22


__all__ = [
    "APPEARANCE_NATURAL_MAX_LEN",
    "APPEARANCE_TAGS_MAX_LEN",
    "NEGATIVE_TAGS_MAX_LEN",
    "MAX_REGISTERED_CHARACTERS",
]
