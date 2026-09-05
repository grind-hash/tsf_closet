"""NovelAI 専用機能（インペイント用マスク管理）の API モデル。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MaskSaveRequest(BaseModel):
    """マスク保存リクエスト"""

    mask_base64: str = Field(..., description="Base64エンコードされたマスクPNG")
    name: str | None = Field(
        None,
        min_length=1,
        max_length=50,
        description="プリセット名 (指定時はプリセットとして保存)",
    )
    auto_save: bool = Field(False, description="自動保存フラグ (変身時にtrue)")


class MaskInfo(BaseModel):
    """マスク情報"""

    id: str = Field(
        ..., description="マスクID (system:filename / history:uuid / preset:uuid)"
    )
    name: str = Field(..., description="表示名")
    type: Literal["system", "history", "preset"] = Field(..., description="マスク種別")
    url: str = Field(..., description="取得用URL")
    created_at: str | None = Field(
        None, description="作成日時 (ISO) - history/presetのみ"
    )


class MaskListResponse(BaseModel):
    """マスク一覧レスポンス"""

    system: list[MaskInfo] = Field(..., description="システムデフォルトマスク")
    history: list[MaskInfo] = Field(..., description="保存済み履歴マスク（最大20件）")
    presets: list[MaskInfo] = Field(
        default_factory=list, description="ユーザープリセットマスク"
    )


class AnlasUsageModel(BaseModel):
    """NovelAI V5 usage limit model."""

    percent: int
    is_negative: bool = False
    time_until_next_percent: int = 0


class AnlasBalanceResponse(BaseModel):
    """Anlas balance response model."""

    fixed_anlas: int | None = None
    purchased_anlas: int | None = None
    total_anlas: int | None = None
    usage: AnlasUsageModel | None = None
