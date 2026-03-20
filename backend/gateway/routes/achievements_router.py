"""
実績システム - Achievement definitions and logic
007-chat-interactive-ux
"""

from dataclasses import dataclass
from typing import Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.achievement_service import achievement_service


@dataclass(frozen=True)
class Achievement:
    """実績定義（静的定義）"""

    id: str  # 一意識別子 (例: "first_transform")
    name: str  # 表示名 (例: "初めての変身")
    description: str  # 説明文
    category: str  # カテゴリ (transform, crossdress, reality, collection)
    icon: str  # アイコン識別子/絵文字
    condition_type: str  # 条件タイプ (count, specific, threshold)
    condition_target: str  # 条件対象 (transform, crossdress, reality_alter, gallery)
    condition_value: int  # 条件値 (回数/閾値)
    is_hidden: bool = False  # 隠し実績かどうか
    hint: str | None = None  # 未開放時のヒントテキスト


# 初期実績一覧
ACHIEVEMENTS: Dict[str, Achievement] = {
    "first_transform": Achievement(
        id="first_transform",
        name="初めての変身",
        description="初めて変身を行った",
        category="transform",
        icon="🌟",
        condition_type="count",
        condition_target="transform",
        condition_value=1,
        hint="変身を試してみましょう",
    ),
    "transform_10": Achievement(
        id="transform_10",
        name="変身マスター",
        description="変身を10回行った",
        category="transform",
        icon="✨",
        condition_type="count",
        condition_target="transform",
        condition_value=10,
        hint="さらに変身を繰り返してみましょう",
    ),
    "transform_50": Achievement(
        id="transform_50",
        name="変身エキスパート",
        description="変身を50回行った",
        category="transform",
        icon="💫",
        condition_type="count",
        condition_target="transform",
        condition_value=50,
        hint="変身の達人を目指して継続しましょう",
    ),
    "crossdress_first": Achievement(
        id="crossdress_first",
        name="女装入門",
        description="初めて女装を行った",
        category="crossdress",
        icon="👗",
        condition_type="count",
        condition_target="crossdress",
        condition_value=1,
        hint="女性用の衣装に着替えてみましょう",
    ),
    "crossdress_10": Achievement(
        id="crossdress_10",
        name="女装マスター",
        description="女装を10回行った",
        category="crossdress",
        icon="👠",
        condition_type="count",
        condition_target="crossdress",
        condition_value=10,
        hint="いろいろな女性用衣装に挑戦しましょう",
    ),
    "gender_change": Achievement(
        id="gender_change",
        name="女体化",
        description="女体化を経験した",
        category="transform",
        icon="🦋",
        condition_type="specific",
        condition_target="gender_change",
        condition_value=1,
        hint="女体化を経験してみましょう",
    ),
    "reality_first": Achievement(
        id="reality_first",
        name="現実改変者",
        description="初めて現実改変を行った",
        category="reality",
        icon="🌀",
        condition_type="count",
        condition_target="reality_alter",
        condition_value=1,
        hint="周囲の認識を変える現実改変を試してみましょう",
    ),
    "reality_10": Achievement(
        id="reality_10",
        name="現実支配者",
        description="現実改変を10回行った",
        category="reality",
        icon="🌌",
        condition_type="count",
        condition_target="reality_alter",
        condition_value=10,
        hint="さらなる現実改変を継続しましょう",
    ),
    "gallery_10": Achievement(
        id="gallery_10",
        name="コレクター",
        description="ギャラリーに10枚の画像を保存した",
        category="collection",
        icon="🖼️",
        condition_type="count",
        condition_target="gallery",
        condition_value=10,
        hint="変身の記録を集めていきましょう",
    ),
    "gallery_50": Achievement(
        id="gallery_50",
        name="ギャラリスト",
        description="ギャラリーに50枚の画像を保存した",
        category="collection",
        icon="🏛️",
        condition_type="count",
        condition_target="gallery",
        condition_value=50,
        hint="より多くの変身画像をコレクションしましょう",
    ),
    "bloom_50": Achievement(
        id="bloom_50",
        name="開花の兆し",
        description="開花度が50に達した",
        category="transform",
        icon="🌸",
        condition_type="threshold",
        condition_target="bloom",
        condition_value=50,
        hint="色々な変身を経験して開花度を上げましょう",
    ),
    "bloom_100": Achievement(
        id="bloom_100",
        name="完全開花",
        description="開花度が100に達した",
        category="transform",
        icon="🌺",
        condition_type="threshold",
        condition_target="bloom",
        condition_value=100,
        hint="完全な開花を目指して継続しましょう",
    ),
    # Self-mode achievements
    "self_first": Achievement(
        id="self_first",
        name="自分自身として",
        description="自分モードで初めて変身を行った",
        category="self",
        icon="🪞",
        condition_type="count",
        condition_target="self_transform",
        condition_value=1,
        hint="自分モードで変身を試してみましょう",
    ),
    "self_10": Achievement(
        id="self_10",
        name="もう一人の自分",
        description="自分モードで変身を10回行った",
        category="self",
        icon="🔮",
        condition_type="count",
        condition_target="self_transform",
        condition_value=10,
        hint="自分モードでさらに変身を重ねましょう",
    ),
    "self_50": Achievement(
        id="self_50",
        name="変身する自分",
        description="自分モードで変身を50回行った",
        category="self",
        icon="💎",
        condition_type="count",
        condition_target="self_transform",
        condition_value=50,
        hint="自分モードの達人を目指して継続しましょう",
    ),
}


