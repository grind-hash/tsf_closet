"""AI箱庭の「関わり方」の定数と文面(世界のメモ・掟の相性・介入・タッチ・会話)。

プロンプトに載せる文は英語、表示や定型の台詞は ja / en。
"""

from __future__ import annotations

from typing import Any

# --- 世界のメモ ---
HAKONIWA_WORLD_MEMO_MAX = 1000

# --- プレイヤーの名前(住民がプレイヤーを呼ぶときの名前。空なら名前で呼ばない) ---
HAKONIWA_PLAYER_NAME_MAX = 20

# --- 掟の相性(既定の掟の組み合わせ。両方が有効なとき生成に足す) ---
HAKONIWA_RULE_SYNERGIES: list[dict[str, Any]] = [
    {
        "cards": ("swap", "dress"),
        "text": {
            "ja": {
                "label": "他人（ひと）のドレス",
                "hint": "入れ替わった体のまま、相手のドレスを着ることになる。",
            },
            "en": {
                "label": "Someone Else's Dress",
                "hint": "The swapped pair end up wearing each other's dresses.",
            },
        },
        "prompt": (
            "The swapped residents must also obey the rule of dresses and wear a dress "
            "that fits their current body. A look that would suit the body's original "
            "owner feels mismatched to the wearer and to everyone around; depict the "
            "laughter and bewilderment that mismatch brings to daily life."
        ),
    },
    {
        "cards": ("swap", "ojousama"),
        "text": {
            "ja": {
                "label": "姿は他人、口調はお嬢様",
                "hint": "入れ替わった姿のまま、上品なお嬢様言葉で話すちぐはぐさ。",
            },
            "en": {
                "label": "Someone Else's Body, a Lady's Words",
                "hint": "Speaking in ladylike phrases from a swapped body.",
            },
        },
        "prompt": (
            "The swapped residents must also speak in ladylike speech. The triple "
            "mismatch of look, behavior and speech throws the two around the most, and "
            "the others struggle not to laugh."
        ),
    },
    {
        "cards": ("dress", "ojousama"),
        "text": {
            "ja": {
                "label": "お嬢様のドレスパーティ",
                "hint": "ドレス姿にふさわしい言葉づかいまで求められる、気品の競演。",
            },
            "en": {
                "label": "A Ladies' Dress Party",
                "hint": "Dresses demand matching manners: a contest of elegance.",
            },
        },
        "prompt": (
            "The residents in dresses believe their words must be as elegant as their "
            "dresses, and quietly compete in graceful manners and greetings. Depict a "
            "glamorous daily life mixed with trying too hard and embarrassment."
        ),
    },
    {
        "cards": ("confession", "no_romance"),
        "text": {
            "ja": {
                "label": "禁じられた告白",
                "hint": "本音を口にしやすい週間と、恋愛禁止の掟がぶつかり合う。",
            },
            "en": {
                "label": "Forbidden Confessions",
                "hint": "A week for honest feelings collides with the romance ban.",
            },
        },
        "prompt": (
            "The mood of Confession Week, which makes honest feelings easy to say, "
            "collides head-on with the rule forbidding romantic feelings. Depict "
            "tightrope conversations: starting to say something and swallowing it when "
            "remembering the rule, or rephrasing it as something that is not romance. "
            "Keep it within everyday life without becoming too dramatic."
        ),
    },
]

# --- 1日1回の介入 ---
# watch は何もしない。support 枠(nudge / arc_boost / adaptation_care)と
# rewrite 枠(rewrite / dissonance_push)は、世界の状況で出し分ける。
HAKONIWA_INTERVENTIONS = (
    "watch",
    "nudge",
    "rewrite",
    "arc_boost",
    "adaptation_care",
    "dissonance_push",
)
INTERVENTION_REWRITE_DISSONANCE = 5
INTERVENTION_DISSONANCE_PUSH_GAIN = 3
INTERVENTION_ADAPTATION_BONUS = 0.5
INTERVENTION_ARC_BOOST_AFFINITY = 3

