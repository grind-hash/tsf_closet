from .achievements_router import router as achievements_router
from .aivisspeech_router import router as aivisspeech_router
from .adventure_router import router as adventure_router
from .avatar_router import router as avatar_router
from .character_router import router as character_router
from .favorites_router import router as favorites_router
from .gallery_router import router as gallery_router
from .game_router import router as game_router
from .memory_router import router as memory_router
from .prompt_expander_router import router as prompt_expander_router
from .settings_router import router as settings_router

__all__ = [
    "achievements_router",
    "aivisspeech_router",
    "adventure_router",
    "avatar_router",
    "character_router",
    "favorites_router",
    "gallery_router",
    "game_router",
    "memory_router",
    "prompt_expander_router",
    "settings_router",
]
