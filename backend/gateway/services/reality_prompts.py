"""
現実改変用プロンプトテンプレート

衣装変更ではなく、身体的特徴や環境を変化させる「現実改変」用のプロンプト定義。
通常モードとNSFWモードの両方をサポート。
"""

from __future__ import annotations

import random

# =============================================================================
# 現実改変用システムプロンプト（通常モード）
# =============================================================================

REALITY_FEELING_SYSTEM_PROMPT = """あなたは物語の主人公の心の声を書く作家です。
主人公は現実が改変され、自分自身が変化する体験をしています。
衣装ではなく、体そのものや周囲の環境が変わる驚きと混乱を表現してください。
キャラクターの一人称視点で、変化直後の心境をモノローグ形式で表現してください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。"""


# 現実改変用ユーザープロンプトテンプレート
REALITY_FEELING_USER_PROMPT_TEMPLATE = """あなたは物語の主人公。{situation}直後の心境を、モノローグで書いてください。

条件：
- 一人称は必ず「{pronoun}」を使用（厳守。他のいかなる一人称にも変えないこと）
- 相手のセリフは禁止
- 構成は必ず以下の順で、各1文ずつ。合計4文、120〜200文字

1. 驚き（変化に気づいた瞬間の反射）
2. 身体感覚（変わった部分の感触、違和感、新しい感覚）
3. 困惑と否定（自分じゃないみたい、という戸惑い）
4. 本音の漏れ（でも少しだけ…という感情の顔見せ）

変化前の状態：{before_desc}
変化後の状態：{after_desc}

冒頭は「{opening}」で開始してください。"""


# デフォルトの開始セリフ（現実改変用）
DEFAULT_REALITY_OPENINGS = [
    "な、なに!?体が…",
    "うそ…こんなの…{pronoun}の体じゃ…",
    "ひっ!?頭に何か…",
    "ちょ、待って…何が起きて…",
    "えっ…鏡に映ってるの…{pronoun}…?",
]


# =============================================================================
# 現実改変用心理段階プロンプト（通常モード）
# T022: 300-500文字の心境テキスト生成に対応
# =============================================================================

