"""AI箱庭: ランダム住民(おまかせの住民)の語彙プール。

移植元 ai_hakoniwa の random_residents.py を元に、日本語と英語を対で持つ。
見た目は (日本語の断片, 英語の断片, 画像タグ) の組で、説明文とタグがずれないようにする。
全員成人。性格の核には、適応の速さ(consts/hakoniwa_story.ADAPTATION_SPEED_KEYWORDS)と
調べ役(INVESTIGATOR_KEYWORDS)の判定語を含める。
"""

from __future__ import annotations

# ランダムに組む人数(作成画面の選択肢)。1人の入れ替えは 1 で呼ぶ
HAKONIWA_RANDOM_COUNT_MIN = 1
HAKONIWA_RANDOM_COUNT_MAX = 7
HAKONIWA_RANDOM_COUNT_DEFAULT = 3
# 生成された項目の長さの上限(名前・性格・外見は consts/hakoniwa の上限を使う)
HAKONIWA_RANDOM_AGE_MAX = 20
HAKONIWA_RANDOM_JOB_MAX = 40
HAKONIWA_RANDOM_PRONOUN_MAX = 8

# 名前は (日本語, 英語)。英語は名・姓の順
SURNAMES = (
    ("佐倉", "Sakura"),
    ("水野", "Mizuno"),
    ("藤原", "Fujiwara"),
    ("小林", "Kobayashi"),
    ("高橋", "Takahashi"),
    ("伊藤", "Ito"),
    ("渡辺", "Watanabe"),
    ("山本", "Yamamoto"),
    ("中村", "Nakamura"),
    ("加藤", "Kato"),
    ("吉田", "Yoshida"),
    ("松本", "Matsumoto"),
    ("井上", "Inoue"),
    ("木村", "Kimura"),
    ("清水", "Shimizu"),
    ("森", "Mori"),
)
GIVEN_NAMES = {
    "female": (
        ("美咲", "Misaki"),
        ("陽菜", "Hina"),
        ("結衣", "Yui"),
        ("凛", "Rin"),
        ("咲良", "Sakura"),
        ("七海", "Nanami"),
        ("心春", "Koharu"),
        ("澪", "Mio"),
        ("楓", "Kaede"),
        ("遥", "Haruka"),
        ("莉子", "Riko"),
        ("琴音", "Kotone"),
        ("雪乃", "Yukino"),
        ("千鶴", "Chizuru"),
        ("紬", "Tsumugi"),
        ("菫", "Sumire"),
    ),
    "male": (
        ("悠真", "Yuma"),
        ("颯太", "Sota"),
        ("大和", "Yamato"),
        ("陸", "Riku"),
        ("健", "Ken"),
        ("翔", "Sho"),
        ("拓海", "Takumi"),
        ("直樹", "Naoki"),
        ("誠", "Makoto"),
        ("涼", "Ryo"),
        ("航", "Wataru"),
        ("圭", "Kei"),
        ("湊", "Minato"),
        ("岳", "Gaku"),
        ("樹", "Itsuki"),
        ("光", "Hikaru"),
    ),
}
# 一人称(日本語)。英語は I
PRONOUNS = {"female": ("私", "わたし", "あたし"), "male": ("俺", "僕", "私")}

