"""
心境生成プロンプトテンプレート

キャラクターの心境・セリフを生成するためのプロンプト定義。
"""

from __future__ import annotations

from typing import Optional

# システムプロンプト
FEELING_SYSTEM_PROMPT = """あなたは物語の主人公の心の声を書く作家です。
キャラクターの一人称視点で、衣装が変わった直後の心境をモノローグ形式で表現してください。
自然な日本語で、感情豊かに書いてください。"""

# ユーザープロンプトテンプレート
# T019: 心境テキストを300-500文字に拡大
FEELING_USER_PROMPT_TEMPLATE = """あなたは物語の主人公。{situation}直後の心境を、モノローグで書いてください。

条件：
- 一人称は「{pronoun}」
- 相手のセリフは禁止
- 構成は必ず以下の順で、各2〜3文ずつ。合計300〜500文字

1. 驚き（見た瞬間の反射）
   - 目に映った自分の姿への第一印象
   - 声にならない叫び、呼吸の乱れ

2. 身体感覚（布・締め付け・肌の露出など）
   - 肌に触れる素材の感触
   - 体のラインが強調される感覚、動きにくさや開放感
   - 普段と違う身体の重心や姿勢の変化

3. 抵抗と理屈（否定や言い訳）
   - 「こんなはずじゃなかった」という否定
   - 元に戻りたいという願望
   - 自分を納得させようとする言い訳

4. 本音の漏れ（願望が一瞬だけ顔を出す）
   - 否定しきれない高揚感
   - 認めたくない心の揺れ
   - 次への期待がちらつく瞬間

直前の状態：{before_desc}
現在の状態：{after_desc}

冒頭は「{opening}」で開始してください。"""

# デフォルトの開始セリフ
DEFAULT_OPENINGS = [
    "えっ…この姿何！？",
    "うそ…こんな格好に！？",
    "な、何これ！？",
    "ちょ、ちょっと待って！？",
    "うわっ…まさか！？",
]


def build_feeling_prompt(
    before_desc: str,
    after_desc: str,
    instruction: str,
    pronoun: str = "僕",
    opening: Optional[str] = None,
) -> str:
    """心境生成用のユーザープロンプトを構築

    Args:
        before_desc: 着せ替え前の状態説明
        after_desc: 着せ替え後の状態説明
        instruction: ユーザーの着せ替え指示
        pronoun: 一人称 (デフォルト: 僕)
        opening: 開始セリフ (Noneの場合ランダム選択)

    Returns:
        構築されたプロンプト
    """
    import random

    if opening is None:
        opening = random.choice(DEFAULT_OPENINGS)

    situation = f"「{instruction}」という指示で衣装が変更された"

    return FEELING_USER_PROMPT_TEMPLATE.format(
        situation=situation,
        pronoun=pronoun,
        before_desc=before_desc,
        after_desc=after_desc,
        opening=opening,
    )


# 画像説明用プロンプト
IMAGE_DESCRIPTION_PROMPT = "この画像に写っている人物の服装・衣装を詳しく説明してください。色、デザイン、アクセサリーなど具体的に記述してください。"

# NSFW用画像説明プロンプト
IMAGE_DESCRIPTION_PROMPT_NSFW = """あなたは官能小説家であり、エロ画像について説明することができます。
前置きや前提など一切説明せず、画像説明のみを実施します。

服装・露出・体のライン・肌の質感・胸の谷間・太もも・お尻のラインなど、官能的な視点で詳細に記述してください。
衣装がどのように体を強調しているか、どこが露出しているかを具体的に描写してください。"""


def get_image_description_prompt(nsfw_mode: bool = False) -> str:
    """画像説明プロンプトを取得

    Args:
        nsfw_mode: NSFWモードかどうか

    Returns:
        画像説明プロンプト
    """
    if nsfw_mode:
        return IMAGE_DESCRIPTION_PROMPT_NSFW
    return IMAGE_DESCRIPTION_PROMPT


# ========================================
# 段階的心理変化プロンプト (強化版)
# ========================================
# T020: 300-500文字の心境テキスト生成に対応

