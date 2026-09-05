from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.settings import (
    ChangeSettingsModel,
    InpaintSettingsModel,
    SelfProfileGenerateRequest,
    SelfProfileSaveRequest,
    SettingsModel,
    SettingsResponse,
    SettingsUpdateRequest,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)
from ..services.settings_service import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


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
            bloom_calc_method=request.bloom_calc_method,
            feeling_mode=request.feeling_mode,
            gender_congruence_llm_enabled=request.gender_congruence_llm_enabled,
            language=request.language,
            novelai_text_model=request.novelai_text_model,
            novelai_image_model=request.novelai_image_model,
            novelai_curated_image_model=request.novelai_curated_image_model,
            tts_enabled=request.tts_enabled,
            tts_use_gpu=request.tts_use_gpu,
            tts_engine_dir=request.tts_engine_dir,
            tts_engine_port=request.tts_engine_port,
            tts_model_dir=request.tts_model_dir,
            tts_speaker_id=request.tts_speaker_id,
            tts_style_id=request.tts_style_id,
            tts_output_format=request.tts_output_format,
        )
        return UserSettingsResponse(**updated)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Self-profile endpoints (US6 T032) ──


@router.post("/self-profile/generate")
async def generate_self_profile(request: SelfProfileGenerateRequest) -> dict:
    """Generate a SelfProfile from free-form text via LLM."""
    if not request.input_text or not request.input_text.strip():
        raise HTTPException(status_code=400, detail="input_text is required")
    try:
        profile = await settings_service.generate_self_profile(request.input_text)
        return profile
    except (ValueError, Exception) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/self-profile")
async def save_self_profile(request: SelfProfileSaveRequest) -> dict:
    """Save the user's self-profile."""
    profile = request.model_dump()
    saved = await settings_service.save_self_profile(profile)
    return saved


@router.get("/self-profile")
async def get_self_profile() -> dict:
    """Retrieve the user's self-profile, or empty dict if not set."""
    profile = await settings_service.get_self_profile()
    return profile or {}
