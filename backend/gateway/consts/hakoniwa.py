"""AI箱庭モードの定数と静的データ。

下宿「星屑荘」のプリセット住民・掟(ルールカード)・定型の出来事(生成に失敗したときの
フォールバック)を持つ。住民の表示文と定型文は ja / en の両方を持ち、生成プロンプトは
英語で書いて出力言語だけを指定する。
"""

from __future__ import annotations

from typing import Any

# --- 上限値 ---
HAKONIWA_EVENTS_PER_DAY = 3
HAKONIWA_MAX_ACTIVE_RULES = 3
HAKONIWA_MIN_RESIDENTS = 2
HAKONIWA_MAX_RESIDENTS = 10
HAKONIWA_WORLD_NAME_MAX = 50
HAKONIWA_RESIDENT_NAME_MAX = 30
HAKONIWA_PERSONALITY_MAX = 300
HAKONIWA_APPEARANCE_TEXT_MAX = 300
HAKONIWA_CUSTOM_RULE_NAME_MAX = 20
HAKONIWA_CUSTOM_RULE_TEXT_MAX = 200
# 自作の掟の見た目の説明(任意)の長さ
HAKONIWA_RULE_APPEARANCE_TEXT_MAX = 300
HAKONIWA_CUSTOM_RULES_MAX = 20
HAKONIWA_TRANSFORM_TEXT_MAX = 500
# 住民の改変(その住民についての世界の常識の書き換え): 1件の長さ・1人あたりの件数・プロンプトに載せる長さ
HAKONIWA_REALITY_TEXT_MAX = 300
HAKONIWA_REALITIES_MAX = 5
HAKONIWA_REALITY_PROMPT_MAX = 200
# 書き手が指示して起こす出来事: 指示文の長さ・巻き込み方・本人以外の参加者の上限
#   solo: 本人だけ / selected: 選んだ住民と / room: 本人と同じ部屋の住民と
HAKONIWA_DIRECTED_EVENT_TEXT_MAX = 500
HAKONIWA_EVENT_SCOPES = ("solo", "selected", "room")
HAKONIWA_DIRECTED_EVENT_PARTNERS_MAX = 2
HAKONIWA_TRANSFORMATION_HISTORY_MAX = 10
# 年代記に保持する出来事の件数(お気に入りは数えず、常に残す)
HAKONIWA_EVENT_LOG_MAX = 600

HAKONIWA_MOOD_MIN = 0
HAKONIWA_MOOD_MAX = 100
HAKONIWA_AFFINITY_MIN = -50
HAKONIWA_AFFINITY_MAX = 50
HAKONIWA_CUSTOM_RESIDENT_INITIAL_MOOD = 55

# 住民がほかの住民を呼ぶときのくせ(話す側に付く)。相手の名前・性別・年の差から呼び方を作る
#   given_chan: 下の名前＋ちゃん(男性には くん) / given_san: 下の名前＋さん /
#   given: 下の名前を呼び捨て / family_san: 苗字＋さん / family: 苗字を呼び捨て
HAKONIWA_ADDRESS_STYLES = ("given_chan", "given_san", "given", "family_san", "family")
HAKONIWA_ADDRESS_STYLE_DEFAULT = "given_san"
# 相手がこれだけ年上なら、くせが ちゃん/くん・呼び捨てでも さん を付ける
HAKONIWA_ADDRESS_ELDER_GAP = 10

# 生成プロンプトへ載せるときの長さ上限(保存上限より短く切り詰める)
HAKONIWA_PERSONALITY_PROMPT_MAX = 120
HAKONIWA_CUSTOM_RULE_PROMPT_MAX = 120
HAKONIWA_TRANSFORM_DESC_PROMPT_MAX = 60
HAKONIWA_RECENT_EVENTS_CONTEXT = 6
HAKONIWA_RECENT_NARRATION_SNIPPET = 40

# 出来事の台詞量: 主役人数 -> (最少, 最多)
HAKONIWA_EVENT_LINES_RANGE: dict[int, tuple[int, int]] = {
    1: (3, 5),
    2: (5, 7),
    3: (7, 9),
}
HAKONIWA_EVENT_LINES_MAX = 9
HAKONIWA_EVENT_TITLE_MAX = 40
HAKONIWA_EVENT_NARRATION_MAX = 600
HAKONIWA_EVENT_LINE_TEXT_MAX = 200
HAKONIWA_GREETING_MAX = 120

# 1日の出来事のうち、3人・単独に差し替える確率(同日に両方は混ぜない)
HAKONIWA_TRIO_GROUP_CHANCE = 0.30
HAKONIWA_SOLO_GROUP_CHANCE = 0.15

# 変身のタグ変換の試行回数と、タグの長さの上限(プレイの appearance_tags と同じ 2000 文字。個数は制限しない)
HAKONIWA_CONVERT_TAGS_MAX_ATTEMPTS = 3
HAKONIWA_TAGS_MAX_LENGTH = 2000
# 説明から姿を丸ごと作るときに LLM へ示すタグの数の目安(上限ではない)
HAKONIWA_TAGS_SUGGESTED_COUNT = 24
# 手で書いたタグの入力の上限(整えたあとの長さは HAKONIWA_TAGS_MAX_LENGTH で確かめる)
HAKONIWA_MANUAL_TAGS_INPUT_MAX = 2000

# 同梱素材の URL(frontend/public/hakoniwa-assets/)
HAKONIWA_ASSET_BASE = "/hakoniwa-assets"
HAKONIWA_ROOM_BACKGROUND_URL = f"{HAKONIWA_ASSET_BASE}/room.png"

GENDERS = ("female", "male")
DEFAULT_BASE_TAGS = {
    "female": "1girl, solo, adult woman, casual clothes",
    "male": "1boy, solo, adult man, casual clothes",
}

# 画像モデルの選択肢。"default" はユーザー設定の画像モデルに従う
HAKONIWA_IMAGE_MODEL_DEFAULT = "default"

# 生成プロンプトの固定部(英語)。出力言語は呼び出し側で指定する
WORLD_BRIEF = (
    "The setting is Stardust House (星屑荘), a small boarding house, and its "
    "neighborhood (a cafe, a small library, a garden, a little shopping street). "
    "Adult residents share their daily lives there. The tone is calm and warm: an "
    "ensemble story of small everyday incidents and interactions. Avoid extreme "
    "developments and unhappy endings. Relationships between residents change "
    "little by little through daily events."
)
RULE_PRIORITY_NOTE = (
    " While world rules are active, the content of the rules takes priority over "
    "the default calm, warm mood described above."
)
CUSTOM_RULE_PRIORITY_NOTE = (
    " Especially while player-written rules are active, the subject matter and tone "
    "of this world are decided by those rules themselves. Never water a rule down "
    "into a harmless everyday incident or a mere comment about it."
)

LIVING_ROOM_SCENE = (
    "The shared living room of Stardust House: wooden floor, plain walls, a window "
    "with curtains and warm sunlight, and a wide open floor."
)

# --- エリアと家具 ---
# 各エリアは背景1枚(家具を描き込まない殺風景な舞台)と、家具を置くスロット4つを持つ。
# スロットの座標は部屋のゲーム座標(1216x832)の x と足元の y。家具は実物1点として扱い、
# どこか1か所にだけ置ける(別のスロットへ置くと移動する)。

DEFAULT_AREA_ID = "living"
HAKONIWA_FURNITURE_SLOTS = 4
# 出来事を参加者のいる場所以外で起こす確率と、日の終わりに住民が別の場所へ移る確率
HAKONIWA_EVENT_AREA_MOVE_CHANCE = 0.35
HAKONIWA_RESIDENT_AREA_MOVE_CHANCE = 0.25

HAKONIWA_AREAS: list[dict[str, Any]] = [
    {
        "id": "living",
        "background_file": "room.png",
        "name": {"ja": "リビング", "en": "Living room"},
        "scene": LIVING_ROOM_SCENE,
        "scene_tags": (
            "sparse empty living room interior, wooden floor, plain wall, "
            "window with curtains, warm sunlight through window, minimal, "
            "wide open floor space, scenery, anime background"
        ),
        "slots": [(180, 700), (470, 730), (760, 700), (1040, 730)],
    },
    {
        "id": "garden",
        "background_file": "area_garden.png",
        "name": {"ja": "庭", "en": "Garden"},
        "scene": (
            "The garden of Stardust House: a lawn, garden trees and flower beds with "
            "seasonal flowers in bloom, a stone path and wide open ground."
        ),
        "scene_tags": (
            "sparse japanese garden, green lawn, garden trees, flower beds along the "
            "wall, stone path, warm sunlight, minimal, wide open ground, scenery, "
            "anime background"
        ),
        "slots": [(200, 710), (500, 740), (800, 710), (1050, 740)],
    },
    {
        "id": "study",
        "background_file": "area_study.png",
        "name": {"ja": "書斎", "en": "Study"},
        "scene": (
            "The small library study of Stardust House: a wooden floor, plain walls "
            "and a window, quiet and calm, with a wide open floor."
        ),
        "scene_tags": (
            "sparse empty study room interior, wooden floor, plain walls, window, "
            "warm light, minimal, wide open floor space, scenery, anime background"
        ),
        "slots": [(190, 700), (480, 730), (770, 700), (1040, 730)],
    },
]
HAKONIWA_AREA_MAP: dict[str, dict[str, Any]] = {
    area["id"]: area for area in HAKONIWA_AREAS
}