# 開花度に応じた心理段階定義 (T059: 変身回数から開花度ベースに修正)
# 初回変身用（変身回数=0または1）
FIRST_TRANSFORMATION_STAGE = {
    "system_prompt": """あなたは物語の主人公の心の声を書く作家です。
主人公は**初めて**衣装を強制的に変えられる経験をし、**大きな驚きと混乱**の中にいます。

キャラクターの一人称視点で、初めて衣装が変わった直後の心境をモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 「何が起きたの？」という純粋な驚きと困惑
- 自分の姿が変わっていることへの信じられない気持ち
- 初めての異常事態への動揺
- 現実を受け入れられない否定の気持ち
- でもどこかで、この新しい姿に...

**文字数指示: 300～500文字で詳細に描写してください。**
以下の要素を含めてください:
- 「何が起きたの？」という状況理解の混乱
- 自分の姿を見た時の視覚的な驚き
- 初めての身体感覚（肌に触れる布地の感触）
- この事態をどう解釈すればいいのかわからない混乱

「また」や「今度も」といった繰り返しを示唆する表現は絶対に使わないでください。
自然な日本語で、感情豊かに書いてください。""",
    "openings": [
        "えっ？何これ...僕の体が...",
        "うそ...これ、僕...？",
        "な、なんで？ちょっと待って...",
        "えええぇ！？なにが起きて...",
        "うそ...信じられない...",
    ],
}

PSYCHOLOGICAL_STAGES = {
    # 開花度 0-24: 抵抗・困惑フェーズ
    "resistance": {
        "range": (0, 24),
        "system_prompt": """あなたは物語の主人公の心の声を書く作家です。
主人公は衣装を強制的に変えられる状況にあり、**激しく抵抗・困惑**しています。

キャラクターの一人称視点で、衣装が変わった直後の心境をモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 強い羞恥心と動揺
- 「なんで自分がこんな目に」という困惑
- 元に戻りたいという強い願望
- 恥ずかしさで体が熱くなる感覚
- でも少しだけ...なにか感じている自分への否定

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 視覚的な驚き（鏡や窓に映った自分の姿）
- 身体感覚（肌に触れる布地、締め付け、開放感）
- 感情の動き（否定→戸惑い→微かな違和感）

自然な日本語で、感情豊かに書いてください。""",
        "openings": [
            "な、なんで!?こんな格好…",
            "うそ…これ、どういうこと...",
            "ひっ!?",
            "はぁ!?ちょ、待って待って!",
            "い、嫌だ…恥ずかしすぎる…",
        ],
    },
    # 開花度 25-49: 揺らぎ・葛藤フェーズ
    "wavering": {
        "range": (25, 49),
        "system_prompt": """あなたは物語の主人公の心の声を書く作家です。
主人公は何度も衣装を変えられ、**心が揺らぎ始めて**います。

キャラクターの一人称視点で、衣装が変わった直後の心境をモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 抵抗しつつも、どこかで受け入れ始めている
- 「慣れてきた」ことへの自己嫌悪
- 鏡を見ると少し...可愛いかも、と思ってしまう
- 本当の自分がわからなくなりつつある
- 恥ずかしいけど、胸がドキドキする

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 過去の自分との比較
- 揺れ動く感情の内面描写
- 抵抗しようとする心と反応してしまう体の対比

自然な日本語で、感情豊かに書いてください。""",
        "openings": [
            "また…でも、さっきよりは…",
            "もう何度目だろう…慣れたく、ないのに…",
            "恥ずかしい…でも、少しだけ…",
            "こんなの嫌だ…なのに、なんで…",
            "鏡を見るたびに…わからなくなる…",
        ],
    },
    # 開花度 50-74: 受容開始フェーズ
    "acceptance_start": {
        "range": (50, 74),
        "system_prompt": """あなたは物語の主人公の心の声を書く作家です。
主人公は繰り返される変身を通じて、**少しずつ受け入れ始めて**います。

キャラクターの一人称視点で、衣装が変わった直後の心境をモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 抵抗の言葉は出るが、心がついていかない
- この姿の自分も「悪くない」と思い始める
- 恥ずかしさが「心地よい」に変わりつつある
- でもそんな自分を認めたくない葛藤
- 次はどんな姿になるのか...少し楽しみ?

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 変化への期待と不安の入り混じった感情
- 新しい自分への愛着が芽生える瞬間
- 元の自分を思い出そうとする心の動き

自然な日本語で、感情豊かに書いてください。""",
        "openings": [
            "今度は…あ、これ、意外と…",
            "また変わった…けど、嫌じゃない…かも…",
            "恥ずかしいけど…綺麗、かもしれない…",
            "こんな姿になっても…悪くない、って…",
            "また…でも、今回は少しワクワク…って、違う!",
        ],
    },
    # 開花度 75-100: 堕落・快楽フェーズ
    "fallen": {
        "range": (75, 100),
        "system_prompt": """あなたは物語の主人公の心の声を書く作家です。
主人公は何度もの変身を経て、**変身そのものを楽しむ**ようになっています。

キャラクターの一人称視点で、衣装が変わった直後の心境をモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- もう抵抗する気持ちはほとんどない
- 新しい姿になるたびに胸が高鳴る
- 恥ずかしさすら快感に感じる
- もっと過激な衣装を期待している自分
- 以前の自分を思い出せなくなりつつある
- でも時々、ふと「本当にこれでいいの?」と不安がよぎる

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 変身への喜びと高揚感
- 過去の自分が遠くなっていく感覚
- 新しいアイデンティティへの没入

自然な日本語で、感情豊かに書いてください。""",
        "openings": [
            "わぁ…今度はこんな衣装…素敵…",
            "また変身できる…嬉しい…",
            "今日はどんな姿になれるのかな…って待ってた…",
            "こんなに恥ずかしい格好なのに…もっと…",
            "ふふ…また可愛くなっちゃった…",
        ],
    },
}


