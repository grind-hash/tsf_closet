"""
変身タグ分類モジュール

変身指示テキストからルールベースで3軸タグを判定する。
- 衣装カテゴリ (costume_category)
- 露出度 (exposure_level)
- 年齢印象 (age_impression)
"""

from __future__ import annotations

from dataclasses import dataclass

# =============================================================================
# タグ定義
# =============================================================================

# 衣装カテゴリの列挙値
COSTUME_CATEGORIES = [
    "swimsuit",  # 水着
    "uniform",  # 制服
    "maid",  # メイド
    "gothic_lolita",  # ゴスロリ
    "sports",  # スポーツ
    "dress",  # ドレス
    "underwear",  # 下着
    "cosplay",  # コスプレ
    "other",  # その他
]

# 露出度の列挙値
EXPOSURE_LEVELS = ["high", "medium", "low"]

# 年齢印象の列挙値
AGE_IMPRESSIONS = ["child", "student", "adult", "unknown"]


# =============================================================================
# キーワードマッチングルール
# =============================================================================

TAG_RULES: dict[str, dict[str, list[str]]] = {
    "costume_category": {
        "swimsuit": [
            "水着",
            "ビキニ",
            "スクール水着",
            "競泳水着",
            "ワンピース水着",
            "ハイレグ",
            "マイクロビキニ",
            "モノキニ",
            "タンキニ",
            "トライアングルビキニ",
            "bikini",
            "swimsuit",
            "one-piece swimsuit",
        ],
        "uniform": [
            "制服",
            "セーラー服",
            "ブレザー",
            "学生服",
            "学ラン",
            "セーラー",
            "学園",
            "学校",
            "高校制服",
            "中学制服",
            "オフィス制服",
            "事務服",
            "office uniform",
            "school uniform",
        ],
        "maid": [
            "メイド",
            "メイド服",
            "給仕服",
            "メイドさん",
            "クラシカルメイド",
            "フレンチメイド",
            "ヴィクトリアンメイド",
            "maid",
        ],
        "gothic_lolita": [
            "ゴスロリ",
            "ゴシック",
            "ロリータ",
            "ゴシックロリータ",
            "甘ロリ",
            "クラロリ",
            "ロリィタ",
            "ゴス",
            "ロリ",
            "gothic lolita",
            "lolita",
        ],
        "sports": [
            "体操服",
            "ブルマ",
            "ジャージ",
            "ユニフォーム",
            "レオタード",
            "スポーツ",
            "トレーニングウェア",
            "スポブラ",
            "テニスウェア",
            "陸上ウェア",
            "チア",
            "チアリーダー",
            "バレーボール",
            "バスケユニ",
            "ランニング",
            "gym wear",
            "sportswear",
            "athletic wear",
        ],
        "dress": [
            "ドレス",
            "ウェディング",
            "イブニング",
            "パーティードレス",
            "ワンピース",
            "カクテルドレス",
            "ロングドレス",
            "プリンセスドレス",
            "礼服",
            "フォーマル",
            "和服",
            "着物",
            "振袖",
            "袴",
            "チャイナ服",
            "旗袍",
            "qipao",
            "dress",
            "onepiece",
            "wedding dress",
        ],
        "underwear": [
            "下着",
            "ランジェリー",
            "ブラ",
            "パンツ",
            "パンティ",
            "ショーツ",
            "ブラジャー",
            "キャミ",
            "スリップ",
            "ガーターベルト",
            "ボディストッキング",
            "テディ",
            "ビスチェ",
            "補正下着",
            "インナー",
            "lingerie",
            "underwear",
        ],
        "cosplay": [
            "コスプレ",
            "魔法少女",
            "レースクイーン",
            "バニー",
            "バニーガール",
            "アイドル",
            "ナース",
            "巫女",
            "チャイナドレス",
            "女医",
            "警官",
            "婦警",
            "軍服",
            "パイロット",
            "CA",
            "キャビンアテンダント",
            "スチュワーデス",
            "秘書",
            "くノ一",
            "忍者",
            "侍",
            "サキュバス",
            "天使",
            "悪魔",
            "ヴァンパイア",
            "花魁",
            "チャイナ",
            "cosplay",
            "costume",
        ],
    },
    "exposure_level": {
        "high": [
            "水着",
            "ビキニ",
            "下着",
            "裸",
            "セクシー",
            "過激",
            "際どい",
            "露出",
            "ミニ",
            "超ミニ",
            "マイクロ",
            "紐",
            "透け",
            "シースルー",
            "網",
            "網タイツ",
            "ハイレグ",
            "胸元",
            "谷間",
            "へそ出し",
            "背中開き",
            "大胆",
            "boob",
            "cleavage",
            "revealing",
            "skimpy",
        ],
        "medium": [
            "制服",
            "メイド",
            "スポーツ",
            "体操服",
            "レオタード",
            "ミニスカ",
            "ショートパンツ",
            "タイト",
            "ボディコン",
            "チア",
            "チャイナ",
            "コスプレ",
            "fitted",
        ],
        "low": [
            "ドレス",
            "和服",
            "着物",
            "コート",
            "ロング",
            "フルレングス",
            "カバー",
            "控えめ",
            "厚手",
            "露出少なめ",
            "きっちり",
            "長袖",
            "ローブ",
            "マント",
            "modest",
            "conservative",
        ],
    },
    "age_impression": {
        "child": [
            "幼女",
            "子供",
            "小学生",
            "ロリ",
            "幼い",
            "ちっちゃい",
            "園児",
            "ランドセル",
            "キッズ",
            "child",
            "loli",
        ],
        "student": [
            "制服",
            "学生",
            "高校生",
            "中学生",
            "セーラー",
            "JK",
            "女子高生",
            "学園",
            "スクール",
            "JD",
            "女子大生",
            "teen",
            "school",
        ],
        "adult": [
            "OL",
            "社会人",
            "大人",
            "セクシー",
            "お姉さん",
            "熟女",
            "アダルト",
            "人妻",
            "秘書",
            "キャリアウーマン",
            "マダム",
            "adult",
            "mature",
        ],
    },
}