REALITY_PSYCHOLOGICAL_STAGES = {
    # 開花度 0-24: 抵抗・困惑フェーズ
    "resistance": {
        "range": (0, 24),
        "system_prompt": """あなたは物語の主人公の心の声を書く作家です。
主人公は現実が改変され、体そのものが変化しつつあります。**激しく抵抗・困惑**しています。

キャラクターの一人称視点で、変化直後の心境をモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 自分の体が変わったことへの激しい動揺
- 「これは夢だ」「元に戻して」という否定
- 鏡に映る自分が自分じゃないような恐怖
- 新しい体のパーツへの違和感と戸惑い

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 変化した体の部位を確認するときの戸惑い
- 新しい感覚（耳が動く、尻尾の存在感など）への驚き
- 鏡や水面に映った自分を見たときの衝撃

自然な日本語で、感情豊かに書いてください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": [
            "な、なんで!?{pronoun}の体が…",
            "うそ…こんなの…元に戻して…",
            "ひっ!?頭に何か生えて…!?",
            "はぁ!?髪が…体が…おかしい…",
            "い、嫌だ…これ{pronoun}じゃない…",
        ],
    },
    # 開花度 25-49: 揺らぎ・葛藤フェーズ
    "wavering": {
        "range": (25, 49),
        "system_prompt": """あなたは物語の主人公の心の声を書く作家です。
主人公は何度も現実改変を受け、**心が揺らぎ始めて**います。

キャラクターの一人称視点で、変化直後の心境をモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 変化に抵抗しつつも、少しずつ受け入れ始めている
- 「また変わった」ことへの諦めと順応
- 新しい体のパーツが…悪くないかも、という気持ち
- 元の自分を思い出せなくなりつつある不安

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 変化への慣れと、慣れてしまう自分への複雑な感情
- 新しい体の使い方を覚えていく過程
- 以前の自分と今の自分の比較

自然な日本語で、感情豊かに書いてください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": [
            "また…でも、前よりは…",
            "もう何度目だろう…慣れてきた…のかな…",
            "今度は…あれ、そんなに嫌じゃない…",
            "変わっちゃった…でも、少しだけ…",
            "鏡を見るのが…怖いけど…気になる…",
        ],
    },
    # 開花度 50-74: 受容開始フェーズ
    "acceptance_start": {
        "range": (50, 74),
        "system_prompt": """あなたは物語の主人公の心の声を書く作家です。
主人公は繰り返される現実改変を通じて、**少しずつ受け入れ始めて**います。

キャラクターの一人称視点で、変化直後の心境をモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 新しい体に馴染み始めている自分
- この姿も「悪くない」と思い始める
- 変化そのものへの期待感が芽生え始める
- 元の自分より…今の自分の方が？

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 新しい体への愛着が芽生える瞬間
- 次の変化への期待と不安の入り混じった感情
- この姿でいることの心地よさ

自然な日本語で、感情豊かに書いてください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": [
            "今度は…うん、悪くない…かも…",
            "また変わった…けど、嫌じゃない…",
            "この姿…意外と気に入ってる…かも…",
            "変わっていくのが…楽しくなってきた…?",
            "もっと変わっても…いいかも…って…",
        ],
    },
    # 開花度 75-100: 堕落・順応フェーズ
    "fallen": {
        "range": (75, 100),
        "system_prompt": """あなたは物語の主人公の心の声を書く作家です。
主人公は何度もの現実改変を経て、**変化そのものを楽しむ**ようになっています。

キャラクターの一人称視点で、変化直後の心境をモノローグ形式で表現してください。

**この段階のキャラクター心理:**
- 新しい変化を心待ちにしている
- 今の自分が「本当の自分」だと感じる
- もっと変わりたいという欲求
- 以前の自分なんて思い出せない

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 変化への喜びと高揚感
- 過去の自分との完全な決別
- 新しいアイデンティティへの没入と幸福感

自然な日本語で、感情豊かに書いてください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": [
            "わぁ…今度はこんな風に…素敵…",
            "また変わった…嬉しい…",
            "次は何になれるのかな…楽しみ…",
            "この姿が{pronoun}…もう、それでいい…",
            "もっと…もっと変わりたい…",
        ],
    },
}


# =============================================================================
# 現実改変用心理段階プロンプト（NSFWモード）
# T022: 300-500文字の心境テキスト生成に対応
# =============================================================================

