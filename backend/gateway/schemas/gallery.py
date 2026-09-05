"""エンディングギャラリーの API モデル。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GalleryEndingItem(BaseModel):
    """ギャラリーのエンディングアイテム"""

    ending_id: str = Field(..., description="エンディングID")
    title: str = Field(..., description="タイトル（未達成時は「???」）")
    achieved: bool = Field(..., description="達成済みか")
    achieved_at: str | None = Field(None, description="達成日時")


class GalleryResponse(BaseModel):
    """ギャラリーレスポンス"""

    endings: list[GalleryEndingItem] = Field(..., description="エンディング一覧")
    total_count: int = Field(..., description="全エンディング数")
    achieved_count: int = Field(..., description="達成済みエンディング数")


class GalleryItem(BaseModel):
    """ギャラリーアイテム"""

    id: str
    session_id: str
    image_url: str
    instruction: str
    feeling_text: str | None
    before_description: str | None
    after_description: str | None
    timestamp: str
    costume_category: str | None
    exposure_level: str | None
    is_favorited: bool = False


class GallerySession(BaseModel):
    """セッション単位のギャラリー情報"""

    session_id: str
    character_name: str | None
    thumbnail_url: str
    item_count: int
    first_timestamp: str
    last_timestamp: str
    self_mode: bool = False
    has_summary: bool = False
    match_snippet: str | None = None
    last_instruction: str | None = None


class GallerySessionsResponse(BaseModel):
    """セッション一覧レスポンス"""

    sessions: list[GallerySession]
    total: int
    page: int
    page_size: int
    has_more: bool


class GalleryListResponse(BaseModel):
    """ギャラリー一覧レスポンス"""

    items: list[GalleryItem]
    total: int
    page: int
    page_size: int
    has_more: bool


class GalleryDetailResponse(BaseModel):
    """ギャラリー詳細レスポンス"""

    item: GalleryItem
    prev_id: str | None
    next_id: str | None


class DeleteResponse(BaseModel):
    """削除結果レスポンス"""

    success: bool
    deleted_count: int
    message: str
