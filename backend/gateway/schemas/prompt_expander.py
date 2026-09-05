"""Prompt Expander の API モデルと入力値の Literal 型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..consts.novelai_models import NovelAIImageModel
from ..consts.novelai_text_models import NovelAITextModel
from ..consts.prompt_expander import (
    DEFAULT_PROMPT_EXPANDER_REFERENCE_FIDELITY,
    DEFAULT_PROMPT_EXPANDER_REFERENCE_STRENGTH,
    DEFAULT_PROMPT_EXPANDER_REFERENCE_TYPE,
    DEFAULT_PROMPT_EXPANDER_TRANSPARENT_EMPHASIS,
    PROMPT_EXPANDER_ANLAS_PER_REFERENCE,
    PROMPT_EXPANDER_CHARACTER_PROMPT_MAX_LEN,
    PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS,
    PROMPT_EXPANDER_IMAGE_SIZES,
    PROMPT_EXPANDER_INSTRUCTION_MAX_LEN,
    PROMPT_EXPANDER_MANGA_LAYOUTS,
    PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO,
    PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX,
    PROMPT_EXPANDER_MANGA_READING_DIRECTIONS,
    PROMPT_EXPANDER_MANGA_TEXT_LANGUAGES,
    PROMPT_EXPANDER_MEMORY_MAX_LEN,
    PROMPT_EXPANDER_NEGATIVE_MAX_LEN,
    PROMPT_EXPANDER_PROMPT_MAX_LEN,
    PROMPT_EXPANDER_REFERENCE_TYPES,
    PROMPT_EXPANDER_SUGGESTION_COUNT_DEFAULT,
    PROMPT_EXPANDER_SUGGESTION_COUNT_MAX,
    PROMPT_EXPANDER_SUGGESTION_COUNT_MIN,
    PROMPT_EXPANDER_TITLE_MAX_LEN,
    PROMPT_EXPANDER_TRANSPARENT_EMPHASIS_LEVELS,
    PROMPT_EXPANDER_UPLOAD_MAX_BASE64_LEN,
)
from ..services.prompt_expander_prompts import MangaOptions
from .novelai import AnlasBalanceResponse

ImageSizeLiteral = Literal["portrait", "landscape", "square"]

ExpandModeLiteral = Literal["japanese", "tags"]

StoredExpandModeLiteral = Literal["off", "japanese", "tags"]

SourceKindLiteral = Literal["none", "history", "entry", "upload"]

MangaLayoutLiteral = Literal["auto", "vertical", "horizontal", "grid"]

MangaTextLanguageLiteral = Literal["auto", "ja", "en"]

MangaReadingDirectionLiteral = Literal["rtl", "ltr"]

ReferenceTypeLiteral = Literal["character", "style", "character&style"]

TransparentEmphasisLiteral = Literal[0, 1, 2, 3]

# Literal と定数の整合性を起動時に検証する（どちらかを直し忘れたときに気付くため）
assert set(NovelAIImageModel.__args__) == set(PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS)  # type: ignore[attr-defined]


assert set(ImageSizeLiteral.__args__) == set(PROMPT_EXPANDER_IMAGE_SIZES)  # type: ignore[attr-defined]

assert set(MangaLayoutLiteral.__args__) == set(PROMPT_EXPANDER_MANGA_LAYOUTS)  # type: ignore[attr-defined]

assert set(MangaTextLanguageLiteral.__args__) == set(
    PROMPT_EXPANDER_MANGA_TEXT_LANGUAGES
)  # type: ignore[attr-defined]

assert set(MangaReadingDirectionLiteral.__args__) == set(
    PROMPT_EXPANDER_MANGA_READING_DIRECTIONS
)  # type: ignore[attr-defined]

assert set(ReferenceTypeLiteral.__args__) == set(PROMPT_EXPANDER_REFERENCE_TYPES)  # type: ignore[attr-defined]

assert set(TransparentEmphasisLiteral.__args__) == set(  # type: ignore[attr-defined]
    PROMPT_EXPANDER_TRANSPARENT_EMPHASIS_LEVELS
)


class MangaOptionsModel(BaseModel):
    """漫画モードの拡張オプション（manga_mode が ON のときだけ意味を持つ）。"""

    panel_count: int = Field(
        PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO,
        ge=PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO,
        le=PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX,
    )
    layout: MangaLayoutLiteral = "auto"
    dialogue: bool = True
    text_language: MangaTextLanguageLiteral = "auto"
    sound_effects: bool = True
    reading_direction: MangaReadingDirectionLiteral = "rtl"
    narration: bool = False

    def to_options(self) -> MangaOptions:
        return MangaOptions(
            panel_count=self.panel_count,
            layout=self.layout,
            dialogue=self.dialogue,
            text_language=self.text_language,
            sound_effects=self.sound_effects,
            reading_direction=self.reading_direction,
            narration=self.narration,
        )


class PromptExpanderSettingsModel(BaseModel):
    text_model: str
    image_model: str
    image_size: str
    i2i_strength: float
    i2i_noise: float
    seed: int | None = None
    restore_seed: bool = False
    memory_text: str = ""
    use_memory: bool = False
    confirm_before_generate: bool = True
    inherit_source_prompts: bool = True
    manga_mode: bool = False
    manga_panel_count: int = PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO
    manga_layout: str = "auto"
    manga_dialogue: bool = True
    manga_text_language: str = "auto"
    manga_sound_effects: bool = True
    manga_reading_direction: str = "rtl"
    manga_narration: bool = False
    use_precise_reference: bool = False
    reference_type: str = DEFAULT_PROMPT_EXPANDER_REFERENCE_TYPE
    reference_strength: float = DEFAULT_PROMPT_EXPANDER_REFERENCE_STRENGTH
    reference_fidelity: float = DEFAULT_PROMPT_EXPANDER_REFERENCE_FIDELITY
    transparent_background: bool = False
    transparent_emphasis: int = DEFAULT_PROMPT_EXPANDER_TRANSPARENT_EMPHASIS
    use_inpaint: bool = False


class TextModelOption(BaseModel):
    id: str
    label: str


class PromptExpanderSettingsResponse(BaseModel):
    settings: PromptExpanderSettingsModel
    text_model_options: list[TextModelOption]
    image_model_options: list[str]
    max_character_prompts: dict[str, int]
    image_sizes: list[str]
    novelai_configured: bool
    manga_panel_count_max: int = PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX
    manga_layouts: list[str] = Field(
        default_factory=lambda: list(PROMPT_EXPANDER_MANGA_LAYOUTS)
    )
    manga_text_languages: list[str] = Field(
        default_factory=lambda: list(PROMPT_EXPANDER_MANGA_TEXT_LANGUAGES)
    )
    manga_reading_directions: list[str] = Field(
        default_factory=lambda: list(PROMPT_EXPANDER_MANGA_READING_DIRECTIONS)
    )
    reference_types: list[str] = Field(
        default_factory=lambda: list(PROMPT_EXPANDER_REFERENCE_TYPES)
    )
    # 精密参照 1 枚あたりの Anlas 消費（FE の料金表示の情報源）
    anlas_per_reference: int = PROMPT_EXPANDER_ANLAS_PER_REFERENCE


class PromptExpanderSettingsUpdateRequest(BaseModel):
    text_model: NovelAITextModel | None = None
    image_model: NovelAIImageModel | None = None
    image_size: ImageSizeLiteral | None = None
    i2i_strength: float | None = Field(None, ge=0.01, le=0.99)
    i2i_noise: float | None = Field(None, ge=0.0, le=0.99)
    # seed は明示的に null を送ると解除（exclude_unset で未指定と区別する）
    seed: int | None = Field(None, ge=0, le=999999999)
    restore_seed: bool | None = None
    memory_text: str | None = Field(None, max_length=PROMPT_EXPANDER_MEMORY_MAX_LEN)
    use_memory: bool | None = None
    confirm_before_generate: bool | None = None
    inherit_source_prompts: bool | None = None
    manga_mode: bool | None = None
    manga_panel_count: int | None = Field(
        None,
        ge=PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO,
        le=PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX,
    )
    manga_layout: MangaLayoutLiteral | None = None
    manga_dialogue: bool | None = None
    manga_text_language: MangaTextLanguageLiteral | None = None
    manga_sound_effects: bool | None = None
    manga_reading_direction: MangaReadingDirectionLiteral | None = None
    manga_narration: bool | None = None
    use_precise_reference: bool | None = None
    reference_type: ReferenceTypeLiteral | None = None
    reference_strength: float | None = Field(None, ge=0.0, le=1.0)
    reference_fidelity: float | None = Field(None, ge=0.0, le=1.0)
    transparent_background: bool | None = None
    transparent_emphasis: TransparentEmphasisLiteral | None = None
    use_inpaint: bool | None = None


class SessionCreateRequest(BaseModel):
    title: str | None = Field(None, max_length=PROMPT_EXPANDER_TITLE_MAX_LEN)


class SessionRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=PROMPT_EXPANDER_TITLE_MAX_LEN)


class PromptExpanderSessionResponse(BaseModel):
    id: str
    title: str
    entry_count: int
    thumbnail_url: str | None = None
    created_at: str
    updated_at: str


class PromptExpanderSessionListResponse(BaseModel):
    sessions: list[PromptExpanderSessionResponse]


class PromptExpanderEntryResponse(BaseModel):
    id: str
    session_id: str
    kind: str
    instruction: str | None = None
    positive_expand_mode: str
    negative_expand_mode: str
    character_mode: bool
    final_prompt: str
    final_negative_prompt: str
    character_prompts: list[str]
    image_model: str | None = None
    text_model: str | None = None
    seed: int | None = None
    i2i_strength: float | None = None
    i2i_noise: float | None = None
    image_size: str | None = None
    manga_mode: bool = False
    manga_panel_count: int | None = None
    source_kind: str
    source_history_id: str | None = None
    source_entry_id: str | None = None
    transparent_background: bool = False
    reference_kind: str = "none"
    reference_history_id: str | None = None
    reference_entry_id: str | None = None
    reference_type: str | None = None
    reference_strength: float | None = None
    reference_fidelity: float | None = None
    inpaint: bool = False
    mask_url: str | None = None
    image_url: str
    nsfw: bool | None = None
    created_at: str


class SessionDetailResponse(BaseModel):
    session: PromptExpanderSessionResponse
    entries: list[PromptExpanderEntryResponse]


class EntryListResponse(BaseModel):
    items: list[PromptExpanderEntryResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class UploadRequest(BaseModel):
    image: str = Field(
        ..., min_length=1, max_length=PROMPT_EXPANDER_UPLOAD_MAX_BASE64_LEN
    )
    instruction: str | None = Field(
        None, max_length=PROMPT_EXPANDER_INSTRUCTION_MAX_LEN
    )


class PromptExpandRequest(BaseModel):
    instruction: str = Field("", max_length=PROMPT_EXPANDER_INSTRUCTION_MAX_LEN)
    expand_positive: bool = True
    positive_mode: ExpandModeLiteral = "tags"
    character_mode: bool = False
    expand_negative: bool = False
    negative_mode: ExpandModeLiteral = "tags"
    negative_instruction: str = Field("", max_length=PROMPT_EXPANDER_NEGATIVE_MAX_LEN)
    image_model: NovelAIImageModel
    text_model: NovelAITextModel
    language: Literal["ja", "en"] = "ja"
    source_kind: SourceKindLiteral = "none"
    source_history_id: str | None = Field(None, max_length=80)
    source_entry_id: str | None = Field(None, max_length=80)
    inherit_source_prompts: bool = True
    # 作業欄に入力済みの内容（参照元より優先して「現在の」内容として渡す）
    current_prompt: str | None = Field(None, max_length=PROMPT_EXPANDER_PROMPT_MAX_LEN)
    current_character_prompts: list[str] = Field(default_factory=list)
    current_negative: str | None = Field(
        None, max_length=PROMPT_EXPANDER_NEGATIVE_MAX_LEN
    )
    # 漫画モード（V5 専用。manga_mode=True のとき manga の内容で拡張する）
    manga_mode: bool = False
    manga: MangaOptionsModel | None = None
    # 背景透過 ON のとき、背景・情景を描写しない規則を system prompt に足す
    transparent_background: bool = False

    @model_validator(mode="after")
    def _check(self) -> PromptExpandRequest:
        if not self.expand_positive and not self.expand_negative:
            raise ValueError("expand_positive か expand_negative のいずれかが必要です")
        if self.expand_positive and not self.instruction.strip():
            raise ValueError("instruction は空にできません")
        if self.expand_negative and not self.negative_instruction.strip():
            raise ValueError("negative_instruction は空にできません")
        if self.source_kind == "history" and not self.source_history_id:
            raise ValueError("source_history_id が必要です")
        if self.source_kind == "entry" and not self.source_entry_id:
            raise ValueError("source_entry_id が必要です")
        return self


class PromptExpandResponse(BaseModel):
    positive_prompt: str | None = None
    character_prompts: list[str] | None = None
    negative_prompt: str | None = None
    text_model: str


class MangaScriptRequest(BaseModel):
    """あらすじ → 記法付きネームの下書き（漫画モード・V5 専用）。"""

    instruction: str = Field(
        ..., min_length=1, max_length=PROMPT_EXPANDER_INSTRUCTION_MAX_LEN
    )
    image_model: NovelAIImageModel
    text_model: NovelAITextModel
    language: Literal["ja", "en"] = "ja"
    manga: MangaOptionsModel | None = None


class MangaScriptResponse(BaseModel):
    script: str
    text_model: str


class PromptExpanderGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=PROMPT_EXPANDER_PROMPT_MAX_LEN)
    negative_prompt: str = Field("", max_length=PROMPT_EXPANDER_NEGATIVE_MAX_LEN)
    character_prompts: list[str] = Field(default_factory=list)
    character_mode: bool = False
    # 拡張 OFF のときは FE が null を送る（最終プロンプトと同文扱い）
    instruction: str | None = Field(
        None, max_length=PROMPT_EXPANDER_INSTRUCTION_MAX_LEN
    )
    positive_expand_mode: StoredExpandModeLiteral = "off"
    negative_expand_mode: StoredExpandModeLiteral = "off"
    image_model: NovelAIImageModel
    text_model: NovelAITextModel | None = None
    image_size: ImageSizeLiteral = "portrait"
    seed: int | None = Field(None, ge=0, le=999999999)
    i2i_strength: float | None = Field(None, ge=0.01, le=0.99)
    i2i_noise: float | None = Field(None, ge=0.0, le=0.99)
    source_kind: SourceKindLiteral = "none"
    source_history_id: str | None = Field(None, max_length=80)
    source_entry_id: str | None = Field(None, max_length=80)
    source_image: str | None = Field(
        None, max_length=PROMPT_EXPANDER_UPLOAD_MAX_BASE64_LEN
    )
    manga_mode: bool = False
    manga_panel_count: int | None = Field(
        None,
        ge=PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO,
        le=PROMPT_EXPANDER_MANGA_PANEL_COUNT_MAX,
    )
    # 精密参照（V4.5 系のみ）。reference_kind != "none" が「参照を送った」唯一の根拠
    reference_kind: SourceKindLiteral = "none"
    reference_history_id: str | None = Field(None, max_length=80)
    reference_entry_id: str | None = Field(None, max_length=80)
    reference_image: str | None = Field(
        None, max_length=PROMPT_EXPANDER_UPLOAD_MAX_BASE64_LEN
    )
    reference_type: ReferenceTypeLiteral = DEFAULT_PROMPT_EXPANDER_REFERENCE_TYPE  # type: ignore[assignment]
    reference_strength: float = Field(
        DEFAULT_PROMPT_EXPANDER_REFERENCE_STRENGTH, ge=0.0, le=1.0
    )
    reference_fidelity: float = Field(
        DEFAULT_PROMPT_EXPANDER_REFERENCE_FIDELITY, ge=0.0, le=1.0
    )
    # 背景透過（V5 はプロンプト指示、V4.5 は白背景生成 + フロント切り抜き）
    transparent_background: bool = False
    transparent_emphasis: TransparentEmphasisLiteral = (
        DEFAULT_PROMPT_EXPANDER_TRANSPARENT_EMPHASIS  # type: ignore[assignment]
    )
    # インペイント（部分修正）。i2i 元をベース画像に使い、マスクの領域だけ描き直す
    inpaint_mask: str | None = Field(
        None, max_length=PROMPT_EXPANDER_UPLOAD_MAX_BASE64_LEN
    )
    inpaint_mask_entry_id: str | None = Field(None, max_length=80)

    @model_validator(mode="after")
    def _check(self) -> PromptExpanderGenerateRequest:
        for item in self.character_prompts:
            if len(item) > PROMPT_EXPANDER_CHARACTER_PROMPT_MAX_LEN:
                raise ValueError("キャラクタープロンプトが長すぎます")
        if self.source_kind == "history" and not self.source_history_id:
            raise ValueError("source_history_id が必要です")
        if self.source_kind == "entry" and not self.source_entry_id:
            raise ValueError("source_entry_id が必要です")
        if self.source_kind == "upload" and not self.source_image:
            raise ValueError("source_image が必要です")
        if self.reference_kind == "history" and not self.reference_history_id:
            raise ValueError("reference_history_id が必要です")
        if self.reference_kind == "entry" and not self.reference_entry_id:
            raise ValueError("reference_entry_id が必要です")
        if self.reference_kind == "upload" and not self.reference_image:
            raise ValueError("reference_image が必要です")
        if self.inpaint_mask and self.inpaint_mask_entry_id:
            raise ValueError("インペイントマスクの指定はどちらか一方だけです")
        if (
            self.inpaint_mask or self.inpaint_mask_entry_id
        ) and self.source_kind == "none":
            raise ValueError("インペイントには元画像（i2i 元）が必要です")
        return self


class PromptExpanderGenerateResponse(BaseModel):
    entry: PromptExpanderEntryResponse
    anlas: AnlasBalanceResponse | None = None


class SuggestCharactersRequest(BaseModel):
    text_model: NovelAITextModel
    image_model: NovelAIImageModel
    mode: ExpandModeLiteral = "tags"
    count: int = Field(
        PROMPT_EXPANDER_SUGGESTION_COUNT_DEFAULT,
        ge=PROMPT_EXPANDER_SUGGESTION_COUNT_MIN,
        le=PROMPT_EXPANDER_SUGGESTION_COUNT_MAX,
    )
    language: Literal["ja", "en"] = "ja"
    # 入力欄の下書き。メモリに加えて提案の方向付けに使う（任意）
    input_text: str | None = Field(None, max_length=PROMPT_EXPANDER_INSTRUCTION_MAX_LEN)


class CharacterSuggestion(BaseModel):
    title: str
    prompt: str


class SuggestCharactersResponse(BaseModel):
    suggestions: list[CharacterSuggestion]
    text_model: str