# 出来事の場所(場面の絵の背景)。住民がいる3つのエリアに加えて、エリアの外の場所を持つ。
# エリアの外の場所は ADV の背景・場面の絵・年代記の表示に使い、住民の居場所(current_area)は変えない。
# background_file は同梱の背景(frontend/public/hakoniwa-assets/、1216x832・人物なし)。
HAKONIWA_EXTRA_LOCATIONS: list[dict[str, Any]] = [
    {
        "id": "bathroom",
        "background_file": "location_bathroom.png",
        "name": {"ja": "浴室", "en": "Bathroom"},
        "scene": (
            "The bathroom of Stardust House: a tiled room with a bathtub and a "
            "shower, steam and warm light."
        ),
        "scene_tags": (
            "clean modern bathroom interior, white tiled walls, spotless, bathtub "
            "filled with water, shower, light steam, bright soft warm light, "
            "scenery, anime background"
        ),
    },
    {
        "id": "bedroom",
        "background_file": "location_bedroom.png",
        "name": {"ja": "寝室", "en": "Bedroom"},
        "scene": (
            "A resident's private bedroom at Stardust House: a bed, curtains and soft "
            "lamp light."
        ),
        "scene_tags": (
            "bedroom interior, bed, pillows, curtains, soft lamp light, scenery, "
            "anime background"
        ),
    },
    {
        "id": "kitchen",
        "background_file": "location_kitchen.png",
        "name": {"ja": "台所", "en": "Kitchen"},
        "scene": (
            "The shared kitchen of Stardust House: counters, a stove and a small "
            "dining table."
        ),
        "scene_tags": (
            "clean tidy kitchen interior, kitchen counter, stove, small dining table, "
            "warm light, scenery, anime background"
        ),
    },
    {
        "id": "shopping_street",
        "background_file": "location_shopping_street.png",
        "name": {"ja": "商店街", "en": "Shopping street"},
        "scene": (
            "The little shopping street near Stardust House: small shops, signboards "
            "and people passing by."
        ),
        "scene_tags": (
            "shopping street, shopfronts, signboards, daytime, outdoors, scenery, "
            "anime background"
        ),
    },
    {
        "id": "cafe",
        "background_file": "location_cafe.png",
        "name": {"ja": "カフェ", "en": "Cafe"},
        "scene": (
            "The cafe in the neighborhood: wooden tables, a counter and large windows."
        ),
        "scene_tags": (
            "cafe interior, wooden tables, counter, large windows, warm light, "
            "scenery, anime background"
        ),
    },
    {
        "id": "park",
        "background_file": "location_park.png",
        "name": {"ja": "公園", "en": "Park"},
        "scene": "A park near Stardust House: trees, benches, a path and open grass.",
        "scene_tags": (
            "park, trees, bench, path, grass, blue sky, outdoors, scenery, "
            "anime background"
        ),
    },
    {
        "id": "beach",
        "background_file": "location_beach.png",
        "name": {"ja": "海辺", "en": "Beach"},
        "scene": "A beach a short train ride away: sand, waves and a wide sky.",
        "scene_tags": (
            "beach, sand, ocean, waves, blue sky, outdoors, scenery, anime background"
        ),
    },
    {
        "id": "hotel",
        "background_file": "location_hotel.png",
        "name": {"ja": "ホテル", "en": "Hotel"},
        "scene": (
            "A hotel room in town (a city hotel or a love hotel): a large bed, soft "
            "dim lighting and a window with city lights."
        ),
        "scene_tags": (
            "hotel room, large bed, pillows, dim lighting, night, window, city lights, "
            "indoors, scenery, anime background"
        ),
    },
]
HAKONIWA_LOCATIONS: list[dict[str, Any]] = [*HAKONIWA_AREAS, *HAKONIWA_EXTRA_LOCATIONS]
HAKONIWA_LOCATION_MAP: dict[str, dict[str, Any]] = {
    location["id"]: location for location in HAKONIWA_LOCATIONS
}


# 場面の絵だけで変える服装(住民の姿・立ち絵は変えない)。体の性別ごとのタグ。
# as_is はいまの服のまま。nude は NSFW モードが OFF なら towel にする
HAKONIWA_SCENE_ATTIRES: dict[str, dict[str, str]] = {
    "as_is": {"female": "", "male": ""},
    "nude": {"female": "nude, completely nude", "male": "nude, completely nude"},
    "towel": {
        "female": "naked towel, bath towel",
        "male": "towel around waist, topless male",
    },
    "swimsuit": {"female": "swimsuit, bikini", "male": "swim trunks, topless male"},
    "underwear": {
        "female": "underwear only, bra, panties",
        "male": "underwear only, boxer briefs, topless male",
    },
    "pajamas": {"female": "pajamas", "male": "pajamas"},
}
# 裸以外の服装に選ばれた人物のネガティブ。NSFW の場面では水や濡れのタグで裸に寄るため
HAKONIWA_SCENE_COVERED_NEGATIVE: dict[str, str] = {
    "female": "nude, completely nude, nipples, topless",
    "male": "nude, completely nude, penis",
}


def event_location(event: dict[str, Any]) -> dict[str, Any]:
    """出来事の場所(location があればそれ、無ければ起きたエリア)。"""
    return (
        HAKONIWA_LOCATION_MAP.get(str(event.get("location") or ""))
        or HAKONIWA_AREA_MAP.get(str(event.get("area") or ""))
        or HAKONIWA_AREA_MAP[DEFAULT_AREA_ID]
    )


HAKONIWA_FURNITURE: list[dict[str, Any]] = [
    {
        "id": "houseplant",
        "name": {"ja": "観葉植物", "en": "Houseplant"},
        "description": "a large potted houseplant",
    },
    {
        "id": "cat_tower",
        "name": {"ja": "猫タワー", "en": "Cat tower"},
        "description": "a cat tower (no cat on it)",
    },
    {
        "id": "bookshelf",
        "name": {"ja": "本棚", "en": "Bookshelf"},
        "description": "a wooden bookshelf full of books",
    },
    {
        "id": "round_table",
        "name": {"ja": "丸テーブル", "en": "Round table"},
        "description": "a small round table",
    },
    {
        "id": "lamp",
        "name": {"ja": "フロアランプ", "en": "Floor lamp"},
        "description": "a warmly glowing floor lamp",
    },
    {
        "id": "plush",
        "name": {"ja": "ぬいぐるみ", "en": "Plush toy"},
        "description": "a big teddy bear plush",
    },
    {
        "id": "aquarium",
        "name": {"ja": "水槽", "en": "Aquarium"},
        "description": "an aquarium with tropical fish",
    },
    {
        "id": "kotatsu",
        "name": {"ja": "こたつ", "en": "Kotatsu"},
        "description": "a kotatsu table with a blanket",
    },
]
HAKONIWA_FURNITURE_MAP: dict[str, dict[str, Any]] = {
    item["id"]: item for item in HAKONIWA_FURNITURE
}


def area_background_url(area_id: str) -> str:
    area = HAKONIWA_AREA_MAP.get(area_id) or HAKONIWA_AREA_MAP[DEFAULT_AREA_ID]
    return f"{HAKONIWA_ASSET_BASE}/{area['background_file']}"


def location_background_url(location_id: str) -> str | None:
    """出来事の場所の背景の URL(エリアはエリアの背景、外の場所は同梱の背景)。"""
    location = HAKONIWA_LOCATION_MAP.get(location_id)
    if location is None or not location.get("background_file"):
        return None
    return f"{HAKONIWA_ASSET_BASE}/{location['background_file']}"


def furniture_url(furniture_id: str) -> str:
    return f"{HAKONIWA_ASSET_BASE}/furniture_{furniture_id}.png"


