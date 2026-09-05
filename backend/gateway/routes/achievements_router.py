"""
実績システム - Achievement definitions and logic
007-chat-interactive-ux
"""

from fastapi import APIRouter, HTTPException

from ..schemas.achievements import AchievementResponse, AchievementsListResponse
from ..services.achievements import (
    ACHIEVEMENTS,
    get_achievement,
    get_global_stats,
    get_user_achievements,
)

# =============================================================================
# API エンドポイント
# =============================================================================

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("", response_model=AchievementsListResponse)
async def get_achievements(session_id: str | None = None):
    """
    実績一覧を取得（グローバル管理）

    session_idは後方互換性のために残すが、実績はグローバルで共有される
    """
    unlocked_ids: set[str] = set()
    unlocked_at_map: dict[str, str] = {}

    # グローバル実績を取得（session_idは無視）
    statuses = get_user_achievements()
    for status in statuses:
        if status.unlocked:
            unlocked_ids.add(status.achievement_id)
            if status.unlocked_at:
                unlocked_at_map[status.achievement_id] = status.unlocked_at

    achievements = []
    for ach in ACHIEVEMENTS.values():
        # 隠し実績で未解除なら非表示
        if ach.is_hidden and ach.id not in unlocked_ids:
            continue

        is_unlocked = ach.id in unlocked_ids
        achievements.append(
            AchievementResponse(
                id=ach.id,
                name=ach.name,
                description=ach.description,
                category=ach.category,
                icon=ach.icon,
                condition_type=ach.condition_type,
                condition_target=ach.condition_target,
                condition_value=ach.condition_value,
                is_hidden=ach.is_hidden,
                unlocked=is_unlocked,
                unlocked_at=unlocked_at_map.get(ach.id),
                hint=ach.hint if not is_unlocked else None,
            )
        )

    global_stats = get_global_stats()

    return AchievementsListResponse(
        achievements=achievements,
        total=len(ACHIEVEMENTS),
        unlocked_count=len(unlocked_ids),
        transform_count=global_stats.transform_count,
        crossdress_count=global_stats.crossdress_count,
        reality_alter_count=global_stats.reality_alter_count,
        gallery_count=global_stats.gallery_count,
    )


@router.get("/{achievement_id}", response_model=AchievementResponse)
async def get_achievement_detail(achievement_id: str, session_id: str | None = None):
    """
    実績詳細を取得（グローバル管理）
    """
    ach = get_achievement(achievement_id)
    if not ach:
        raise HTTPException(status_code=404, detail="Achievement not found")

    unlocked = False
    unlocked_at = None

    # グローバル実績を取得
    statuses = get_user_achievements()
    for status in statuses:
        if status.achievement_id == achievement_id:
            unlocked = status.unlocked
            unlocked_at = status.unlocked_at
            break

    return AchievementResponse(
        id=ach.id,
        name=ach.name,
        description=ach.description,
        category=ach.category,
        icon=ach.icon,
        condition_type=ach.condition_type,
        condition_target=ach.condition_target,
        condition_value=ach.condition_value,
        is_hidden=ach.is_hidden,
        unlocked=unlocked,
        unlocked_at=unlocked_at,
        hint=ach.hint if not unlocked else None,
    )
