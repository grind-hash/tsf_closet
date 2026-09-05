"""実績システム - 実績定義（カタログ）と判定ロジック。

DB アクセスは achievement_service に委ね、ここでは実績の定義・検索・判定だけを持つ。
routes/achievements_router.py と services/game_service.py の両方から使う。
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from .achievement_service import achievement_service


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
ACHIEVEMENTS: dict[str, Achievement] = {
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
    # Self-mode reality alter achievements
    "self_reality_first": Achievement(
        id="self_reality_first",
        name="自分の現実を変える",
        description="自分モードで初めて現実改変を行った",
        category="self",
        icon="🌊",
        condition_type="count",
        condition_target="self_reality_alter",
        condition_value=1,
        hint="自分モードで現実改変を試してみましょう",
    ),
    "self_reality_10": Achievement(
        id="self_reality_10",
        name="自分だけの世界",
        description="自分モードで現実改変を10回行った",
        category="self",
        icon="🌠",
        condition_type="count",
        condition_target="self_reality_alter",
        condition_value=10,
        hint="自分モードで現実改変を重ねましょう",
    ),
    # Self-mode action achievements
    "self_action_first": Achievement(
        id="self_action_first",
        name="自分で行動する",
        description="自分モードで初めて行動を行った",
        category="self",
        icon="🏃",
        condition_type="count",
        condition_target="self_action",
        condition_value=1,
        hint="自分モードで行動を試してみましょう",
    ),
    "self_action_10": Achievement(
        id="self_action_10",
        name="行動派の自分",
        description="自分モードで行動を10回行った",
        category="self",
        icon="⚡",
        condition_type="count",
        condition_target="self_action",
        condition_value=10,
        hint="自分モードで積極的に行動しましょう",
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


def get_global_stats() -> AchievementStats:
    """
    全セッション通算の累積統計を取得

    Returns:
        累積されたSessionStats
    """
    stats = achievement_service.get_global_stats()
    return AchievementStats(**stats)


# =============================================================================
# 実績判定ロジック
# =============================================================================


@dataclass
class UserAchievementStatus:
    """ユーザーの実績状態"""

    achievement_id: str
    unlocked: bool
    unlocked_at: str | None = None


class AchievementStats(BaseModel):
    """セッション統計（判定用）"""

    transform_count: int = 0
    crossdress_count: int = 0
    reality_alter_count: int = 0
    gallery_count: int = 0
    self_transform_count: int = 0
    self_reality_alter_count: int = 0
    self_action_count: int = 0
    bloom: int = 0
    shame: int = 0
    adaptation: int = 0
    has_gender_change: bool = False


def check_achievement(achievement: Achievement, stats: AchievementStats) -> bool:
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
        elif target == "self_reality_alter":
            return stats.self_reality_alter_count >= achievement.condition_value
        elif target == "self_action":
            return stats.self_action_count >= achievement.condition_value
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
    session_id: str, stats: AchievementStats, already_unlocked: set[str]
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