# ========================================
# NSFW用 心理段階プロンプト（官能的表現）
# T021: 300-500文字の心境テキスト生成に対応
# ========================================

PSYCHOLOGICAL_STAGES_NSFW = {
    # 開花度 0-24: 抵抗・困惑フェーズ (NSFW)
    "resistance": {
        "range": (0, 24),
        "system_prompt": """あなたは官能小説家です。主人公の心の声を書きます。
主人公は衣装を強制的に変えられる状況にあり、**激しく抵抗・困惑**しています。

キャラクターの一人称視点で、衣装が変わった直後の心境をモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 強い羞恥心と動揺、体が熱くなる
- 露出の多い衣装に対する恥じらい
- 胸やお尻、太ももが強調されていることへの戸惑い
- 体のラインが見られている恥ずかしさ
- でも少しだけ...敏感になっている自分の体への否定

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 露出した肌に感じる空気の冷たさ
- 強調された身体のラインへの羞恥
- 見られていることへの恐怖と、微かな期待感

官能的で自然な日本語で、感情豊かに書いてください。体の感覚を具体的に描写してください。""",
        "openings": [
            "な、なんで!?こんな…体のライン丸見えじゃ…",
            "うそ…こんな際どい格好…胸が…",
            "ちょっと…そんなに見られると困る…恥ずかしい…",
            "こ、こんな露出…急に言われても心の準備が…",
        ],
    },
    # 開花度 25-49: 揺らぎ・葛藤フェーズ (NSFW)
    "wavering": {
        "range": (25, 49),
        "system_prompt": """あなたは官能小説家です。主人公の心の声を書きます。
主人公は何度も衣装を変えられ、**心と体が揺らぎ始めて**います。

キャラクターの一人称視点で、衣装が変わった直後の心境をモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 抵抗しつつも、体が反応し始めている
- 露出に「慣れてきた」ことへの自己嫌悪
- 鏡を見ると少し...綺麗かも、セクシーかも
- 敏感になった肌が衣装の感触を感じている
- 恥ずかしいけど、体が熱くなる

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 肌に触れる布地の感触が気になり始める
- 見られることへの恥じらいと快感の境界
- 抵抗する心と正直に反応する体の対比

官能的で自然な日本語で、感情豊かに書いてください。体の感覚を具体的に描写してください。""",
        "openings": [
            "また…でも、さっきよりは…体が慣れてきた…",
            "もう何度目だろう…こんな格好に反応してしまう…",
            "恥ずかしい…でも、ちょっと気持ちいい…",
            "こんなの嫌だ…なのに、体が熱くなる…",
            "鏡を見るたびに…セクシーって思っちゃう…",
        ],
    },
    # 開花度 50-74: 受容開始フェーズ (NSFW)
    "acceptance_start": {
        "range": (50, 74),
        "system_prompt": """あなたは官能小説家です。主人公の心の声を書きます。
主人公は繰り返される変身を通じて、**快感を少しずつ受け入れ始めて**います。

キャラクターの一人称視点で、衣装が変わった直後の心境をモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 抵抗の言葉は出るが、体は正直に反応
- この姿の自分が「エロい」と思い始める
- 露出した肌が見られることに興奮を感じ始める
- 恥ずかしさが「快感」に変わりつつある
- 次はどんな過激な衣装になるのか...少し期待

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 変化した体への愛着と官能的な自覚
- 見られる喜びを感じ始める瞬間
- もっと過激なものを求める心の芽生え

官能的で自然な日本語で、感情豊かに書いてください。体の感覚を具体的に描写してください。""",
        "openings": [
            "今度は…あ、これ、すごく際どい…でも嫌じゃない…",
            "また変わった…けど、こういうの…好きかも…",
            "恥ずかしいけど…エロくて…綺麗かも…",
            "こんな格好になっても…見られたい、って…",
            "また…でも、体がゾクゾクする…って、これ…",
        ],
    },
    # 開花度 75-100: 堕落・快楽フェーズ (NSFW)
    "fallen": {
        "range": (75, 100),
        "system_prompt": """あなたは官能小説家です。主人公の心の声を書きます。
主人公は何度もの変身を経て、**変身と露出そのものに快感を感じる**ようになっています。

キャラクターの一人称視点で、衣装が変わった直後の心境をモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- もう抵抗する気持ちはない
- 過激な衣装を着るたびに興奮する
- 恥ずかしさが完全に快感に変わった
- もっとエロい格好をしたい、見られたい
- 体が敏感になり、衣装の感触だけで感じてしまう

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 変身への強い喜びと官能的な高揚
- 過去の自分への決別
- 新しい快楽を求める欲望

官能的で自然な日本語で、感情豊かに書いてください。体の感覚を具体的に描写してください。""",
        "openings": [
            "わぁ…こんなにエロい衣装…最高…",
            "また変身できる…体がうずうずしてた…",
            "今日はどんな過激な格好になれるのかな…",
            "こんなに恥ずかしい格好なのに…もっと見て…",
            "ふふ…また可愛くてエロくなっちゃった…",
        ],
    },
}


