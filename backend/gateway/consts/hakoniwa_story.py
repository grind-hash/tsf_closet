"""AI箱庭の「物語の厚み」の定数と文面(記憶・適応・名残・物語の弧・世界の違和感)。

状態には種類と参照(住民 id・掟 id・数値)だけを保存し、文は表示とプロンプトのときに
言語ごとに組み立てる。プロンプトは英語で書くので、プロンプト用の文はすべて英語。
"""

from __future__ import annotations

# --- 世界の違和感 ---
# 掟の切り替えや変身といった「書き換え」で溜まり、書き換えの無い日は少し静まる。
# 到達点に達すると一度だけ住民が書き手へ呼びかけ(対面)、その後は「公認」になる。
DISSONANCE_MIN = 0
DISSONANCE_MAX = 100
DISSONANCE_RULE_GAIN = 8
DISSONANCE_CUSTOM_RULE_GAIN = 12
DISSONANCE_TRANSFORM_GAIN = 10
DISSONANCE_DIRECTED_EVENT_GAIN = 10
# 指示した出来事の「続き」。同じ介入の延長なので、重ねても急には溜まらない量にする
DISSONANCE_CONTINUED_EVENT_GAIN = 3
DISSONANCE_DAILY_DECAY = 3
DISSONANCE_CONFRONTATION_THRESHOLD = 80
DISSONANCE_AFTER_CONFRONTATION = 40
# (下限, 段階)。下限の降順
DISSONANCE_STAGES: tuple[tuple[int, str], ...] = (
    (80, "confrontation"),
    (50, "probing"),
    (20, "stirring"),
    (0, "stillness"),
)
# 調査の弧と調べ役の寄せが働く段階
DISSONANCE_INVESTIGATION_STAGES = frozenset({"probing", "confrontation"})
# 世界の変化を調べる役回りを担いやすいプリセット住民(好奇心の強い順)
INVESTIGATOR_PREFERENCE = ("ritsu", "shiori")
INVESTIGATOR_KEYWORDS = ("好奇心", "curious", "curiosity")

# --- 本人の適応(変身・入れ替わり) ---
ADAPTATION_MAX_STAGE = 3
# 性格の語 -> 1日に進む量。先に一致した区分を使う(日本語と英語の両方を見る)
ADAPTATION_SPEED_KEYWORDS: tuple[tuple[tuple[str, ...], float], ...] = (
    (("好奇心", "curious"), 1.0),
    (
        (
            "明るく",
            "明るい",
            "世話好き",
            "お節介",
            "積極",
            "社交",
            "cheerful",
            "caring",
            "meddl",
            "outgoing",
            "sociable",
        ),
        0.75,
    ),
    (("内気", "慎重", "静か", "人見知り", "shy", "cautious", "timid", "reserved"), 0.4),
)
ADAPTATION_SPEED_DEFAULT = 0.6

# --- 世界の側の適応(周囲が新しい姿に慣れていく側) ---
WORLD_ADAPTATION_MAX_STAGE = 3
WORLD_ADAPTATION_DAILY_PROGRESS = 0.5

# --- 名残 ---
REMNANT_BASE_DAYS = 2
# 段階2以上の名残の候補(住民 id で決定的に選ぶ)
REMNANT_HABIT_VARIANTS = {
    "swap": ("gesture", "mirror", "pronoun", "nostalgia"),
    "transform": ("gesture", "posture", "speech", "nostalgia"),
}

# --- 記憶 ---
MEMORY_MAX = 8
MEMORY_WEIGHT_MAJOR = 3
MEMORY_WEIGHT_NOTABLE = 2
MEMORY_WEIGHT_MINOR = 1
MEMORY_AFFINITY_THRESHOLD = 8
MEMORY_TEXT_MAX = 120

# --- 物語の弧 ---
ARC_MAX_ACTIVE = 2
ARC_BEATS_TO_CLIMAX = 3
ARC_BOND_AFFINITY_THRESHOLD = 22
ARC_REOPEN_COOLDOWN_DAYS = 5
ARC_MAX_AGE_DAYS = 12
ARC_LOG_MAX = 5
# 状態に残す閉じた弧の数(古い順に捨てる)
ARC_CLOSED_KEEP = 10

