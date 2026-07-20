from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..consts.history_lookback import (
    HISTORY_LOOKBACK_DEFAULT,
    HISTORY_LOOKBACK_MAX,
    HISTORY_LOOKBACK_MIN,
)
from ..consts.language import DEFAULT_LANGUAGE, LanguageCode
from ..services.settings_service import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


class UserSettingsModel(BaseModel):
    nsfw_mode: bool = False
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    language: LanguageCode = DEFAULT_LANGUAGE


# NovelAI Text API で選択可能なモデル
NOVELAI_TEXT_MODEL_OPTIONS = ("glm-4-6", "xialong-v1")


class UserSettingsResponse(BaseModel):
    nsfw_mode: bool
    difficulty: str
    bloom_calc_method: str = "legacy"
    feeling_mode: str = "legacy"
    gender_congruence_llm_enabled: bool = False
    language: LanguageCode
    novelai_text_model: str = "glm-4-6"
    tts_enabled: bool = False
    tts_use_gpu: bool = False
    tts_engine_dir: str | None = None
    tts_model_dir: str | None = None
    tts_speaker_id: str | None = None
    tts_style_id: str | None = None
    tts_output_format: Literal["wav"] = "wav"


class UserSettingsUpdateRequest(BaseModel):
    nsfw_mode: bool | None = None
    difficulty: Literal["easy", "normal", "hard"] | None = None
    bloom_calc_method: Literal["legacy", "new"] | None = None
    # new/experimental は誤保存互換。正規化後は legacy | gender_aware
    feeling_mode: Literal["legacy", "gender_aware", "new", "experimental"] | None = None
    gender_congruence_llm_enabled: bool | None = None
    language: LanguageCode | None = None
    novelai_text_model: Literal["glm-4-6", "xialong-v1"] | None = None
    tts_enabled: bool | None = None
    tts_use_gpu: bool | None = None
    tts_engine_dir: str | None = None
    tts_model_dir: str | None = None
    tts_speaker_id: str | None = None
    tts_style_id: str | None = None
    tts_output_format: Literal["wav"] | None = None


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
    enable_surroundings_image: bool = False
    surroundings_include_people: bool = False
    history_lookback_count: int = Field(
        default=HISTORY_LOOKBACK_DEFAULT,
        ge=HISTORY_LOOKBACK_MIN,
        le=HISTORY_LOOKBACK_MAX,
    )


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
    enable_surroundings_image: bool | None = None
    surroundings_include_people: bool | None = None
    history_lookback_count: int | None = Field(
        default=None, ge=HISTORY_LOOKBACK_MIN, le=HISTORY_LOOKBACK_MAX
    )


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
            tts_enabled=request.tts_enabled,
            tts_use_gpu=request.tts_use_gpu,
            tts_engine_dir=request.tts_engine_dir,
            tts_model_dir=request.tts_model_dir,
            tts_speaker_id=request.tts_speaker_id,
            tts_style_id=request.tts_style_id,
            tts_output_format=request.tts_output_format,
        )
        return UserSettingsResponse(**updated)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Self-profile endpoints (US6 T032) ──


class SelfProfileGenerateRequest(BaseModel):
    input_text: str


class SelfProfileSaveRequest(BaseModel):
    display_name: str = ""
    personality: str = ""
    reaction_style: str = "default"
    pronoun: str = "僕"
    gender: str = "man"
    interests: list[str] = []
    tsf_attitude: str = ""
    raw_input: str = ""


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