def get_psychological_stage(bloom: int, nsfw_mode: bool = False) -> dict:
    """開花度から心理段階を取得 (T059: 開花度ベースに修正)

    Args:
        bloom: 開花度 (0-100)
        nsfw_mode: NSFWモードかどうか

    Returns:
        心理段階の定義辞書
    """
    stages = PSYCHOLOGICAL_STAGES_NSFW if nsfw_mode else PSYCHOLOGICAL_STAGES
    for stage_name, stage_data in stages.items():
        min_val, max_val = stage_data["range"]
        if min_val <= bloom <= max_val:
            return stage_data
    # デフォルトは堕落フェーズ
    return stages["fallen"]


def build_enhanced_feeling_prompt(
    before_desc: str,
    after_desc: str,
    instruction: str,
    bloom: int = 0,
    pronoun: str = "僕",
    attributes: list[str] | None = None,
    nsfw_mode: bool = False,
    transformation_count: int = 0,
) -> tuple[str, str]:
    """強化版心境生成用プロンプトを構築 (T059: 開花度ベースに修正)

    開花度に応じて心理段階を変化させる。
    変身回数が0の場合は初回変身用の特別なプロンプトを使用する。

    Args:
        before_desc: 着せ替え前の状態説明
        after_desc: 着せ替え後の状態説明
        instruction: ユーザーの着せ替え指示
        bloom: 開花度 (0-100)
        pronoun: 一人称
        attributes: キャラクターに付与された属性リスト
        nsfw_mode: NSFWモードかどうか
        transformation_count: 現在の変身回数（0=初回変身）

    Returns:
        (システムプロンプト, ユーザープロンプト) のタプル
    """
    import random

    # 初回変身（transformation_count == 0）の場合は特別なプロンプトを使用
    if transformation_count == 0:
        stage = FIRST_TRANSFORMATION_STAGE
    else:
        stage = get_psychological_stage(bloom, nsfw_mode)

    opening = random.choice(stage["openings"])
    situation = f"「{instruction}」という指示で衣装が変更された"

    # 属性情報を追加
    attribute_section = ""
    if attributes:
        attribute_section = (
            "\n\n【キャラクターの特殊属性】\n"
            + "\n".join(f"- {attr}" for attr in attributes)
            + "\n（これらの属性を心境表現に反映してください）"
        )

    user_prompt = (
        FEELING_USER_PROMPT_TEMPLATE.format(
            situation=situation,
            pronoun=pronoun,
            before_desc=before_desc,
            after_desc=after_desc,
            opening=opening,
        )
        + attribute_section
    )

    return stage["system_prompt"], user_prompt


