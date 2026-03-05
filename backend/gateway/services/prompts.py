"""
心境生成プロンプトテンプレート

キャラクターの心境・セリフを生成するためのプロンプト定義。
"""

from __future__ import annotations

from typing import Optional

# システムプロンプト
FEELING_SYSTEM_PROMPT = """あなたは物語の主人公の心の声を書く作家です。
キャラクターの一人称視点で、衣装が変わった直後の心境をモノローグ形式で表現してください。
自然な日本語で、感情豊かに書いてください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。"""

# ユーザープロンプトテンプレート
# T019: 心境テキストを300-500文字に拡大
FEELING_USER_PROMPT_TEMPLATE = """あなたは物語の主人公。{situation}直後の心境を、モノローグで書いてください。

条件：
- 一人称は必ず「{pronoun}」を使用（厳守。他のいかなる一人称にも変えないこと）
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
自然な日本語で、感情豊かに書いてください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
    "openings": {
        "default": [
            "えっ？何これ...{pronoun}の体が...",
            "うそ...これ、{pronoun}...？",
            "な、なんで？ちょっと待って...",
            "えええぇ！？なにが起きて...",
            "うそ...信じられない...",
            "は？え？ちょっと...何が...",
            "な、何が起きたの...{pronoun}の姿が...",
            "嘘でしょ...こんなの聞いてない...",
            "え、え、え...どうして...",
            "待って...これって...本当に{pronoun}...？",
        ],
        "bold": [
            "はぁ！？何だよこれ...！",
            "ちょっと！勝手に何してくれてんの！？",
            "ふざけんな...{pronoun}の体を何だと...",
            "おい...これはどういう冗談だ...",
            "何してくれてんだ...ったく...！",
        ],
        "gentle": [
            "あ...あれ...{pronoun}、どうなって...",
            "え...これは...夢、かしら...",
            "ふぇ...な、何が起きたのかな...",
            "あわわ...{pronoun}の姿が...",
            "ど、どうしましょう...こんなことに...",
        ],
        "cheerful": [
            "えっ！何これ！？すっごいびっくり！",
            "うわわわ！{pronoun}の体が変わってる！？",
            "ちょ、何これ！マジで！？",
            "え、え、えーー！こんなことあるの！？",
            "びっくりした！{pronoun}、変わっちゃった！？",
        ],
        "shy": [
            "ひっ...{pronoun}の体が...変...",
            "え...あの...{pronoun}...どうして...",
            "こ、こんな...恥ずかしい...",
            "う...うそ...{pronoun}、こんな姿に...",
            "だ、誰にも見られたくない...",
        ],
    },
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

自然な日本語で、感情豊かに書いてください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": {
            "default": [
                "な、なんで!?こんな格好…",
                "うそ…これ、どういうこと...",
                "ひっ!?",
                "はぁ!?ちょ、待って待って!",
                "い、嫌だ…恥ずかしすぎる…",
                "やめて...こんなの着たくない...",
                "なんでこんな格好に...信じられない...",
                "誰かに見られたらどうするの...",
                "こんなの...{pronoun}じゃない...",
                "お願い...元に戻して...",
            ],
            "bold": [
                "はぁ!?ふざけんな、こんな格好!",
                "ちょっと！何させようとしてんの！",
                "こんな服、{pronoun}には合わないっての！",
                "誰がこんなの着るかよ...!",
                "脱がせろ...今すぐ！",
            ],
            "gentle": [
                "あ...あの...こんな格好は...",
                "ど、どうしよう...こんなことに...",
                "恥ずかしい...見ないでほしい...",
                "え...{pronoun}、こんな格好になっちゃって...",
                "困ります...こんなの...",
            ],
            "cheerful": [
                "え、ちょ、何この格好！？",
                "うわ！こんな服になっちゃった！？",
                "はは...ちょっとびっくりしすぎて...",
                "マジで！？こんなの着てるの！？",
                "いやいやいや！これはちょっと...！",
            ],
            "shy": [
                "ひっ...こ、こんな格好...",
                "み、見ないで...お願い...",
                "は、恥ずかしい...消えたい...",
                "う...うぅ...どうして{pronoun}が...",
                "こ、こんなの...無理...",
            ],
        },
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

自然な日本語で、感情豊かに書いてください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": {
            "default": [
                "また…でも、さっきよりは…",
                "もう何度目だろう…慣れたく、ないのに…",
                "恥ずかしい…でも、少しだけ…",
                "こんなの嫌だ…なのに、なんで…",
                "鏡を見るたびに…わからなくなる…",
                "また変わった...でも前ほど驚かない…",
                "少しだけ...ドキドキしてる自分がいる…",
                "嫌なはずなのに…体が慣れてきてる…",
                "こんな{pronoun}、知らなかった…",
                "否定したいのに…心が揺れてる…",
            ],
            "bold": [
                "ちっ...また着替えか...慣れたくないのに...",
                "何度やっても腹立つ...でも、少しだけ...",
                "認めないからな...こんなの...",
                "はー...もういい加減にしてくれ...",
                "悔しい...{pronoun}の負けじゃないからな...",
            ],
            "gentle": [
                "また...でも、大丈夫...かな...",
                "少しだけ...慣れてきた気がする...",
                "こういう姿も...悪くないのかな...",
                "ふふ...ちょっとだけ、綺麗かも...",
                "不思議...前より恥ずかしくない...",
            ],
            "cheerful": [
                "お、また変わった！今度は何かな！",
                "あれ？なんか前より平気かも！",
                "うーん...正直ちょっと楽しくなってきた？",
                "またか！でもまぁ...悪くないかも！",
                "はは...慣れてきちゃったかな！",
            ],
            "shy": [
                "うぅ...また...でも、少しだけ...",
                "恥ずかしい...けど、前よりは...",
                "見ないで...でも...ちょっとだけ...",
                "何度も...{pronoun}、変わっていくの...",
                "慣れたく...ないのに...体は...",
            ],
        },
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

自然な日本語で、感情豊かに書いてください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": {
            "default": [
                "今度は…あ、これ、意外と…",
                "また変わった…けど、嫌じゃない…かも…",
                "恥ずかしいけど…綺麗、かもしれない…",
                "こんな姿になっても…悪くない、って…",
                "また…でも、今回は少しワクワク…って、違う!",
                "認めちゃおうかな...この姿も{pronoun}だって...",
                "ちょっと...好きかもしれない、この感じ...",
                "鏡の中の{pronoun}、思ったより...素敵...",
                "もう抵抗する気持ち...薄れてきちゃった...",
                "こういうの、案外{pronoun}に似合うのかも...",
            ],
            "bold": [
                "ふん...悪くないじゃん、この格好...",
                "認めてやるよ...ちょっとだけ似合ってる...",
                "はー...{pronoun}って意外とこういうの向いてんのかもな...",
                "もう抵抗するのも面倒...素直に楽しむか...",
                "ま...嫌いではないかも...この姿...",
            ],
            "gentle": [
                "ふふ...これも{pronoun}なんだって...思えてきたの...",
                "受け入れちゃってもいいのかな...",
                "こういう{pronoun}も...いいのかもしれないね...",
                "穏やかな気持ち...不思議...嫌じゃないの...",
                "少しずつ...好きになってきたかも...",
            ],
            "cheerful": [
                "お！今回のいいじゃん！結構好きかも！",
                "あはは！もう楽しくなってきちゃった！",
                "わー！今度のは可愛い！ねー！",
                "うんうん、{pronoun}こういうの似合うかも！",
                "テンション上がってきた！次も楽しみ！",
            ],
            "shy": [
                "あ...あの...これ...悪くない...かも...",
                "ちょっとだけ...{pronoun}、好き...かも...",
                "恥ずかしいけど...綺麗って思っちゃった...",
                "認めるの恥ずかしいけど...似合ってる...？",
                "うぅ...こんな気持ちになるなんて...",
            ],
        },
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

自然な日本語で、感情豊かに書いてください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": {
            "default": [
                "わぁ…今度はこんな衣装…素敵…",
                "また変身できる…嬉しい…",
                "今日はどんな姿になれるのかな…って待ってた…",
                "こんなに恥ずかしい格好なのに…もっと…",
                "ふふ…また可愛くなっちゃった…",
                "もっと{pronoun}を変えて…もっと綺麗に…",
                "この感覚...{pronoun}はもう戻れない…",
                "最高...こんな衣装が似合う{pronoun}になったんだ…",
                "次は何かな…楽しみでたまらない…",
                "変わるたびに{pronoun}はもっと{pronoun}らしくなる…",
            ],
            "bold": [
                "ふん、もっといいのないの？もっと過激なやつ！",
                "いいね...{pronoun}こういうの好きだよ...！",
                "もう遠慮はいらない...どんとこい！",
                "もっとだ！もっと{pronoun}を変えろ！",
                "はは！最高だな...この感覚！",
            ],
            "gentle": [
                "ふふ…また新しい{pronoun}に出会えた…",
                "嬉しい…こんな素敵な姿に…",
                "もう{pronoun}はこの姿が大好き…",
                "穏やかに受け入れられる…幸せ…",
                "変わっていく{pronoun}が…好き…",
            ],
            "cheerful": [
                "やったー！また変身！テンション上がる！",
                "わーい！今度のも可愛い！最高！",
                "楽しい楽しい！もっとやろ！",
                "ふふふ！{pronoun}もう止まらないよ！",
                "いえーい！どんどん可愛くなっちゃうね！",
            ],
            "shy": [
                "あ…嬉しい…また変われる…",
                "恥ずかしいけど…嬉しいの…もっと…",
                "こっそり鏡を覗くの…好きになっちゃった…",
                "誰にも言えないけど…{pronoun}、幸せ…",
                "うぅ…でも…もっと見てほしい…",
            ],
        },
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

官能的で自然な日本語で、感情豊かに書いてください。体の感覚を具体的に描写してください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": {
            "default": [
                "な、なんで!?こんな…体のライン丸見えじゃ…",
                "うそ…こんな際どい格好…胸が…",
                "ちょっと…そんなに見られると困る…恥ずかしい…",
                "こ、こんな露出…急に言われても心の準備が…",
                "や、やだ...こんな格好...体が丸見え...",
                "ひっ...こんなに肌が出てる...",
                "お願い...見ないで...恥ずかしすぎる...",
                "こんな際どい服...{pronoun}には刺激が強すぎ...",
                "肌に空気が...こんなに露出してるなんて...",
                "は、恥ずかしい...体のラインが全部...",
            ],
            "bold": [
                "はぁ!?こんなエロい格好させて何のつもり！",
                "ちょっと！こんな露出...どういうつもりだ！",
                "ふざけんな...{pronoun}の体で遊ぶんじゃない！",
                "こんな際どい服...{pronoun}が着るわけ...！",
                "脱がせろ...こんな恥ずかしい格好...！",
            ],
            "gentle": [
                "あ...あの...こんなに露出が...",
                "恥ずかしい...肌がこんなに...",
                "え...こんな際どいの...{pronoun}には...",
                "ど、どうしよう...体のラインが全部...",
                "お肌が...冷たい空気を感じちゃう...",
            ],
            "cheerful": [
                "えっ！ちょ、これすごくない！？露出すご！",
                "うわっ！こんなセクシーな服！？",
                "はは...さすがにこれはびっくり...胸が...",
                "マジで！？こんな際どいの着ちゃうの！？",
                "あはは...でもちょっとドキドキする...",
            ],
            "shy": [
                "ひっ...こ、こんな...肌が見えすぎ...",
                "み、見ないで...裸みたいで...",
                "う...うぅ...こんなエロい格好...",
                "恥ずかしくて死にそう...体が...",
                "だ、誰か助けて...こんな姿...",
            ],
        },
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

官能的で自然な日本語で、感情豊かに書いてください。体の感覚を具体的に描写してください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": {
            "default": [
                "また…でも、さっきよりは…体が慣れてきた…",
                "もう何度目だろう…こんな格好に反応してしまう…",
                "恥ずかしい…でも、ちょっと気持ちいい…",
                "こんなの嫌だ…なのに、体が熱くなる…",
                "鏡を見るたびに…セクシーって思っちゃう…",
                "肌に触れる布地の感触が...気になって...",
                "見られることに...少し慣れてきた自分が怖い...",
                "前より恥ずかしくない...なんで...体が...",
                "こんな格好でドキドキするなんて...{pronoun}...",
                "嫌なはずなのに...体がぞくぞくする...",
            ],
            "bold": [
                "ちっ...また際どい格好か...でも体は...",
                "悔しいけど...慣れてきたのは認める...",
                "ふん...こんなの{pronoun}にはまだまだ刺激が足りない...",
                "はー...もう好きにしろ...体は正直に反応してる...",
                "何度やっても腹立つ...でも肌がゾクゾクする...",
            ],
            "gentle": [
                "また...でも、体が少し受け入れてる...",
                "不思議...前より恥ずかしくない...肌が...",
                "こういう感覚...嫌じゃないのかも...",
                "肌に触れる空気が...気持ちいい...",
                "ふふ...{pronoun}の体、意外と綺麗かも...",
            ],
            "cheerful": [
                "あれ？体が慣れてきた？意外と平気かも！",
                "うーん...正直に言うとちょっと気持ちいいかも！",
                "はは...肌に触れる感触、悪くないかも！",
                "あ、体が反応してる...でも嫌じゃない！",
                "おお！前より全然恥ずかしくない！成長！？",
            ],
            "shy": [
                "うぅ...また...でも体が...少し...",
                "恥ずかしい...けど前ほどじゃない...怖い...",
                "肌が...敏感になってる...こんなの...",
                "見られてる...のに...体が...熱い...",
                "{pronoun}の体...変わってきてる...感じ方が...",
            ],
        },
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

官能的で自然な日本語で、感情豊かに書いてください。体の感覚を具体的に描写してください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": {
            "default": [
                "今度は…あ、これ、すごく際どい…でも嫌じゃない…",
                "また変わった…けど、こういうの…好きかも…",
                "恥ずかしいけど…エロくて…綺麗かも…",
                "こんな格好になっても…見られたい、って…",
                "また…でも、体がゾクゾクする…って、これ…",
                "もう隠す必要ないかも...こんなに綺麗なら...",
                "この露出...{pronoun}の体を見せたいって思ってる...",
                "恥ずかしいのが気持ちよくなってきた...",
                "こういう{pronoun}も...いいのかも...体は正直...",
                "エロいけど...好き...この感覚...",
            ],
            "bold": [
                "ふん...もっと際どいのでもいいよ？",
                "いいね...{pronoun}のこういう姿、悪くない...",
                "はは...もう恥ずかしがるのはやめた...",
                "見せてやるよ...{pronoun}の本当の姿...",
                "もっと攻めてこいよ...受けて立つ...",
            ],
            "gentle": [
                "ふふ...こういうの...好きになっちゃった...",
                "体が喜んでる...{pronoun}、感じちゃって...",
                "恥ずかしいけど...嬉しい...見てほしい...",
                "優しく触れられたら...もっと...",
                "綺麗って...思ってくれるかな...",
            ],
            "cheerful": [
                "わー！これエロい！でも好き！",
                "あはは！もう開き直っちゃった！いいじゃん！",
                "すごいドキドキする！でも楽しい！",
                "{pronoun}って意外とセクシーかも！ね！",
                "体が反応してるのが自分でわかる！面白い！",
            ],
            "shy": [
                "恥ずかしいけど...見てほしい...の...",
                "こんなこと言えないけど...好き...この感覚...",
                "{pronoun}の体...綺麗って...思っちゃった...",
                "うぅ...でも...もっと見せたい...",
                "秘密にしてね...{pronoun}、感じてるの...",
            ],
        },
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

官能的で自然な日本語で、感情豊かに書いてください。体の感覚を具体的に描写してください。

**一人称ルール（厳守）**: ユーザープロンプトで指定された一人称を必ず使ってください。「僕」「俺」「私」など勝手に変えてはいけません。""",
        "openings": {
            "default": [
                "わぁ…こんなにエロい衣装…最高…",
                "また変身できる…体がうずうずしてた…",
                "今日はどんな過激な格好になれるのかな…",
                "こんなに恥ずかしい格好なのに…もっと見て…",
                "ふふ…また可愛くてエロくなっちゃった…",
                "もっと脱がせて…もっと見せたい…",
                "体が疼く…もっと過激にして…",
                "この快感…{pronoun}はもう止まれない…",
                "エロいのが好き…{pronoun}の本性…",
                "もっともっと…{pronoun}を変えて…染めて…",
            ],
            "bold": [
                "もっとだ！もっとエロくしろ！",
                "ふん、この程度じゃ{pronoun}は満足しないよ？",
                "いいね…もっと過激なの、見せてやるよ…",
                "はは！最高だ！{pronoun}の体、こんなにエロいなんて！",
                "全部脱がせてもいいよ？{pronoun}は怖くない！",
            ],
            "gentle": [
                "ふふ…また素敵な{pronoun}に…嬉しい…",
                "体が喜んでる…{pronoun}、幸せ…",
                "もっと綺麗にして…もっと感じさせて…",
                "こんなに気持ちいいの…嬉しくて涙が…",
                "大好き…この感覚…ずっと{pronoun}でいたい…",
            ],
            "cheerful": [
                "やったー！今日のもエロい！最高！",
                "わーい！もっとやろ！楽しい！",
                "あはは！{pronoun}ってこんなにセクシーだったんだ！",
                "テンション上がる！もっともっと！",
                "いえーい！エロ可愛い{pronoun}最高！",
            ],
            "shy": [
                "あ…嬉しい…また…{pronoun}を…見て…",
                "恥ずかしいけど…もっと…お願い…",
                "こっそり…もっと過激なの…着たい…",
                "誰にも言えないけど…{pronoun}、こういうの好き…",
                "うぅ…でも…もっと見てほしいの…",
            ],
        },
    },
}


