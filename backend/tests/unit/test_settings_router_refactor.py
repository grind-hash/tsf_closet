from gateway.routes.settings_router import (
    ChangeSettingsModel,
    InpaintSettingsModel,
    SettingsModel,
    SettingsUpdateRequest,
)
from gateway.routes.settings_router import (
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
