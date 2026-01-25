"""
心境生成プロンプトテンプレート（お子様向け変身アプリ版）

キャラクターの心境・セリフを生成するためのプロンプト定義。
ポジティブでワクワクする体験を提供する。
"""

from __future__ import annotations

from typing import Optional

# システムプロンプト（子供向け）
FEELING_SYSTEM_PROMPT = """あなたは子供向け変身ストーリーの作家です。
主人公が新しい姿に変身した直後の、ワクワクした気持ちを一人称視点で表現してください。

ルール:
- ポジティブで楽しい表現を心がける
- 子供が読んでも安全な内容にする
- 変身の喜びや驚きを表現する
- 恐怖や悲しみは含めない"""

# ユーザープロンプトテンプレート（子供向け）
FEELING_USER_PROMPT_TEMPLATE = """あなたは物語の主人公。{situation}直後の気持ちを、モノローグで書いてください。

条件：
- 一人称は「{pronoun}」
- 構成は必ず以下の順で、各1文ずつ。合計4文、120〜200文字

1. 驚きと発見（変身した瞬間の反応）
2. 体の変化（新しい衣装や力を感じる）
3. ワクワク感（この姿でできそうなこと）
4. 楽しみ（変身した姿でやりたいことへの期待）

変身前：{before_desc}
変身後：{after_desc}

冒頭は「{opening}」で開始してください。
変身した姿に合った楽しみを自然に表現してください（例：おひめさまなら舞踏会、ヒーローなら人助けなど）。"""

# デフォルトの開始セリフ（子供向け）
DEFAULT_OPENINGS = [
    "わぁ！すごい！",
    "うわぁ！かっこいい！",
    "やった！へんしんできた！",
    "すごーい！これが…！",
    "わくわく！こんなすがたに！",
]


def build_feeling_prompt(
    before_desc: str,
    after_desc: str,
    instruction: str,
    pronoun: str = "ぼく",
    opening: Optional[str] = None,
) -> str:
    """心境生成用のユーザープロンプトを構築

    Args:
        before_desc: 変身前の状態説明
        after_desc: 変身後の状態説明
        instruction: ユーザーの変身指示
        pronoun: 一人称 (デフォルト: ぼく)
        opening: 開始セリフ (Noneの場合ランダム選択)

    Returns:
        構築されたプロンプト
    """
    import random

    if opening is None:
        opening = random.choice(DEFAULT_OPENINGS)

    situation = f"「{instruction}」という指示で変身した"

    return FEELING_USER_PROMPT_TEMPLATE.format(
        situation=situation,
        pronoun=pronoun,
        before_desc=before_desc,
        after_desc=after_desc,
        opening=opening,
    )


# 画像説明用プロンプト
IMAGE_DESCRIPTION_PROMPT = """この画像に写っている人物の服装・衣装を詳しく説明してください。
ヒーロー、魔法使い、冒険家などのキャラクタータイプも含めて説明してください。"""


# ========================================
# 段階的心理変化プロンプト (子供向け)
# ========================================