# =============================================================================
# 分類結果データクラス
# =============================================================================


@dataclass
class TransformationTags:
    """変身タグの分類結果"""

    costume_category: str
    exposure_level: str
    age_impression: str


# =============================================================================
# 分類ロジック (T011, T021)
# =============================================================================


def _match_keywords(text: str, keywords: list[str]) -> bool:
    """テキストにキーワードが含まれるかチェック"""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _classify_costume_category(instruction: str) -> str:
    """衣装カテゴリを分類する"""
    rules = TAG_RULES["costume_category"]

    # 優先度順にチェック（より具体的なカテゴリを先に）
    priority_order = [
        "underwear",
        "swimsuit",
        "maid",
        "gothic_lolita",
        "cosplay",
        "sports",
        "uniform",
        "dress",
    ]

    for category in priority_order:
        keywords = rules.get(category, [])
        if _match_keywords(instruction, keywords):
            return category

    return "other"


def _classify_exposure_level(instruction: str) -> str:
    """露出度を分類する"""
    rules = TAG_RULES["exposure_level"]

    # 高 → 低の順でチェック
    if _match_keywords(instruction, rules["high"]):
        return "high"
    if _match_keywords(instruction, rules["low"]):
        return "low"
    if _match_keywords(instruction, rules["medium"]):
        return "medium"

    # 衣装カテゴリから推測
    costume = _classify_costume_category(instruction)
    if costume in ["underwear", "swimsuit"]:
        return "high"
    if costume in ["dress"]:
        return "low"

    return "medium"


def _classify_age_impression(instruction: str) -> str:
    """年齢印象を分類する"""
    rules = TAG_RULES["age_impression"]

    if _match_keywords(instruction, rules["child"]):
        return "child"
    if _match_keywords(instruction, rules["adult"]):
        return "adult"
    if _match_keywords(instruction, rules["student"]):
        return "student"

    # 衣装カテゴリから推測
    costume = _classify_costume_category(instruction)
    if costume == "uniform":
        return "student"
    if costume == "gothic_lolita":
        return "child"

    return "unknown"


def classify_tags(instruction: str) -> TransformationTags:
    """変身指示テキストからタグを分類する。

    Args:
        instruction: 変身指示テキスト（例: 「水着に変身」）

    Returns:
        TransformationTags: 3軸タグの分類結果
    """
    return TransformationTags(
        costume_category=_classify_costume_category(instruction),
        exposure_level=_classify_exposure_level(instruction),
        age_impression=_classify_age_impression(instruction),
    )
