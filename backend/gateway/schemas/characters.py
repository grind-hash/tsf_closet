"""キャラクター一覧、セッション人物、人物プリセット、人物タグ生成の API モデル。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CharacterInfo(BaseModel):
    """キャラクター情報 (API用)"""

    id: str = Field(..., description="キャラクターID")
    name: str = Field(..., description="キャラクター名")
    thumbnail: str = Field(..., description="Base64エンコードされたサムネイル画像")
    description: str = Field(..., description="キャラクター説明")


class CharacterListResponse(BaseModel):
    """キャラクター一覧レスポンス"""

    characters: list[CharacterInfo] = Field(..., description="キャラクター一覧")


CharacterPositionLiteral = Literal[
    "left", "center-left", "center", "center-right", "right"
]


class SessionCharacterRead(BaseModel):
    """Read model for SessionCharacter."""

    id: str
    session_id: str
    slot_index: int
    name: str
    appearance_natural: str
    appearance_tags: str
    position: CharacterPositionLiteral
    is_protagonist: bool = False
    appearance_lock: bool = False
    exclude_from_effects: bool = False
    source_preset_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SessionCharacterCreate(BaseModel):
    """Create payload for adding a character to a session."""

    name: str = Field(..., min_length=1, max_length=120)
    appearance_natural: str = Field("", max_length=1000)
    appearance_tags: str = Field("", max_length=2000)
    position: CharacterPositionLiteral = "center"
    slot_index: int | None = Field(None, ge=0, le=3)
    source_preset_id: str | None = None
    appearance_lock: bool = False
    exclude_from_effects: bool = False


class SessionCharacterUpdate(BaseModel):
    """Partial update payload for an existing SessionCharacter."""

    name: str | None = Field(None, min_length=1, max_length=120)
    appearance_natural: str | None = Field(None, max_length=1000)
    appearance_tags: str | None = Field(None, max_length=2000)
    position: CharacterPositionLiteral | None = None
    slot_index: int | None = Field(None, ge=0, le=3)
    appearance_lock: bool | None = None
    exclude_from_effects: bool | None = None


class CharacterPresetRead(BaseModel):
    """Read model for CharacterPreset."""

    id: str
    name: str
    appearance_natural: str
    appearance_tags: str
    default_position: CharacterPositionLiteral
    created_at: datetime
    updated_at: datetime


class PresetCreateFromCharacter(BaseModel):
    """Create a preset by copying an existing SessionCharacter."""

    from_character_id: str
    name: str = Field(..., min_length=1, max_length=120)


class PresetCreateRaw(BaseModel):
    """Create a preset directly from raw fields."""

    name: str = Field(..., min_length=1, max_length=120)
    appearance_natural: str = Field("", max_length=1000)
    appearance_tags: str = Field("", max_length=2000)
    default_position: CharacterPositionLiteral = "center"


class CharacterPresetUpdate(BaseModel):
    """Partial update payload for a preset."""

    name: str | None = Field(None, min_length=1, max_length=120)
    appearance_natural: str | None = Field(None, max_length=1000)
    appearance_tags: str | None = Field(None, max_length=2000)
    default_position: CharacterPositionLiteral | None = None


class GenerateTagsItem(BaseModel):
    """One natural-language input for batch tag generation."""

    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=120)
    natural: str = Field(..., max_length=1000)


class GenerateTagsRequest(BaseModel):
    """Batch tag-generation request body."""

    items: list[GenerateTagsItem] = Field(..., min_length=1, max_length=4)


class GenerateTagsResultItem(BaseModel):
    """One result entry for batch tag generation."""

    id: str
    tags: str


class GenerateTagsResponse(BaseModel):
    """Batch tag-generation response body."""

    results: list[GenerateTagsResultItem]


class SessionCharacterListResponse(BaseModel):
    """Wrapper for GET /game/session/{id}/characters."""

    characters: list[SessionCharacterRead]


class CharacterPresetListResponse(BaseModel):
    """Wrapper for GET /game/character-presets."""

    presets: list[CharacterPresetRead]


class GenerateBaseTagsRequest(BaseModel):
    """外見タグ自動生成リクエスト"""

    name: str = Field("", description="キャラクター名")
    description: str = Field("", description="外見の説明")
    gender: str = Field("other", description="性別 (man/woman/other)")
    personality: str = Field("", description="パーソナリティ")
