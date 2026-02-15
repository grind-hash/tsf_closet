from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..consts.language import DEFAULT_LANGUAGE, LanguageCode
from ..services.settings_service import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


class UserSettingsModel(BaseModel):
    nsfw_mode: bool = False
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    language: LanguageCode = DEFAULT_LANGUAGE


class UserSettingsResponse(BaseModel):
    nsfw_mode: bool
    difficulty: str
    language: LanguageCode


class UserSettingsUpdateRequest(BaseModel):
    nsfw_mode: bool | None = None
    difficulty: Literal["easy", "normal", "hard"] | None = None
    language: LanguageCode | None = None


class InpaintSettingsModel(BaseModel):
    strength: float = 0.75
    mask_blur: int = 4
    inpaint_full_res: bool = True
    inpaint_full_res_padding: int = 32


class ChangeSettingsModel(BaseModel):
    preserve_face: bool = True
    preserve_hair: bool = True
    seed: int | None = None
    use_random_seed: bool = True


class SettingsModel(BaseModel):
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    nsfw_mode: bool = False
    image_provider: Literal["selfhost", "openrouter", "novelai"] = "selfhost"
    default_instruction_type: Literal["dress_up", "reality_change", "conversation"] = (
        "dress_up"
    )
    inpaint_settings: InpaintSettingsModel = InpaintSettingsModel()
    inpaint_enabled: bool = False
    change_settings: ChangeSettingsModel = ChangeSettingsModel()
    show_achievement_notifications: bool = True
    sound_enabled: bool = True
    sound_volume: float = 0.5
    right_panel_open: bool = False


class SettingsResponse(BaseModel):
    settings: SettingsModel
    saved_at: str | None = None


class SettingsUpdateRequest(BaseModel):
    difficulty: Literal["easy", "normal", "hard"] | None = None
    nsfw_mode: bool | None = None
    image_provider: Literal["selfhost", "openrouter", "novelai"] | None = None
    default_instruction_type: (
        Literal["dress_up", "reality_change", "conversation"] | None
    ) = None
    inpaint_settings: InpaintSettingsModel | None = None
    inpaint_enabled: bool | None = None
    change_settings: ChangeSettingsModel | None = None
    show_achievement_notifications: bool | None = None
    sound_enabled: bool | None = None
    sound_volume: float | None = None
    right_panel_open: bool | None = None


@router.get("", response_model=SettingsResponse)
async def get_settings(session_id: str = "default") -> SettingsResponse:
    settings = settings_service.get_settings_for_session(session_id, SettingsModel)
    return SettingsResponse(settings=settings, saved_at=None)


@router.put("", response_model=SettingsResponse)
async def update_settings(
    request: SettingsUpdateRequest, session_id: str = "default"
) -> SettingsResponse:
    try:
        updated = settings_service.update_settings_for_session(
            session_id=session_id,
            updates=request,
            settings_model_cls=SettingsModel,
            inpaint_model_cls=InpaintSettingsModel,
            change_model_cls=ChangeSettingsModel,
        )
        return SettingsResponse(
            settings=updated, saved_at=settings_service.utc_now_iso()
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("")
async def reset_settings(session_id: str = "default") -> dict[str, str]:
    return settings_service.reset_settings_for_session(session_id)


@router.get("/user", response_model=UserSettingsResponse)
async def get_user_settings() -> UserSettingsResponse:
    settings = await settings_service.get_user_settings()
    return UserSettingsResponse(**settings)


@router.put("/user", response_model=UserSettingsResponse)
async def update_user_settings(
    request: UserSettingsUpdateRequest,
) -> UserSettingsResponse:
    try:
        updated = await settings_service.update_user_settings(
            nsfw_mode=request.nsfw_mode,
            difficulty=request.difficulty,
            language=request.language,
        )
        return UserSettingsResponse(**updated)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