# 年代: (日本語, 英語, タグの年齢, 女性の主語タグ, 男性の主語タグ)。女性の40代以降は mature
AGES = (
    ("20代前半", "early 20s", "23 years old", "adult woman", "adult man"),
    ("20代後半", "late 20s", "27 years old", "adult woman", "adult man"),
    ("30代前半", "early 30s", "32 years old", "adult woman", "adult man"),
    ("30代後半", "late 30s", "37 years old", "adult woman", "adult man"),
    ("40代", "40s", "45 years old", "mature female", "adult man"),
    ("50代", "50s", "55 years old", "mature female", "mature male"),
)
JOBS = (
    ("パン屋の店員", "bakery clerk"),
    ("花屋の店主", "florist"),
    ("郵便局員", "postal worker"),
    ("カフェのバリスタ", "cafe barista"),
    ("洋服屋の店員", "clothing store clerk"),
    ("薬剤師", "pharmacist"),
    ("保育士", "nursery teacher"),
    ("イラストレーター", "illustrator"),
    ("翻訳者", "translator"),
    ("時計修理職人", "watch repairer"),
    ("写真家", "photographer"),
    ("大工", "carpenter"),
    ("看護師", "nurse"),
    ("雑貨屋の店主", "general store owner"),
    ("陶芸家", "potter"),
    ("新聞記者", "newspaper reporter"),
    ("ピアノ講師", "piano teacher"),
    ("和菓子職人", "Japanese confectioner"),
    ("本屋の店員", "bookstore clerk"),
)
# 性格の核と生活の癖: (日本語, 英語)
PERSONALITY_CORES = (
    ("明るく社交的", "cheerful and sociable"),
    ("穏やかで聞き上手", "calm and a good listener"),
    ("好奇心旺盛で行動的", "curious and active"),
    ("しっかり者で几帳面", "dependable and meticulous"),
    ("のんびり屋でマイペース", "easygoing and goes at their own pace"),
    ("真面目で努力家", "earnest and hardworking"),
    ("おっとりしていて優しい", "gentle and kind"),
    ("勝ち気で負けず嫌い", "strong-willed and competitive"),
    ("人懐っこくて世話好き", "friendly and caring"),
    ("静かだが芯が強い", "quiet but strong at heart"),
    ("少し内気で慎重", "a little shy and cautious"),
)
PERSONALITY_QUIRKS = (
    (
        "朝は弱く、コーヒーが欠かせない",
        "slow in the morning and cannot do without coffee",
    ),
    ("甘いものに目がない", "has a weakness for sweets"),
    ("植物を育てるのが趣味", "grows plants as a hobby"),
    ("読書が何よりの楽しみ", "loves reading above all"),
    ("料理の腕には自信がある", "is proud of their cooking"),
    ("占いを少し信じている", "half believes in fortune telling"),
    ("方向音痴でよく道に迷う", "has no sense of direction and often gets lost"),
    ("猫を見るとつい足が止まる", "always stops to look at cats"),
    (
        "手先が器用で、頼まれごとが多い",
        "is good with their hands and often asked for help",
    ),
    ("雨の日は少し物思いにふける", "grows a little pensive on rainy days"),
)
# 見た目: (日本語, 英語, タグ)
HAIR_COLORS = (
    ("黒", "black", "black hair"),
    ("茶色", "brown", "brown hair"),
    ("栗色", "chestnut", "chestnut hair"),
    ("金色", "blonde", "blonde hair"),
    ("銀色", "silver", "silver hair"),
    ("深緑", "dark green", "dark green hair"),
    ("淡いピンク", "light pink", "light pink hair"),
    ("紺色", "navy blue", "dark blue hair"),
)
HAIR_STYLES = {
    "female": (
        ("ロングヘア", "long hair", "long hair"),
        ("ポニーテール", "ponytail", "ponytail"),
        ("ツインテール", "twin tails", "twintails"),
        ("ボブカット", "bob cut", "bob cut"),
        ("ショートヘア", "short hair", "short hair"),
        ("三つ編み", "braid", "braid"),
        ("お団子ヘア", "hair bun", "hair bun"),
        ("ウェーブのかかった髪", "wavy hair", "wavy hair"),
    ),
    "male": (
        ("ショートヘア", "short hair", "short hair"),
        ("少し長めの髪", "slightly long hair", "medium hair"),
        ("七三分け", "side-parted hair", "side part"),
        ("マッシュヘア", "mushroom cut", "mushroom hair"),
        ("短く刈り上げた髪", "close-cropped hair", "very short hair"),
        ("ゆるいパーマ", "loose wavy hair", "wavy hair"),
    ),
}
EYES = (
    ("茶色の瞳", "brown eyes", "brown eyes"),
    ("黒い瞳", "black eyes", "black eyes"),
    ("緑の瞳", "green eyes", "green eyes"),
    ("青い瞳", "blue eyes", "blue eyes"),
    ("紫の瞳", "purple eyes", "purple eyes"),
    ("金色の瞳", "amber eyes", "amber eyes"),
)
# 特徴は無いこともある(空の組)
FEATURES = (
    ("眼鏡をかけている", "wears glasses", "glasses"),
    ("そばかすがある", "has freckles", "freckles"),
    ("泣きぼくろがある", "has a mole under one eye", "mole under eye"),
    ("小さなピアスをしている", "wears small earrings", "earrings"),
    ("", "", ""),
    ("", "", ""),
)
OUTFITS = {
    "female": (
        (
            "カジュアルなワンピース",
            "a casual one-piece dress",
            "casual one-piece dress",
        ),
        ("シャツとジーンズ", "a shirt and jeans", "shirt, jeans, casual clothes"),
        ("カーディガンとスカート", "a cardigan and skirt", "cardigan, skirt"),
        ("パーカーとショートパンツ", "a hoodie and shorts", "hoodie, shorts"),
        ("ブラウスとロングスカート", "a blouse and long skirt", "blouse, long skirt"),
    ),
    "male": (
        ("シャツとチノパン", "a shirt and chinos", "shirt, chino pants"),
        ("作業着", "work clothes", "work clothes"),
        ("ジャケット", "a jacket", "jacket, casual clothes"),
        ("パーカー", "a hoodie", "hoodie, casual clothes"),
        ("ニットとスラックス", "a sweater and slacks", "sweater, slacks"),
    ),
}
EXPRESSIONS = (
    "gentle smile",
    "cheerful smile",
    "shy smile",
    "serious expression",
    "sleepy expression",
)

# 外見の説明の組み立て: {hair} {eyes} {feature} {outfit}
APPEARANCE_TEMPLATES = {
    "ja": "{hair_color}の{hair_style}に{eyes}。{feature}{outfit}姿。",
    "en": "{hair_color} {hair_style} and {eyes}. {feature}Wears {outfit}.",
}
