"""通常プレイの入力文字数の上限。

値は文字数（Python str の文字単位）。
"""

from __future__ import annotations

from typing import Final

# 着せ替え・現実改変・行動の指示の上限。お気に入りプロンプトの内容上限と揃え、
# 保存したタグをそのまま挿入しても送信できるようにする。
INSTRUCTION_MAX_LENGTH: Final[int] = 4000

# 現実改変の指示は、この前置きを付けてセッション属性へ自動追加する。
REALITY_ATTRIBUTE_PREFIX: Final[str] = "[現実改変] "

# 属性の上限。現実改変で自動追加された属性もそのまま編集できるよう、前置きの分を足す。
ATTRIBUTE_TEXT_MAX_LENGTH: Final[int] = INSTRUCTION_MAX_LENGTH + len(
    REALITY_ATTRIBUTE_PREFIX
)
