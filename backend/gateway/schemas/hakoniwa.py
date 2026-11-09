"""AI箱庭モードの API モデル。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..consts.hakoniwa import (
    HAKONIWA_APPEARANCE_TEXT_MAX,
    HAKONIWA_CUSTOM_RULE_NAME_MAX,
    HAKONIWA_CUSTOM_RULE_TEXT_MAX,
    HAKONIWA_MAX_RESIDENTS,
    HAKONIWA_PERSONALITY_MAX,
    HAKONIWA_RESIDENT_NAME_MAX,
    HAKONIWA_TRANSFORM_TEXT_MAX,
    HAKONIWA_WORLD_NAME_MAX,
)

Gender = Literal["female", "male"]


class HakoniwaLanguageRequest(BaseModel):
    language: str | None = Field(
        None, description="表示・生成の言語。未指定はユーザー設定"
    )


class HakoniwaCharacterEntry(BaseModel):
    character_preset_id: str = Field(
        ..., description="キャラクター画面で作ったキャラの id"
    )
    gender: Gender | None = Field(
        None, description="キャラクターの性別が未設定のときに使う性別"
    )


class HakoniwaCreateRequest(HakoniwaLanguageRequest):
    name: str = Field(..., max_length=HAKONIWA_WORLD_NAME_MAX, description="世界の名前")
    preset_ids: list[str] = Field(
        default_factory=list,
        max_length=HAKONIWA_MAX_RESIDENTS,
        description="住民にするプリセットの id",
    )
    characters: list[HakoniwaCharacterEntry] = Field(
        default_factory=list,
        max_length=HAKONIWA_MAX_RESIDENTS,
        description="住民にする登録キャラクター",
    )


class HakoniwaSettingsRequest(HakoniwaLanguageRequest):
    image_model: str = Field(
        ..., description="アバター生成の画像モデル。default はユーザー設定に従う"
    )


class HakoniwaRuleToggleRequest(HakoniwaLanguageRequest):
    active: bool


class HakoniwaCustomRuleRequest(HakoniwaLanguageRequest):
    name: str = Field(..., max_length=HAKONIWA_CUSTOM_RULE_NAME_MAX)
    text: str = Field(..., max_length=HAKONIWA_CUSTOM_RULE_TEXT_MAX)


class HakoniwaResidentRequest(HakoniwaLanguageRequest):
    name: str = Field(..., max_length=HAKONIWA_RESIDENT_NAME_MAX)
    personality: str = Field(..., max_length=HAKONIWA_PERSONALITY_MAX)
    gender: Gender
    appearance_text: str = Field(
        "",
        max_length=HAKONIWA_APPEARANCE_TEXT_MAX,
        description="外見の説明(日本語の文章か英語のタグ)。画像タグは別に作る",
    )
    dress_text: str = Field(
        "",
        max_length=HAKONIWA_APPEARANCE_TEXT_MAX,
        description="ドレスの掟で着るドレス姿の説明(任意)",
    )


class HakoniwaCharacterResidentRequest(HakoniwaLanguageRequest):
    character_preset_id: str
    gender: Gender | None = None


class HakoniwaTransformRequest(HakoniwaLanguageRequest):
    instruction: str = Field(..., min_length=1, max_length=HAKONIWA_TRANSFORM_TEXT_MAX)


class HakoniwaReapplyRequest(HakoniwaLanguageRequest):
    image: str = Field(..., description="履歴の変身の画像ファイル名")


class HakoniwaAvatarRequest(HakoniwaLanguageRequest):
    variant: Literal["base", "dress"] = "base"


class HakoniwaFavoriteRequest(HakoniwaLanguageRequest):
    favorite: bool


class HakoniwaLine(BaseModel):
    speaker: str = Field(..., description="話す住民の id")
    text: str


class HakoniwaEvent(BaseModel):
    id: str
    day: int
    title: str
    narration: str
    lines: list[HakoniwaLine]
    participants: list[str]
    mood_delta: dict[str, int]
    affinity_delta: int
    source: str = Field(..., description="llm / template / player")
    kind: str | None = Field(None, description="transform(変身の出来事)など")
    change_text: str | None = None
    favorite: bool = False


class HakoniwaTransformation(BaseModel):
    description: str
    tags: str
    image: str
    image_url: str | None
    day: int


class HakoniwaResident(BaseModel):
    id: str
    source: str = Field(..., description="preset / character / custom")
    preset_id: str | None
    character_preset_id: str | None
    name: str
    gender: Gender
    body_gender: Gender = Field(..., description="いま見えている体の性別")
    age: str
    job: str
    personality: str
    pronoun: str
    appearance_text: str
    base_tags: str = Field(..., description="通常の姿の画像タグ(外見の説明から作る)")
    dress_text: str
    dress_tags: str
    mood: int
    affinities: dict[str, int]
    transformation: HakoniwaTransformation | None
    transformation_history: list[HakoniwaTransformation]
    swapped_with: str | None
    display_avatar_url: str | None = Field(..., description="いま表示する姿")
    display_kind: str = Field(..., description="transform / dress / base")
    display_owner_id: str = Field(
        ..., description="表示する姿の持ち主(入れ替わり中は相手)"
    )
    own_avatar_url: str | None
    avatar_url: str | None
    dress_avatar_url: str | None


class HakoniwaRuleCard(BaseModel):
    id: str
    name: str
    description: str
    custom: bool
    active: bool


class HakoniwaWorldResponse(BaseModel):
    id: str
    name: str
    day: int
    created_at: str | None
    updated_at: str | None
    background_url: str
    image_model: str
    image_model_effective: str
    image_model_default: str = Field(..., description="ユーザー設定の画像モデル")
    image_model_options: list[str]
    transparency: str = Field(
        ..., description="native(V5 の透過生成)/ removal(白背景を表示側で抜く)"
    )
    active_rules: list[str]
    swap_pair: list[str] | None
    rule_cards: list[HakoniwaRuleCard]
    residents: list[HakoniwaResident]
    events: list[HakoniwaEvent]


class HakoniwaResidentPreview(BaseModel):
    id: str
    name: str
    avatar_url: str | None


class HakoniwaWorldSummary(BaseModel):
    id: str
    name: str
    day: int
    resident_count: int
    event_count: int
    created_at: str | None
    updated_at: str | None
    residents: list[HakoniwaResidentPreview]


class HakoniwaWorldListResponse(BaseModel):
    worlds: list[HakoniwaWorldSummary]


class HakoniwaPreset(BaseModel):
    id: str
    gender: Gender
    name: str
    age: str
    job: str
    personality: str
    avatar_url: str
    dress_avatar_url: str


class HakoniwaCatalogRuleCard(BaseModel):
    id: str
    name: str
    description: str


class HakoniwaCatalogResponse(BaseModel):
    presets: list[HakoniwaPreset]
    rule_cards: list[HakoniwaCatalogRuleCard]
    background_url: str
    image_model_options: list[str]


class HakoniwaDayResponse(BaseModel):
    world: HakoniwaWorldResponse
    new_events: list[HakoniwaEvent]
    cost_usd: float | None = None


class HakoniwaResidentChangeResponse(BaseModel):
    world: HakoniwaWorldResponse
    resident_id: str
    tag_expansion_failed: bool = Field(
        False, description="外見の説明を画像タグにできず、元のタグのままにした"
    )
    cost_usd: float | None = None


class HakoniwaGreetingResponse(BaseModel):
    resident_id: str
    text: str
    source: str = Field(..., description="llm / template")
    cost_usd: float | None = None


class HakoniwaImageResponse(BaseModel):
    world: HakoniwaWorldResponse
    cost_usd: float | None = None