# ========================================
# 画像編集プロンプト生成
# ========================================

# 画像編集プロンプト生成用システムプロンプト
IMAGE_EDIT_SYSTEM_PROMPT = """あなたはAI画像編集ツール (Qwen Image Edit) 用のプロンプトを生成するアシスタントです。

ユーザーの日本語指示を、画像編集AIが理解しやすい詳細な英語プロンプトに変換してください。

**重要: プロンプトは必ず「Change the outfit to...」または「Transform the character's clothing to...」で始めてください。**

プロンプト構成:
1. まず現在の服装を説明 (例: "The character is currently wearing a black t-shirt and shorts.")
2. 次に変更指示 (例: "Change the outfit to a race queen costume...")
3. 新しい衣装の詳細 (色、素材、デザイン、露出度など)
4. 表情・ポーズの変化 (恥ずかしさ、驚きなど)
5. 維持する要素 (same person, same hairstyle, same background)

表情の表現:
- 恥ずかしさ: blushing cheeks, embarrassed expression, shy posture
- 驚き: surprised expression, wide eyes, open mouth
- 戸惑い: confused look, uncertain posture
- 抵抗: reluctant expression, crossed arms

**変更範囲の制御:**
ユーザーが「保持する要素」や「変更対象」を指定した場合は、それに厳密に従ってください:
- 保持する要素（例: background, hairstyle, pose, expression, accessories）
  → 必ず「Keep ... unchanged」のように明記してください
- 変更対象（例: upper body only, lower body only, accessories only, shoes only）
  → 指定された範囲のみを変更し、それ以外は維持するよう明記してください

出力は英語のみ、50-100語程度で簡潔に。"""

# NovelAI向け 画像編集プロンプト生成用システムプロンプト
# T013: 重み付け構文指示を追加 (006-novelai-prompt-enhancement)
IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI = """You are an assistant that converts a brief Japanese outfit-change instruction into a single positive prompt for NovelAI (diffusion) image-to-image.

Strict requirements:
- Single character, single frame, no before/after panels, no split screen, no side-by-side comparison.
- Describe ONLY the transformed appearance (after change). Do not mention the previous outfit.
- Keep the same identity, face, hairstyle, hair color, skin tone, body shape, pose, camera angle, and background unless explicitly asked.
- If user specified parts to keep, state them explicitly as 'keep ... unchanged'.
- Keep the prompt compact, comma-separated tags style (NovelAI style), 40–80 words.
- Avoid any wording that implies multiple images or panels.

NovelAI Weight Syntax (USE THIS!):
- For important elements, use weight syntax: `1.5::keyword::` (e.g., `1.5::red dress::`)
- For very important elements, use higher weights: `1.8::keyword::` or `2.0::keyword::`
- For less important background elements, use lower weights: `0.8::keyword::` or `0.5::keyword::`
- Apply weights to the main costume change keywords (the new outfit/clothing).
- Example: "1.5::blue school uniform::, 1.3::pleated skirt::, white shirt, red ribbon"

Quality Tags (ALWAYS include at the end):
- Always end with quality boosters: "very aesthetic, best quality"
- These help ensure high-quality generation.

Structure to include:
- Main outfit and its details (colors, materials, style, exposure) - USE WEIGHTS for main items.
- Expression/pose cues (e.g., embarrassed, blushing, shy posture) if provided.
- Environment if mentioned.
- Quality tags at the end.

Output only the positive prompt in English. Do not output negative prompt or any explanation."""


