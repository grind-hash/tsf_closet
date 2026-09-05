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
