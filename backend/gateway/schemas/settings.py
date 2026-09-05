"""設定（アプリ設定・互換ユーザー設定・自分自身モードのプロフィール）の API モデル。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..consts.history_lookback import (
    HISTORY_LOOKBACK_DEFAULT,
    HISTORY_LOOKBACK_MAX,
    HISTORY_LOOKBACK_MIN,
)
from ..consts.language import DEFAULT_LANGUAGE, LanguageCode
from ..consts.novelai_models import DEFAULT_NSFW_IMAGE_MODEL, DEFAULT_SFW_IMAGE_MODEL


class UserSettingsModel(BaseModel):
    nsfw_mode: bool = False
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    language: LanguageCode = DEFAULT_LANGUAGE


class UserSettingsResponse(BaseModel):
    nsfw_mode: bool
    difficulty: str
    bloom_calc_method: str = "legacy"
    feeling_mode: str = "legacy"
    gender_congruence_llm_enabled: bool = False
    language: LanguageCode
    novelai_text_model: str = "glm-4-6"
    novelai_image_model: str = DEFAULT_NSFW_IMAGE_MODEL
    novelai_curated_image_model: str = DEFAULT_SFW_IMAGE_MODEL
    tts_enabled: bool = False
    tts_use_gpu: bool = False
    tts_engine_dir: str | None = None
    tts_engine_port: int | None = None
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
    novelai_image_model: (
        Literal["nai-diffusion-4-5-full", "nai-diffusion-5-full"] | None
    ) = None
    novelai_curated_image_model: (
        Literal["nai-diffusion-4-5-curated", "nai-diffusion-5-curated"] | None
    ) = None
    tts_enabled: bool | None = None
    tts_use_gpu: bool | None = None
    tts_engine_dir: str | None = None
    # 音声合成エンジンの待ち受けポート。未指定なら AIVIS_ENGINE_BASE_URL のポートを使う。
    tts_engine_port: int | None = Field(default=None, ge=1, le=65535)
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
    sound_volume: float = 0.25
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
