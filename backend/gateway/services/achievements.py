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
    category: str  # カテゴリ (transform, crossdress, reality, collection, self, salon)
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
    "request_first": Achievement(
        id="request_first",
        name="願いを叶える",
        description="依頼モードで初めてキャラクターの依頼を達成した",
        category="transform",
        icon="💌",
        condition_type="count",
        condition_target="request_fulfilled",
        condition_value=1,
        hint="依頼モードで、キャラクターの願いを着せ替えで叶えてみましょう",
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
    # サロン経営: 期の決算(期の最終週の締め)で判定する。黒字は期末の現金 − 期首の現金
    # (1 期目は開業資金)で、難易度による開業資金の差が出ないようにする
    "salon_first_season": Achievement(
        id="salon_first_season",
        name="初めての決算",
        description="サロン経営で、倒産せずに期を終えた",
        category="salon",
        icon="📒",
        condition_type="count",
        condition_target="salon_completed",
        condition_value=1,
        hint="サロン経営で、1期を倒産せずに乗り切りましょう(4週でも12週でも)",
    ),
    "salon_success": Achievement(
        id="salon_success",
        name="黒字経営",
        description="サロン経営で、期首より多くの現金を残して期を終えた",
        category="salon",
        icon="💰",
        condition_type="count",
        condition_target="salon_success",
        condition_value=1,
        hint="お客様の願いを叶えて、期首より多くの現金を残しましょう",
    ),
    "salon_success_hard": Achievement(
        id="salon_success_hard",
        name="敏腕オーナー",
        description="経営の難易度「むずかしい」で、サロン経営の期を黒字で終えた",
        category="salon",
        icon="👑",
        condition_type="count",
        condition_target="salon_hard_success",
        condition_value=1,
        hint="開業資金の少ない「むずかしい」で、黒字を目指しましょう",
    ),
    "salon_profit_30": Achievement(
        id="salon_profit_30",
        name="繁盛店",
        description="サロン経営で、1期に黒字30万円以上を残した",
        category="salon",
        icon="🌹",
        condition_type="threshold",
        condition_target="salon_best_profit",
        condition_value=300_000,
        hint="多くのお客様の願いを叶えて、黒字を伸ばしましょう",
    ),
    "salon_profit_50": Achievement(
        id="salon_profit_50",
        name="名店の誉れ",
        description="サロン経営で、1期に黒字50万円以上を残した",
        category="salon",
        icon="💎",
        condition_type="threshold",
        condition_target="salon_best_profit",
        condition_value=500_000,
        hint="評判を上げて、チップと常連の指名料で売上を伸ばしましょう",
    ),
    "salon_profit_100": Achievement(
        id="salon_profit_100",
        name="街の評判店",
        description="サロン経営で、1期に黒字100万円以上を残した",
        category="salon",
        icon="🏛️",
        condition_type="threshold",
        condition_target="salon_best_profit",
        condition_value=1_000_000,
        hint="12週の期で、半分以上のお客様の願いを叶え続けましょう",
    ),
    "salon_profit_200": Achievement(
        id="salon_profit_200",
        name="伝説のサロン",
        description="サロン経営で、1期に黒字200万円以上を残した",
        category="salon",
        icon="🌟",
        condition_type="threshold",
        condition_target="salon_best_profit",
        condition_value=2_000_000,
        hint="予約を断らず、ほとんどのお客様の願いを叶えると届きます",
    ),
}


def _hakoniwa(
    achievement_id: str,
    name: str,
    description: str,
    icon: str,
    condition_type: str,
    condition_target: str,
    condition_value: int,
    hint: str,
) -> Achievement:
    return Achievement(
        id=achievement_id,
        name=name,
        description=description,
        category="hakoniwa",
        icon=icon,
        condition_type=condition_type,
        condition_target=condition_target,
        condition_value=condition_value,
        hint=hint,
    )