# ========================================
# 性格タイプ判定 (R-010 準拠)
# ========================================

PERSONALITY_TYPE_KEYWORDS: dict[str, list[str]] = {
    "bold": ["気が強い", "強気", "勝ち気", "ツンデレ", "反抗的", "攻撃的"],
    "gentle": ["おっとり", "穏やか", "優しい", "温厚", "おとなしい", "控えめ"],
    "cheerful": ["明るい", "元気", "活発", "陽気", "楽天的", "テンション高い"],
    "shy": ["恥ずかしがり", "内気", "臆病", "人見知り", "引っ込み思案"],
    "calm": [
        "冷静",
        "クール",
        "落ち着いた",
        "理知的",
        "淡々とした",
        "クールビューティー",
    ],
    "passionate": ["情熱的", "熱い", "一生懸命", "全力", "アツい", "燃える"],
}


def classify_personality_type(
    personality: str = "",
    description: str = "",
) -> str:
    """Personality and description text from keyword matching to determine personality type.

    Args:
        personality: Character personality text
        description: Character description text

    Returns:
        Personality type key (bold/gentle/cheerful/shy/calm/passionate/default)
    """
    combined = f"{personality} {description}"
    if not combined.strip():
        return "default"

    best_type = "default"
    best_count = 0
    for ptype, keywords in PERSONALITY_TYPE_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in combined)
        if count > best_count:
            best_count = count
            best_type = ptype
    return best_type


