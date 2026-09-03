import pytest

from gateway.routes.settings_router import (
    ChangeSettingsModel,
    InpaintSettingsModel,
    SettingsModel,
    SettingsUpdateRequest,
    router as new_settings_router,
)
from gateway.services.settings_service import settings_service
from gateway.settings import router as legacy_settings_router


def test_settings_router_backward_compatibility_export() -> None:
    assert legacy_settings_router is new_settings_router


def test_settings_service_updates_nested_settings() -> None:
    session_id = "unit-refactor-test"
    updates = SettingsUpdateRequest(
        inpaint_settings=InpaintSettingsModel(strength=0.55, mask_blur=8),
        change_settings=ChangeSettingsModel(preserve_face=False, preserve_hair=True),
        inpaint_enabled=True,
    )

    updated = settings_service.update_settings_for_session(
        session_id=session_id,
        updates=updates,
        settings_model_cls=SettingsModel,
        inpaint_model_cls=InpaintSettingsModel,
        change_model_cls=ChangeSettingsModel,
    )

    assert updated.inpaint_enabled is True
    assert updated.inpaint_settings.strength == 0.55
    assert updated.inpaint_settings.mask_blur == 8
    assert updated.change_settings.preserve_face is False


@pytest.mark.asyncio
async def test_user_settings_response_reports_real_world_availability(
    monkeypatch,
) -> None:
    """設定画面が「なぜ効かないか」を出し分けるためのサーバ側フラグを返す。"""
    import importlib
    from unittest.mock import AsyncMock

    from gateway.routes.settings_router import UserSettingsUpdateRequest

    # gateway.routes は同名で APIRouter を再輸出しているため、モジュール自体を取る
    settings_router = importlib.import_module("gateway.routes.settings_router")
    from gateway.services.real_world_context_service import settings as app_settings

    defaults = settings_service._default_user_settings()
    monkeypatch.setattr(
        settings_router.settings_service,
        "get_user_settings",
        AsyncMock(return_value=defaults),
    )
    monkeypatch.setattr(app_settings, "enable_prompt_preview", True)
    monkeypatch.setattr(app_settings, "weather_location", "Tokyo")
    monkeypatch.setattr(app_settings, "tavily_api_key", "")

    response = await settings_router.get_user_settings()

    assert response.prompt_preview_enabled is True
    assert response.weather_configured is True
    assert response.web_search_configured is False
    assert response.real_world_weather_enabled is False
    assert response.real_world_search_enabled is False

    request = UserSettingsUpdateRequest(real_world_search_enabled=True)
    assert request.real_world_search_enabled is True
    assert request.real_world_weather_enabled is None