# AI箱庭の観察記録(すべての世界を通して数える)。アイコンは記号の文字
HAKONIWA_ACHIEVEMENTS: tuple[Achievement, ...] = (
    _hakoniwa(
        "hakoniwa_first_day",
        "初めての日",
        "AI箱庭で、初めて1日を進めた",
        "◇",
        "count",
        "hakoniwa_day",
        2,
        "「1日進める」を押してみましょう",
    ),
    _hakoniwa(
        "hakoniwa_day_7",
        "一週間の観察",
        "AI箱庭のどこかの世界で、7日目に到達した",
        "◆",
        "count",
        "hakoniwa_day",
        7,
        "同じ世界で日を重ねてみましょう",
    ),
    _hakoniwa(
        "hakoniwa_day_30",
        "一ヶ月の観察",
        "AI箱庭のどこかの世界で、30日目に到達した",
        "◈",
        "count",
        "hakoniwa_day",
        30,
        "ひとつの世界を長く見守ってみましょう",
    ),
    _hakoniwa(
        "hakoniwa_events_10",
        "見届けた日々・10",
        "AI箱庭で、出来事を10件見届けた",
        "✎",
        "count",
        "hakoniwa_events",
        10,
        "日を進めて出来事を見届けましょう",
    ),
    _hakoniwa(
        "hakoniwa_events_50",
        "見届けた日々・50",
        "AI箱庭で、出来事を50件見届けた",
        "✐",
        "count",
        "hakoniwa_events",
        50,
        "さらに日を重ねてみましょう",
    ),
    _hakoniwa(
        "hakoniwa_all_rules",
        "掟の蒐集家",
        "AI箱庭で、すべての既定の掟を一度は有効にした",
        "§",
        "specific",
        "hakoniwa_all_rules",
        1,
        "5枚の既定の掟を、それぞれ一度は有効にしてみましょう",
    ),
    _hakoniwa(
        "hakoniwa_custom_rule",
        "立法者",
        "AI箱庭で、初めて自作の掟を作った",
        "¶",
        "specific",
        "hakoniwa_custom_rule",
        1,
        "掟タブで、自分だけの掟を書いてみましょう",
    ),
    _hakoniwa(
        "hakoniwa_first_transform",
        "初めての変身",
        "AI箱庭で、初めて住民を変身させた",
        "✧",
        "count",
        "hakoniwa_transforms",
        1,
        "住民タブの「その場で変身」を試してみましょう",
    ),
    _hakoniwa(
        "hakoniwa_transform_5",
        "変身の常連",
        "AI箱庭で、住民を5回変身させた",
        "✦",
        "count",
        "hakoniwa_transforms",
        5,
        "いろいろな姿に変身させてみましょう",
    ),
    _hakoniwa(
        "hakoniwa_dress_all",
        "ドレスの観客",
        "AI箱庭で、ある世界の住民全員のドレス姿を見た",
        "♢",
        "specific",
        "hakoniwa_dress_all",
        1,
        "ドレスの掟を有効にしてみましょう",
    ),
    _hakoniwa(
        "hakoniwa_swap",
        "入れ替わりの朝",
        "AI箱庭で、入れ替わりを体験した",
        "⇄",
        "specific",
        "hakoniwa_swap",
        1,
        "入れ替わりの朝を有効にしてみましょう",
    ),
    _hakoniwa(
        "hakoniwa_affinity_close",
        "親密な二人",
        "AI箱庭で、いずれかの二人の好感度が「親密」に達した",
        "♡",
        "threshold",
        "hakoniwa_affinity",
        30,
        "同じ二人の出来事を重ねてみましょう",
    ),
    _hakoniwa(
        "hakoniwa_favorites_5",
        "お気に入りの棚",
        "AI箱庭で、お気に入りの出来事を5件集めた",
        "☆",
        "count",
        "hakoniwa_favorites",
        5,
        "年代記の☆で、気に入った出来事を残しましょう",
    ),
    _hakoniwa(
        "hakoniwa_new_world",
        "新しい世界",
        "AI箱庭で、2つ目の世界を作った",
        "○",
        "count",
        "hakoniwa_worlds",
        2,
        "別の顔ぶれで、もうひとつ世界を作ってみましょう",
    ),
    _hakoniwa(
        "hakoniwa_dissonance_stirring",
        "ざわめきの始まり",
        "AI箱庭で、世界の違和感が「ざわめき」に達した",
        "∴",
        "threshold",
        "hakoniwa_dissonance",
        20,
        "掟の切り替えや変身で、世界を書き換えてみましょう",
    ),
    _hakoniwa(
        "hakoniwa_dissonance_probing",
        "真実への接近",
        "AI箱庭で、世界の違和感が「探り合い」に達した",
        "∵",
        "threshold",
        "hakoniwa_dissonance",
        50,
        "書き換えを重ねると、住民たちが調べ始めます",
    ),
    _hakoniwa(
        "hakoniwa_dissonance_confrontation",
        "書き手への呼びかけ",
        "AI箱庭で、住民たちが書き手へ呼びかける「対面」に到達した",
        "※",
        "count",
        "hakoniwa_confrontations",
        1,
        "違和感が80に達すると、何かが起きます",
    ),
)
ACHIEVEMENTS.update({item.id: item for item in HAKONIWA_ACHIEVEMENTS})


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
    request_fulfilled_count: int = 0
    salon_completed_count: int = 0
    salon_success_count: int = 0
    salon_hard_success_count: int = 0
    salon_best_profit: int = 0
    bloom: int = 0
    shame: int = 0
    adaptation: int = 0
    has_gender_change: bool = False
    # AI箱庭(すべての世界を通して)
    hakoniwa_max_day: int = 0
    hakoniwa_event_count: int = 0
    hakoniwa_transform_count: int = 0
    hakoniwa_confrontation_count: int = 0
    hakoniwa_favorite_count: int = 0
    hakoniwa_world_count: int = 0
    hakoniwa_max_affinity: int = 0
    hakoniwa_max_dissonance: int = 0
    hakoniwa_all_rules: bool = False
    hakoniwa_custom_rule: bool = False
    hakoniwa_dress_all: bool = False
    hakoniwa_swap: bool = False


