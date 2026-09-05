"""共通の API レスポンスモデル。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """エラーレスポンス"""

    error: str = Field(..., description="エラーコード")
    message: str = Field(..., description="エラーメッセージ")
