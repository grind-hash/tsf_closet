from typing import Any

from .app_settings import BASE_DIR, Settings, configure_logging, settings

__all__ = [
    "BASE_DIR",
    "Settings",
    "configure_logging",
    "settings",
    "router",
    "UserSettingsModel",
    "UserSettingsResponse",
    "UserSettingsUpdateRequest",
    "InpaintSettingsModel",
    "ChangeSettingsModel",
    "SettingsModel",
    "SettingsResponse",
    "SettingsUpdateRequest",
]


def __getattr__(name: str) -> Any:
    if name in {
        "router",
        "UserSettingsModel",
        "UserSettingsResponse",
        "UserSettingsUpdateRequest",
        "InpaintSettingsModel",
        "ChangeSettingsModel",
        "SettingsModel",
        "SettingsResponse",
        "SettingsUpdateRequest",
    }:
        from ..routes.settings_router import (
            ChangeSettingsModel,
            InpaintSettingsModel,
            SettingsModel,
            SettingsResponse,
            SettingsUpdateRequest,
            UserSettingsModel,
            UserSettingsResponse,
            UserSettingsUpdateRequest,
            router,
        )

        export_map = {
            "router": router,
            "UserSettingsModel": UserSettingsModel,
            "UserSettingsResponse": UserSettingsResponse,
            "UserSettingsUpdateRequest": UserSettingsUpdateRequest,
            "InpaintSettingsModel": InpaintSettingsModel,
            "ChangeSettingsModel": ChangeSettingsModel,
            "SettingsModel": SettingsModel,
            "SettingsResponse": SettingsResponse,
            "SettingsUpdateRequest": SettingsUpdateRequest,
        }
        return export_map[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
