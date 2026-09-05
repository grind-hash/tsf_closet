"""お気に入りの API モデル。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FavoriteCreateRequest(BaseModel):
    history_id: str = Field(..., min_length=1, description="履歴ID")
    label: str | None = Field(None, max_length=80, description="任意ラベル")


class FavoriteUpdateRequest(BaseModel):
    label: str | None = Field(
        None, max_length=80, description="任意ラベル（空でクリア）"
    )


class FavoriteItemResponse(BaseModel):
    id: str
    history_id: str
    session_id: str
    label: str | None = None
    image_url: str
    instruction: str
    costume_category: str | None = None
    history_created_at: str | None = None
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
