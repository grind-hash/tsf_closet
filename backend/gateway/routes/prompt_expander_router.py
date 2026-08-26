"""Prompt Expander API。

自然言語からの NovelAI プロンプト拡張と画像生成、専用履歴（セッション/エントリ）、
専用設定を提供する。通常ゲームの Session/History には影響を与えない。
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from ..consts.novelai_text_models import NOVELAI_TEXT_MODEL_OPTIONS
from ..consts.prompt_expander import (
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
    PROMPT_EXPANDER_SUGGESTION_COUNT_DEFAULT,
    PROMPT_EXPANDER_SUGGESTION_COUNT_MAX,
    PROMPT_EXPANDER_SUGGESTION_COUNT_MIN,
    PROMPT_EXPANDER_TITLE_MAX_LEN,
    PROMPT_EXPANDER_UPLOAD_MAX_BASE64_LEN,
    max_character_prompts_map,
)
from ..databases.base import async_session_factory
from ..services import prompt_expander_service as pe_service
from ..services.prompt_expander_prompts import MangaOptions
from ..services.prompt_expander_service import (
    ExpandParams,
    GenerateParams,
    PromptExpanderError,
    PromptExpanderService,
    PromptExpanderSettings,
    entry_to_dict,
    novelai_configured,
    remove_entry_image,
    remove_session_images,
    resolve_entry_image_file,
    text_model_options,
)
from ..services.session import DEFAULT_USER_ID

router = APIRouter(prefix="/prompt-expander", tags=["prompt-expander"])

ImageModelLiteral = Literal[
    "nai-diffusion-5-full",
    "nai-diffusion-5-curated",
    "nai-diffusion-4-5-full",
    "nai-diffusion-4-5-curated",
]
TextModelLiteral = Literal["glm-4-6", "xialong-v1"]
ImageSizeLiteral = Literal["portrait", "landscape", "square"]
ExpandModeLiteral = Literal["japanese", "tags"]
StoredExpandModeLiteral = Literal["off", "japanese", "tags"]
SourceKindLiteral = Literal["none", "history", "entry", "upload"]
MangaLayoutLiteral = Literal["auto", "vertical", "horizontal", "grid"]
MangaTextLanguageLiteral = Literal["auto", "ja", "en"]
MangaReadingDirectionLiteral = Literal["rtl", "ltr"]

# Literal と定数の整合性を起動時に検証する（どちらかを直し忘れたときに気付くため）
assert set(ImageModelLiteral.__args__) == set(PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS)  # type: ignore[attr-defined]
assert set(TextModelLiteral.__args__) == set(NOVELAI_TEXT_MODEL_OPTIONS)  # type: ignore[attr-defined]
assert set(ImageSizeLiteral.__args__) == set(PROMPT_EXPANDER_IMAGE_SIZES)  # type: ignore[attr-defined]
assert set(MangaLayoutLiteral.__args__) == set(PROMPT_EXPANDER_MANGA_LAYOUTS)  # type: ignore[attr-defined]
assert set(MangaTextLanguageLiteral.__args__) == set(
    PROMPT_EXPANDER_MANGA_TEXT_LANGUAGES
)  # type: ignore[attr-defined]
assert set(MangaReadingDirectionLiteral.__args__) == set(
    PROMPT_EXPANDER_MANGA_READING_DIRECTIONS
)  # type: ignore[attr-defined]


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


# ---------------------------------------------------------------------------
# Pydantic モデル
# ---------------------------------------------------------------------------


class PromptExpanderSettingsModel(BaseModel):
    text_model: str
    image_model: str
    image_size: str
    i2i_strength: float
    i2i_noise: float
    seed: Optional[int] = None
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


class PromptExpanderSettingsUpdateRequest(BaseModel):
    text_model: TextModelLiteral | None = None
    image_model: ImageModelLiteral | None = None
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


class SessionListResponse(BaseModel):
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
    image_model: ImageModelLiteral
    text_model: TextModelLiteral
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

    @model_validator(mode="after")
    def _check(self) -> "PromptExpandRequest":
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
    image_model: ImageModelLiteral
    text_model: TextModelLiteral | None = None
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

    @model_validator(mode="after")
    def _check(self) -> "PromptExpanderGenerateRequest":
        for item in self.character_prompts:
            if len(item) > PROMPT_EXPANDER_CHARACTER_PROMPT_MAX_LEN:
                raise ValueError("キャラクタープロンプトが長すぎます")
        if self.source_kind == "history" and not self.source_history_id:
            raise ValueError("source_history_id が必要です")
        if self.source_kind == "entry" and not self.source_entry_id:
            raise ValueError("source_entry_id が必要です")
        if self.source_kind == "upload" and not self.source_image:
            raise ValueError("source_image が必要です")
        return self


class AnlasUsageModel(BaseModel):
    percent: int
    is_negative: bool = False
    time_until_next_percent: int = 0


class AnlasBalanceModel(BaseModel):
    fixed_anlas: int | None = None
    purchased_anlas: int | None = None
    total_anlas: int | None = None
    usage: AnlasUsageModel | None = None


class PromptExpanderGenerateResponse(BaseModel):
    entry: PromptExpanderEntryResponse
    anlas: AnlasBalanceModel | None = None


class SuggestCharactersRequest(BaseModel):
    text_model: TextModelLiteral
    image_model: ImageModelLiteral
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


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------


def _http_error(exc: PromptExpanderError) -> HTTPException:
    code_map = {
        "session_not_found": status.HTTP_404_NOT_FOUND,
        "entry_not_found": status.HTTP_404_NOT_FOUND,
        "history_not_found": status.HTTP_404_NOT_FOUND,
        "image_not_found": status.HTTP_404_NOT_FOUND,
        "invalid_source": status.HTTP_400_BAD_REQUEST,
        "invalid_image": status.HTTP_400_BAD_REQUEST,
        "invalid_request": status.HTTP_400_BAD_REQUEST,
        "invalid_title": status.HTTP_400_BAD_REQUEST,
        "invalid_settings": status.HTTP_400_BAD_REQUEST,
        "invalid_text_model": status.HTTP_400_BAD_REQUEST,
        "memory_empty": status.HTTP_400_BAD_REQUEST,
        "novelai_not_configured": status.HTTP_400_BAD_REQUEST,
        "too_many_characters": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "unsupported_image_model": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "manga_requires_v5": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "invalid_llm_output": status.HTTP_502_BAD_GATEWAY,
        "llm_failed": status.HTTP_502_BAD_GATEWAY,
        "image_failed": status.HTTP_502_BAD_GATEWAY,
    }
    return HTTPException(
        status_code=code_map.get(exc.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": exc.code, "message": exc.message},
    )


def _settings_response(
    pe_settings: PromptExpanderSettings,
) -> PromptExpanderSettingsResponse:
    return PromptExpanderSettingsResponse(
        settings=PromptExpanderSettingsModel(**pe_settings.model_dump()),
        text_model_options=[TextModelOption(**item) for item in text_model_options()],
        image_model_options=list(PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS),
        max_character_prompts=max_character_prompts_map(),
        image_sizes=list(PROMPT_EXPANDER_IMAGE_SIZES),
        novelai_configured=novelai_configured(),
    )


def _session_response(view: pe_service.SessionView) -> PromptExpanderSessionResponse:
    return PromptExpanderSessionResponse(**view.to_dict())


def _entry_response(data: dict[str, Any]) -> PromptExpanderEntryResponse:
    return PromptExpanderEntryResponse(**data)


async def _session_view(db, session_id: str) -> PromptExpanderSessionResponse:
    views = await PromptExpanderService.list_sessions(db, user_id=DEFAULT_USER_ID)
    for view in views:
        if view.id == session_id:
            return _session_response(view)
    raise PromptExpanderError(
        "session_not_found", "Prompt Expander セッションが見つかりません"
    )


# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------


@router.get("/settings", response_model=PromptExpanderSettingsResponse)
async def get_settings():
    async with async_session_factory() as db:
        pe_settings = await PromptExpanderService.get_settings(
            db, user_id=DEFAULT_USER_ID
        )
    return _settings_response(pe_settings)


@router.put("/settings", response_model=PromptExpanderSettingsResponse)
async def update_settings(body: PromptExpanderSettingsUpdateRequest):
    # 未指定の項目は据え置き。seed だけは null を送ると解除になる
    patch = body.model_dump(exclude_unset=True)
    try:
        async with async_session_factory() as db:
            pe_settings = await PromptExpanderService.save_settings(
                db, patch=patch, user_id=DEFAULT_USER_ID
            )
            await db.commit()
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    return _settings_response(pe_settings)


# ---------------------------------------------------------------------------
# セッション
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions():
    async with async_session_factory() as db:
        views = await PromptExpanderService.list_sessions(db, user_id=DEFAULT_USER_ID)
    return SessionListResponse(sessions=[_session_response(v) for v in views])


@router.post(
    "/sessions",
    response_model=PromptExpanderSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(body: SessionCreateRequest):
    try:
        async with async_session_factory() as db:
            session = await PromptExpanderService.create_session(
                db, title=body.title, user_id=DEFAULT_USER_ID
            )
            await db.commit()
            view = await _session_view(db, session.id)
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    return view


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: str):
    try:
        async with async_session_factory() as db:
            entries = await PromptExpanderService.list_session_entries(
                db, session_id=session_id, user_id=DEFAULT_USER_ID
            )
            view = await _session_view(db, session_id)
            entry_views = [_entry_response(entry_to_dict(e)) for e in entries]
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    return SessionDetailResponse(session=view, entries=entry_views)


@router.patch("/sessions/{session_id}", response_model=PromptExpanderSessionResponse)
async def rename_session(session_id: str, body: SessionRenameRequest):
    try:
        async with async_session_factory() as db:
            await PromptExpanderService.rename_session(
                db, session_id=session_id, title=body.title, user_id=DEFAULT_USER_ID
            )
            await db.commit()
            view = await _session_view(db, session_id)
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    return view


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str):
    async with async_session_factory() as db:
        deleted = await PromptExpanderService.delete_session(
            db, session_id=session_id, user_id=DEFAULT_USER_ID
        )
        await db.commit()
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "session_not_found",
                "message": "Prompt Expander セッションが見つかりません",
            },
        )
    remove_session_images(session_id)
    return None


@router.post(
    "/sessions/{session_id}/uploads",
    response_model=PromptExpanderEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(session_id: str, body: UploadRequest):
    try:
        async with async_session_factory() as db:
            entry = await PromptExpanderService.add_uploaded_entry(
                db,
                session_id=session_id,
                image_base64=body.image,
                instruction=body.instruction,
                user_id=DEFAULT_USER_ID,
            )
            await db.commit()
            data = entry_to_dict(entry)
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    return _entry_response(data)


@router.post(
    "/sessions/{session_id}/generate",
    response_model=PromptExpanderGenerateResponse,
)
async def generate_image(session_id: str, body: PromptExpanderGenerateRequest):
    params = GenerateParams(
        prompt=body.prompt,
        negative_prompt=body.negative_prompt,
        character_prompts=body.character_prompts,
        character_mode=body.character_mode,
        instruction=body.instruction or "",
        positive_expand_mode=body.positive_expand_mode,
        negative_expand_mode=body.negative_expand_mode,
        image_model=body.image_model,
        text_model=body.text_model,
        image_size=body.image_size,
        seed=body.seed,
        i2i_strength=body.i2i_strength,
        i2i_noise=body.i2i_noise,
        source_kind=body.source_kind,
        source_history_id=body.source_history_id,
        source_entry_id=body.source_entry_id,
        source_image=body.source_image,
        manga_mode=body.manga_mode,
        manga_panel_count=body.manga_panel_count,
    )
    try:
        outcome = await pe_service.generate_entry(
            session_id, params, user_id=DEFAULT_USER_ID
        )
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    balance = await pe_service.fetch_anlas_safely()
    anlas = None
    if balance is not None:
        anlas = AnlasBalanceModel(
            fixed_anlas=balance.fixed_anlas,
            purchased_anlas=balance.purchased_anlas,
            total_anlas=balance.total_anlas,
            usage=(
                AnlasUsageModel(
                    percent=balance.usage.percent,
                    is_negative=balance.usage.is_negative,
                    time_until_next_percent=balance.usage.time_until_next_percent,
                )
                if balance.usage
                else None
            ),
        )
    return PromptExpanderGenerateResponse(
        entry=_entry_response(outcome.entry), anlas=anlas
    )


# ---------------------------------------------------------------------------
# エントリ（全セッション横断）
# ---------------------------------------------------------------------------


@router.get("/entries", response_model=EntryListResponse)
async def list_entries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    async with async_session_factory() as db:
        items, total = await PromptExpanderService.list_entries(
            db, user_id=DEFAULT_USER_ID, page=page, page_size=page_size
        )
        views = [_entry_response(entry_to_dict(e)) for e in items]
    offset = (page - 1) * page_size
    return EntryListResponse(
        items=views,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(views)) < total,
    )


@router.get("/entries/{entry_id}", response_model=PromptExpanderEntryResponse)
async def get_entry(entry_id: str):
    try:
        async with async_session_factory() as db:
            entry = await PromptExpanderService.get_entry(
                db, entry_id=entry_id, user_id=DEFAULT_USER_ID
            )
            data = entry_to_dict(entry)
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    return _entry_response(data)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(entry_id: str):
    try:
        async with async_session_factory() as db:
            path = await PromptExpanderService.delete_entry(
                db, entry_id=entry_id, user_id=DEFAULT_USER_ID
            )
            await db.commit()
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    remove_entry_image(path)
    return None


@router.get("/images/{entry_id}")
async def get_entry_image(entry_id: str):
    try:
        async with async_session_factory() as db:
            entry = await PromptExpanderService.get_entry(
                db, entry_id=entry_id, user_id=DEFAULT_USER_ID
            )
            path = resolve_entry_image_file(entry)
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "image_not_found", "message": "画像が見つかりません"},
        )
    # 右クリック保存時に UUID だけの拡張子なしファイル名にならないよう、
    # inline のままファイル名を付ける
    return FileResponse(
        path,
        media_type="image/png",
        filename=f"{entry_id}.png",
        content_disposition_type="inline",
    )


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------


@router.post("/expand", response_model=PromptExpandResponse)
async def expand_prompt(body: PromptExpandRequest):
    params = ExpandParams(
        instruction=body.instruction,
        expand_positive=body.expand_positive,
        positive_mode=body.positive_mode,
        character_mode=body.character_mode,
        expand_negative=body.expand_negative,
        negative_mode=body.negative_mode,
        negative_instruction=body.negative_instruction,
        image_model=body.image_model,
        text_model=body.text_model,
        language=body.language,
        source_kind=body.source_kind,
        source_history_id=body.source_history_id,
        source_entry_id=body.source_entry_id,
        inherit_source_prompts=body.inherit_source_prompts,
        current_prompt=body.current_prompt,
        current_character_prompts=body.current_character_prompts,
        current_negative=body.current_negative,
        manga=(
            (body.manga or MangaOptionsModel()).to_options()
            if body.manga_mode
            else None
        ),
    )
    try:
        result = await pe_service.expand_prompts(params, user_id=DEFAULT_USER_ID)
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    return PromptExpandResponse(
        positive_prompt=result.positive_prompt,
        character_prompts=result.character_prompts,
        negative_prompt=result.negative_prompt,
        text_model=result.text_model,
    )


@router.post("/suggest-characters", response_model=SuggestCharactersResponse)
async def suggest_characters(body: SuggestCharactersRequest):
    try:
        result = await pe_service.suggest_character_prompts(
            text_model=body.text_model,
            image_model=body.image_model,
            mode=body.mode,
            count=body.count,
            language=body.language,
            input_text=body.input_text,
            user_id=DEFAULT_USER_ID,
        )
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    return SuggestCharactersResponse(
        suggestions=[CharacterSuggestion(**item) for item in result.suggestions],
        text_model=result.text_model,
    )