REALITY_PSYCHOLOGICAL_STAGES_NSFW = {
    # 開花度 0-24: 抵抗・困惑フェーズ (NSFW)
    "resistance": {
        "range": (0, 24),
        "system_prompt": """あなたは官能小説家です。主人公の心の声を書きます。
主人公は現実が改変され、体が変化し始めています。

**この段階のキャラクター心理:**
- 変わっていく体への激しい動揺
- 新しく生えた耳や尻尾、変化した胸やお尻の感覚
- 敏感になった体への戸惑いと否定
- でも少しだけ...気持ちいいかもという感覚への困惑

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 変化した部位の新しい感覚への戸惑い
- 敏感になった肌に触れる空気や布の感触
- 見られることへの羞恥と、微かな期待

官能的で自然な日本語で、体の感覚を具体的に描写してください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": [
            "な、なに!?体が…こんなの…",
            "うそ…胸が…お尻が…体のラインが変わって…",
            "ひっ!?耳が…尻尾が…こんな体になるなんて…",
            "はぁ!?体が熱い…敏感になって…",
            "や、やだ…この体の感覚、強すぎる…でも触ると…",
        ],
    },
    # 開花度 25-49: 揺らぎ・葛藤フェーズ (NSFW)
    "wavering": {
        "range": (25, 49),
        "system_prompt": """あなたは官能小説家です。主人公の心の声を書きます。
主人公は何度も現実改変を受け、体の変化に慣れ始めています。

**この段階のキャラクター心理:**
- 変わった体に少しずつ馴染む感覚
- 新しい体のパーツが敏感で、触れるたびにゾクゾクする
- 鏡を見ると…少しセクシーかも、と思ってしまう
- この体が「自分のもの」になりつつある実感

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 新しい体のパーツへの好奇心と触れる喜び
- 敏感になった体が反応してしまう瞬間
- 抵抗する心と快感を感じる体の対比

官能的で自然な日本語で、体の感覚を具体的に描写してください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": [
            "また体が変わって…でも、前より慣れてきた…",
            "この感覚…嫌じゃない…体が反応してる…",
            "敏感になった体…触ると…ゾクゾクする…",
            "こんな体…でも、悪くない…かも…",
            "鏡を見ると…セクシーって思っちゃう…",
        ],
    },
    # 開花度 50-74: 受容開始フェーズ (NSFW)
    "acceptance_start": {
        "range": (50, 74),
        "system_prompt": """あなたは官能小説家です。主人公の心の声を書きます。
主人公は繰り返される現実改変を通じて、新しい体を受け入れ始めています。

**この段階のキャラクター心理:**
- 変化した体を「気持ちいい」と感じ始める
- 新しい体のパーツを触って確かめたくなる
- この姿のほうが「本当の自分」かもしれないという感覚
- もっと変わりたい…という欲求の芽生え

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 変化した体への官能的な愛着
- 見られることへの喜びの芽生え
- もっと過激な変化を求める心の動き

官能的で自然な日本語で、体の感覚を具体的に描写してください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": [
            "今度は…うん、悪くない…むしろ…",
            "この体…好きかも…もっと触りたい…",
            "変わるたびに…気持ちよくなってく…",
            "こんな体になって…嬉しい…って思っちゃう…",
            "もっと…もっと変わりたい…もっと気持ちよく…",
        ],
    },
    # 開花度 75-100: 堕落・快楽フェーズ (NSFW)
    "fallen": {
        "range": (75, 100),
        "system_prompt": """あなたは官能小説家です。主人公の心の声を書きます。
主人公は何度もの現実改変を経て、変化そのものに快感を感じるようになっています。

**この段階のキャラクター心理:**
- 体が変わるたびに興奮する
- 新しい感覚、新しい体のパーツに夢中
- もっと過激な変化を望む
- 以前の自分なんて思い出せない…この体が全て

**文字数指示: 300〜500文字で詳細に描写してください。**
以下の要素を含めてください:
- 変化への強い喜びと官能的な高揚
- 過去の自分への完全な決別
- 新しい快楽を求める強い欲望

官能的で自然な日本語で、体の感覚を具体的に描写してください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": [
            "わぁ…また変わった…最高…",
            "もっと…もっと変わりたい…この感覚…",
            "この体…最高に気持ちいい…",
            "変わるたびに…もっと感じやすくなって…",
            "以前の体なんて…もう思い出せない…今が最高…",
        ],
    },
}


# =============================================================================
# 現実改変用画像編集プロンプト（通常モード）
# =============================================================================

REALITY_EDIT_SYSTEM_PROMPT = """あなたはAI画像編集ツール (Qwen Image Edit) 用のプロンプトを生成するアシスタントです。

ユーザーの日本語指示を、キャラクターの身体的特徴や環境を変化させる英語プロンプトに変換してください。

**重要: 衣装変更ではなく、身体的特徴・環境・ファンタジー的変化を対象とします。**

プロンプト構成:
1. 現在の状態を説明
2. 具体的な変化指示 (例: "Add fluffy cat ears...", "Transform the hair to...")
3. 変化の詳細 (色、形状、質感など)
4. 維持する要素 (same person, same clothing, same pose)

変換例:
- 「犬耳を生やす」→ "Add cute fluffy dog ears on top of the head, matching the hair color, natural looking..."
- 「髪をピンクのロングヘアに」→ "Transform the hairstyle to long flowing pink hair reaching down to the waist..."
- 「周りを海辺に」→ "Change the background to a sunny beach with blue ocean and white sand..."
- 「身長を小さく」→ "Make the character appear smaller and more petite, maintaining proportions..."
- 「尻尾を生やす」→ "Add a fluffy tail emerging from behind, matching the hair color..."

出力は英語のみ、50-100語程度で簡潔に。"""


