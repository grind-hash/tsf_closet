"""
エンディングモジュール（お子様向け変身アプリ版）

エンディング定義と判定ロジックを提供する。
性別中立で、すべての子供が楽しめるエンディング。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import SessionStats


# =============================================================================
# エンディング定義（子供向け・性別中立）
# =============================================================================


@dataclass(frozen=True)
class Ending:
    """エンディング定義"""

    id: str
    title: str
    description: str
    condition_text: str
    final_speech: str
    summary: str


# 子供向けエンディング定義（4種類・性別中立）
ENDINGS: Dict[str, Ending] = {
    "super_hero": Ending(
        id="super_hero",
        title="スーパーヒーローエンド",
        description="たくさんのヒーロー変身を経験した",
        condition_text="ワクワク度100 + ヒーロー系変身が最多",
        final_speech="みんなを守るヒーローになるぞ！",
        summary="たくさんのヒーローに変身したキミは、"
        "本物のスーパーヒーローになりました！"
        "これからもみんなを守るために活躍してね！",
    ),
    "magic_master": Ending(
        id="magic_master",
        title="マスターまほうつかいエンド",
        description="魔法使いの道を極めた",
        condition_text="ワクワク度100 + 魔法使い系変身が最多",
        final_speech="どんな魔法も使えるようになった！",
        summary="たくさんの魔法使いに変身したキミは、"
        "最高の魔法使いマスターになりました！"
        "これからもすてきな魔法で世界を明るくしてね！",
    ),
    "adventurer": Ending(
        id="adventurer",
        title="だいぼうけんかエンド",
        description="たくさんの冒険スタイルを経験した",
        condition_text="変身15回 + ワクワク度50未満を維持",
        final_speech="どんな冒険も怖くない！",
        summary="いろんな冒険者スタイルを試したキミは、"
        "どんな場所でも活躍できる大冒険家になりました！"
        "これからもわくわくする冒険に出かけてね！",
    ),
    "transformation_master": Ending(
        id="transformation_master",
        title="へんしんマスターエンド",
        description="いろんな変身を楽しんだ",
        condition_text="ワクワク度100 + 変身タイプが分散",
        final_speech="どんな姿にもなれるぞ！",
        summary="たくさんの種類の変身を楽しんだキミは、"
        "最高の変身マスターになりました！"
        "これからもいろんな姿に変身して楽しんでね！",
    ),
}


# =============================================================================
# 判定結果
# =============================================================================


@dataclass
class EndingResult:
    """エンディング判定結果"""

    triggered: bool
    ending_id: Optional[str] = None
    ending: Optional[Ending] = None
    is_new: bool = False  # 初達成かどうか


# =============================================================================
# 判定ロジック
# =============================================================================

# ヒーロー系カテゴリ
HERO_CATEGORIES = {"hero", "warrior", "ninja", "sports"}

# 魔法使い・ファンタジー系カテゴリ
MAGIC_CATEGORIES = {"wizard", "fantasy", "fairy", "magical"}

# 冒険家系カテゴリ
ADVENTURE_CATEGORIES = {"adventure", "explorer", "space", "animal"}


def get_dominant_category(tag_counts: Dict[str, int]) -> Optional[str]:
    """タグ累積から最多カテゴリを算出する。

    Args:
        tag_counts: タグカテゴリ別の累積カウント

    Returns:
        最多カテゴリ名、または分散している場合はNone
    """
    if not tag_counts:
        return None

    max_count = max(tag_counts.values())
    if max_count == 0:
        return None

    max_categories = [k for k, v in tag_counts.items() if v == max_count]

    # 複数のカテゴリが同数なら分散とみなす
    if len(max_categories) > 1:
        return None

    return max_categories[0]


def _is_hero_dominant(tag_counts: Dict[str, int]) -> bool:
    """ヒーロー系が最多かチェック"""
    hero_count = sum(tag_counts.get(cat, 0) for cat in HERO_CATEGORIES)
    magic_count = sum(tag_counts.get(cat, 0) for cat in MAGIC_CATEGORIES)
    adventure_count = sum(tag_counts.get(cat, 0) for cat in ADVENTURE_CATEGORIES)
    return hero_count > max(magic_count, adventure_count)


def _is_magic_dominant(tag_counts: Dict[str, int]) -> bool:
    """魔法使い系が最多かチェック"""
    hero_count = sum(tag_counts.get(cat, 0) for cat in HERO_CATEGORIES)
    magic_count = sum(tag_counts.get(cat, 0) for cat in MAGIC_CATEGORIES)
    adventure_count = sum(tag_counts.get(cat, 0) for cat in ADVENTURE_CATEGORIES)
    return magic_count > max(hero_count, adventure_count)


def _is_tag_distributed(tag_counts: Dict[str, int]) -> bool:
    """タグが分散しているかチェック（3カテゴリ以上使用）"""
    used_categories = sum(1 for v in tag_counts.values() if v > 0)
    return used_categories >= 3


def judge_ending(
    stats: "SessionStats",
    transformation_count: int,
    tag_counts: Dict[str, int],
    achieved_ending_ids: List[str],
) -> EndingResult:
    """エンディング判定を行う。

    判定条件:
    1. ワクワク度100到達 OR 変身15回到達でエンディング判定
    2. ワクワク度100 + ヒーロータグ最多 → スーパーヒーローエンド
    3. ワクワク度100 + 魔法使いタグ最多 → マスター魔法使いエンド
    4. ワクワク度100 + タグ分散 → 変身マスターエンド
    5. 変身15回 + ワクワク度<50 → 大冒険家エンド

    Args:
        stats: セッション統計（ワクワク度等）
        transformation_count: 変身回数
        tag_counts: タグカテゴリ別の累積カウント
        achieved_ending_ids: 既に達成済みのエンディングIDリスト

    Returns:
        EndingResult: 判定結果
    """
    ending_id: Optional[str] = None

    # ワクワク度を取得
    excitement = stats.excitement

    # ワクワク度100到達時の判定
    if excitement >= 100:
        if _is_hero_dominant(tag_counts):
            ending_id = "super_hero"
        elif _is_magic_dominant(tag_counts):
            ending_id = "magic_master"
        elif _is_tag_distributed(tag_counts):
            ending_id = "transformation_master"
        else:
            # デフォルト: 変身マスターエンド
            ending_id = "transformation_master"

    # 変身15回 + ワクワク度50未満の判定（冒険家エンド）
    elif transformation_count >= 15 and excitement < 50:
        ending_id = "adventurer"

    # エンディング未到達
    if ending_id is None:
        return EndingResult(triggered=False)

    # エンディング情報を取得
    ending = ENDINGS.get(ending_id)
    if ending is None:
        return EndingResult(triggered=False)

    # 初達成かどうか
    is_new = ending_id not in achieved_ending_ids

    return EndingResult(
        triggered=True,
        ending_id=ending_id,
        ending=ending,
        is_new=is_new,
    )
