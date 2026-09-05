"""パラメータシステム（開花度・羞恥心・順応度、難易度）の API モデル。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SessionStatsResponse(BaseModel):
    """セッション統計レスポンス"""

    bloom: int = Field(..., ge=0, le=100, description="開花度")
    shame: int = Field(..., ge=0, le=100, description="羞恥心")
    adaptation: int = Field(..., ge=-50, le=50, description="順応度")
    passed_critical_points: list[int] = Field(
        ..., description="通過済み臨界点", alias="passedCriticalPoints"
    )
    difficulty: str = Field(..., description="難易度")
    nsfw_mode: bool = Field(False, description="NSFWモード", alias="nsfwMode")
    enable_prompt_preview: bool = Field(
        False, description="プロンプト確認有効化", alias="enablePromptPreview"
    )

    model_config = ConfigDict(populate_by_name=True)


class DifficultyResponse(BaseModel):
    """難易度レスポンス"""

    id: str = Field(..., description="難易度ID")
    name: str = Field(..., description="難易度名")
    description: str = Field(..., description="難易度説明")


class DifficultyListResponse(BaseModel):
    """難易度一覧レスポンス"""

    difficulties: list[DifficultyResponse] = Field(..., description="難易度一覧")