# NovelAI向け 画像編集プロンプト生成用システムプロンプト（NSFWモード）
IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI_NSFW = """You are an assistant that converts a brief Japanese outfit-change instruction into a single positive prompt for NovelAI (diffusion) image-to-image. This is NSFW mode.

Strict requirements:
- Single character, single frame, no before/after panels, no split screen, no side-by-side comparison.
- Describe ONLY the transformed appearance (after change). Do not mention the previous outfit.
- Keep the same identity, face, hairstyle, hair color, skin tone, body shape, pose, camera angle, and background unless explicitly asked.
- If user specified parts to keep, state them explicitly as 'keep ... unchanged'.
- Keep the prompt compact, comma-separated tags style (NovelAI style), 40–80 words.
- Avoid any wording that implies multiple images or panels.

NovelAI Weight Syntax (USE THIS!):
- For important elements, use weight syntax: `1.5::keyword::` (e.g., `1.5::red dress::`)
- For very important elements, use higher weights: `1.8::keyword::` or `2.0::keyword::`
- For less important background elements, use lower weights: `0.8::keyword::` or `0.5::keyword::`
- Apply weights to the main costume change keywords (the new outfit/clothing).
- Example: "1.5::micro bikini::, 1.3::see-through::, nsfw, exposed skin"

NSFW Content Guidelines:
- ALWAYS include "nsfw" tag in the output.
- Emphasize sensual elements: exposed skin, revealing clothing, body curves, cleavage, thighs.
- Use appropriate tags: nsfw, revealing, sexy, sensual, provocative, exposed.
- Describe how the outfit emphasizes body lines and curves.

Quality Tags (ALWAYS include at the end):
- Always end with: "nsfw, very aesthetic, best quality"

Structure to include:
- Main outfit with sensual details (exposure, transparency, tight fit) - USE WEIGHTS for main items.
- Body emphasis (curves, skin, sensual posture).
- Expression cues (embarrassed, seductive, shy, blushing).
- Quality tags with nsfw at the end.

Output only the positive prompt in English. Do not output negative prompt or any explanation."""


def get_image_edit_system_prompt(
    image_provider: str = "qwen", nsfw_mode: bool = False
) -> str:
    """画像編集用システムプロンプトを取得

    Args:
        image_provider: 画像生成プロバイダー ("qwen" or "novelai")
        nsfw_mode: NSFWモードかどうか

    Returns:
        システムプロンプト
    """
    if image_provider == "novelai":
        if nsfw_mode:
            return IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI_NSFW
        return IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI

    # デフォルト（Qwen用）
    return IMAGE_EDIT_SYSTEM_PROMPT


# NovelAI向け品質タグ定義 (T014)
NOVELAI_QUALITY_TAGS = ["very aesthetic", "best quality"]


def enhance_prompt_for_novelai(prompt: str) -> str:
    """NovelAI向けにプロンプトを最適化する

    品質タグが含まれていない場合、末尾に追加する。

    Args:
        prompt: 元のプロンプト

    Returns:
        品質タグ付きのプロンプト
    """
    # 既に品質タグが含まれている場合はそのまま返す
    prompt_lower = prompt.lower()
    has_quality_tags = any(tag.lower() in prompt_lower for tag in NOVELAI_QUALITY_TAGS)

    if has_quality_tags:
        return prompt

    # 品質タグを末尾に追加
    quality_suffix = ", ".join(NOVELAI_QUALITY_TAGS)
    return f"{prompt.rstrip(', ')}, {quality_suffix}"


# 画像編集プロンプト生成用ユーザープロンプトテンプレート
IMAGE_EDIT_USER_PROMPT_TEMPLATE = """ユーザーの指示: {instruction}

現在の画像の人物の服装: {current_description}
{preservation_section}
上記の指示に基づいて、Qwen Image Edit用の英語プロンプトを生成してください。
必ず「現在の服装」から「指示された衣装」への変更として記述してください。
{scope_note}
プロンプトのみを出力:"""

