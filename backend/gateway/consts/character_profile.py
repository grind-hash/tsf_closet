"""登場人物の性格プロフィールで使う列挙値と、プロンプトへ載せるときの切り詰め長。

性格プロフィールの形は自分自身モードの SelfProfile と揃えている
（personality / reaction_style / pronoun / gender / interests / tsf_attitude）。
"""

from __future__ import annotations

from typing import Final

REACTION_STYLES: Final[tuple[str, ...]] = (
    "default",
    "bold",
    "gentle",
    "cheerful",
    "shy",
    "calm",
    "passionate",
)
DEFAULT_REACTION_STYLE: Final[str] = "default"

# 空文字は「未設定」。性別を決めずに性格だけ持たせる人物を許すため。
GENDERS: Final[tuple[str, ...]] = ("man", "woman", "")

REACTION_STYLE_LABELS_JA: Final[dict[str, str]] = {
    "bold": "大胆",
    "gentle": "穏やか",
    "cheerful": "明るい",
    "shy": "内気",
    "calm": "冷静",
    "passionate": "情熱的",
}

# 保存時の上限（文字数・個数）
PROFILE_PERSONALITY_MAX_LEN: Final[int] = 500
PROFILE_PRONOUN_MAX_LEN: Final[int] = 20
PROFILE_INTEREST_MAX_LEN: Final[int] = 40
PROFILE_INTERESTS_MAX_COUNT: Final[int] = 10
PROFILE_TSF_ATTITUDE_MAX_LEN: Final[int] = 300
PROFILE_MEMO_MAX_LEN: Final[int] = 1000

# 登場人物一覧としてプロンプトへ載せるときの上限。22 人分を載せても
# 1 人あたり 150 文字程度に収まるよう、保存時より短く切る。
PROMPT_PERSONALITY_MAX_LEN: Final[int] = 120
PROMPT_TSF_ATTITUDE_MAX_LEN: Final[int] = 80
PROMPT_INTERESTS_MAX_COUNT: Final[int] = 3


__all__ = [
    "REACTION_STYLES",
    "DEFAULT_REACTION_STYLE",
    "GENDERS",
    "REACTION_STYLE_LABELS_JA",
    "PROFILE_PERSONALITY_MAX_LEN",
    "PROFILE_PRONOUN_MAX_LEN",
    "PROFILE_INTEREST_MAX_LEN",
    "PROFILE_INTERESTS_MAX_COUNT",
    "PROFILE_TSF_ATTITUDE_MAX_LEN",
    "PROFILE_MEMO_MAX_LEN",
    "PROMPT_PERSONALITY_MAX_LEN",
    "PROMPT_TSF_ATTITUDE_MAX_LEN",
    "PROMPT_INTERESTS_MAX_COUNT",
]