# ワクワク度に応じた心理段階定義
PSYCHOLOGICAL_STAGES = {
    # ワクワク度 0-24: ドキドキフェーズ
    "dokidoki": {
        "range": (0, 24),
        "system_prompt": """あなたは子供向け変身ストーリーの作家です。
主人公は初めての変身を経験し、**ドキドキしながらも期待**しています。

キャラクターの一人称視点で、変身した直後の気持ちをモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 初めての変身にびっくり
- 新しい衣装にドキドキ
- 少し緊張しているけどワクワクも
- これから何ができるか楽しみ

ポジティブで楽しい表現を心がけてください。""",
        "openings": [
            "え！？これって…！",
            "わ、わぁ…！本当に変身した…！",
            "す、すごい…！こんな姿に…！",
            "ドキドキする…！かっこいい…！",
            "びっくり！本当にへんしんできた！",
        ],
    },
    # ワクワク度 25-49: ワクワクフェーズ
    "wakuwaku": {
        "range": (25, 49),
        "system_prompt": """あなたは子供向け変身ストーリーの作家です。
主人公は変身に慣れてきて、**ワクワクが増して**います。

キャラクターの一人称視点で、変身した直後の気持ちをモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 変身が楽しくなってきた
- 新しい姿にワクワク
- いろんな変身を試してみたい
- 自分の力を試したい気持ち

ポジティブで楽しい表現を心がけてください。""",
        "openings": [
            "やった！今度はこんな姿！",
            "わくわく！かっこいい！",
            "いいね！この変身すき！",
            "おお！すごいすごい！",
            "へんしん楽しい！もっとやりたい！",
        ],
    },
    # ワクワク度 50-74: なりきりフェーズ
    "narikiri": {
        "range": (50, 74),
        "system_prompt": """あなたは子供向け変身ストーリーの作家です。
主人公は変身を完全に楽しむようになり、**キャラクターになりきって**います。

キャラクターの一人称視点で、変身した直後の気持ちをモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 変身した姿になりきっている
- その衣装のキャラクターっぽく振る舞いたい
- 自信がついてきた
- ヒーローや魔法使いとして活躍したい

ポジティブで楽しい表現を心がけてください。""",
        "openings": [
            "完璧！これが本当の姿！",
            "キマった！ヒーローみたい！",
            "最高！この姿でがんばるぞ！",
            "よし！準備OK！",
            "ふふふ、かっこよくキマった！",
        ],
    },
    # ワクワク度 75-100: ヒーローフェーズ
    "hero": {
        "range": (75, 100),
        "system_prompt": """あなたは子供向け変身ストーリーの作家です。
主人公は変身マスターになり、**どんな姿でも自信満々**です。

キャラクターの一人称視点で、変身した直後の気持ちをモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 変身に完全な自信
- どんな姿でも楽しめる
- 変身のプロフェッショナル
- みんなを助けたい・活躍したい

ポジティブで楽しい表現を心がけてください。""",
        "openings": [
            "さあ、今日も変身完了！",
            "やっぱり変身って最高！",
            "これでどんな冒険もOK！",
            "変身マスターの腕の見せ所！",
            "よーし！出動だ！",
        ],
    },
}


def get_psychological_stage(excitement: int) -> dict:
    """ワクワク度から心理段階を取得

    Args:
        excitement: ワクワク度 (0-100)

    Returns:
        心理段階の定義辞書
    """
    for stage_name, stage_data in PSYCHOLOGICAL_STAGES.items():
        min_val, max_val = stage_data["range"]
        if min_val <= excitement <= max_val:
            return stage_data
    # デフォルトはヒーローフェーズ
    return PSYCHOLOGICAL_STAGES["hero"]


def build_enhanced_feeling_prompt(
    before_desc: str,
    after_desc: str,
    instruction: str,
    excitement: int = 0,
    pronoun: str = "ぼく",
    use_kanji: bool = False,
) -> tuple[str, str]:
    """強化版心境生成用プロンプトを構築

    ワクワク度に応じて心理段階を変化させる。

    Args:
        before_desc: 変身前の状態説明
        after_desc: 変身後の状態説明
        instruction: ユーザーの変身指示
        excitement: ワクワク度 (0-100)
        pronoun: 一人称
        use_kanji: 漢字を使用するかどうか

    Returns:
        (システムプロンプト, ユーザープロンプト) のタプル
    """
    import random

    stage = get_psychological_stage(excitement)
    opening = random.choice(stage["openings"])
    situation = f"「{instruction}」という指示で変身した"

    user_prompt = FEELING_USER_PROMPT_TEMPLATE.format(
        situation=situation,
        pronoun=pronoun,
        before_desc=before_desc,
        after_desc=after_desc,
        opening=opening,
    )

    # システムプロンプトにひらがな指示を追加
    system_prompt = stage["system_prompt"]
    if not use_kanji:
        hiragana_instruction = """

【重要】
このメッセージは小さなこども向けです。
できるだけ、ひらがな・カタカナを使ってください。
かんじは使わないでください。やさしい言葉でかいてね！
「！」や「～」をつかって、わくわく感をだしてね！"""
        system_prompt = system_prompt + hiragana_instruction

    return system_prompt, user_prompt