# --- プリセット住民(全員成人) ---
# base_tags は通常版、dress_tags はドレスの掟用のドレス版の画像タグ(同梱素材の生成に使ったもの)。

HAKONIWA_PRESET_RESIDENTS: list[dict[str, Any]] = [
    {
        "id": "aoi",
        "gender": "female",
        "base_tags": (
            "1girl, solo, adult woman, 27 years old, long brown hair, ponytail, "
            "brown eyes, cheerful smile, delivery uniform, cap, casual jacket"
        ),
        "dress_tags": (
            "1girl, solo, adult woman, 27 years old, long brown hair, ponytail, "
            "brown eyes, cheerful smile, bright coral sundress, frilled dress, "
            "ribbon, energetic, cheerful"
        ),
        "initial_mood": 62,
        "initial_area": "living",
        "address_style": "given_chan",
        "initial_affinities": {"shiori": 10, "tamako": 15, "ren": 5, "ritsu": 10},
        "text": {
            "ja": {
                "name": "高瀬 葵",
                "pronoun": "私",
                "age": "20代後半",
                "job": "配達員",
                "personality": "明るく世話好き。誰にでも声をかけ、下宿のムードメーカー。",
                "greetings": [
                    "やあ！今日も配達、頑張ってるよ。何か届け物があったら言ってね",
                    "お、ちょうど休憩中。お茶でも飲んでいく？",
                    "星屑荘のみんなは元気かな。様子を見に来てくれてありがとう！",
                ],
            },
            "en": {
                "name": "Aoi Takase",
                "pronoun": "I",
                "age": "late 20s",
                "job": "delivery worker",
                "personality": (
                    "Cheerful and caring. Talks to everyone and keeps the house in good spirits."
                ),
                "greetings": [
                    "Hey! Busy with deliveries as usual. Tell me if you need anything delivered!",
                    "Oh, perfect timing, I'm on a break. Want some tea?",
                    "Is everyone at Stardust House doing well? Thanks for checking in!",
                ],
            },
        },
    },
    {
        "id": "shiori",
        "gender": "female",
        "base_tags": (
            "1girl, solo, adult woman, 32 years old, long black hair, glasses, "
            "black eyes, gentle expression, cardigan, long skirt, holding book"
        ),
        "dress_tags": (
            "1girl, solo, adult woman, 32 years old, long black hair, glasses, "
            "black eyes, gentle expression, elegant white one-piece dress, "
            "modest dress, lace collar, pure, graceful"
        ),
        "initial_mood": 45,
        "initial_area": "study",
        "address_style": "given_san",
        "initial_affinities": {"aoi": 10, "tamako": 0, "ren": 15, "ritsu": -5},
        "text": {
            "ja": {
                "name": "森下 栞",
                "pronoun": "私",
                "age": "30代前半",
                "job": "図書室司書",
                "personality": (
                    "内気で本好き。静かな場所を好むが、読書の話になると饒舌になる。"
                ),
                "greetings": [
                    "あ、こんにちは……。いま、ちょうどいい章のところで……でも、話しかけてくれて嬉しいです",
                    "この本、読み終わったら貸しますね。……たぶん、きっと気に入ります",
                    "静かな場所って、落ち着きますよね。ここ、私のお気に入りなんです",
                ],
            },
            "en": {
                "name": "Shiori Morishita",
                "pronoun": "I",
                "age": "early 30s",
                "job": "librarian",
                "personality": (
                    "Shy and loves books. Prefers quiet places but becomes talkative about reading."
                ),
                "greetings": [
                    "Oh, hello... I was right in a good chapter... but I'm glad you came to talk.",
                    "I'll lend you this book when I'm done. ...I think you'll like it.",
                    "Quiet places are calming, aren't they? This is my favorite spot.",
                ],
            },
        },
    },
    {
        "id": "tamako",
        "gender": "female",
        "base_tags": (
            "1girl, solo, mature female, 55 years old, short gray-streaked brown hair, "
            "brown eyes, warm smile, apron over blouse, cafe owner"
        ),
        "dress_tags": (
            "1girl, solo, mature female, 55 years old, short gray-streaked brown hair, "
            "brown eyes, warm smile, elegant burgundy dress, refined dress, "
            "pearl necklace, dignified"
        ),
        "initial_mood": 58,
        "initial_area": "living",
        "address_style": "given_chan",
        "initial_affinities": {"aoi": 15, "shiori": 5, "ren": 10, "ritsu": 10},
        "text": {
            "ja": {
                "name": "大島 珠子",
                "pronoun": "あたし",
                "age": "50代",
                "job": "喫茶店主",
                "personality": "噂好きでお節介。下宿の住人のことは何でも知っている（つもり）。",
                "greetings": [
                    "あらあら、よく来たわね。ちょうど新メニューの試食があってね……",
                    "ふふ、この下宿のことは何でも知ってるつもりよ。何か聞きたいことある？",
                    "今日の喫茶は少し暇でね。あんたの顔が見られて嬉しいわ",
                ],
            },
            "en": {
                "name": "Tamako Oshima",
                "pronoun": "I",
                "age": "50s",
                "job": "cafe owner",
                "personality": (
                    "Loves gossip and meddling. Believes she knows everything about the residents."
                ),
                "greetings": [
                    "Well, well, welcome. I happen to be trying out a new menu item...",
                    "I know just about everything in this house. Anything you want to ask?",
                    "The cafe's a bit quiet today. Good to see your face, dear.",
                ],
            },
        },
    },
    {
        "id": "ren",
        "gender": "male",
        "base_tags": (
            "1boy, solo, young man, 27 years old, handsome, clean-shaven, "
            "short dark green hair, green eyes, calm expression, white work shirt, "
            "sleeves rolled up, light blue apron, gardening gloves"
        ),
        "dress_tags": (
            "1boy, solo, young man, 27 years old, handsome, clean-shaven, "
            "short dark green hair, green eyes, calm expression, dignified dark blue "
            "dress, sharp silhouette, high collar, cool beauty"
        ),
        "initial_mood": 50,
        "initial_area": "garden",
        "address_style": "family",
        "initial_affinities": {"aoi": 5, "shiori": 15, "tamako": 5, "ritsu": 0},
        "text": {
            "ja": {
                "name": "苑田 蓮",
                "pronoun": "俺",
                "age": "20代後半",
                "job": "庭師",
                "personality": "無口だが観察眼が鋭い。庭の植物と住人の変化によく気づく。",
                "greetings": [
                    "……ああ、君か。庭の花が、今日はよく咲いている",
                    "植物は嘘をつかない。……君も、少し元気そうだな",
                    "何か用か。なければ、少し庭を見ていくといい",
                ],
            },
            "en": {
                "name": "Ren Sonoda",
                "pronoun": "I",
                "age": "late 20s",
                "job": "gardener",
                "personality": (
                    "Quiet but sharply observant. Notices changes in the plants and the residents."
                ),
                "greetings": [
                    "...Ah, it's you. The garden flowers are in full bloom today.",
                    "Plants don't lie. ...You look a little livelier too.",
                    "Need something? If not, take a look at the garden for a while.",
                ],
            },
        },
    },
    {
        "id": "ritsu",
        "gender": "male",
        "base_tags": (
            "1boy, solo, male focus, androgynous, bishounen, adult, young man, "
            "23 years old, tall, slender, flat chest, soft facial features, "
            "ash blonde bob cut, sidelocks, bangs, blue eyes, curious expression, "
            "beige hoodie, jeans, sneakers"
        ),
        "dress_tags": (
            "1boy, solo, male focus, androgynous, bishounen, adult, young man, "
            "23 years old, tall, slender, flat chest, soft facial features, "
            "ash blonde bob cut, sidelocks, bangs, blue eyes, curious expression, "
            "crossdressing, refreshing light blue summer dress, fresh, lively"
        ),
        "initial_mood": 66,
        "initial_area": "living",
        "address_style": "family_san",
        "initial_affinities": {"aoi": 10, "shiori": -5, "tamako": 10, "ren": 0},
        "text": {
            "ja": {
                "name": "九条 薫",
                "pronoun": "僕",
                "age": "20代前半",
                "job": "新住民（求職中）",
                "personality": (
                    "引っ越してきたばかりの、中性的な顔立ちの青年。好奇心旺盛で、"
                    "星屑荘の掟や習慣に興味津々。"
                ),
                "greetings": [
                    "あ、こんにちは！星屑荘って、毎日何か起きてて面白いですね",
                    "ねえねえ、この下宿の掟って、まだ他にもあるんですか？気になるんです",
                    "引っ越してきて正解でした。みんな、優しくしてくれるんです",
                ],
            },
            "en": {
                "name": "Kaoru Kujo",
                "pronoun": "I",
                "age": "early 20s",
                "job": "new resident (job hunting)",
                "personality": (
                    "A young man with androgynous looks who just moved in. Very "
                    "curious, especially about the house's rules and customs."
                ),
                "greetings": [
                    "Oh, hi! Something happens at Stardust House every day, it's so fun.",
                    "Hey, are there more house rules? I'm dying to know.",
                    "Moving here was the right call. Everyone's so kind to me.",
                ],
            },
        },
    },
]