# --- 表示とプロンプトの文面 ---

MEMORY_TEXTS: dict[str, dict[str, str]] = {
    "transform_self": {
        "ja": "自分の姿が変わった: 「{change}」",
        "en": "Their own look changed: “{change}”",
    },
    "transform_witness": {
        "ja": "{partner}の姿が変わる場面に居合わせた: 「{change}」",
        "en": "Saw {partner}'s look change: “{change}”",
    },
    "confrontation": {
        "ja": "世界を書き換えている存在（書き手）へ呼びかけた",
        "en": "Called out to the one rewriting this world (the writer)",
    },
    "bond": {
        "ja": "{partner}との関係が大きく動いた（好感度 {delta}）: 「{title}」",
        "en": "The relationship with {partner} moved a lot (affinity {delta}): “{title}”",
    },
    "rule_start": {
        "ja": "掟『{rule}』が始まった",
        "en": "The rule “{rule}” began",
    },
    "rule_end": {
        "ja": "掟『{rule}』が終わった",
        "en": "The rule “{rule}” ended",
    },
    "swap_start": {
        "ja": "{partner}と体が入れ替わった",
        "en": "Swapped bodies with {partner}",
    },
    "swap_end": {
        "ja": "{partner}との入れ替わりが終わり、元の体に戻った",
        "en": "The swap with {partner} ended and they got their own body back",
    },
}

REMNANT_TEXTS: dict[str, dict[str, dict[str, str]]] = {
    "swap": {
        "faint": {
            "ja": "入れ替わっていた頃の感覚が、まだ少し体に残っている気がする",
            "en": "A faint feeling of the swapped body still seems to linger",
        },
        "recall": {
            "ja": "{partner}の体で過ごした日々の感覚を、時々ふっと思い出す",
            "en": "Now and then, the feeling of the days in {partner}'s body comes back",
        },
        "gesture": {
            "ja": "時々、入れ替わっていた相手の癖が自分の仕草に混ざる",
            "en": "The swap partner's habits sometimes slip into their gestures",
        },
        "mirror": {
            "ja": "鏡を見るたび、入れ替わっていた頃の姿が一瞬よぎる",
            "en": "Each time they look in a mirror, the swapped look flickers past",
        },
        "pronoun": {
            "ja": "一人称がふと揺れることがあり、自分で驚くことがある",
            "en": "Their way of referring to themselves sometimes wavers, surprising them",
        },
        "nostalgia": {
            "ja": "入れ替わっていた頃の体の感覚が懐かしく、時々思い出してしまう",
            "en": "They miss the feel of the swapped body and keep remembering it",
        },
    },
    "transform": {
        "faint": {
            "ja": "変わっていた頃の感覚が、まだ少し体に残っている気がする",
            "en": "A faint feeling of the changed look still seems to linger",
        },
        "recall": {
            "ja": "ふとした拍子に、変わっていた頃の所作が顔を出すことがある",
            "en": "Manners from the changed look sometimes show up without warning",
        },
        "gesture": {
            "ja": "無意識に髪を耳にかけたり、裾を押さえたりする仕草が時々出る",
            "en": "They sometimes tuck their hair behind an ear or hold down a hem without thinking",
        },
        "posture": {
            "ja": "鏡の前で、つい変わっていた頃の姿勢を取ってしまうことがある",
            "en": "In front of a mirror they slip into the posture of the changed look",
        },
        "speech": {
            "ja": "言葉の端々に、変わっていた頃の名残がにじむことがある",
            "en": "Traces of the changed look seep into their words now and then",
        },
        "nostalgia": {
            "ja": "変わっていた頃の感覚が懐かしく、時々思い出してしまう",
            "en": "They miss how the changed look felt and keep remembering it",
        },
    },
}

# プロンプト用の段階の名前
ADAPTATION_STAGE_NAMES = (
    "bewildered",
    "trial and error",
    "getting used to it",
    "accepted",
)
WORLD_ADAPTATION_STAGE_NAMES = (
    "surprise",
    "getting used to it",
    "treated as normal",
    "settled",
)