INTERVENTION_DIRECTIVES = {
    "nudge": (
        "\n\n[The player's intervention: a gentle nudge]\n"
        "Weave in a small push today: the residents' distance shrinks a little, or "
        "adapting to a changed look takes a step forward. Do not show anyone "
        "intervening; let it happen naturally as chance or the flow of things."
    ),
    "rewrite": (
        "\n\n[The player's intervention: stronger rewrites]\n"
        "Move the story more than usual today. Include at least one turning point, "
        "such as a turn in a relationship, a secret or true feeling coming out, or a "
        "big step concerning a look or a rule. Do not end it as an extension of the "
        "everyday; leave a change that leads into tomorrow."
    ),
    "arc_boost": (
        "\n\n[The player's intervention: pushing the ongoing story]\n"
        "Keep the ongoing stories especially in mind today. Weave in developments "
        "where the people carrying a story grow closer or step nearer to its core. Do "
        "not show anyone intervening; let it happen naturally."
    ),
    "adaptation_care": (
        "\n\n[The player's intervention: supporting the changed residents]\n"
        "Weave in scenes where others quietly support a resident whose look has "
        "changed, or where that resident takes a step forward in the new look. Add a "
        "warm push that moves their adaptation along a little."
    ),
    "dissonance_push": (
        "\n\n[The player's intervention: stirring up the strangeness]\n"
        "Weave in scenes where the residents touch on the world's unnatural changes "
        "(rewritten rules and looks): rumors, questions about the changes, or someone's "
        "casual remark that spreads a stir. Make it an event that grows the seeds of "
        "strangeness."
    ),
}

# --- タッチ ---
TOUCH_PARTS = ("head", "chest", "lower")
TOUCH_TOLERANT_MOOD = 70
TOUCH_PART_PROMPTS = {
    "head": "had their head gently patted",
    "chest": "was touched on the chest by a hand",
    "lower": "was touched below the waist (around the hips) by a hand",
}
TOUCH_REACTION_TEMPLATES: dict[str, dict[tuple[str, str], list[str]]] = {
    "ja": {
        ("head", "standard"): [
            "えっ……あ、頭？ 急に撫でられると、ちょっと照れるね",
            "ん……撫でられると、なんだか落ち着くかも",
            "あ……。もう、大人なんだからさ。……まあ、嫌じゃないけど",
        ],
        ("head", "confused"): [
            "あ、髪……撫でるなら乱さないでくれ。まだ扱いに慣れてないんだ",
            "ん……今の髪、撫でられると変な感じがする……悪い気はしないけど",
        ],
        ("chest", "standard"): [
            "ちょっ……！ 胸は駄目だって。いきなり触らないでよ",
            "わっ！？ ……今の、わざと？ 次は許さないからね",
        ],
        ("chest", "tolerant"): [
            "も、もう……仕方ないなあ。……少しだけ、だからね",
            "んっ……。驚いたけど、まあ……今日は許してあげる",
        ],
        ("chest", "risque"): [
            "きゃっ……！ だ、駄目だよ、こんな格好のときに……見られるだけでも恥ずかしいのに",
            "やっ、そこは……！ この姿、普段以上に意識しちゃうから……",
        ],
        ("chest", "confused"): [
            "ま、待て……！ そこが今どうなってるか分かってて触ってるのか……？",
            "うわっ！？ ……頼む、そこは本当に勘弁してくれ。まだ慣れてないんだ……",
        ],
        ("lower", "standard"): [
            "ちょっと、どこ触ってるの！？ ……次は本当に怒るからね",
            "ひゃっ！ ……腰の辺り、くすぐったいし、落ち着かないって",
        ],
        ("lower", "tolerant"): [
            "もう……。悪戯するなら、せめて誰も見てないか確認してよね",
            "ん……。仕方ない人だなあ。……ほどほどにね",
        ],
        ("lower", "risque"): [
            "やんっ……！ 裾、短いんだから……って、何言わせるの！",
            "だ、駄目……！ こんな姿のときに、そんなとこ触られたら……",
        ],
        ("lower", "confused"): [
            "待て待て待て！ ……今の体で、そこは本当にまずいだろ……",
            "うわっ、そこは絶対に駄目だ！ ……この体の扱い、まだ全然分からないんだよ……",
        ],
    },
    "en": {
        ("head", "standard"): [
            "Oh... my head? Getting patted out of nowhere is a little embarrassing.",
            "Mm... being patted is kind of soothing.",
        ],
        ("head", "confused"): [
            "Hey, the hair... don't mess it up. I'm still not used to it.",
            "Mm... it feels strange with this hair. Not that I mind.",
        ],
        ("chest", "standard"): [
            "Hey...! Not there. Don't just touch me like that.",
            "Whoa?! ...Was that on purpose? Next time I won't forgive you.",
        ],
        ("chest", "tolerant"): [
            "Oh, come on... fine. Just a little, okay?",
            "Mm... that surprised me, but... I'll let it slide today.",
        ],
        ("chest", "risque"): [
            "Eek...! Not when I'm dressed like this... being looked at is bad enough.",
            "N-not there...! I'm extra self-conscious in this look...",
        ],
        ("chest", "confused"): [
            "W-wait...! Do you even know what's going on there right now?",
            "Whoa?! ...Please, not there. I'm still not used to it...",
        ],
        ("lower", "standard"): [
            "Hey, where do you think you're touching?! Next time I'll really be mad.",
            "Eek! ...That tickles. I can't relax like this.",
        ],
        ("lower", "tolerant"): [
            "Geez... if you're going to tease me, at least check no one's watching.",
            "Mm... you're hopeless. Don't overdo it.",
        ],
        ("lower", "risque"): [
            "Ah...! This hem is short, you know... wait, what am I saying!",
            "D-don't...! Not when I'm dressed like this...",
        ],
        ("lower", "confused"): [
            "Wait wait wait! ...That's really not okay with this body...",
            "No, not there! ...I still have no idea how to handle this body...",
        ],
    },
}