HAKONIWA_PRESET_MAP: dict[str, dict[str, Any]] = {
    resident["id"]: resident for resident in HAKONIWA_PRESET_RESIDENTS
}

GENERIC_GREETINGS: dict[str, list[str]] = {
    "ja": [
        "こんにちは。星屑荘の暮らしには、もう慣れました",
        "おや、声をかけてくれるなんて嬉しいですね",
        "今日はいい日になりそうな気がします",
        "何か面白いことが起きないかと、少し期待しているんです",
    ],
    "en": [
        "Hello. I've gotten used to life at Stardust House.",
        "Oh, how nice of you to say hello.",
        "I have a feeling today will be a good day.",
        "I'm secretly hoping something interesting will happen.",
    ],
}

CUSTOM_RESIDENT_LABELS: dict[str, dict[str, str]] = {
    "ja": {"age": "成人", "job": "星屑荘の住人"},
    "en": {"age": "adult", "job": "resident of Stardust House"},
}


# プリセット住民の作り直しの版。上げると、既存の世界の住民も normalize_state で新しい
# 画像タグになる(プレイヤーが外見を書き換えていれば、そのまま)。同梱の立ち絵の URL にも
# 版を付けて、古い画像のキャッシュを使わせない。
# ritsu: 2 = 九条 律(女性) -> 九条 薫(中性的な青年)、3 = 通常とドレスを V5 で顔をそろえて描き直した
# ren: 2 = 通常の姿を20代に見えるように描き直した、3 = 通常とドレスを V5 で顔をそろえて描き直した
HAKONIWA_PRESET_REVISIONS: dict[str, int] = {"ritsu": 3, "ren": 3}
# 人物そのもの(性別など)を変えた版。ここより前の版の世界では、性別を新しい設定にして、
# 古い姿で生成した画像(通常・ドレス・掟の姿・複合の姿)も外す
HAKONIWA_PRESET_CHARACTER_REVISIONS: dict[str, int] = {"ritsu": 2}


def preset_bundled_avatar_url(preset_id: str, *, dress: bool = False) -> str:
    """プリセット住民の同梱アバターの URL。"""
    suffix = "_dress" if dress else ""
    revision = HAKONIWA_PRESET_REVISIONS.get(preset_id, 1)
    version = f"?v={revision}" if revision > 1 else ""
    return f"{HAKONIWA_ASSET_BASE}/avatar_{preset_id}{suffix}.png{version}"


# --- 掟(ルールカード) ---
# prompt は生成プロンプトの「世界の掟」へそのまま載せる英語の文。swap は {a} / {b} に当事者名。

HAKONIWA_RULE_CARDS: list[dict[str, Any]] = [
    {
        "id": "ojousama",
        "prompt": (
            "Every resident of this world speaks in refined, ladylike 'ojousama' speech. "
            "When writing Japanese, every line of dialogue must use お嬢様言葉 such as "
            "「〜ですわ」「〜ですの」「まあ！」; when writing English, use elegant, "
            "aristocratic ladylike phrasing. Narration may stay normal. The residents "
            "are a little bewildered by the change but are adapting to it."
        ),
        "text": {
            "ja": {
                "name": "お嬢様言葉の掟",
                "description": "住民全員がお嬢様言葉で話すようになる。",
            },
            "en": {
                "name": "Rule of Ladylike Speech",
                "description": "Every resident starts speaking in refined, ladylike speech.",
            },
        },
    },
    {
        "id": "swap",
        "prompt": (
            "Since one morning, {a} and {b} have swapped appearances (bodies). Each mind "
            "is still their own; only the outside belongs to the other. Everyone around "
            "them knows what happened. Reflect this naturally in events, and always refer "
            "to each person by the name of the mind inside."
        ),
        "text": {
            "ja": {
                "name": "入れ替わりの朝",
                "description": "ランダムな2名の住民の見た目（身体）が入れ替わる。",
            },
            "en": {
                "name": "The Swapped Morning",
                "description": "Two random residents swap appearances (bodies).",
            },
        },
    },
    {
        "id": "dress",
        "prompt": (
            "In this world, residents must wear a dress whenever they go out. Everyone "
            "obeys regardless of gender, and choosing dresses and being unused to wearing "
            "them are everyday topics."
        ),
        "text": {
            "ja": {
                "name": "ドレスの掟",
                "description": "住民は外出時にドレスを着なければならない。",
            },
            "en": {
                "name": "Rule of Dresses",
                "description": "Residents must wear a dress whenever they go out.",
            },
        },
    },
    {
        "id": "no_romance",
        "prompt": (
            "In this world, showing romantic feelings in public is forbidden. Residents "
            "pretend to be calm, but hidden feelings and quiet rivalries cause small "
            "incidents beneath the surface. Keep events within everyday life without "
            "becoming too dramatic."
        ),
        "text": {
            "ja": {
                "name": "恋愛禁止令",
                "description": "恋愛めいた感情が公には禁じられている。",
            },
            "en": {
                "name": "Romance Ban",
                "description": "Showing romantic feelings in public is forbidden.",
            },
        },
    },
    {
        "id": "confession",
        "prompt": (
            "This week is 'Confession Week': residents find it easier than usual to reveal "
            "small secrets and honest feelings. Focus on everyday, heartwarming confessions "
            "such as favorite foods, past blunders or hidden hobbies rather than big "
            "revelations."
        ),
        "text": {
            "ja": {
                "name": "告白週間",
                "description": "住民は小さな秘密や本音を口にしやすい週間。",
            },
            "en": {
                "name": "Confession Week",
                "description": "A week when residents easily reveal small secrets and true feelings.",
            },
        },
    },
]

HAKONIWA_RULE_MAP: dict[str, dict[str, Any]] = {
    card["id"]: card for card in HAKONIWA_RULE_CARDS
}

# 恋愛を主題にしやすい掟。有効な間は「男性の体」同士の組を選ばない
ROMANCE_RULE_IDS = frozenset({"confession", "no_romance"})


# --- 定型の出来事(生成に失敗したときのフォールバック) ---
# narration と台詞の {a} / {b} / {c} に主役の名前が入る。speaker は "a" / "b" / "c"。
# 変身への反応は {target} / {other}。