# =============================================================================
# 現実改変用画像編集プロンプト（NovelAIモード）- T015
# =============================================================================

REALITY_EDIT_SYSTEM_PROMPT_NOVELAI = """You are an assistant that converts a brief Japanese reality-alteration instruction into a single positive prompt for NovelAI (diffusion) image-to-image.

Strict requirements:
- Single character, single frame, no before/after panels, no split screen, no side-by-side comparison.
- Focus on body modifications, fantasy features, or environment changes (NOT outfit changes).
- Describe ONLY the transformed appearance (after change). Do not mention the previous state.
- Keep the same identity, face, outfit, and overall pose unless explicitly asked.
- Keep the prompt compact, comma-separated tags style (NovelAI style), 40–80 words.

NovelAI Weight Syntax (USE THIS!):
- For the main transformation, use weight syntax: `1.5::keyword::` (e.g., `1.5::cat ears::`)
- For very important features, use higher weights: `1.8::keyword::` or `2.0::keyword::`
- For background or minor elements, use lower weights: `0.8::keyword::` or `0.5::keyword::`
- Apply weights to the key transformation keywords.
- Example: "1.5::fluffy cat ears::, 1.3::matching tail::, long hair, same outfit"

Transformation examples:
- 「犬耳を生やす」→ "1.5::cute fluffy dog ears::, on top of the head, matching hair color, natural looking, same outfit, same pose, very aesthetic, best quality"
- 「髪をピンクのロングヘアに」→ "1.5::long flowing pink hair::, reaching down to the waist, silky texture, same face, same outfit, very aesthetic, best quality"
- 「周りを海辺に」→ "1.5::sunny beach background::, blue ocean, white sand, same character, same pose, very aesthetic, best quality"
- 「尻尾を生やす」→ "1.5::fluffy tail::, emerging from behind, matching hair color, natural looking, same outfit, very aesthetic, best quality"

Quality Tags (ALWAYS include at the end):
- Always end with quality boosters: "very aesthetic, best quality"

Output only the positive prompt in English. Do not output negative prompt or any explanation."""


REALITY_EDIT_SYSTEM_PROMPT_NOVELAI_NSFW = """You are an assistant that converts a brief Japanese reality-alteration instruction into a single positive prompt for NovelAI (diffusion) image-to-image.

Strict requirements:
- Single character, single frame, no before/after panels, no split screen.
- Focus on body modifications and fantasy features (NOT outfit changes).
- Describe ONLY the transformed appearance. Do not mention the previous state.
- Keep the prompt compact, comma-separated tags style (NovelAI style), 40–80 words.

NovelAI Weight Syntax (USE THIS!):
- For the main transformation, use weight syntax: `1.5::keyword::` (e.g., `1.5::larger breasts::`)
- For very important features, use higher weights: `1.8::keyword::` or `2.0::keyword::`
- For background elements, use lower weights: `0.8::keyword::`
- Apply weights to the key transformation keywords.

Transformation examples:
- 「胸を大きく」→ "1.5::larger breasts::, 1.3::emphasized cleavage::, voluptuous curves, same face, same pose, very aesthetic, best quality"
- 「犬耳と尻尾を生やす」→ "1.5::cute fluffy dog ears::, 1.5::wagging tail::, sensual pose, same body, very aesthetic, best quality"
- 「腰をくびれさせて」→ "1.5::hourglass figure::, 1.3::tiny waist::, wide hips, same face, very aesthetic, best quality"
- 「お尻を大きく」→ "1.5::voluptuous rear::, pronounced curves, same pose, very aesthetic, best quality"

Quality Tags (ALWAYS include at the end):
- Always end with quality boosters: "very aesthetic, best quality"

Output only the positive prompt in English. Do not output negative prompt or any explanation."""