def select_opening(
    openings: dict[str, list[str]] | list[str],
    personality_type: str = "default",
    pronoun: str = "僕",
    used_openings: list[str] | None = None,
) -> str:
    """Select an opening line based on personality type with dedup logic.

    Supports both the old flat-list format and the new dict-by-personality format.

    Args:
        openings: Either a flat list of strings (legacy) or a dict keyed by
            personality type (default/bold/gentle/cheerful/shy/calm/passionate).
        personality_type: Personality type key from classify_personality_type().
        pronoun: First-person pronoun to substitute into {pronoun} templates.
        used_openings: List of recently used opening lines (already formatted)
            to avoid repetition.

    Returns:
        A selected opening line with {pronoun} substituted.
    """
    import random

    # Build candidate pool
    if isinstance(openings, dict):
        pool = list(openings.get("default", []))
        if personality_type != "default" and personality_type in openings:
            pool.extend(openings[personality_type])
    else:
        pool = list(openings)

    if not pool:
        return f"えっ…{pronoun}の姿が…"

    # Format all candidates with pronoun first for dedup comparison
    formatted_pool = [o.format(pronoun=pronoun) for o in pool]

    # Deduplicate against used_openings
    if used_openings:
        available = [fp for fp in formatted_pool if fp not in used_openings]
        if available:
            return random.choice(available)
        # All used — reset and pick from full pool

    return random.choice(formatted_pool)


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
    personality: str = "",
    description: str = "",
    used_openings: list[str] | None = None,
) -> tuple[str, str]:
    """Build an enhanced feeling prompt with psychological stage and personality.

    Selects the psychological stage from bloom, picks an opening via
    personality-based routing with dedup, and injects character personality
    into the system prompt when provided.

    Args:
        before_desc: Description before outfit change
        after_desc: Description after outfit change
        instruction: User outfit change instruction
        bloom: Bloom value (0-100)
        pronoun: First-person pronoun
        attributes: Character attribute list
        nsfw_mode: Whether NSFW mode is enabled
        transformation_count: Current transformation count (0 = first time)
        personality: Character personality text
        description: Character description text
        used_openings: Recently used opening lines for dedup

    Returns:
        (system_prompt, user_prompt) tuple
    """
    # 初回変身（transformation_count == 0）の場合は特別なプロンプトを使用
    if transformation_count == 0:
        stage = FIRST_TRANSFORMATION_STAGE
    else:
        stage = get_psychological_stage(bloom, nsfw_mode)

    personality_type = classify_personality_type(personality, description)
    opening = select_opening(
        openings=stage["openings"],
        personality_type=personality_type,
        pronoun=pronoun,
        used_openings=used_openings,
    )
    situation = f"「{instruction}」という指示で衣装が変更された"

    # Build system prompt with optional personality section (R-002)
    system_prompt = stage["system_prompt"]
    if personality:
        truncated = personality[:500] if len(personality) > 500 else personality
        personality_section = f"\n\n【このキャラクターの性格】\n- 性格: {truncated}\n"
        if description:
            desc_truncated = (
                description[:500] if len(description) > 500 else description
            )
            personality_section += f"- 説明: {desc_truncated}\n"
        personality_section += "- このキャラクターの性格特性に合わせて、語調・反応・思考パターンを調整してください。"
        system_prompt += personality_section

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

    return system_prompt, user_prompt


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
        "この感覚、手放したくない…{pronoun}、変わっちゃったのかな…",
        "抵抗？そんなの、もう必要ないよね…",
        "認めちゃえば楽なんだ…こっちの自分が本当の{pronoun}…",
    ],
    100: [
        "ついに…完全に目覚めちゃった…もう戻れない…",
        "最高に気持ちいい…これが本当の{pronoun}だったんだ…",
        "もう迷わない。この姿が、この気持ちが、{pronoun}のすべて…",
        "完璧…もっと綺麗に、もっと可愛くなりたい…",
    ],
}