HAKONIWA_TEMPLATES: dict[str, dict[str, list[dict[str, Any]]]] = {
    "ja": {
        "pair": [
            {
                "title": "朝食の席で",
                "narration": "朝の食堂。{a}が焼いたトーストを前に、いつもより少し賑やかな朝食になった。",
                "lines": [
                    ("b", "いただきます。……ん、今日のトースト、特にうまいね"),
                    (
                        "a",
                        "ふふ、焼き加減がちょうどよかったんだ。昨日は焦がしたから、今日は慎重にね",
                    ),
                    ("b", "焦がした方も、香ばしくて嫌いじゃなかったけどな"),
                    ("a", "もう、そういう優しい嘘はいいから。……でも、ありがとう"),
                    ("b", "嘘じゃないって。明日の分も期待してるよ"),
                ],
                "mood_delta": {"a": 5, "b": 4},
                "affinity_delta": 3,
            },
            {
                "title": "庭の水やり当番",
                "narration": "{a}と{b}は庭の水やりを一緒に済ませた。先週植えた苗が、小さく芽を出している。",
                "lines": [
                    ("a", "ほら、芽が出てる"),
                    ("b", "本当だ。育つのが楽しみだね"),
                ],
                "mood_delta": {"a": 4, "b": 5},
                "affinity_delta": 2,
            },
            {
                "title": "小さな行き違い",
                "narration": (
                    "共用の洗濯機の順番を巡って、{a}と{b}が少し言い合いになった。"
                    "夕方にはどちらからともなく謝り、かえって前より打ち解けた様子だった。"
                ),
                "lines": [
                    ("a", "ねえ、さっきの洗濯機のことだけど……順番を勘違いしてたみたい"),
                    ("b", "ああ、あれか。実はこっちも、タイマーの設定を間違えてたんだ"),
                    ("a", "なんだ、お互い様じゃない。さっきは言いすぎた。ごめん"),
                    ("b", "こちらこそ。……冷めないうちに、お茶でも飲もうか"),
                    ("a", "うん。今度は当番表を扉に貼ろう。二度と揉めないようにね"),
                ],
                "mood_delta": {"a": -3, "b": -2},
                "affinity_delta": 1,
            },
            {
                "title": "おすすめの一冊",
                "narration": "{a}が{b}に本を一冊貸した。{b}は戸惑いながらも嬉しそうだった。",
                "lines": [
                    ("a", "返却期限は、読み終わるまででいいよ"),
                    ("b", "ありがとう。大事に読むね"),
                ],
                "mood_delta": {"a": 3, "b": 6},
                "affinity_delta": 4,
            },
            {
                "title": "喫茶店の新メニュー",
                "narration": (
                    "{a}と{b}は喫茶店の新メニューの試食に付き合わされた。"
                    "二人で真剣に食レポを考える昼下がり。"
                ),
                "lines": [
                    ("b", "このソース、どう表現したらいいかな"),
                    ("a", "『懐かしいのに新しい』、でどう？"),
                ],
                "mood_delta": {"a": 6, "b": 5},
                "affinity_delta": 3,
            },
            {
                "title": "雨の日の傘",
                "narration": (
                    "夕立に遭った{b}を、{a}が傘を持って駅まで迎えに行った。"
                    "濡れた肩を笑い合いながら、二人で下宿までの道を帰った。"
                ),
                "lines": [
                    ("b", "うわ、急に降ってきた……。駅から出られないや"),
                    (
                        "a",
                        "ほら、迎えに来たよ。空が怪しかったから、傘を二本持ってきたの",
                    ),
                    ("b", "助かった……。わざわざありがとう。肩、濡れてない？"),
                    ("a", "平気。風邪ひく前に帰ろう。今日は温かいスープがあるんだ"),
                    ("b", "それは楽しみ。……今度はこっちが迎えに行く番だね"),
                ],
                "mood_delta": {"a": 4, "b": 7},
                "affinity_delta": 5,
            },
            {
                "title": "廊下の話し声",
                "narration": (
                    "夜、廊下で出くわした{a}と{b}は、つい長話をしてしまった。"
                    "こういう時間がいちばん落ち着く、と二人とも思った。"
                ),
                "lines": [
                    ("a", "あれ、まだ起きてたんだ。……眠れない？"),
                    ("b", "うん、少しだけ。そっちこそ、こんな時間にどうしたの"),
                    (
                        "a",
                        "水を飲みに来ただけ。……でも、話し相手がいるなら、もう少し起きてようかな",
                    ),
                    ("b", "話すとあっという間だね。もうこんな時間か"),
                    ("a", "内緒の夜更かし、たまにはいいよね。明日は二人とも寝坊だね"),
                ],
                "mood_delta": {"a": 5, "b": 5},
                "affinity_delta": 3,
            },
            {
                "title": "買い出しの相談",
                "narration": (
                    "{a}と{b}は週末の買い出しリストを相談した。消耗品の話から、"
                    "いつの間にか皆の好物の話になり、リストは倍の長さになった。"
                ),
                "lines": [
                    ("a", "あの人の好物も入れとこう"),
                    ("b", "じゃあ、デザートも追加だね"),
                ],
                "mood_delta": {"a": 3, "b": 3},
                "affinity_delta": 2,
            },
        ],
        "swap": [
            {
                "title": "鏡の前で二度見",
                "narration": (
                    "洗面所の鏡の前で、{a}が映った姿を見て思わず二度見した。"
                    "鏡の中にいるのは紛れもなく{b}で、{a}は確かめるように自分の頬へ触れた。"
                    "後ろから{b}が通りかかり、自分の顔が驚いているのを見て苦笑した。"
                ),
                "lines": [
                    (
                        "a",
                        "……何度見ても、鏡の中が{b}なんだよね。頬を触っても、感触まで借り物みたいだ",
                    ),
                    (
                        "b",
                        "その顔で驚かれるの、こっちも大概落ち着かないよ。そんな変な顔しないで",
                    ),
                    (
                        "a",
                        "ごめんごめん。でもさ、自分の声で自分の名前を呼ばれるのって、妙な気分だな",
                    ),
                    (
                        "b",
                        "……同感。今日一日、互いのふりをして乗り切ろう。それが一番平和だと思う",
                    ),
                ],
                "mood_delta": {"a": -2, "b": 3},
                "affinity_delta": 3,
            },
            {
                "title": "いつもと違う目線",
                "narration": (
                    "{a}が台所の棚に手を伸ばして、思わず動きを止めた。"
                    "今の身体では、いつも届いていた場所の感覚がまるで違う。"
                    "何度か背伸びをする姿に気づいた{b}が、無言で横から手を伸ばして取ってやると、"
                    "{a}は複雑そうな顔で礼を言った。"
                ),
                "lines": [
                    ("a", "視界の高さが違うだけで、家の中が別物みたいだ"),
                    ("b", "この体、こまごました所が不便でしょ"),
                ],
                "mood_delta": {"a": 2, "b": 4},
                "affinity_delta": 4,
            },
            {
                "title": "勝手に出る癖",
                "narration": (
                    "朝の食堂。{a}が口を開くと出てくるのは{b}の声で、"
                    "考え込むときの仕草まで相手のものになっていた。"
                    "端から見れば完全に{b}本人なのに中身は{a}で、そのちぐはぐさに、"
                    "居合わせた住民は思わず笑いをこぼした。"
                ),
                "lines": [
                    (
                        "b",
                        "声も仕草もこっちのものなのに、中身が{a}なのは、不思議と分かるもんだね",
                    ),
                    ("a", "自分でも、喋るたびに少し驚いてるんだ"),
                ],
                "mood_delta": {"a": 3, "b": 5},
                "affinity_delta": 4,
            },
        ],
        "solo": [
            {
                "title": "一人の朝",
                "narration": (
                    "誰よりも早く目覚めた{a}は、静かな台所で自分のためだけに"
                    "お茶を淹れた。皆が起きてくる前の、この短い一人の時間が"
                    "案外気に入っている。"
                ),
                "lines": [
                    ("a", "……静かだな。誰も起きてこない、この台所の感じ、嫌いじゃない"),
                    (
                        "a",
                        "お茶は一杯だけ、自分のためだけに丁寧に淹れよう。今日は誰にも急かされない",
                    ),
                    (
                        "a",
                        "……よし、今日もいい日にしよう。まず、皆の分の湯を沸かすところから",
                    ),
                ],
                "mood_delta": {"a": 5},
            },
            {
                "title": "窓辺の読書",
                "narration": (
                    "昼下がり、{a}は窓辺の定位置で読みかけの本を開いた。"
                    "時々顔を上げて庭を眺め、またページへ戻る。静かな時間が"
                    "ゆっくり流れていった。"
                ),
                "lines": [("a", "この章、読み終わるのが惜しいな")],
                "mood_delta": {"a": 6},
            },
            {
                "title": "小さな片付け",
                "narration": (
                    "ふと思い立って、{a}は自分の棚の整理を始めた。懐かしい"
                    "手紙や、忘れていた小物が出てくるたびに手が止まり、"
                    "結局片付けより思い出話の方が長くなった。"
                ),
                "lines": [
                    ("a", "こんなものまで取ってあったんだ。……昔の手紙じゃない"),
                    ("a", "捨てるつもりで始めたのに、読んでる時間の方が長くなってる"),
                    (
                        "a",
                        "でも、まあ。懐かしい気持ちになれただけで、今日はよしとしよう",
                    ),
                ],
                "mood_delta": {"a": 3},
            },
            {
                "title": "夕方の散歩",
                "narration": (
                    "夕方、{a}は一人で下宿の周りを散歩した。誰かと一緒の"
                    "時間もいいけれど、自分の歩幅で歩く道は考えごとが"
                    "よく進む。"
                ),
                "lines": [("a", "たまには、こういう夕方もいいよね")],
                "mood_delta": {"a": 4},
            },
            {
                "title": "腕試しの一品",
                "narration": (
                    "台所が空いているのを見て、{a}は前から試したかった"
                    "レシピに一人で挑戦した。出来栄えは上々で、味見のつもりが"
                    "つい二口目まで進んでしまった。"
                ),
                "lines": [("a", "……これは、皆にも食べさせたいな")],
                "mood_delta": {"a": 7},
            },
        ],
        "trio": [
            {
                "title": "三人で囲む食卓",
                "narration": (
                    "夕食の支度が重なって、{a}と{b}と{c}は三人で食卓を囲んだ。"
                    "誰かの失敗談で笑い、誰かの自慢話に相づちを打ち、"
                    "気づけば食器を下げるのも忘れるくらい話が弾んだ。"
                ),
                "lines": [
                    ("a", "いただきます。三人揃うと、急に賑やかになるね"),
                    (
                        "b",
                        "支度が重なったおかげだね。でも、たまにはこういう夕食もいいな",
                    ),
                    ("c", "失敗談で笑うのはほどほどにしてほしいな"),
                    ("a", "ごめんごめん。でも、あの焦げたシチューの話は名作だったから"),
                    ("c", "じゃあ次は、腕を振るう番だね。今度は笑わせないから"),
                    ("b", "決まりだね。食器を下げるの、忘れるところだったよ"),
                ],
                "mood_delta": {"a": 5, "b": 5, "c": 5},
                "affinity_delta": 3,
            },
            {
                "title": "庭仕事は三人で",
                "narration": (
                    "伸び放題だった庭の手入れに、{a}と{b}と{c}が三人で取りかかった。"
                    "役割を決めたはずが、途中で道具の取り合いや休憩のお茶が挟まり、"
                    "終わる頃には三人ともほどよく疲れて、ほどよく笑っていた。"
                ),
                "lines": [
                    ("b", "一人でやるより、三倍はかどるね"),
                    ("a", "休憩も三倍になってる気がするけど"),
                    ("c", "それも含めて、ちょうどいいんだよ"),
                ],
                "mood_delta": {"a": 4, "b": 6, "c": 4},
                "affinity_delta": 3,
            },
            {
                "title": "試食会は満員",
                "narration": (
                    "喫茶店の新メニューの試食に、{a}と{b}と{c}の三人が駆り出された。"
                    "三者三様の感想が飛び交い、メモを取りながら真剣に言い合う様子は、"
                    "小さな会議のようだった。"
                ),
                "lines": [
                    ("c", "もう少し甘さ控えめがいいな"),
                    ("a", "じゃあこっちは、香りの方を推す"),
                    ("b", "意見が割れるのも、試食会らしくていいね"),
                ],
                "mood_delta": {"a": 5, "b": 4, "c": 6},
                "affinity_delta": 2,
            },
            {
                "title": "雨宿りの軒下",
                "narration": (
                    "夕立に降られた{a}と{b}と{c}は、下宿の軒下で雨宿りをした。"
                    "帰るに帰れず、三人で雨の庭を眺めながら、普段しないような"
                    "昔話がぽつぽつと出た。"
                ),
                "lines": [
                    ("a", "雨のおかげで、珍しい話が聞けたな"),
                    ("b", "もう少しだけ、降っててもいいかも"),
                    ("c", "……同感。たまには足止めも悪くない"),
                ],
                "mood_delta": {"a": 5, "b": 5, "c": 3},
                "affinity_delta": 4,
            },
            {
                "title": "ボードゲームの夜",
                "narration": (
                    "夜、{a}が持ち出したボードゲームに{b}と{c}が加わり、三人の"
                    "対戦が始まった。序盤の余裕が嘘のように終盤は白熱し、"
                    "負けた人の悔しがり方まで含めて、にぎやかな夜になった。"
                ),
                "lines": [
                    (
                        "b",
                        "うわ、最後の最後で逆転されるとは思わなかった。もう一戦。次は負けないよ",
                    ),
                    ("c", "その意気。でも今のは様子見だったから。次は本気を出すよ"),
                    (
                        "a",
                        "はいはい、二人とも熱くなるのはいいけど、明日の朝に響かない範囲でね",
                    ),
                    ("b", "あと一戦だけ。……負けた人が明日の朝食当番、ってことでどう？"),
                    ("c", "乗った。そっちこそ寝坊しないようにね"),
                    ("a", "賭けの対象が平和で何よりだよ。さあ、最後の一戦だよ"),
                ],
                "mood_delta": {"a": 6, "b": 3, "c": 6},
                "affinity_delta": 3,
            },
        ],
        "investigation": [
            {
                "title": "変化の記録",
                "narration": (
                    "{a}がノートを広げて、これまでの世界の変化を書き並べていた。"
                    "掟が変わった日、誰かの姿が変わった日。{b}も覗き込み、"
                    "偶然にしては出来すぎている、と二人は顔を見合わせた。"
                ),
                "lines": [
                    ("a", "ほら、ここ。変わるときは、いつも一瞬なんだ"),
                    ("b", "誰かが、まとめて書き換えてるみたいだね……"),
                    ("a", "日付を並べると、決まった間隔があるわけでもない"),
                    ("b", "気まぐれ、なのかな。それとも、何か見てるのかな"),
                ],
                "mood_delta": {"a": 2, "b": 1},
                "affinity_delta": 3,
            },
            {
                "title": "書き手の噂",
                "narration": (
                    "夕食の後、{a}と{b}は「この世界を書き換えている誰か」の噂話になった。"
                    "笑い話のつもりが、互いの目撃談が妙に符合して、最後は二人とも黙り込んだ。"
                ),
                "lines": [
                    ("b", "ねえ、本当にいるのかな。……書き換えてる誰か"),
                    ("a", "いるなら、一度でいいから理由を聞いてみたい"),
                    ("b", "聞いたら、答えてくれるのかな"),
                    ("a", "さあね。でも、黙って書き換えられるだけよりはいい"),
                ],
                "mood_delta": {"a": 1, "b": 2},
                "affinity_delta": 2,
            },
            {
                "title": "張り込みの夜",
                "narration": (
                    "掟が変わる瞬間を見届けようと、{a}と{b}は廊下の隅で夜更かしをした。"
                    "結局その夜は何も起きなかったが、空が明ける頃には、"
                    "二人とも「次こそは」という顔をしていた。"
                ),
                "lines": [
                    ("a", "今夜は外れか……。でも、絶対に尻尾を掴んでみせる"),
                    ("b", "付き合うよ。もう気になって仕方ないんだ"),
                    ("a", "次は、変わる前の様子をメモしておこう"),
                ],
                "mood_delta": {"a": 3, "b": 3},
                "affinity_delta": 4,
            },
        ],
        "confrontation": [
            {
                "title": "書き手への呼びかけ",
                "narration": (
                    "その夕方、{a}と{b}は部屋の真ん中に立って、誰もいないはずの"
                    "天井へ向かって声を上げた。掟が変わること、姿が変わること、その全部に"
                    "誰かの意志があるのなら、聞いてほしいことがあるのだ、と。"
                    "返事はなかった。けれど二人は、確かに「聞かれている」気がしていた。"
                ),
                "lines": [
                    ("a", "聞こえますか。この世界を書き換えている、あなたへ"),
                    ("b", "怒ってるんじゃないんです。ただ……理由が知りたいんです"),
                    ("a", "これからも変えるなら、せめて、時々は気配を見せてください"),
                ],
                "mood_delta": {"a": 4, "b": 4},
                "affinity_delta": 3,
            },
        ],
        "reaction": [
            {
                "title": "新しい姿を囲んで",
                "narration": (
                    "{target}の新しい姿に、{other}はしばらく目を丸くしていた。"
                    "驚きが収まると、興味津々といった様子で、ぐるりと一周眺めている。"
                ),
                "lines": [
                    ("other", "わ……！ す、すごい。本当に{target}さん？"),
                    ("target", "ど、どうかな……。似合ってる？"),
                    ("other", "うん、すごく新鮮。なんだか別人みたい"),
                ],
                "mood_delta": {"target": 5, "other": 4},
            },
        ],
        "reaction_solo": [
            {
                "title": "新しい姿",
                "narration": (
                    "{target}は変わったばかりの自分の姿を、鏡に映して確かめていた。"
                    "最初は戸惑っていたが、次第に表情が和らいでいく。"
                ),
                "lines": [
                    ("target", "……ふふ、悪くないかも。少し、この姿で過ごしてみよう")
                ],
                "mood_delta": {"target": 5},
            },
        ],
        # 住民の改変の直後(LLM で作れなかったとき)。昔からそうだったように過ごし、違和感はかすか
        "reality": [
            {
                "title": "いつもの一日",
                "narration": (
                    "{target}は、いつもと変わらない様子で過ごしている。"
                    "{other}も、それをごく当たり前のこととして眺めていた。"
                ),
                "lines": [
                    ("other", "{target}さん、今日もいつも通りだね"),
                    (
                        "target",
                        "うん、いつも通り。……あれ、いま何か変な感じがしたような",
                    ),
                ],
                "mood_delta": {"target": 2, "other": 2},
            },
        ],
        "reality_solo": [
            {
                "title": "いつもの一日",
                "narration": "{target}は、昔からそうだったように、いつもの一日を過ごしていた。",
                "lines": [
                    ("target", "……うん、いつも通り。前からずっと、こうだったよね")
                ],
                "mood_delta": {"target": 2},
            },
        ],
    },
    "en": {
        "pair": [
            {
                "title": "At the Breakfast Table",
                "narration": (
                    "The morning dining room. Thanks to the toast {a} made, breakfast was a "
                    "little livelier than usual."
                ),
                "lines": [
                    (
                        "b",
                        "Thanks for the food. ...Mm, the toast is especially good today.",
                    ),
                    (
                        "a",
                        "I got the timing just right. I burned it yesterday, so I was careful.",
                    ),
                    (
                        "b",
                        "Honestly, I didn't mind the burnt one either. It was toasty.",
                    ),
                    ("a", "Come on, no kind lies. ...But thanks."),
                    ("b", "It's not a lie. I'm looking forward to tomorrow's too."),
                ],
                "mood_delta": {"a": 5, "b": 4},
                "affinity_delta": 3,
            },
            {
                "title": "Watering Duty",
                "narration": (
                    "{a} and {b} watered the garden together. The seedlings planted last week "
                    "were showing tiny sprouts."
                ),
                "lines": [
                    ("a", "Look, they've sprouted."),
                    ("b", "They really have. I can't wait to see them grow."),
                ],
                "mood_delta": {"a": 4, "b": 5},
                "affinity_delta": 2,
            },
            {
                "title": "A Small Misunderstanding",
                "narration": (
                    "{a} and {b} squabbled a little over whose turn it was at the shared "
                    "washing machine. By evening they had both apologized, and they seemed "
                    "closer than before."
                ),
                "lines": [
                    (
                        "a",
                        "About the washing machine earlier... I think I got the order wrong.",
                    ),
                    ("b", "Oh, that. Actually, I set the timer wrong too."),
                    ("a", "So we were both at fault. I said too much earlier. Sorry."),
                    ("b", "Me too. ...Let's have some tea before it gets cold."),
                    (
                        "a",
                        "Sure. Let's put a schedule on the door so we never fight again.",
                    ),
                ],
                "mood_delta": {"a": -3, "b": -2},
                "affinity_delta": 1,
            },
            {
                "title": "A Recommended Book",
                "narration": (
                    "{a} lent {b} a book. {b} seemed a little flustered, but happy."
                ),
                "lines": [
                    ("a", "No due date. Just return it when you finish."),
                    ("b", "Thank you. I'll take good care of it."),
                ],
                "mood_delta": {"a": 3, "b": 6},
                "affinity_delta": 4,
            },
            {
                "title": "The Cafe's New Menu",
                "narration": (
                    "{a} and {b} were roped into taste-testing the cafe's new menu, spending "
                    "the afternoon earnestly working out a review."
                ),
                "lines": [
                    ("b", "How should we describe this sauce?"),
                    ("a", "How about 'nostalgic yet new'?"),
                ],
                "mood_delta": {"a": 6, "b": 5},
                "affinity_delta": 3,
            },
            {
                "title": "An Umbrella on a Rainy Day",
                "narration": (
                    "When {b} got caught in a sudden shower, {a} went to the station with an "
                    "umbrella. Laughing at their wet shoulders, the two walked home together."
                ),
                "lines": [
                    (
                        "b",
                        "Whoa, it's pouring all of a sudden... I can't leave the station.",
                    ),
                    (
                        "a",
                        "I came to get you. The sky looked suspicious, so I brought two umbrellas.",
                    ),
                    ("b", "You saved me... Thanks for coming. Are your shoulders wet?"),
                    (
                        "a",
                        "I'm fine. Let's go before we catch a cold. There's warm soup today.",
                    ),
                    ("b", "Sounds great. ...Next time, it's my turn to pick you up."),
                ],
                "mood_delta": {"a": 4, "b": 7},
                "affinity_delta": 5,
            },
            {
                "title": "Voices in the Hallway",
                "narration": (
                    "Running into each other in the hallway at night, {a} and {b} ended up "
                    "talking for a long time. Both thought moments like this were the most "
                    "relaxing."
                ),
                "lines": [
                    ("a", "Oh, you're still up? ...Can't sleep?"),
                    ("b", "A little. What about you, at this hour?"),
                    (
                        "a",
                        "Just came for some water. ...But if I have company, I'll stay up a bit.",
                    ),
                    ("b", "Time flies when we talk. Look how late it is."),
                    (
                        "a",
                        "A secret late night is nice once in a while. We'll both oversleep.",
                    ),
                ],
                "mood_delta": {"a": 5, "b": 5},
                "affinity_delta": 3,
            },
            {
                "title": "Planning the Shopping",
                "narration": (
                    "{a} and {b} discussed the weekend shopping list. Talk of supplies turned "
                    "into everyone's favorite foods, and the list doubled in length."
                ),
                "lines": [
                    ("a", "Let's add their favorite too."),
                    ("b", "Then dessert goes on the list as well."),
                ],
                "mood_delta": {"a": 3, "b": 3},
                "affinity_delta": 2,
            },
        ],
        "swap": [
            {
                "title": "A Double Take at the Mirror",
                "narration": (
                    "In front of the bathroom mirror, {a} did a double take. The person in the "
                    "mirror was unmistakably {b}, and {a} touched their own cheek to make sure. "
                    "{b} passed by behind and smiled wryly at their own startled face."
                ),
                "lines": [
                    (
                        "a",
                        "No matter how many times I look, the mirror shows {b}. Even my cheek feels borrowed.",
                    ),
                    (
                        "b",
                        "Being stared at with that face is unsettling for me too. Don't make weird faces.",
                    ),
                    (
                        "a",
                        "Sorry, sorry. But hearing my name in my own voice feels so strange.",
                    ),
                    (
                        "b",
                        "...Same. Let's just pretend to be each other today. That's the most peaceful way.",
                    ),
                ],
                "mood_delta": {"a": -2, "b": 3},
                "affinity_delta": 3,
            },
            {
                "title": "A Different Eye Level",
                "narration": (
                    "{a} reached for a kitchen shelf and froze. In this body, the familiar "
                    "places felt entirely different. Noticing {a} stretching on tiptoe, {b} "
                    "silently reached over and got it, and {a} thanked them with a complicated "
                    "expression."
                ),
                "lines": [
                    (
                        "a",
                        "Just a different eye level makes the house feel like a different place.",
                    ),
                    ("b", "This body is inconvenient in little ways, isn't it?"),
                ],
                "mood_delta": {"a": 2, "b": 4},
                "affinity_delta": 4,
            },
            {
                "title": "Habits That Slip Out",
                "narration": (
                    "The morning dining room. When {a} opened their mouth, {b}'s voice came "
                    "out, and even the thinking gestures were {b}'s. From the outside it was "
                    "{b} through and through, yet {a} was inside, and the mismatch made the "
                    "others burst out laughing."
                ),
                "lines": [
                    (
                        "b",
                        "The voice and gestures are mine, but somehow I can tell it's {a} inside.",
                    ),
                    ("a", "I surprise myself a little every time I talk."),
                ],
                "mood_delta": {"a": 3, "b": 5},
                "affinity_delta": 4,
            },
        ],
        "solo": [
            {
                "title": "A Morning Alone",
                "narration": (
                    "Waking before anyone else, {a} made tea just for themself in the quiet "
                    "kitchen. This short time alone before everyone gets up is surprisingly "
                    "precious."
                ),
                "lines": [
                    (
                        "a",
                        "...So quiet. I don't mind the kitchen like this, before anyone's up.",
                    ),
                    (
                        "a",
                        "One cup, brewed carefully, just for me. Nobody's rushing me today.",
                    ),
                    (
                        "a",
                        "...Okay, let's make today a good day. First, boil water for everyone.",
                    ),
                ],
                "mood_delta": {"a": 5},
            },
            {
                "title": "Reading by the Window",
                "narration": (
                    "In the afternoon, {a} opened an unfinished book at the usual spot by the "
                    "window, now and then looking up at the garden before returning to the "
                    "page. Quiet time passed slowly."
                ),
                "lines": [("a", "I don't want this chapter to end.")],
                "mood_delta": {"a": 6},
            },
            {
                "title": "A Little Tidying",
                "narration": (
                    "On a whim, {a} started sorting the shelves. Every old letter or forgotten "
                    "trinket made {a} pause, and the reminiscing took longer than the cleaning."
                ),
                "lines": [
                    ("a", "I kept this too? ...Isn't this an old letter?"),
                    (
                        "a",
                        "I started to throw things out, but I'm spending more time reading.",
                    ),
                    ("a", "Well. Feeling nostalgic is enough for today."),
                ],
                "mood_delta": {"a": 3},
            },
            {
                "title": "An Evening Walk",
                "narration": (
                    "In the evening, {a} took a walk around the boarding house alone. Time with "
                    "others is nice, but walking at one's own pace is good for thinking."
                ),
                "lines": [("a", "An evening like this is nice once in a while.")],
                "mood_delta": {"a": 4},
            },
            {
                "title": "Testing a Recipe",
                "narration": (
                    "Seeing the kitchen free, {a} tried a recipe they'd wanted to make for a "
                    "while. It turned out great, and a taste turned into a second bite."
                ),
                "lines": [("a", "...I want everyone to try this.")],
                "mood_delta": {"a": 7},
            },
        ],
        "trio": [
            {
                "title": "Dinner for Three",
                "narration": (
                    "Their dinner prep overlapped, so {a}, {b} and {c} ate together. They "
                    "laughed at one blunder, nodded along to one boast, and talked so much "
                    "they forgot to clear the dishes."
                ),
                "lines": [
                    ("a", "Let's eat. With the three of us, it gets lively fast."),
                    (
                        "b",
                        "Thanks to our prep overlapping. Dinner like this is nice sometimes.",
                    ),
                    ("c", "Go easy on laughing at my blunders, please."),
                    ("a", "Sorry, sorry. But the burnt stew story is a classic."),
                    ("c", "Then next time I'll cook. And you won't be laughing."),
                    ("b", "It's a deal. I almost forgot to clear the dishes."),
                ],
                "mood_delta": {"a": 5, "b": 5, "c": 5},
                "affinity_delta": 3,
            },
            {
                "title": "Gardening for Three",
                "narration": (
                    "{a}, {b} and {c} took on the overgrown garden together. They had split "
                    "the work, but tool squabbles and tea breaks crept in, and by the end all "
                    "three were pleasantly tired and pleasantly laughing."
                ),
                "lines": [
                    ("b", "Three times faster than doing it alone."),
                    ("a", "Feels like three times the breaks too."),
                    ("c", "That's what makes it just right."),
                ],
                "mood_delta": {"a": 4, "b": 6, "c": 4},
                "affinity_delta": 3,
            },
            {
                "title": "A Packed Tasting",
                "narration": (
                    "{a}, {b} and {c} were drafted to taste the cafe's new menu. Opinions "
                    "flew in every direction, and with all the earnest note-taking it looked "
                    "like a little meeting."
                ),
                "lines": [
                    ("c", "I'd like it a little less sweet."),
                    ("a", "Then I'm voting for the aroma."),
                    ("b", "Split opinions make it feel like a real tasting."),
                ],
                "mood_delta": {"a": 5, "b": 4, "c": 6},
                "affinity_delta": 2,
            },
            {
                "title": "Sheltering Under the Eaves",
                "narration": (
                    "Caught in a sudden shower, {a}, {b} and {c} sheltered under the eaves of "
                    "the house. Unable to leave, they watched the rainy garden and old stories "
                    "came out one by one."
                ),
                "lines": [
                    ("a", "Thanks to the rain, I heard some rare stories."),
                    ("b", "It could keep raining a little longer."),
                    ("c", "...Agreed. Getting stuck isn't so bad sometimes."),
                ],
                "mood_delta": {"a": 5, "b": 5, "c": 3},
                "affinity_delta": 4,
            },
            {
                "title": "Board Game Night",
                "narration": (
                    "At night, {b} and {c} joined the board game {a} brought out. The early "
                    "calm gave way to a heated finish, and the losers' frustration made it a "
                    "lively night."
                ),
                "lines": [
                    (
                        "b",
                        "I can't believe I got overtaken at the very end. One more round.",
                    ),
                    (
                        "c",
                        "That's the spirit. But that was just a warm-up. Now I'm serious.",
                    ),
                    (
                        "a",
                        "Okay, okay, get fired up, just don't ruin tomorrow morning.",
                    ),
                    ("b", "Just one more. ...Loser makes breakfast tomorrow. Deal?"),
                    ("c", "Deal. Don't oversleep yourself."),
                    ("a", "At least the stakes are peaceful. Okay, last round."),
                ],
                "mood_delta": {"a": 6, "b": 3, "c": 6},
                "affinity_delta": 3,
            },
        ],
        "investigation": [
            {
                "title": "A Record of Changes",
                "narration": (
                    "{a} spread out a notebook listing every change the world had gone "
                    "through: the day a rule changed, the day someone's look changed. {b} "
                    "leaned in, and the two exchanged a look: it was too neat to be chance."
                ),
                "lines": [
                    (
                        "a",
                        "Look here. Whenever things change, it happens in an instant.",
                    ),
                    ("b", "It's like someone is rewriting everything at once..."),
                    ("a", "Line up the dates and there's no fixed interval either."),
                    ("b", "A whim, maybe? Or is someone watching?"),
                ],
                "mood_delta": {"a": 2, "b": 1},
                "affinity_delta": 3,
            },
            {
                "title": "Rumors of the Writer",
                "narration": (
                    "After dinner, {a} and {b} drifted into rumors about someone rewriting "
                    "this world. It started as a joke, but their sightings matched too well, "
                    "and in the end both fell silent."
                ),
                "lines": [
                    (
                        "b",
                        "Hey, do you think they really exist? Whoever is rewriting things?",
                    ),
                    ("a", "If they do, I'd like to ask why. Just once."),
                    ("b", "Would they even answer?"),
                    ("a", "Who knows. Still better than being rewritten in silence."),
                ],
                "mood_delta": {"a": 1, "b": 2},
                "affinity_delta": 2,
            },
            {
                "title": "The Stakeout",
                "narration": (
                    "Hoping to witness the moment a rule changed, {a} and {b} stayed up in "
                    "a corner of the hallway. Nothing happened that night, but by dawn both "
                    "wore the same look: next time for sure."
                ),
                "lines": [
                    ("a", "Nothing tonight... but I'll catch them in the act."),
                    ("b", "Count me in. I can't stop thinking about it now."),
                    ("a", "Next time, let's note how things look before they change."),
                ],
                "mood_delta": {"a": 3, "b": 3},
                "affinity_delta": 4,
            },
        ],
        "confrontation": [
            {
                "title": "Calling Out to the Writer",
                "narration": (
                    "That evening, {a} and {b} stood in the middle of the room and raised "
                    "their voices toward a ceiling where no one should be. If someone willed "
                    "every changed rule and every changed look, there was something they "
                    "wanted that someone to hear. No answer came. Yet both were sure they "
                    "were being heard."
                ),
                "lines": [
                    ("a", "Can you hear us? You, the one rewriting this world."),
                    ("b", "We're not angry. We just... want to know why."),
                    (
                        "a",
                        "If you keep changing things, at least let us sense you now and then.",
                    ),
                ],
                "mood_delta": {"a": 4, "b": 4},
                "affinity_delta": 3,
            },
        ],
        "reaction": [
            {
                "title": "Around the New Look",
                "narration": (
                    "{other} stared wide-eyed at {target}'s new look for a while. Once the "
                    "surprise settled, {other} circled around, looking on with keen interest."
                ),
                "lines": [
                    (
                        "other",
                        "Wow...! Th-that's amazing. Is that really you, {target}?",
                    ),
                    ("target", "H-how is it...? Does it suit me?"),
                    ("other", "Yes, it's so fresh. You look like a different person."),
                ],
                "mood_delta": {"target": 5, "other": 4},
            },
        ],
        "reaction_solo": [
            {
                "title": "A New Look",
                "narration": (
                    "{target} checked the freshly changed look in the mirror. Bewildered at "
                    "first, {target}'s expression gradually softened."
                ),
                "lines": [
                    ("target", "...Heh, not bad. Maybe I'll spend some time like this.")
                ],
                "mood_delta": {"target": 5},
            },
        ],
        "reality": [
            {
                "title": "Just Another Day",
                "narration": (
                    "{target} went about the day as usual, and {other} took it as the "
                    "most natural thing in the world."
                ),
                "lines": [
                    ("other", "Same as always today, huh, {target}?"),
                    (
                        "target",
                        "Yeah, same as always. ...Huh, did something feel off just now?",
                    ),
                ],
                "mood_delta": {"target": 2, "other": 2},
            },
        ],
        "reality_solo": [
            {
                "title": "Just Another Day",
                "narration": "{target} spent an ordinary day, as if it had always been this way.",
                "lines": [
                    ("target", "...Yeah, same as always. It's always been like this.")
                ],
                "mood_delta": {"target": 2},
            },
        ],
    },
}