def get_achievement(achievement_id: str) -> Achievement | None:
    """実績IDから実績定義を取得"""
    return ACHIEVEMENTS.get(achievement_id)


def get_achievements_by_category(category: str) -> list[Achievement]:
    """カテゴリで実績を絞り込み"""
    return [a for a in ACHIEVEMENTS.values() if a.category == category]


def get_all_achievements() -> list[Achievement]:
    """すべての実績定義を取得"""
    return list(ACHIEVEMENTS.values())


def get_achievement_counts() -> tuple[int, int, int]:
    """
    グローバルな実績カウントを取得

    Returns:
        (crossdress_count, gender_change_count, reality_alter_count)
    """
    return achievement_service.get_achievement_counts()


def update_achievement_counts(categories: list[str]) -> None:
    """
    分類結果に基づいてグローバルカウントを更新

    Args:
        categories: 該当カテゴリのリスト (CROSS_DRESS, GENDER_CHANGE, REALITY_ALTER)
    """
    achievement_service.update_achievement_counts(categories)


def get_global_stats() -> "SessionStats":
    """
    全セッション通算の累積統計を取得

    Returns:
        累積されたSessionStats
    """
    stats = achievement_service.get_global_stats()
    return SessionStats(**stats)


# =============================================================================
# 実績判定ロジック
# =============================================================================


@dataclass
class UserAchievementStatus:
    """ユーザーの実績状態"""

    achievement_id: str
    unlocked: bool
    unlocked_at: str | None = None


class SessionStats(BaseModel):
    """セッション統計（判定用）"""

    transform_count: int = 0
    crossdress_count: int = 0
    reality_alter_count: int = 0
    gallery_count: int = 0
    self_transform_count: int = 0
    bloom: int = 0
    shame: int = 0
    adaptation: int = 0
    has_gender_change: bool = False


def check_achievement(achievement: Achievement, stats: SessionStats) -> bool:
    """単一の実績条件をチェック"""
    if achievement.condition_type == "count":
        target = achievement.condition_target
        if target == "transform":
            return stats.transform_count >= achievement.condition_value
        elif target == "crossdress":
            return stats.crossdress_count >= achievement.condition_value
        elif target == "reality_alter":
            return stats.reality_alter_count >= achievement.condition_value
        elif target == "gallery":
            return stats.gallery_count >= achievement.condition_value
        elif target == "self_transform":
            return stats.self_transform_count >= achievement.condition_value
    elif achievement.condition_type == "threshold":
        target = achievement.condition_target
        if target == "bloom":
            return stats.bloom >= achievement.condition_value
        elif target == "shame":
            return stats.shame >= achievement.condition_value
        elif target == "adaptation":
            return stats.adaptation >= achievement.condition_value
    elif achievement.condition_type == "specific":
        if achievement.condition_target == "gender_change":
            return stats.has_gender_change
    return False


def check_achievements(
    session_id: str, stats: SessionStats, already_unlocked: set[str]
) -> list[Achievement]:
    """
    統計データに基づいて新規解除された実績をチェック

    Returns:
        新規解除された実績のリスト
    """
    return achievement_service.get_newly_unlocked(
        achievements=list(ACHIEVEMENTS.values()),
        stats=stats,
        already_unlocked=already_unlocked,
        checker=check_achievement,
    )


def save_user_achievement(session_id: str, achievement_id: str) -> None:
    """ユーザー実績を保存（グローバル管理）"""
    achievement_service.save_user_achievement(achievement_id)


def get_user_achievements(session_id: str | None = None) -> list[UserAchievementStatus]:
    """ユーザーの解除済み実績を取得（グローバル管理）"""
    rows = achievement_service.get_user_achievements()
    unlocked_ids = {achievement_id: achieved_at for achievement_id, achieved_at in rows}

    result = []
    for achievement in ACHIEVEMENTS.values():
        result.append(
            UserAchievementStatus(
                achievement_id=achievement.id,
                unlocked=achievement.id in unlocked_ids,
                unlocked_at=unlocked_ids.get(achievement.id),
            )
        )

    return result


# =============================================================================
# API エンドポイント
# =============================================================================

router = APIRouter(prefix="/achievements", tags=["achievements"])


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