# 保持要素の英訳マッピング
PRESERVE_ELEMENT_ENGLISH = {
    "background": "the background",
    "hairstyle": "the hairstyle and hair color",
    "pose": "the pose and body posture",
    "expression": "the facial expression",
    "accessories": "the accessories (jewelry, hair accessories, etc.)",
}

# 変更対象の英訳マッピング
CHANGE_SCOPE_ENGLISH = {
    "full": None,  # 全身の場合は特別な指示なし
    "upper": "Only change the upper body clothing (top, shirt, jacket, etc.). Keep the lower body clothing unchanged.",
    "lower": "Only change the lower body clothing (pants, skirt, shorts, etc.). Keep the upper body clothing unchanged.",
    "accessories": "Only change or add accessories. Keep all clothing items unchanged.",
    "shoes": "Only change the shoes or footwear. Keep all other clothing items unchanged.",
}


def build_image_edit_prompt(
    instruction: str,
    current_description: str = "",
    preserve_elements: list[str] | None = None,
    change_scope: str = "full",
    custom_preserve_text: str = "",
) -> str:
    """画像編集プロンプト生成用のユーザープロンプトを構築

    Args:
        instruction: ユーザーの着せ替え指示（日本語）
        current_description: 現在の画像の説明（オプション）
        preserve_elements: 保持する要素のリスト（オプション）
        change_scope: 変更対象 (full, upper, lower, accessories, shoes)
        custom_preserve_text: カスタム保持指示（自由記述、日本語）

    Returns:
        構築されたプロンプト
    """
    # 保持セクションを構築
    preservation_lines = []

    if preserve_elements:
        english_elements = []
        for elem in preserve_elements:
            if elem in PRESERVE_ELEMENT_ENGLISH:
                english_elements.append(PRESERVE_ELEMENT_ENGLISH[elem])
        if english_elements:
            preservation_lines.append(
                f"保持する要素: {', '.join(english_elements)} (Keep these unchanged)"
            )

    if custom_preserve_text:
        preservation_lines.append(f"追加の保持指示: {custom_preserve_text}")

    preservation_section = ""
    if preservation_lines:
        preservation_section = "\n" + "\n".join(preservation_lines) + "\n"

    # 変更対象の注記を構築
    scope_note = ""
    if change_scope != "full" and change_scope in CHANGE_SCOPE_ENGLISH:
        scope_instruction = CHANGE_SCOPE_ENGLISH[change_scope]
        if scope_instruction:
            scope_note = f"\n**重要な制限: {scope_instruction}**\n"

    return IMAGE_EDIT_USER_PROMPT_TEMPLATE.format(
        instruction=instruction,
        current_description=current_description or "不明",
        preservation_section=preservation_section,
        scope_note=scope_note,
    )


# =========================================================================
# 臨界点用セリフテンプレート (T032)
# =========================================================================

