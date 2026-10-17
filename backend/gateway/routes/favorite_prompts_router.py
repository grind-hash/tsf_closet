"""お気に入りプロンプト API（TSF Closet 内保存。NovelAI とは同期しない）。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from ..databases.base import async_session_factory
from ..databases.models import FavoritePrompt, FavoritePromptCategory
from ..schemas.favorite_prompts import (
    DeleteFavoritePromptResponse,
    FavoritePromptCategoryCreateRequest,
    FavoritePromptCategoryResponse,
    FavoritePromptCategoryUpdateRequest,
    FavoritePromptCreateRequest,
    FavoritePromptImportPreviewResponse,
    FavoritePromptImportResponse,
    FavoritePromptImportTarget,
    FavoritePromptItemResponse,
    FavoritePromptListResponse,
    FavoritePromptUpdateRequest,
)
from ..services.favorite_prompt_file import (
    MAX_FILE_BYTES,
    FavoritePromptFileEntries,
    FavoritePromptFileError,
    parse_file,
    render_csv,
    render_json,
)
from ..services.favorite_prompt_service import (
    FavoritePromptImportPlan,
    FavoritePromptService,
    FavoritePromptServiceError,
)
from ..services.session import DEFAULT_USER_ID

router = APIRouter(prefix="/favorite-prompts", tags=["favorite-prompts"])


def _serialize_prompt(prompt: FavoritePrompt) -> FavoritePromptItemResponse:
    return FavoritePromptItemResponse(
        id=prompt.id,
        category_id=prompt.category_id,
        label=prompt.label,
        content=prompt.content,
        color=prompt.color,
        sort_order=prompt.sort_order,
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
    )


def _serialize_category(
    category: FavoritePromptCategory,
) -> FavoritePromptCategoryResponse:
    return FavoritePromptCategoryResponse(
        id=category.id,
        label=category.label,
        color=category.color,
        sort_order=category.sort_order,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


def _serialize_import_plan(
    plan: FavoritePromptImportPlan,
) -> FavoritePromptImportPreviewResponse:
    return FavoritePromptImportPreviewResponse(
        create_count=len(plan.creates),
        overwrites=[
            FavoritePromptImportTarget(category=item.category, label=item.label)
            for _, item in plan.overwrites
        ],
        new_categories=[label for label, _ in plan.new_categories],
    )


def _http_error(
    exc: FavoritePromptServiceError | FavoritePromptFileError,
) -> HTTPException:
    code_map = {
        "prompt_not_found": status.HTTP_404_NOT_FOUND,
        "category_not_found": status.HTTP_404_NOT_FOUND,
        "label_required": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "label_too_long": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "content_required": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "content_too_long": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "invalid_color": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "invalid_import_file": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "unsupported_import_version": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "invalid_encoding": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "empty_file": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "file_too_large": status.HTTP_413_CONTENT_TOO_LARGE,
    }
    return HTTPException(
        status_code=code_map.get(exc.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": exc.code, "message": exc.message},
    )


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": code, "message": message},
    )


@router.get("", response_model=FavoritePromptListResponse)
async def list_favorite_prompts():
    async with async_session_factory() as db:
        categories, prompts = await FavoritePromptService.list_all(
            db, user_id=DEFAULT_USER_ID
        )
    return FavoritePromptListResponse(
        categories=[_serialize_category(c) for c in categories],
        prompts=[_serialize_prompt(p) for p in prompts],
    )


@router.post(
    "",
    response_model=FavoritePromptItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_favorite_prompt(body: FavoritePromptCreateRequest):
    try:
        async with async_session_factory() as db:
            prompt = await FavoritePromptService.create_prompt(
                db,
                label=body.label,
                content=body.content,
                color=body.color,
                category_id=body.category_id,
                user_id=DEFAULT_USER_ID,
            )
            await db.commit()
    except FavoritePromptServiceError as exc:
        raise _http_error(exc) from exc
    return _serialize_prompt(prompt)


# インポート / エクスポート・カテゴリー系は動的パス /{prompt_id} より先に定義する
@router.get("/export")
async def export_favorite_prompts(
    file_format: Literal["json", "csv"] = Query("json", alias="format"),
    lang: Literal["ja", "en"] = Query("ja", description="CSV の列見出しの言語"),
) -> Response:
    async with async_session_factory() as db:
        data = await FavoritePromptService.export_file(db, user_id=DEFAULT_USER_ID)
    if file_format == "csv":
        content = render_csv(data, lang)
        media_type = "text/csv; charset=utf-8"
    else:
        content = render_json(data)
        media_type = "application/json"
    filename = f"tsf-closet-favorite-prompts.{file_format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _read_import_file(file: UploadFile) -> FavoritePromptFileEntries:
    # 上限を 1 バイト超えて読み、超過は parse_file で弾く
    raw = await file.read(MAX_FILE_BYTES + 1)
    return parse_file(file.filename, raw)


@router.post(
    "/import/preview",
    response_model=FavoritePromptImportPreviewResponse,
)
async def preview_favorite_prompt_import(file: UploadFile = File(...)):
    """書き込まずに、追加・上書きされる件数と対象を返す（上書き確認用）。"""
    try:
        entries = await _read_import_file(file)
        async with async_session_factory() as db:
            plan = await FavoritePromptService.preview_import(
                db, entries=entries, user_id=DEFAULT_USER_ID
            )
    except (FavoritePromptFileError, FavoritePromptServiceError) as exc:
        raise _http_error(exc) from exc
    return _serialize_import_plan(plan)


@router.post("/import", response_model=FavoritePromptImportResponse)
async def import_favorite_prompts(file: UploadFile = File(...)):
    """CSV / JSON を取り込む。同じカテゴリー・同じ名前のものは上書きする。"""
    try:
        entries = await _read_import_file(file)
        async with async_session_factory() as db:
            plan = await FavoritePromptService.import_file(
                db, entries=entries, user_id=DEFAULT_USER_ID
            )
            await db.commit()
            categories, prompts = await FavoritePromptService.list_all(
                db, user_id=DEFAULT_USER_ID
            )
    except (FavoritePromptFileError, FavoritePromptServiceError) as exc:
        raise _http_error(exc) from exc
    summary = _serialize_import_plan(plan)
    return FavoritePromptImportResponse(
        **summary.model_dump(),
        categories=[_serialize_category(c) for c in categories],
        prompts=[_serialize_prompt(p) for p in prompts],
    )


@router.post(
    "/categories",
    response_model=FavoritePromptCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_favorite_prompt_category(body: FavoritePromptCategoryCreateRequest):
    try:
        async with async_session_factory() as db:
            category = await FavoritePromptService.create_category(
                db,
                label=body.label,
                color=body.color,
                user_id=DEFAULT_USER_ID,
            )
            await db.commit()
    except FavoritePromptServiceError as exc:
        raise _http_error(exc) from exc
    return _serialize_category(category)


@router.patch(
    "/categories/{category_id}",
    response_model=FavoritePromptCategoryResponse,
)
async def update_favorite_prompt_category(
    category_id: str, body: FavoritePromptCategoryUpdateRequest
):
    try:
        async with async_session_factory() as db:
            category = await FavoritePromptService.update_category(
                db,
                category_id=category_id,
                changes=body.model_dump(exclude_unset=True),
                user_id=DEFAULT_USER_ID,
            )
            await db.commit()
    except FavoritePromptServiceError as exc:
        raise _http_error(exc) from exc
    return _serialize_category(category)


@router.delete(
    "/categories/{category_id}",
    response_model=DeleteFavoritePromptResponse,
)
async def delete_favorite_prompt_category(category_id: str):
    async with async_session_factory() as db:
        deleted = await FavoritePromptService.delete_category(
            db,
            category_id=category_id,
            user_id=DEFAULT_USER_ID,
        )
        await db.commit()
    if not deleted:
        raise _not_found("category_not_found", "カテゴリーが見つかりません")
    return DeleteFavoritePromptResponse(success=True, deleted=True)


@router.patch("/{prompt_id}", response_model=FavoritePromptItemResponse)
async def update_favorite_prompt(prompt_id: str, body: FavoritePromptUpdateRequest):
    try:
        async with async_session_factory() as db:
            prompt = await FavoritePromptService.update_prompt(
                db,
                prompt_id=prompt_id,
                changes=body.model_dump(exclude_unset=True),
                user_id=DEFAULT_USER_ID,
            )
            await db.commit()
    except FavoritePromptServiceError as exc:
        raise _http_error(exc) from exc
    return _serialize_prompt(prompt)


@router.delete("/{prompt_id}", response_model=DeleteFavoritePromptResponse)
async def delete_favorite_prompt(prompt_id: str):
    async with async_session_factory() as db:
        deleted = await FavoritePromptService.delete_prompt(
            db,
            prompt_id=prompt_id,
            user_id=DEFAULT_USER_ID,
        )
        await db.commit()
    if not deleted:
        raise _not_found("prompt_not_found", "お気に入りプロンプトが見つかりません")
    return DeleteFavoritePromptResponse(success=True, deleted=True)
