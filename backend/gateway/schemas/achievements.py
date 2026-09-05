"""実績一覧の API モデル。"""

from __future__ import annotations

from pydantic import BaseModel


class AchievementResponse(BaseModel):
    """実績レスポンス"""

    id: str
    name: str
    description: str
    category: str
    icon: str
    condition_type: str
    condition_target: str
    condition_value: int
    is_hidden: bool
    unlocked: bool
    unlocked_at: str | None
    hint: str | None = None  # 未開放時のヒントテキスト


class AchievementsListResponse(BaseModel):
    """実績一覧レスポンス"""

    achievements: list[AchievementResponse]
    total: int
    unlocked_count: int
    transform_count: int = 0
    crossdress_count: int = 0
    reality_alter_count: int = 0
    gallery_count: int = 0
