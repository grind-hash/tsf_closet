from .achievements_router import router as achievements_router
from .gallery_router import router as gallery_router
from .game_router import router as game_router
from .settings_router import router as settings_router

__all__ = [
    "achievements_router",
    "gallery_router",
    "game_router",
    "settings_router",
]
