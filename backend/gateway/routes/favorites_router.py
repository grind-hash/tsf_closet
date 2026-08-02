"""お気に入り衣装スナップショット API。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..databases.base import async_session_factory
from ..services.favorite_service import (
    FavoriteOutfitService,
    FavoriteServiceError,
    FavoriteOutfitView,
)
from ..services.session import DEFAULT_USER_ID

router = APIRouter(prefix="/favorites", tags=["favorites"])


def _to_iso(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return datetime.now().isoformat()


class FavoriteCreateRequest(BaseModel):
    history_id: str = Field(..., min_length=1, description="履歴ID")
    label: Optional[str] = Field(None, max_length=80, description="任意ラベル")


class FavoriteUpdateRequest(BaseModel):
    label: Optional[str] = Field(
        None, max_length=80, description="任意ラベル（空でクリア）"
    )


class FavoriteItemResponse(BaseModel):
    id: str
    history_id: str
    session_id: str
    label: Optional[str] = None
    image_url: str
    instruction: str
    costume_category: Optional[str] = None
    history_created_at: Optional[str] = None
    created_at: str


class FavoriteListResponse(BaseModel):
    items: list[FavoriteItemResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class DeleteFavoriteResponse(BaseModel):
    success: bool = True
    deleted: bool = True


def _serialize(view: FavoriteOutfitView) -> FavoriteItemResponse:
    return FavoriteItemResponse(
        id=view.id,
        history_id=view.history_id,
        session_id=view.session_id,
        label=view.label,
        image_url=view.image_url,
        instruction=view.instruction,
        costume_category=view.costume_category,
        history_created_at=(
            _to_iso(view.history_created_at) if view.history_created_at else None
        ),
        created_at=_to_iso(view.created_at),
    )


def _http_error(exc: FavoriteServiceError) -> HTTPException:
    code_map = {
        "history_not_found": status.HTTP_404_NOT_FOUND,
        "favorite_not_found": status.HTTP_404_NOT_FOUND,
        "already_favorited": status.HTTP_409_CONFLICT,
        "label_too_long": status.HTTP_422_UNPROCESSABLE_ENTITY,
    }
    return HTTPException(
        status_code=code_map.get(exc.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": exc.code, "message": exc.message},
    )


@router.get("", response_model=FavoriteListResponse)
async def list_favorites(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    async with async_session_factory() as db:
        items, total = await FavoriteOutfitService.list_for_user(
            db,
            user_id=DEFAULT_USER_ID,
            page=page,
            page_size=page_size,
        )
    offset = (page - 1) * page_size
    return FavoriteListResponse(
        items=[_serialize(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(items)) < total,
    )


@router.post(
    "",
    response_model=FavoriteItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_favorite(body: FavoriteCreateRequest):
    try:
        async with async_session_factory() as db:
            view = await FavoriteOutfitService.add(
                db,
                history_id=body.history_id,
                label=body.label,
                user_id=DEFAULT_USER_ID,
            )
            await db.commit()
    except FavoriteServiceError as exc:
        raise _http_error(exc) from exc
    return _serialize(view)


@router.patch("/{favorite_id}", response_model=FavoriteItemResponse)
async def update_favorite(favorite_id: str, body: FavoriteUpdateRequest):
    try:
        async with async_session_factory() as db:
            view = await FavoriteOutfitService.update_label(
                db,
                favorite_id=favorite_id,
                label=body.label,
                user_id=DEFAULT_USER_ID,
            )
            await db.commit()
    except FavoriteServiceError as exc:
        raise _http_error(exc) from exc
    return _serialize(view)


@router.delete(
    "/by-history/{history_id}",
    response_model=DeleteFavoriteResponse,
)
async def delete_favorite_by_history(history_id: str):
    """履歴ID指定の削除。動的パスより先に定義する。"""
    async with async_session_factory() as db:
        deleted = await FavoriteOutfitService.delete_by_history(
            db,
            history_id=history_id,
            user_id=DEFAULT_USER_ID,
        )
        await db.commit()
    return DeleteFavoriteResponse(success=True, deleted=deleted)


@router.delete("/{favorite_id}", response_model=DeleteFavoriteResponse)
async def delete_favorite(favorite_id: str):
    async with async_session_factory() as db:
        deleted = await FavoriteOutfitService.delete(
            db,
            favorite_id=favorite_id,
            user_id=DEFAULT_USER_ID,
        )
        await db.commit()
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "favorite_not_found",
                "message": "お気に入りが見つかりません",
            },
        )
    return DeleteFavoriteResponse(success=True, deleted=True)