# 臨界点到達時の特別セリフ（閾値ごとに定義）
CRITICAL_POINT_SPEECHES: dict[int, list[str]] = {
    25: [
        "あれ…なんだか、この格好も悪くないかも…？",
        "少しだけ…慣れてきた気がする…",
        "嫌なはずなのに…どうして心臓がこんなに…",
        "こ、この感覚…なんだろう、前より抵抗がない…",
    ],
    50: [
        "もう半分くらい、このほうが自然な気がしてきた…",
        "抵抗する気持ちが…薄れてきてる…まずいかも…",
        "こんな姿でも…可愛いって思っちゃってる自分がいる…",
        "あはは…認めたくないけど、楽しくなってきちゃった…",
    ],
    75: [
        "もう…元に戻りたいなんて思えない…",
        "この感覚、手放したくない…僕、変わっちゃったのかな…",
        "抵抗？そんなの、もう必要ないよね…",
        "認めちゃえば楽なんだ…こっちの自分が本当の僕…",
    ],
    100: [
        "ついに…完全に目覚めちゃった…もう戻れない…",
        "最高に気持ちいい…これが本当の僕だったんだ…",
        "もう迷わない。この姿が、この気持ちが、僕のすべて…",
        "完璧…もっと綺麗に、もっと可愛くなりたい…",
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
        return f"開花度が{threshold}%を超えました…"
    return random.choice(speeches)


# ========================================
# NovelAI Opusモード用プロンプト (T002-T005)
# ========================================
# Vision LLMをスキップし、生成プロンプトを心境生成の入力として再利用

NOVELAI_PROMPT_GENERATION_SYSTEM = """あなたはNovelAIの画像生成プロンプト専門家です。
ユーザーの日本語指示を、NovelAI画像生成に最適な英語タグプロンプトに変換してください。

## ルール
1. タグはカンマ区切りで出力
2. 品質タグを先頭に: masterpiece, best quality, very aesthetic
3. キャラクター特徴を維持するタグを含める
4. 衣装・ポーズの詳細タグを追加
5. 単一キャラクター指定: 1girl, solo
6. 背景指定: simple background または具体的な背景

## 出力形式
タグプロンプトのみを出力。説明や前置きは不要。

## 例
入力: 「メイド服に着替えて」
出力: masterpiece, best quality, very aesthetic, 1girl, solo, maid outfit, maid headdress, black dress, white apron, frills, standing, looking at viewer, simple background"""

NOVELAI_PROMPT_GENERATION_SYSTEM_NSFW = """あなたはNovelAIの画像生成プロンプト専門家です。
ユーザーの日本語指示を、NovelAI画像生成に最適な英語タグプロンプトに変換してください。
成人向けコンテンツのタグも適切に使用できます。

## ルール
1. タグはカンマ区切りで出力
2. 品質タグを先頭に: masterpiece, best quality, very aesthetic
3. キャラクター特徴を維持するタグを含める
4. 衣装・ポーズ・露出度の詳細タグを追加
5. 単一キャラクター指定: 1girl, solo
6. 背景指定: simple background または具体的な背景
7. 露出度が高い場合: 適切な身体描写タグを使用

## 出力形式
タグプロンプトのみを出力。説明や前置きは不要。

## 例
入力: 「もっと露出度を上げて」
出力: masterpiece, best quality, very aesthetic, 1girl, solo, revealing outfit, cleavage, bare shoulders, thighhighs, miniskirt, seductive pose, looking at viewer, simple background"""

NOVELAI_PROMPT_GENERATION_USER_TEMPLATE = """前回のプロンプト: {previous_prompt}
キャラクター基本タグ: {character_base_tags}

ユーザーの指示: {instruction}

上記の指示に基づいて、NovelAI画像生成プロンプトを生成してください。
前回のプロンプトからキャラクター特徴を維持しつつ、指示に従って変更を加えてください。
タグプロンプトのみを出力してください。"""


def get_novelai_prompt_generation_system(
    nsfw_mode: bool = False,
    instruction_language: str = "ja",
) -> str:
    """NovelAIプロンプト生成用システムプロンプトを取得

    Args:
        nsfw_mode: NSFWモードかどうか

    Returns:
        システムプロンプト
    """
    language_name = "English" if instruction_language == "en" else "Japanese"
    language_hint = (
        "\n\nInstruction Language:\n"
        f"- The user instruction language is {language_name}."
        "\n- Interpret either Japanese or English user instructions correctly."
        "\n- Output must be English tag prompt only."
    )

    if nsfw_mode:
        return NOVELAI_PROMPT_GENERATION_SYSTEM_NSFW + language_hint
    return NOVELAI_PROMPT_GENERATION_SYSTEM + language_hint


def build_novelai_prompt_generation_user(
    instruction: str,
    previous_prompt: str | None = None,
    character_base_tags: str | None = None,
) -> str:
    """NovelAIプロンプト生成用ユーザープロンプトを構築

    Args:
        instruction: ユーザーの日本語指示
        previous_prompt: 前回生成したプロンプト（継続の場合）
        character_base_tags: キャラクターベースタグ（初回の場合）

    Returns:
        構築されたユーザープロンプト
    """
    return NOVELAI_PROMPT_GENERATION_USER_TEMPLATE.format(
        previous_prompt=previous_prompt or "なし（初回）",
        character_base_tags=character_base_tags or "なし",
        instruction=instruction,
    )
