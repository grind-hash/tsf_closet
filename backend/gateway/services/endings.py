"""
エンディングモジュール

エンディング定義と判定ロジックを提供する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import SessionStats


# =============================================================================
# エンディング定義
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
    badge: str = "🎭"  # デフォルトバッジ


# 初期エンディング定義（4種類）
ENDINGS: Dict[str, Ending] = {
    "pleasure_fall": Ending(
        id="pleasure_fall",
        title="快楽開花エンド",
        description="変身を心から楽しむようになった",
        condition_text="開花度100 + 露出系変身が最多",
        final_speech="もっと…もっと変身したい…♡",
        summary="最初は恥ずかしがっていたキャラクターは、度重なる変身を経て、"
        "ついに変身そのものを心から楽しむようになりました。"
        "もはや元の姿に戻ることなど考えもせず、次の変身を心待ちにしています。",
        badge="💖",
    ),
    "self_acceptance": Ending(
        id="self_acceptance",
        title="自己受容エンド",
        description="新しい自分を受け入れた",
        condition_text="開花度100 + 可愛い系変身が最多",
        final_speech="この姿も…悪くないかも…♪",
        summary="様々な可愛らしい衣装を経験したキャラクターは、"
        "自分の新しい一面を発見し、それを受け入れることを選びました。"
        "恥ずかしさを超えて、新しい自分を楽しんでいます。",
        badge="🌸",
    ),
    "resistance_limit": Ending(
        id="resistance_limit",
        title="抵抗の限界エンド",
        description="最後まで抵抗し続けた",
        condition_text="変身5回 + 開花度50未満",
        final_speech="負けない…絶対に負けないんだから…！",
        summary="度重なる変身にも関わらず、キャラクターは最後まで抵抗し続けました。"
        "心は折れず、元の自分を守り抜くことができました。"
        "その強い意志は、どんな変身にも屈することはありませんでした。",
        badge="🛡️",
    ),
    "curiosity_explosion": Ending(
        id="curiosity_explosion",
        title="好奇心の暴走エンド",
        description="多様な変身を経験した",
        condition_text="開花度100 + 変身タイプが分散",
        final_speech="まだ見たことない衣装…試してみたい…",
        summary="様々な種類の衣装を経験したキャラクターは、"
        "変身への好奇心が止まらなくなりました。"
        "もっと色々な衣装を試してみたいという欲求が溢れています。",
        badge="✨",
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
# 判定ロジック (T012, T045, T046)
# =============================================================================

# 露出系カテゴリ（快楽堕落エンド判定用）
EXPOSURE_CATEGORIES = {"swimsuit", "underwear"}

# 可愛い系カテゴリ（自己受容エンド判定用）
CUTE_CATEGORIES = {"maid", "gothic_lolita", "dress", "cosplay"}


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


def _is_exposure_dominant(tag_counts: Dict[str, int]) -> bool:
    """露出系が最多かチェック"""
    exposure_count = sum(tag_counts.get(cat, 0) for cat in EXPOSURE_CATEGORIES)
    cute_count = sum(tag_counts.get(cat, 0) for cat in CUTE_CATEGORIES)
    other_count = sum(
        v
        for k, v in tag_counts.items()
        if k not in EXPOSURE_CATEGORIES and k not in CUTE_CATEGORIES
    )
    return exposure_count > max(cute_count, other_count)


def _is_cute_dominant(tag_counts: Dict[str, int]) -> bool:
    """可愛い系が最多かチェック"""
    exposure_count = sum(tag_counts.get(cat, 0) for cat in EXPOSURE_CATEGORIES)
    cute_count = sum(tag_counts.get(cat, 0) for cat in CUTE_CATEGORIES)
    other_count = sum(
        v
        for k, v in tag_counts.items()
        if k not in EXPOSURE_CATEGORIES and k not in CUTE_CATEGORIES
    )
    return cute_count > max(exposure_count, other_count)


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
    1. 堕落度100到達 OR 変身15回到達でエンディング判定
    2. 堕落度100 + 露出タグ最多 → 快楽堕落エンド
    3. 堕落度100 + 可愛さタグ最多 → 自己受容エンド
    4. 堕落度100 + タグ分散 → 好奇心の暴走エンド
    5. 変身15回 + 堕落度<50 → 抵抗の限界エンド

    Args:
        stats: セッション統計（堕落度等）
        transformation_count: 変身回数
        tag_counts: タグカテゴリ別の累積カウント
        achieved_ending_ids: 既に達成済みのエンディングIDリスト

    Returns:
        EndingResult: 判定結果
    """
    ending_id: Optional[str] = None

    # 開花度100到達時の判定
    if stats.bloom >= 100:
        if _is_exposure_dominant(tag_counts):
            ending_id = "pleasure_fall"
        elif _is_cute_dominant(tag_counts):
            ending_id = "self_acceptance"
        elif _is_tag_distributed(tag_counts):
            ending_id = "curiosity_explosion"
        else:
            # デフォルト: 好奇心の暴走エンド
            ending_id = "curiosity_explosion"

    # 変身15回 + 開花度50未満の判定（抵抗成功）
    elif transformation_count >= 15 and stats.bloom < 50:
        ending_id = "resistance_limit"

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
