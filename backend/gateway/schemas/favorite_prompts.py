"""お気に入りプロンプトの API モデル。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FavoritePromptCreateRequest(BaseModel):
    label: str = Field(..., max_length=80, description="名前")
    content: str = Field(..., max_length=4000, description="挿入される内容")
    color: str | None = Field(None, description="#RRGGBB（省略時は既定色）")
    category_id: str | None = Field(None, description="カテゴリーID（省略で未分類）")


class FavoritePromptUpdateRequest(BaseModel):
    """送った項目だけを更新する。category_id に null を送ると未分類へ移動する。"""

    label: str | None = Field(None, max_length=80)
    content: str | None = Field(None, max_length=4000)
    color: str | None = None
    category_id: str | None = None


class FavoritePromptPlacement(BaseModel):
    id: str
    category_id: str | None = Field(None, description="カテゴリーID（null で未分類）")


class FavoritePromptReorderRequest(BaseModel):
    """表示順（未分類 → カテゴリー順）に並べたプロンプトと、それぞれの移動先。"""

    prompts: list[FavoritePromptPlacement]


class FavoritePromptCategoryCreateRequest(BaseModel):
    label: str = Field(..., max_length=80, description="カテゴリー名")
    color: str | None = Field(None, description="#RRGGBB（省略時は既定色）")


class FavoritePromptCategoryUpdateRequest(BaseModel):
    label: str | None = Field(None, max_length=80)
    color: str | None = None


class FavoritePromptItemResponse(BaseModel):
    id: str
    category_id: str | None = None
    label: str
    content: str
    color: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class FavoritePromptCategoryResponse(BaseModel):
    id: str
    label: str
    color: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class FavoritePromptListResponse(BaseModel):
    categories: list[FavoritePromptCategoryResponse]
    prompts: list[FavoritePromptItemResponse]


class DeleteFavoritePromptResponse(BaseModel):
    success: bool = True
    deleted: bool = True


# ---- インポート / エクスポート ----
# ID は環境ごとに異なるため、ファイルではカテゴリーを名前で参照する。
# 文字数などの検証はサービス側で行い、何件目の項目かをメッセージに含める。


class FavoritePromptFileCategory(BaseModel):
    label: str
    color: str | None = None


class FavoritePromptFilePrompt(BaseModel):
    category: str | None = Field(None, description="カテゴリー名（null で未分類）")
    label: str
    content: str
    color: str | None = None


class FavoritePromptFile(BaseModel):
    """エクスポートファイルの中身（インポート時もこの形で受け取る）。"""

    format: str
    version: int
    exported_at: datetime | None = None
    categories: list[FavoritePromptFileCategory] = Field(default_factory=list)
    prompts: list[FavoritePromptFilePrompt] = Field(default_factory=list)


class FavoritePromptImportTarget(BaseModel):
    category: str | None = None
    label: str


class FavoritePromptImportPreviewResponse(BaseModel):
    create_count: int
    overwrites: list[FavoritePromptImportTarget]
    new_categories: list[str]


class FavoritePromptImportResponse(FavoritePromptImportPreviewResponse):
    """取り込み結果と、取り込み後の一覧。"""

    categories: list[FavoritePromptCategoryResponse]
    prompts: list[FavoritePromptItemResponse]
