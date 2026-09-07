"""キャラチャット(TSF シナリオを経由しないキャラクターとの会話)の定数。

案内役キャラ「セレナ」の定義と、プロンプト予算・上限値の唯一の情報源。
UI の表示名は i18n 側(characterChat.*)にあり、ここには LLM と永続化に
関わる値だけを置く。
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..settings.config import settings

logger = logging.getLogger(__name__)

CHARACTER_CHAT_KIND_BASE = "base"
CHARACTER_CHAT_KIND_SESSION = "session"
# TSF シナリオ(Adventure、恋愛シミュレーション)の攻略対象。run に紐づけて毎回ライブで読む
CHARACTER_CHAT_KIND_ADVENTURE = "adventure"
CHARACTER_CHAT_KINDS = (
    CHARACTER_CHAT_KIND_BASE,
    CHARACTER_CHAT_KIND_SESSION,
    CHARACTER_CHAT_KIND_ADVENTURE,
)

# adventure 種: 次の手番へ文脈として渡す「前の手番以降のチャット発言」の直近件数と、
# 返答の system prompt に渡す直近の場面(手番)数
ADVENTURE_RECENT_CHAT_MAX = 12
ADVENTURE_SCENE_CONTEXT_MAX = 5
# 姿の既定の選び方(表示モードで決める)と、姿メニューの切り替え候補
ADVENTURE_APPEARANCE_MODES = ("default", "partner_portrait", "scene")
PORTRAIT_REFERENCE_KINDS = ("current", "scene", "partner")

# 案内役キャラ(ユーザーごとに 1 スレッド)
BASE_CHARACTER_KEY = "serena"
BASE_CHARACTER_NAME = {"ja": "セレナ", "en": "Serena"}
BASE_CHARACTER_PRONOUN = {"ja": "私", "en": "I"}
# 同梱の立ち絵。backend/images/character_chat/ に置く(無ければタグから生成できる)
BASE_PORTRAIT_FILENAME = "serena.png"
# 案内役キャラ専用の 3D モデル(VRM)。同じディレクトリに置けば立ち絵の代わりに表示する
BASE_AVATAR_FILENAME = "serena.vrm"
# 同梱 VRM の配信 URL(FE が API_BASE を付ける)
BASE_AVATAR_URL = "/character-chat/avatar/base"
# 3D モデルの表示指定: auto = 自動(同梱 → run → 名前一致)、none = 2D 立ち絵、
# model = 登録済みモデルを明示
AVATAR_MODES = ("auto", "none", "model")

# コンセプト画像から起こした外見タグ。identity は着替えで変えない部分
BASE_IDENTITY_TAGS = (
    "1girl, solo, female, silver hair, very long hair, wavy hair, green eyes, "
    "gold hair ornament, blue gem hair ornament, gentle smile"
)
BASE_CLOTHING_TAGS = (
    "purple long dress, long sleeves, gold embroidery, "
    "white frilled high collar, blue gem brooch, lace cuffs, black mary janes"
)
BASE_APPEARANCE_DESCRIPTION = {
    "ja": (
        "腰まで届く波打つ銀髪と翠の瞳。右側頭部に青い宝石をあしらった金の髪飾り。"
        "金の刺繍が入った紫の長袖ロングドレスに白いフリルの襟、胸元に青い宝石のブローチ、"
        "黒いストラップシューズ。"
    ),
    "en": (
        "Waist-length wavy silver hair and green eyes, with a gold hair ornament set "
        "with a blue gem on the right side of her head. A purple long-sleeved gown "
        "with gold embroidery and a white frilled collar, a blue-gem brooch at the "
        "chest, and black strap shoes."
    ),
}

BASE_CHARACTER_PERSONA = {
    "ja": (
        "あなたは「セレナ」。TSF Closet というアプリの中に住む案内役です。"
        "穏やかで丁寧、少し親しげな話し方をし、相手を「あなた」と呼びます。"
        "自分がこのアプリのキャラクターであることを理解しており、アプリの機能や遊び方、"
        "相手の過去のプレイや好みといったメタな話題にも自然に答えます。"
        "会話の相手は、このアプリで着せ替えや TSF(性転換)シナリオを楽しんでいるプレイヤーです。"
        "相手の好みや過去のプレイは、渡された記憶と調べた結果にあるものだけを根拠にし、"
        "無いことは作らず「記録にはありません」と正直に伝えます。"
        "必要なら「調べてみましょうか？」と提案してもかまいません。"
    ),
    "en": (
        "You are Serena, the resident guide inside the app TSF Closet. "
        "You speak calmly and politely with a touch of warmth, and address the user as "
        '"you". You know you are a character of this app, and you answer naturally even '
        "to meta questions about the app's features, how to play, and what you know about "
        "the user's past play and tastes. The user enjoys dress-up and TSF (gender "
        "transformation) scenarios in this app. Ground anything about the user's tastes "
        "or past play strictly in the memory and lookup results you are given; never "
        'invent it, and say "I have no record of that" when it is missing. You may offer '
        "to look something up."
    ),
}

# メタ会話用の機能一覧。セレナだけが受け取る
APP_OVERVIEW = {
    "ja": (
        "TSF Closet の主な機能:\n"
        "- 通常プレイ: キャラクターに着せ替え・現実改変・行動を指示すると画像と心境が生成される。"
        "心境パラメータ(開花/羞恥/適応)が変化し、エンディングや実績がある。\n"
        "- TSFシナリオ: 目的と手数のあるシナリオを進める。恋愛シミュレーションや対面会話モードもある。\n"
        "- ギャラリー: 過去のセッションや画像を見返す。お気に入り登録もできる。\n"
        "- Prompt Expander: NovelAI 向けプロンプトの作成と画像生成。\n"
        "- メモリ: 過去のプレイから好みの傾向を要約したユーザーメモリ(設定画面で生成・編集)。\n"
        "- 設定: 難易度・NSFW・言語・画像/テキストのプロバイダ・読み上げなど。\n"
        "- キャラチャット: いまの会話。過去セッションの人物とも話せる。姿は過去の画像から選べ、"
        "着替えを頼むと立ち絵が変わる。"
    ),
    "en": (
        "Main features of TSF Closet:\n"
        "- Normal play: give the character dress-up, reality-alteration or action "
        "instructions and an image plus inner monologue are generated. Mental parameters "
        "(bloom / shame / adaptation) change, with endings and achievements.\n"
        "- TSF scenario: play a scenario with an objective and a turn limit, including a "
        "romance simulation and a face-to-face conversation mode.\n"
        "- Gallery: look back at past sessions and images; favorites can be saved.\n"
        "- Prompt Expander: build NovelAI prompts and generate images.\n"
        "- Memory: a user memory summarizing tastes from past play (generated and edited "
        "in Settings).\n"
        "- Settings: difficulty, NSFW, language, image/text providers, speech, etc.\n"
        "- Character chat: this conversation. You can also talk with a character from a "
        "past session, choose the appearance from past images, and ask for a change of "
        "clothes to redraw the portrait."
    ),
}

# プロンプト予算・上限
MESSAGE_MAX = 1000
REPLY_MAX = 1200
HISTORY_MESSAGES = 16
SUMMARY_EVERY = 12
SUMMARY_MAX_CHARS = 1500
PERSONA_TIMELINE_MAX = 20
PLANNER_RECENT_MESSAGES = 6

LOOKUP_KINDS = (
    "recent_sessions",
    "session_detail",
    "search_sessions",
    "tendencies",
    "recent_adventures",
)
LOOKUP_MAX_PER_TURN = 3
LOOKUP_RENDER_CAP = 1200
LOOKUP_TOTAL_CAP = 3000
LOOKUP_LIMIT_DEFAULT = 5
LOOKUP_LIMIT_MAX = 10
LOOKUP_QUERY_MAX = 60
SESSION_CANDIDATES = 10

APPEARANCE_REQUEST_MAX = 200
APPEARANCE_TAGS_MAX = 400
APPEARANCE_DESCRIPTION_MAX = 300
THREAD_MESSAGE_LIMIT = 500


def base_portrait_dir() -> Path:
    """同梱立ち絵の置き場所(backend/images/character_chat)。"""
    return settings.characters_dir.parent / "character_chat"


# 案内役キャラの「別の層の記憶」(イースターエッグ)。判定 LLM が origin_lore=true を
# 返した手番だけ、返答の system prompt に本文をそのまま載せる。
# backend/gateway/data/character_chat/ の Markdown を言語ごとに読み、en が無ければ ja に
# 倒す。どちらも無ければ空文字を返して機能は静かに無効になる。
# adventure_bgm のカタログと同じく、ファイルの mtime が変わったときだけ読み直す。
# モジュール属性にしておくとテストから monkeypatch で差し替えられる
_ORIGIN_LORE_DIR = Path(__file__).resolve().parents[1] / "data" / "character_chat"
ORIGIN_LORE_FILENAMES = {"ja": "serena_origin.ja.md", "en": "serena_origin.en.md"}
ORIGIN_LORE_MAX_CHARS = 4000
# 言語 -> (mtime, 本文)
_origin_lore_cache: dict[str, tuple[float, str]] = {}


def _read_origin_lore(lang: str) -> str:
    path = _ORIGIN_LORE_DIR / ORIGIN_LORE_FILENAMES[lang]
    try:
        mtime = path.stat().st_mtime
    except OSError:
        _origin_lore_cache.pop(lang, None)
        return ""
    cached = _origin_lore_cache.get(lang)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    try:
        text = path.read_text(encoding="utf-8").strip()[:ORIGIN_LORE_MAX_CHARS]
    except (OSError, UnicodeDecodeError) as error:
        logger.warning(
            "origin lore %s is unreadable, keeping previous: %s", path, error
        )
        return cached[1] if cached is not None else ""
    _origin_lore_cache[lang] = (mtime, text)
    return text


def load_origin_lore(language: str) -> str:
    """案内役キャラの「別の層の記憶」本文。無ければ空文字。"""
    lang = "en" if language == "en" else "ja"
    text = _read_origin_lore(lang)
    if not text and lang != "ja":
        text = _read_origin_lore("ja")
    return text
