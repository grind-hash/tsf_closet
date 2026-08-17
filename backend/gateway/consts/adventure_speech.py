"""Speech register options for Adventure mode.

The speech style controls how the player character and the romance partner
speak in dialogue. It is independent from narration voice, which only decides
the grammatical person of the surrounding prose.

polite is the default because a player working a service job reads as rude
when the model defaults to casual speech toward the partner.
"""

from __future__ import annotations

from typing import Literal

SpeechStyle = Literal["polite", "casual", "formal", "custom"]

SPEECH_STYLES: tuple[str, ...] = (
    "polite",
    "casual",
    "formal",
    "custom",
)
SPEECH_STYLE_DEFAULT: str = "polite"
# custom を選んだときの自由入力。システムプロンプトへ入るため短く抑える
SPEECH_CUSTOM_MAX_LENGTH: int = 120
# 攻略対象の口調。LLM が生成するか、ユーザーが上書きする
PARTNER_SPEECH_STYLE_MAX_LENGTH: int = 200

__all__ = [
    "SpeechStyle",
    "SPEECH_STYLES",
    "SPEECH_STYLE_DEFAULT",
    "SPEECH_CUSTOM_MAX_LENGTH",
    "PARTNER_SPEECH_STYLE_MAX_LENGTH",
]