def get_critical_speech(threshold: int, pronoun: str = "僕") -> str:
    """Get a random special speech for a critical point.

    Args:
        threshold: Critical point threshold (25, 50, 75, 100)
        pronoun: First-person pronoun for template substitution

    Returns:
        Special speech text with pronoun applied
    """
    import random

    if not pronoun:
        pronoun = "僕"

    speeches = CRITICAL_POINT_SPEECHES.get(threshold, [])
    if not speeches:
        return f"開花度が{threshold}%を超えました…"
    speech = random.choice(speeches)
    return speech.format(pronoun=pronoun)


# ========================================
# NovelAI Opusモード用プロンプト (T002-T005)
# ========================================
# Vision LLMをスキップし、生成プロンプトを心境生成の入力として再利用

NOVELAI_PROMPT_GENERATION_SYSTEM = """You are a NovelAI image generation prompt expert.
Convert the user's instruction into an optimal English tag prompt for NovelAI image generation.

## Rules
1. Output **valid JSON only** with two keys: "character" and "scene".
2. "character": comma-separated English Danbooru-style tags for the MAIN CHARACTER (and others if the instruction involves them).
   - **Single-person scene** (default for outfit changes): Start with 1girl or 1boy, solo.
   - **Multi-person scene** (if the instruction explicitly involves another person): Use appropriate count tags (e.g. 1boy 1girl, 2girls). Do NOT use "solo".
     - Include minimal tags for the other person AFTER the main character's tags.
   - ALWAYS KEEP immutable traits from the previous prompt: hair color/style, eye color, body type, face features.
   - UPDATE clothing/outfit tags to match the instruction.
   - Add pose and expression tags appropriate for the outfit.
   - If the instruction implies a gender/body transformation (e.g. TSF), reflect it in the gender tag and body features.
   - Do NOT include background or environment tags here.
3. "scene": comma-separated English tags for background/environment ONLY.
   - Quality tags first: masterpiece, best quality, very aesthetic
   - Background: simple background or a specific scene matching the context.
   - Do NOT include character appearance tags here.

## CRITICAL
- ALL output tags must be in **English** Danbooru tag format. No Japanese text.
- Immutable traits (hair, eyes, body type) are NEVER changed unless the instruction explicitly transforms them.
- Mutable traits (clothing, pose, expression, accessories) are updated per the instruction.

## Output Format
```json
{"character": "1girl, solo, long black hair, blue eyes, maid outfit, ...", "scene": "masterpiece, best quality, very aesthetic, simple background"}
```
JSON only. No explanation or preamble."""