ADAPTATION_STAGE_GUIDANCE = (
    (
        "They are not at all used to the new body yet. Depict the physical sensations "
        "in detail: the shifted center of gravity, the weight of the hair, a different "
        "eye level, clothes touching the skin in unfamiliar ways, the strange sound of "
        "their own voice. They notice and fumble at every movement, and openly voice "
        "surprise, embarrassment or the wish to go back. Do not let them handle it "
        "calmly."
    ),
    (
        "They are trying to get used to the new body through trial and error: "
        "practicing how to wear clothes or move, failing, being taught or watched over "
        "by others. Let both a small sense of achievement over what they could do "
        "better than yesterday and frustration over what they still cannot do show."
    ),
    (
        "They have grown fairly used to the new body. Gestures and manners that suit "
        "the look come out unconsciously, but include a moment where they suddenly "
        "notice their own change and are surprised or embarrassed. A contrast with "
        "what they could not do before works well."
    ),
    (
        "They have fully accepted the new look. Daily life in it feels natural and "
        "their words hesitate less. Others treat the look as a matter of course. Let "
        "memories of the old look cross their mind only occasionally, without dwelling "
        "on the old confusion."
    ),
)

WORLD_ADAPTATION_STAGE_GUIDANCE = (
    (
        "The people around are still surprised and puzzled by the look: eyes gather, "
        "people whisper, double-take and say their surprise out loud."
    ),
    (
        "The people around are getting used to the look. The surprise has faded, but "
        "they still become conscious of it now and then, and the way they speak to "
        "them is a little awkward."
    ),
    (
        "The people around have begun to treat the look as normal: invitations and "
        "remarks that assume the look, and comments that it suits them, come "
        "naturally."
    ),
    (
        "The look has fully settled in this world. Everyone takes the role and place "
        "that comes with it for granted, and nobody questions it."
    ),
)

DISSONANCE_CONTEXT = {
    "acknowledged": (
        "Premise: the residents openly know that the rules and looks of this world are "
        "rewritten by an unseen being they call the writer. Everyday talk may naturally "
        "include signs of the writer, expectations of the next rewrite, or complaints."
    ),
    "stirring": (
        "Premise: lately the residents have faintly noticed unnatural changes in the "
        "world's rules and events, and now and then say that something seems to have "
        "changed."
    ),
    "probing": (
        "Premise: the residents seriously discuss whether someone is rewriting the "
        "world's rules and their looks. Some keep records of the changes, and some try "
        "to witness the moment of a rewrite."
    ),
}

INVESTIGATION_FOCUS = (
    "\n\nImportant: make this an event about investigating the world's changes.\n"
    "Center it on {name}, and make the investigation or discussion of whether the "
    "world's rules and the residents' looks are being unnaturally rewritten the theme "
    "of the event. Include at least one of these concretely: a notebook or notes "
    "recording the changes so far; an eyewitness account of the moment a rule "
    "changed; questioning a resident whose look changed; guesses about who the writer "
    "is or what they intend; a plan to witness the next change. Show the residents "
    "approaching the truth of the world in both narration and lines."
)

ARC_TITLES = {
    "investigation": "{a}'s investigation: chasing the world's strangeness",
    "swap": "The swapped days of {a} and {b}",
    "transform": "Around {a}'s new look",
    "bond": "The distance between {a} and {b}",
}

ARC_CONTINUE_INSTRUCTION = (
    "Write this event as a continuation of that story. Following the flow so far, "
    "move the story forward just a little (do not resolve it suddenly; leave a "
    "lingering sense that it continues)."
)
ARC_CLIMAX_INSTRUCTION = (
    "Today is the climax of this story. Depict a turning point that brings it to a "
    "close: a turn in the relationship, settling of feelings, a big realization or a "
    "confession. End it in a way that follows the flow so far, with the weight a "
    "climax deserves."
)

CONFRONTATION_SYSTEM = (
    "You are the narrator of this miniature world. The residents have noticed that "
    "the world's rules and their looks keep being rewritten by someone, and they "
    "finally resolve to call out to that being (the writer). Create exactly one "
    "special event that marks this turning point. The lines are the two main "
    "characters' words, and they must include calling out to or questioning the "
    "writer. Make it not anger but a call mixed with bewilderment, curiosity and a "
    "little expectation."
)
