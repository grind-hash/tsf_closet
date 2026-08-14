"""BGM category keys for Adventure mode.

The LLM selects one semantic key per turn; the frontend maps keys to
audio files and handles playback. Keys are the only contract between
the two layers, so the LLM must never see or emit filenames.
"""

from __future__ import annotations

from typing import Literal

BgmKey = Literal[
    "private_action",
    "bossa_nova",
    "elegant_party",
    "royal",
    "dark",
    "daily",
    "important_event",
    "bar",
]

BGM_KEYS: tuple[str, ...] = (
    "private_action",
    "bossa_nova",
    "elegant_party",
    "royal",
    "dark",
    "daily",
    "important_event",
    "bar",
)

# daily is also the fallback when no category clearly fits the scene.
BGM_KEY_DEFAULT: str = "daily"

BGM_DESCRIPTIONS: dict[str, str] = {
    "private_action": "intimate private moments",
    "bossa_nova": "beach, resort, or travel scenes",
    "elegant_party": "lavish parties, celebrities, formal social events",
    "royal": "castles, palaces, royalty",
    "dark": "dark, ominous, sad, dangerous, or serious events",
    "daily": "everyday ordinary scenes; also the fallback",
    "important_event": (
        "rare climactic turning points only: confessions, life-changing "
        "revelations, decisive relationship shifts"
    ),
    "bar": "cafes, bars, lounges, restaurants",
}

# Shared enumeration for the director and resolution system prompts.
BGM_PROMPT_GUIDE: str = ", ".join(
    f"{key} ({description})" for key, description in BGM_DESCRIPTIONS.items()
)

# Shared selection policy for the director and resolution system prompts.
# Grounds "importance" in relationship/story progression so a minor early
# event (e.g. a small gift right after the start) never gets the climax track.
BGM_SELECTION_RULES: str = (
    "Choose the category from the scene's location and mood, weighed against "
    "how far the story and the relationship have actually progressed. "
    "important_event is reserved for a rare climactic turning point relative "
    "to that progression, such as a confession, its decisive answer, or a "
    "revelation that permanently changes the relationship or the story. When "
    "state.sim.affection (0-100) and state.sim.stage are present, measure the "
    "relationship progression with them: while affection is low or the stage "
    "is early, greetings, small gifts, first outings, and pleasant "
    "conversation are ordinary courtship beats that take daily or the "
    "category matching the location, even when the partner is delighted. "
    "When no category clearly fits, use daily; when in doubt between "
    "important_event and another category, choose the other category."
)

__all__ = [
    "BgmKey",
    "BGM_KEYS",
    "BGM_KEY_DEFAULT",
    "BGM_DESCRIPTIONS",
    "BGM_PROMPT_GUIDE",
    "BGM_SELECTION_RULES",
]