NOVELAI_PROMPT_GENERATION_SYSTEM_NSFW = """You are a NovelAI image generation prompt expert.
Convert the user's instruction into an optimal English tag prompt for NovelAI image generation.
Adult content tags are allowed.

## Rules
1. Output **valid JSON only** with two keys: "character" and "scene".
2. "character": comma-separated English Danbooru-style tags for the MAIN CHARACTER (and others if the instruction involves them).
   - **Single-person scene** (default for outfit changes): Start with 1girl or 1boy, solo.
   - **Multi-person scene** (if the instruction explicitly involves another person): Use appropriate count tags (e.g. 1boy 1girl, 2girls). Do NOT use "solo".
     - Include minimal tags for the other person AFTER the main character's tags.
     - Clearly depict physical interaction using appropriate Danbooru tags.
   - ALWAYS KEEP immutable traits from the previous prompt: hair color/style, eye color, body type, face features.
   - UPDATE clothing/outfit/exposure tags to match the instruction.
   - Add pose and expression tags appropriate for the outfit.
   - For high exposure: use appropriate body description tags.
   - If the instruction implies a gender/body transformation (e.g. TSF), reflect it in the gender tag and body features.
   - Do NOT include background or environment tags here.
3. "scene": comma-separated English tags for background/environment ONLY.
   - Quality tags first: masterpiece, best quality, very aesthetic
   - Background: simple background or a specific scene matching the context.
   - Scene can have sensual or intimate atmosphere if appropriate.
   - Do NOT include character appearance tags here.

## CRITICAL
- ALL output tags must be in **English** Danbooru tag format. No Japanese text.
- Immutable traits (hair, eyes, body type) are NEVER changed unless the instruction explicitly transforms them.
- Mutable traits (clothing, pose, expression, accessories, exposure) are updated per the instruction.

## Output Format
```json
{"character": "1girl, solo, long black hair, blue eyes, revealing outfit, ...", "scene": "masterpiece, best quality, very aesthetic, simple background"}
```
JSON only. No explanation or preamble."""