# AI箱庭の観察記録: 条件対象 -> 判定に使う統計
_HAKONIWA_COUNTS = {
    "hakoniwa_day": "hakoniwa_max_day",
    "hakoniwa_events": "hakoniwa_event_count",
    "hakoniwa_transforms": "hakoniwa_transform_count",
    "hakoniwa_confrontations": "hakoniwa_confrontation_count",
    "hakoniwa_favorites": "hakoniwa_favorite_count",
    "hakoniwa_worlds": "hakoniwa_world_count",
    "hakoniwa_affinity": "hakoniwa_max_affinity",
    "hakoniwa_dissonance": "hakoniwa_max_dissonance",
}
_HAKONIWA_FLAGS = {
    "hakoniwa_all_rules": "hakoniwa_all_rules",
    "hakoniwa_custom_rule": "hakoniwa_custom_rule",
    "hakoniwa_dress_all": "hakoniwa_dress_all",
    "hakoniwa_swap": "hakoniwa_swap",
}


def check_achievement(achievement: Achievement, stats: AchievementStats) -> bool:
    """単一の実績条件をチェック"""
    target = achievement.condition_target
    if target in _HAKONIWA_COUNTS:
        return int(getattr(stats, _HAKONIWA_COUNTS[target])) >= (
            achievement.condition_value
        )
    if target in _HAKONIWA_FLAGS:
        return bool(getattr(stats, _HAKONIWA_FLAGS[target]))
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
        elif target == "request_fulfilled":
            return stats.request_fulfilled_count >= achievement.condition_value
        elif target == "salon_completed":
            return stats.salon_completed_count >= achievement.condition_value
        elif target == "salon_success":
            return stats.salon_success_count >= achievement.condition_value
        elif target == "salon_hard_success":
            return stats.salon_hard_success_count >= achievement.condition_value
    elif achievement.condition_type == "threshold":
        target = achievement.condition_target
        if target == "bloom":
            return stats.bloom >= achievement.condition_value
        elif target == "shame":
            return stats.shame >= achievement.condition_value
        elif target == "adaptation":
            return stats.adaptation >= achievement.condition_value
        elif target == "salon_best_profit":
            return stats.salon_best_profit >= achievement.condition_value
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
