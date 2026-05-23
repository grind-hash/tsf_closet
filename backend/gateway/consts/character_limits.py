"""SessionCharacter の外見フィールドに対するサーバ側ハードキャップ定数。

長ターン運用で LLM が `appearance_natural` / `appearance_tags` に差分を追記し続け、
レコードが肥大化していく事象を防ぐための上限。

- プロンプト側では更に短め（natural 120 文字程度）を推奨するが、ここではその上限を
  超えた出力もサイレントに切り詰めるための安全網として、やや緩めの値を採用する。
- 値は文字数（Python str の文字単位）。
"""

from __future__ import annotations

from typing import Final

# 外見・自然文の上限（文字数）。プロンプト指示 120 文字に対する安全網として余裕を持たせる。
APPEARANCE_NATURAL_MAX_LEN: Final[int] = 200

# 外見タグの上限（文字数）。NovelAI 形式タグの数十個分を許容する想定。
APPEARANCE_TAGS_MAX_LEN: Final[int] = 400

# プロンプト指示で LLM に伝える簡潔さの目安（自然文）。
APPEARANCE_NATURAL_SOFT_LIMIT: Final[int] = 120


__all__ = [
    "APPEARANCE_NATURAL_MAX_LEN",
    "APPEARANCE_TAGS_MAX_LEN",
    "APPEARANCE_NATURAL_SOFT_LIMIT",
]