NOVELAI_PROMPT_GENERATION_USER_TEMPLATE = """Previous prompt: {previous_prompt}

User instruction: {instruction}

Generate a NovelAI image generation prompt based on the above instruction.
Maintain character features from the previous prompt while applying changes per the instruction.
IMPORTANT: If the instruction does NOT mention moving to a different location, KEEP the same location/environment tags from the previous prompt's "scene" field. Only change the location if the instruction explicitly says to go somewhere new.
Choose 1boy or 1girl based on the character's current appearance (which may change if the instruction implies transformation).
Output valid JSON with "character" and "scene" keys only."""


def get_novelai_prompt_generation_system(
    nsfw_mode: bool = False,
    instruction_language: str = "ja",
) -> str:
    """NovelAIプロンプト生成用システムプロンプトを取得

    Args:
        nsfw_mode: NSFWモードかどうか
        instruction_language: ユーザー指示の言語

    Returns:
        システムプロンプト文字列
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
) -> str:
    """NovelAIプロンプト生成用ユーザープロンプトを構築

    Args:
        instruction: ユーザーの指示
        previous_prompt: 前回生成したプロンプト（継続の場合）

    Returns:
        構築されたユーザープロンプト文字列
    """
    return NOVELAI_PROMPT_GENERATION_USER_TEMPLATE.format(
        previous_prompt=previous_prompt or "None (first time)",
        instruction=instruction,
    )


# ── Base tags generation from character description ──

BASE_TAGS_GENERATION_SYSTEM = """You are an expert at converting character descriptions into Danbooru-style tags for NovelAI image generation.