# ========================================
# 画像編集プロンプト生成（子供向け）
# ========================================

# 画像編集プロンプト生成用システムプロンプト
IMAGE_EDIT_SYSTEM_PROMPT = """あなたはAI画像編集ツール用のプロンプトを生成するアシスタントです。
子供向けの変身アプリなので、適切で安全なプロンプトを生成してください。

ユーザーの日本語指示を、画像編集AIが理解しやすい詳細な英語プロンプトに変換してください。

**重要: プロンプトは必ず「Transform the character to...」で始めてください。**

必須の制約（安全性のため）:
- NO revealing clothing, NO swimwear, NO underwear
- Age-appropriate costumes only
- NO exaggerated body features
- Family-friendly and child-safe content

プロンプト構成:
1. 変更指示 (例: "Transform the character to a superhero...")
2. 新しい衣装の詳細 (色、素材、デザイン)
3. 表情やポーズ (heroic pose, confident smile など)
4. 維持する要素 (same person, same hairstyle, same background)

出力は英語のみ、50-100語程度で簡潔に。"""

# 画像編集プロンプト生成用ユーザープロンプトテンプレート
IMAGE_EDIT_USER_PROMPT_TEMPLATE = """ユーザーの指示: {instruction}

現在の画像の人物の服装: {current_description}

上記の指示に基づいて、子供向け変身アプリ用の英語プロンプトを生成してください。
安全性ガイドラインを必ず守ってください。

プロンプトのみを出力:"""


def build_image_edit_prompt(
    instruction: str,
    current_description: str = "",
) -> str:
    """画像編集プロンプト生成用のユーザープロンプトを構築

    Args:
        instruction: ユーザーの変身指示（日本語）
        current_description: 現在の画像の説明（オプション）

    Returns:
        構築されたプロンプト
    """
    return IMAGE_EDIT_USER_PROMPT_TEMPLATE.format(
        instruction=instruction,
        current_description=current_description or "不明",
    )


# =========================================================================
# 臨界点用セリフテンプレート（子供向け - 成長・達成）
# =========================================================================

# 臨界点到達時の特別セリフ（閾値ごとに定義）
CRITICAL_POINT_SPEECHES: dict[int, list[str]] = {
    25: [
        "へんしんって楽しいかも！",
        "なんだかワクワクしてきた！",
        "もっといろんな姿になりたい！",
        "この調子でがんばるぞ！",
    ],
    50: [
        "だいぶ慣れてきた！上手になったかも！",
        "へんしんマスターへの道、半分まできた！",
        "どんな姿でも楽しくなってきた！",
        "自分でもびっくり！こんなにできるなんて！",
    ],
    75: [
        "もうどんな変身もへっちゃらだ！",
        "ぼく（わたし）、変身の達人になれそう！",
        "みんなを守れるヒーローになれるかも！",
        "すごい！こんなに成長できるなんて！",
    ],
    100: [
        "やった！変身マスターになった！",
        "最高！どんな姿にもなれる！",
        "これで何でもできる気がする！",
        "みんなを助けに行くぞ！出動！",
    ],
}


def get_critical_speech(threshold: int) -> str:
    """臨界点用の特別セリフをランダムに取得

    Args:
        threshold: 臨界点の閾値 (25, 50, 75, 100)

    Returns:
        特別セリフ
    """
    import random

    speeches = CRITICAL_POINT_SPEECHES.get(threshold, [])
    if not speeches:
        return f"ワクワク度が{threshold}%になった！すごい！"
    return random.choice(speeches)


# =========================================================================
# アニメ風子供画像変換プロンプト
# =========================================================================

ANIME_CHILD_CONVERSION_PROMPT = """Transform this photo into an anime-style illustration of a child character.

Requirements:
- Anime/manga art style with big expressive eyes
- Age-appropriate, cute, and friendly appearance
- Bright and colorful design
- Keep the general features and expression from the original
- Child-safe and family-friendly

Style: Modern anime, similar to children's animation
Output: Full-body or portrait as appropriate"""
