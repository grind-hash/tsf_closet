"""Turn budget boundaries for auto-generated Adventure missions.

Authored scenarios take max_turns from their JSON template and replays
inherit it from the source run, so these bounds apply only to the
auto-generated branch of AdventureService.create_run.
"""

from __future__ import annotations

ADVENTURE_TURNS_DEFAULT: int = 15
ADVENTURE_TURNS_MIN: int = 5
ADVENTURE_TURNS_MAX: int = 30

__all__ = [
    "ADVENTURE_TURNS_DEFAULT",
    "ADVENTURE_TURNS_MIN",
    "ADVENTURE_TURNS_MAX",
]