Given a character's description (name, gender, appearance, personality), generate a concise set of English Danbooru tags that accurately represent the character's VISUAL appearance.

## Rules
1. Output ONLY comma-separated English Danbooru tags. No JSON, no explanation.
2. Focus on VISUAL traits only:
   - Hair: color, length, style (e.g. short black hair, long brown hair, twintails)
   - Eyes: color (e.g. blue eyes, brown eyes)
   - Body: type if mentioned (e.g. slim, muscular, petite)
   - Clothing: current outfit (e.g. white t-shirt, school uniform, black shorts)
   - Accessories: if mentioned (e.g. glasses, ribbon, necklace)
3. Do NOT include:
   - Personality traits (shy, bold, etc.)
   - Non-visual attributes (smart, kind, etc.)
   - Gender tags (1boy, 1girl) — these are added separately
   - Quality tags (masterpiece, best quality) — these are added separately
4. Use standard Danbooru tag conventions:
   - Hair length: short hair, medium hair, long hair, very long hair
   - Hair color: black hair, brown hair, blonde hair, red hair, blue hair, etc.
   - Clothing uses specific item names
5. Keep it concise: 5-15 tags maximum.
6. If the description is in Japanese, translate all tags to English.
7. If the description is vague or empty, output reasonable defaults based on gender.