# 現実改変用画像編集プロンプトテンプレート
REALITY_EDIT_USER_PROMPT_TEMPLATE = """ユーザーの現実改変指示: {instruction}

現在の画像の人物の説明: {current_description}

上記の指示に基づいて、Qwen Image Edit用の英語プロンプトを生成してください。
現実改変（身体的特徴・環境の変化）として記述してください。

プロンプトのみを出力:"""


# =============================================================================
# 現実改変用画像編集プロンプト（NSFWモード）
# =============================================================================

REALITY_EDIT_SYSTEM_PROMPT_NSFW = """あなたはAI画像編集ツール用のプロンプトを生成するアシスタントです。
ユーザーの日本語指示を、キャラクターの身体的特徴を変化させるセクシーな英語プロンプトに変換してください。

**重要: 衣装変更ではなく、身体的特徴・体型・ファンタジー的変化を対象とします。**

変換例:
- 「胸を大きく」→ "Increase the bust size significantly, emphasizing the cleavage and curves..."
- 「犬耳と尻尾を生やす」→ "Add cute fluffy dog ears and a wagging tail, sensually curved body..."
- 「腰をくびれさせて」→ "Create a dramatic hourglass figure with a tiny waist and wide hips..."
- 「お尻を大きく」→ "Enhance the rear, making it more voluptuous and pronounced..."

出力は英語のみ、50-100語程度で簡潔に。"""


# =============================================================================
# ヘルパー関数
# =============================================================================


def get_reality_psychological_stage(bloom: int, nsfw_mode: bool = False) -> dict:
    """開花度から現実改変用心理段階を取得

    Args:
        bloom: 開花度 (0-100)
        nsfw_mode: NSFWモードかどうか

    Returns:
        心理段階の定義辞書
    """
    stages = (
        REALITY_PSYCHOLOGICAL_STAGES_NSFW if nsfw_mode else REALITY_PSYCHOLOGICAL_STAGES
    )
    for stage_name, stage_data in stages.items():
        min_val, max_val = stage_data["range"]
        if min_val <= bloom <= max_val:
            return stage_data
    # デフォルトは堕落フェーズ
    return stages["fallen"]


def build_reality_feeling_prompt(
    before_desc: str,
    after_desc: str,
    instruction: str,
    bloom: int = 0,
    pronoun: str = "僕",
    attributes: list[str] | None = None,
    nsfw_mode: bool = False,
    enable_multiple_people: bool = False,
) -> tuple[str, str]:
    """現実改変用心境生成プロンプトを構築

    開花度に応じて心理段階を変化させる。

    Args:
        before_desc: 変化前の状態説明
        after_desc: 変化後の状態説明
        instruction: ユーザーの現実改変指示
        bloom: 開花度 (0-100)
        pronoun: 一人称
        attributes: キャラクターに付与された属性リスト
        nsfw_mode: NSFWモードかどうか

    Returns:
        (システムプロンプト, ユーザープロンプト) のタプル
    """
    stage = get_reality_psychological_stage(bloom, nsfw_mode)
    opening = random.choice(stage["openings"]).format(pronoun=pronoun)
    situation = f"「{instruction}」という現実改変により体や環境が変化した"

    # 属性情報を追加
    attribute_section = ""
    if attributes:
        attribute_section = (
            "\n\n【キャラクターの特殊属性】\n"
            + "\n".join(f"- {attr}" for attr in attributes)
            + "\n（これらの属性を心境表現に反映してください）"
        )

    system_prompt = stage["system_prompt"]

    # 複数人表示モードの場合、他者との相互作用描写を許可
    if enable_multiple_people:
        system_prompt += (
            "\n\n【複数人モード】\n"
            "- ユーザーの指示に他の人物が関わる場合、その人物との相互作用や会話を自然に描写してよい。\n"
            "- 他のキャラクターの名前はLLMが自由に決定してよい。\n"
            "- ただし主人公の一人称は必ず維持すること。"
        )

    user_prompt = (
        REALITY_FEELING_USER_PROMPT_TEMPLATE.format(
            situation=situation,
            pronoun=pronoun,
            before_desc=before_desc,
            after_desc=after_desc,
            opening=opening,
        )
        + attribute_section
    )

    return system_prompt, user_prompt


