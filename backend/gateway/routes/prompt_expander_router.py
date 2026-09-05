"""Prompt Expander API。

自然言語からの NovelAI プロンプト拡張と画像生成、専用履歴（セッション/エントリ）、
専用設定を提供する。通常ゲームの Session/History には影響を与えない。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from ..consts.prompt_expander import (
    PROMPT_EXPANDER_IMAGE_MODEL_OPTIONS,
    PROMPT_EXPANDER_IMAGE_SIZES,
    max_character_prompts_map,
)
from ..databases.base import async_session_factory
from ..schemas.novelai import AnlasBalanceResponse, AnlasUsageModel
from ..schemas.prompt_expander import (
    CharacterSuggestion,
    EntryListResponse,
    MangaOptionsModel,
    MangaScriptRequest,
    MangaScriptResponse,
    PromptExpanderEntryResponse,
    PromptExpanderGenerateRequest,
    PromptExpanderGenerateResponse,
    PromptExpanderSessionListResponse,
    PromptExpanderSessionResponse,
    PromptExpanderSettingsModel,
    PromptExpanderSettingsResponse,
    PromptExpanderSettingsUpdateRequest,
    PromptExpandRequest,
    PromptExpandResponse,
    SessionCreateRequest,
    SessionDetailResponse,
    SessionRenameRequest,
    SuggestCharactersRequest,
    SuggestCharactersResponse,
    TextModelOption,
    UploadRequest,
)
from ..services import prompt_expander_service as pe_service
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
    resolve_entry_mask_file,
    text_model_options,
)
from ..services.session import DEFAULT_USER_ID

router = APIRouter(prefix="/prompt-expander", tags=["prompt-expander"])


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------


def _http_error(exc: PromptExpanderError) -> HTTPException:
    code_map = {
        "session_not_found": status.HTTP_404_NOT_FOUND,
        "entry_not_found": status.HTTP_404_NOT_FOUND,
        "history_not_found": status.HTTP_404_NOT_FOUND,
        "image_not_found": status.HTTP_404_NOT_FOUND,
        "mask_not_found": status.HTTP_404_NOT_FOUND,
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
        "precise_reference_requires_v45": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "inpaint_requires_source": status.HTTP_422_UNPROCESSABLE_ENTITY,
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


@router.get("/sessions", response_model=PromptExpanderSessionListResponse)
async def list_sessions():
    async with async_session_factory() as db:
        views = await PromptExpanderService.list_sessions(db, user_id=DEFAULT_USER_ID)
    return PromptExpanderSessionListResponse(
        sessions=[_session_response(v) for v in views]
    )


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
        reference_kind=body.reference_kind,
        reference_history_id=body.reference_history_id,
        reference_entry_id=body.reference_entry_id,
        reference_image=body.reference_image,
        reference_type=body.reference_type,
        reference_strength=body.reference_strength,
        reference_fidelity=body.reference_fidelity,
        transparent_background=body.transparent_background,
        transparent_emphasis=body.transparent_emphasis,
        inpaint_mask=body.inpaint_mask,
        inpaint_mask_entry_id=body.inpaint_mask_entry_id,
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
        anlas = AnlasBalanceResponse(
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
            paths = await PromptExpanderService.delete_entry(
                db, entry_id=entry_id, user_id=DEFAULT_USER_ID
            )
            await db.commit()
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    for path in paths:
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


@router.get("/entries/{entry_id}/mask")
async def get_entry_mask(entry_id: str):
    """インペイントで使ったマスクを返す（同じ領域で差分を作り直すため）。"""
    try:
        async with async_session_factory() as db:
            entry = await PromptExpanderService.get_entry(
                db, entry_id=entry_id, user_id=DEFAULT_USER_ID
            )
            path = resolve_entry_mask_file(entry)
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "mask_not_found", "message": "マスク画像が見つかりません"},
        )
    return FileResponse(
        path,
        media_type="image/png",
        filename=f"{entry_id}_mask.png",
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
        transparent_background=body.transparent_background,
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


@router.post("/manga-script", response_model=MangaScriptResponse)
async def draft_manga_script(body: MangaScriptRequest):
    params = pe_service.MangaScriptParams(
        instruction=body.instruction,
        image_model=body.image_model,
        text_model=body.text_model,
        language=body.language,
        manga=(body.manga or MangaOptionsModel()).to_options(),
    )
    try:
        result = await pe_service.draft_manga_script(params, user_id=DEFAULT_USER_ID)
    except PromptExpanderError as exc:
        raise _http_error(exc) from exc
    return MangaScriptResponse(script=result.script, text_model=result.text_model)


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