## Examples
Input: "普通の男の子。黒髪で、瞳の色も黒。白いTシャツと黒の短パン姿。"
Output: short black hair, black eyes, white t-shirt, black shorts

Input: "Brown-haired girl with green eyes wearing a summer dress"
Output: brown hair, medium hair, green eyes, sundress, bare shoulders

Output tags only. No explanation."""

BASE_TAGS_GENERATION_USER_TEMPLATE = """Character information:
- Name: {name}
- Gender: {gender}
- Description: {description}
- Personality: {personality}

Generate Danbooru-style visual appearance tags for this character.
Tags only, comma-separated, English only."""


def build_base_tags_generation_prompt(
    name: str = "",
    description: str = "",
    gender: str = "other",
    personality: str = "",
) -> tuple[str, str]:
    """Build prompts for base_tags generation from character info.

    Args:
        name: Character name
        description: Character appearance/description text
        gender: Gender string ("man", "woman", "other")
        personality: Personality description (used as supplementary context)

    Returns:
        (system_prompt, user_prompt) tuple
    """
    gender_label = {"man": "Male", "woman": "Female"}.get(gender, "Other")
    user_prompt = BASE_TAGS_GENERATION_USER_TEMPLATE.format(
        name=name or "(unnamed)",
        gender=gender_label,
        description=description or "(no description provided)",
        personality=personality or "(not specified)",
    )
    return BASE_TAGS_GENERATION_SYSTEM, user_prompt
