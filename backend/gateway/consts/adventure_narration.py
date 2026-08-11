"""Narration voice options for Adventure mode.

The voice controls only the grammatical person of the generated prose.
second_person is the default because it matches how existing runs were
generated before the option existed.
"""

from __future__ import annotations

from typing import Literal

NarrationVoice = Literal["second_person", "third_person", "first_person"]

NARRATION_VOICES: tuple[str, ...] = (
    "second_person",
    "third_person",
    "first_person",
)
NARRATION_VOICE_DEFAULT: str = "second_person"
NARRATION_PRONOUN_DEFAULT: str = "僕"
NARRATION_PRONOUN_MAX_LENGTH: int = 10

__all__ = [
    "NarrationVoice",
    "NARRATION_VOICES",
    "NARRATION_VOICE_DEFAULT",
    "NARRATION_PRONOUN_DEFAULT",
    "NARRATION_PRONOUN_MAX_LENGTH",
]