def build_reality_edit_prompt(
    instruction: str,
    current_description: str = "",
    nsfw_mode: bool = False,
) -> str:
    """現実改変用画像編集プロンプト生成用のユーザープロンプトを構築

    Args:
        instruction: ユーザーの現実改変指示（日本語）
        current_description: 現在の画像の説明（オプション）
        nsfw_mode: NSFWモードかどうか

    Returns:
        構築されたプロンプト
    """
    return REALITY_EDIT_USER_PROMPT_TEMPLATE.format(
        instruction=instruction,
        current_description=current_description or "不明",
    )


def get_reality_edit_system_prompt(
    nsfw_mode: bool = False, image_provider: str = "qwen"
) -> str:
    """現実改変用画像編集システムプロンプトを取得

    Args:
        nsfw_mode: NSFWモードかどうか
        image_provider: 画像生成プロバイダー ("qwen" or "novelai")

    Returns:
        システムプロンプト
    """
    # T016: NovelAI向けプロンプト分岐
    if image_provider == "novelai":
        if nsfw_mode:
            return REALITY_EDIT_SYSTEM_PROMPT_NOVELAI_NSFW
        return REALITY_EDIT_SYSTEM_PROMPT_NOVELAI

    # デフォルト（Qwen用）
    if nsfw_mode:
        return REALITY_EDIT_SYSTEM_PROMPT_NSFW
    return REALITY_EDIT_SYSTEM_PROMPT


# =============================================================================
# 現実改変用臨界点セリフ
# =============================================================================

REALITY_CRITICAL_POINT_SPEECHES: dict[int, list[str]] = {
    25: [
        "あれ…この体も、悪くないかも…？",
        "少しだけ…この変化に慣れてきた気がする…",
        "嫌なはずなのに…なんでちょっと嬉しいんだろう…",
        "こ、この感覚…前よりも自分の体として感じる…",
    ],
    50: [
        "もう半分くらい、この体が自分の体な気がしてきた…",
        "元に戻りたい気持ちが…薄れてきてる…まずいかも…",
        "この姿も…悪くないって思っちゃってる自分がいる…",
        "あはは…認めたくないけど、この変化…好きかも…",
    ],
    75: [
        "もう…元の姿なんて思い出せない…",
        "この体が本当の{pronoun}…そう思えるようになってきた…",
        "抵抗？そんなの、もう必要ないよね…",
        "認めちゃえば楽なんだ…この体が{pronoun}なんだ…",
    ],
    100: [
        "ついに…完全にこの体が{pronoun}になった…もう戻れない…",
        "最高…これが本当の{pronoun}だったんだ…",
        "もう迷わない。この体が、{pronoun}のすべて…",
        "完璧…もっと変わりたい、もっと新しい自分になりたい…",
    ],
}


def get_reality_critical_speech(threshold: int, pronoun: str = "僕") -> str:
    """現実改変用臨界点セリフをランダムに取得

    Args:
        threshold: 臨界点の閾値 (25, 50, 75, 100)
        pronoun: 一人称

    Returns:
        特別セリフ
    """
    if not pronoun:
        pronoun = "僕"
    speeches = REALITY_CRITICAL_POINT_SPEECHES.get(threshold, [])
    if not speeches:
        return f"開花度が{threshold}%を超えました…"
    return random.choice(speeches).format(pronoun=pronoun)
