"""キャラクター一覧、セッション人物、人物プリセット、人物タグ生成の API モデル。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..consts.character_limits import (
    MAX_REGISTERED_CHARACTERS,
    NEGATIVE_TAGS_MAX_LEN,
)
from ..consts.character_profile import (
    PROFILE_INTEREST_MAX_LEN,
    PROFILE_INTERESTS_MAX_COUNT,
    PROFILE_MEMO_MAX_LEN,
    PROFILE_PERSONALITY_MAX_LEN,
    PROFILE_PRONOUN_MAX_LEN,
    PROFILE_TSF_ATTITUDE_MAX_LEN,
)

# slot_index の上限（主人公が 0、他の人物が 1 以降）
_MAX_SLOT_INDEX = MAX_REGISTERED_CHARACTERS - 1
# サムネイルは API 相対パスのみ受け付ける（外部 URL を保存させない）
_THUMBNAIL_URL_PATTERN = r"^/[^/]"
_THUMBNAIL_URL_MAX_LEN = 300


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

ReactionStyleLiteral = Literal[
    "default", "bold", "gentle", "cheerful", "shy", "calm", "passionate"
]
ProfileGenderLiteral = Literal["man", "woman", ""]


class CharacterProfile(BaseModel):
    """登場人物の性格プロフィール（自分自身モードの SelfProfile と同じ項目）。"""

    personality: str = Field("", max_length=PROFILE_PERSONALITY_MAX_LEN)
    reaction_style: ReactionStyleLiteral = "default"
    pronoun: str = Field("", max_length=PROFILE_PRONOUN_MAX_LEN)
    gender: ProfileGenderLiteral = ""
    interests: list[str] = Field(
        default_factory=list, max_length=PROFILE_INTERESTS_MAX_COUNT
    )
    tsf_attitude: str = Field("", max_length=PROFILE_TSF_ATTITUDE_MAX_LEN)
    memo: str = Field("", max_length=PROFILE_MEMO_MAX_LEN)

    @model_validator(mode="after")
    def _clip_interests(self) -> CharacterProfile:
        self.interests = [
            item.strip()[:PROFILE_INTEREST_MAX_LEN]
            for item in self.interests
            if item and item.strip()
        ]
        return self


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
    negative_tags: str = ""
    profile: CharacterProfile | None = None
    on_stage: bool = True
    thumbnail_url: str | None = None
    # 今の姿の出どころ: 設定 / 直前の手番の結果（履歴） / 姿を固定
    look_source: Literal["spec", "history", "fixed"] = "spec"
    # 直前の手番で描いた姿（履歴に残したタグ）。まだ無ければ None
    current_tags: str | None = None
    created_at: datetime
    updated_at: datetime


class SessionCharacterCreate(BaseModel):
    """Create payload for adding a character to a session."""

    name: str = Field(..., min_length=1, max_length=120)
    appearance_natural: str = Field("", max_length=1000)
    appearance_tags: str = Field("", max_length=2000)
    position: CharacterPositionLiteral = "center"
    slot_index: int | None = Field(None, ge=0, le=_MAX_SLOT_INDEX)
    source_preset_id: str | None = None
    appearance_lock: bool = False
    exclude_from_effects: bool = False
    negative_tags: str = Field("", max_length=NEGATIVE_TAGS_MAX_LEN)
    profile: CharacterProfile | None = None
    on_stage: bool = True
    thumbnail_url: str | None = Field(
        None, max_length=_THUMBNAIL_URL_MAX_LEN, pattern=_THUMBNAIL_URL_PATTERN
    )


class SessionCharacterUpdate(BaseModel):
    """Partial update payload for an existing SessionCharacter."""

    name: str | None = Field(None, min_length=1, max_length=120)
    appearance_natural: str | None = Field(None, max_length=1000)
    appearance_tags: str | None = Field(None, max_length=2000)
    position: CharacterPositionLiteral | None = None
    slot_index: int | None = Field(None, ge=0, le=_MAX_SLOT_INDEX)
    appearance_lock: bool | None = None
    exclude_from_effects: bool | None = None
    negative_tags: str | None = Field(None, max_length=NEGATIVE_TAGS_MAX_LEN)
    profile: CharacterProfile | None = None
    on_stage: bool | None = None
    thumbnail_url: str | None = Field(
        None, max_length=_THUMBNAIL_URL_MAX_LEN, pattern=_THUMBNAIL_URL_PATTERN
    )
    # true: 次の手番は直前の姿を引き継がず、設定の姿で描く
    reset_look: bool | None = None


class CharacterPresetRead(BaseModel):
    """Read model for CharacterPreset."""

    id: str
    name: str
    appearance_natural: str
    appearance_tags: str
    default_position: CharacterPositionLiteral
    negative_tags: str = ""
    profile: CharacterProfile | None = None
    thumbnail_url: str | None = None
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
    negative_tags: str = Field("", max_length=NEGATIVE_TAGS_MAX_LEN)
    profile: CharacterProfile | None = None
    thumbnail_url: str | None = Field(
        None, max_length=_THUMBNAIL_URL_MAX_LEN, pattern=_THUMBNAIL_URL_PATTERN
    )


class CharacterPresetUpdate(BaseModel):
    """Partial update payload for a preset."""

    name: str | None = Field(None, min_length=1, max_length=120)
    appearance_natural: str | None = Field(None, max_length=1000)
    appearance_tags: str | None = Field(None, max_length=2000)
    default_position: CharacterPositionLiteral | None = None
    negative_tags: str | None = Field(None, max_length=NEGATIVE_TAGS_MAX_LEN)
    profile: CharacterProfile | None = None
    thumbnail_url: str | None = Field(
        None, max_length=_THUMBNAIL_URL_MAX_LEN, pattern=_THUMBNAIL_URL_PATTERN
    )


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


class CharacterGroupMember(BaseModel):
    """組み合わせプリセットに保存される 1 人分のスナップショット。"""

    name: str = Field(..., min_length=1, max_length=120)
    appearance_natural: str = ""
    appearance_tags: str = ""
    negative_tags: str = ""
    position: CharacterPositionLiteral = "center"
    appearance_lock: bool = False
    exclude_from_effects: bool = False
    on_stage: bool = True
    profile: CharacterProfile | None = None
    thumbnail_url: str | None = None


class CharacterGroupPresetRead(BaseModel):
    """Read model for CharacterGroupPreset."""

    id: str
    name: str
    members: list[CharacterGroupMember]
    created_at: datetime
    updated_at: datetime


class CharacterGroupPresetCreate(BaseModel):
    """今のセッションの登場人物（主人公以外）を組み合わせとして保存する。"""

    name: str = Field(..., min_length=1, max_length=120)
    from_session_id: str = Field(..., min_length=1)


class CharacterGroupPresetUpdate(BaseModel):
    """名前の変更、またはセッションの登場人物での上書き。"""

    name: str | None = Field(None, min_length=1, max_length=120)
    from_session_id: str | None = Field(None, min_length=1)


class CharacterGroupPresetListResponse(BaseModel):
    """Wrapper for GET /game/character-group-presets."""

    groups: list[CharacterGroupPresetRead]


class CharacterProfileGenerateRequest(BaseModel):
    """登場人物の性格プロフィール自動生成リクエスト。"""

    name: str = Field("", max_length=120)
    appearance_natural: str = Field("", max_length=1000)
    appearance_tags: str = Field("", max_length=2000)
    memo: str = Field("", max_length=PROFILE_MEMO_MAX_LEN)


class CharacterSourceResolveRequest(BaseModel):
    """セッション・お気に入り・Prompt Expander の選択から外見を取り出す。"""

    session_id: str | None = None
    history_id: str | None = None
    prompt_expander_entry_id: str | None = None

    @model_validator(mode="after")
    def _require_source(self) -> CharacterSourceResolveRequest:
        if not self.session_id and not self.prompt_expander_entry_id:
            raise ValueError("session_id or prompt_expander_entry_id is required")
        return self


class CharacterSourceResolveResponse(BaseModel):
    """選択したソースから取り出した名前と外見。"""

    name: str | None = None
    appearance_natural: str = ""
    appearance_tags: str = ""


class GenerateBaseTagsRequest(BaseModel):
    """外見タグ自動生成リクエスト"""

    name: str = Field("", description="キャラクター名")
    description: str = Field("", description="外見の説明")
    gender: str = Field("other", description="性別 (man/woman/other)")
    personality: str = Field("", description="パーソナリティ")