# --- 会話 ---
HAKONIWA_CHAT_MESSAGE_MAX = 500
HAKONIWA_CHAT_REPLY_MAX = 360
HAKONIWA_CHAT_HISTORY_MAX = 40
HAKONIWA_CHAT_HISTORY_CONTEXT = 12
CHAT_FALLBACKS = {
    "ja": (
        "うん、聞いているよ。もう少し詳しく教えてくれる？",
        "なるほどね。そういうこと、考えたこともなかったな。",
        "そっか。……ねえ、その話、もう少し聞かせて。",
    ),
    "en": (
        "Mm, I'm listening. Could you tell me a bit more?",
        "I see. I'd never thought about it that way.",
        "Huh... tell me more about that.",
    ),
}
# 改変の指示とみなす言い回し(元に戻す / 変身)。あいまいな文だけを LLM の分類へ回す
CHAT_CLEAR_PATTERNS = (
    r"元(?:の姿|の格好|通り)?に(?:戻して|戻せ|戻って)",
    r"変身を(?:解除|解いて|やめて|戻して)",
    r"(?:いつも|普段)の(?:姿|格好)に(?:戻して|戻せ|戻って|して)",
    r"\b(?:change|turn|go) back\b",
    r"\bback to (?:normal|your (?:usual|normal) (?:look|self))\b",
    r"\bundo (?:the|your) transformation\b",
)
CHAT_TRANSFORM_PATTERNS = (
    r"変身(?:して|させて|しなさい|してください)",
    r"(?:髪|髪型).{0,24}(?:短く|長く|変えて|切って|結んで|ほどいて|染めて|にして)",
    r"(?:ドレス|ワンピース|制服|衣装|服|スカート|パンツ|靴|帽子|眼鏡|メガネ|リボン|エプロン|水着|下着).{0,24}"
    r"(?:着替えて|着て|着せて|履いて|履かせて|被って|かけて|つけて|付けて|脱いで|脱がせて|にして)",
    r"(?:姿|格好|見た目).{0,16}(?:にして|に変えて|へ変えて|変えて)",
    r"(?:女の子|女性|男の子|男性|女装|ドレス姿|メイド|学生|大人っぽく).{0,16}(?:になって|にして|変身して)",
    # 英語は命令形だけ(「You wear that well」のような感想を拾わない)
    r"^(?:please[, ]+)?(?:transform|change|turn)(?: yourself)? into\b",
    r"^(?:please[, ]+)?(?:put on|wear|change into|dress (?:up )?(?:as|in))\b",
    r"\bplease\b.{0,20}\b(?:transform into|put on|wear|change into|dress up as)\b",
)
# 一致した直後がこれらの文字なら、指示ではなく様子を言っている(「にしてる」「着てた」など)
CHAT_CONTINUATION_CHARS = "るたいおあ"
CHAT_ALTERATION_MARKERS = (
    "変身",
    "変え",
    "戻し",
    "姿",
    "格好",
    "髪",
    "服",
    "着替",
    "着せ",
    "着て",
    "脱",
    "履",
    "ドレス",
    "スカート",
    "衣装",
    "メイク",
    "transform",
    "outfit",
    "dress",
    "hair",
    "wear",
    "clothes",
    "look",
)
CHAT_ALTERATION_RESULT = {
    "transform": {
        "ja": "変身として実行しました:「{instruction}」。元に戻すときは「元に戻して」と送ってください。",
        "en": 'Carried out as a transformation: "{instruction}". Send "change back" to undo it.',
    },
    "clear": {
        "ja": "変身を解いて、元の姿に戻しました。",
        "en": "The transformation was undone; back to the usual look.",
    },
    "not_transformed": {
        "ja": "いまは変身していないので、戻す姿はありませんでした。",
        "en": "Not transformed right now, so there was nothing to undo.",
    },
}
CHAT_ALTERATION_FAILED = {
    "ja": "変身として実行できませんでした: {reason}",
    "en": "Could not carry it out as a transformation: {reason}",
}
CHAT_TRANSFORM_FALLBACK = {
    "ja": "……姿が変わったみたい。どうかな、似合ってる？",
    "en": "...Looks like I've changed. How do I look?",
}

# --- 掟の即時反応(切り替え直後の短い反応。年代記には残さない定型文) ---
# {partner} は相手の名前、{pronoun} は話す住民の一人称、{rule} は自作の掟の名前。
RULE_REACTION_TEMPLATES = {
    "swap_start_male": {
        "ja": "……え？ この姿、{partner}……？ 声まで{partner}だ。なんで{pronoun}がこんなことに……",
        "en": "...Huh? This body is {partner}... Even the voice is {partner}. Why is this happening to me...",
    },
    "swap_start": {
        "ja": "待って、{pronoun}の声が{partner}になってる……。鏡、鏡を見せて！",
        "en": "Wait, my voice sounds just like {partner}... A mirror, someone get me a mirror!",
    },
    "swap_end_male": {
        "ja": "やっと……やっと自分の体に戻った！",
        "en": "Finally... finally back in my own body!",
    },
    "swap_end_first": {
        "ja": "戻った……！ 自分の体だ、間違いない！",
        "en": "I am back...! This is my own body, no doubt about it!",
    },
    "swap_end_second": {
        "ja": "もう片方の体にも慣れかけていたから、少し変な感じ",
        "en": "I was getting used to the other body, so this feels a little strange.",
    },
    "dress_male": {
        "ja": "……{pronoun}もドレスなのか。その、スカートは落ち着かないんだが",
        "en": "...A dress for me too? Skirts are, well, not exactly comfortable.",
    },
    "dress_female": {
        "ja": "今日はみんなドレスなのね。なんだか華やかで嬉しい！",
        "en": "Everyone is in dresses today. It feels so festive!",
    },
    "ojousama": {
        "ja": "まあ、今日からは皆さまお嬢様言葉で過ごすのね。ごきげんよう",
        "en": "Oh my, from today we all speak like refined young ladies. Good day to you.",
    },
    "custom_look": {
        "ja": "『{rule}』のとおりのこの姿、すっかり当たり前だね。……あれ、前からこうだったっけ？",
        "en": "Looking the way '{rule}' says is just normal... Huh, has it always been like this?",
    },
    "custom": {
        "ja": "『{rule}』のとおりに過ごすのが当たり前だもんね。……今、何か変な感じがしたような",
        "en": "Living by '{rule}' is just how things are... Did something feel off just now?",
    },
    "other_start": {
        "ja": "何だか今日から様子が変わりそう。……気のせいかな",
        "en": "Something feels different from today on... Or is it just me?",
    },
    "other_end": {
        "ja": "ふう、いつもの日常に戻った感じがする",
        "en": "Phew, it feels like everyday life is back.",
    },
}

# --- 実験テーマ(世界ごとの「今回の実験」。進み具合は1日のまとめに出す) ---
# プリセットはプレイヤーの目標なので生成には渡さない。自由文だけを控えめな指示として渡す
HAKONIWA_THEME_PRESETS = ("swap", "dress", "dissonance", "transform", "free")
HAKONIWA_THEME_TEXT_MAX = 100
HAKONIWA_THEME_DRESS_TARGET_DAYS = 7
