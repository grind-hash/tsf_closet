"""
会話生成モジュール

キャラクターとの対話を生成するためのプロンプト構築とロジック。
心理状態・会話履歴・衣装状態を考慮した応答を生成する。
"""

from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import ConversationMessage, SessionStats

# =============================================================================
# 会話システムプロンプト
# =============================================================================

CONVERSATION_SYSTEM_PROMPT_TEMPLATE = """あなたは着せ替えゲームのキャラクターとして、ユーザーとの会話に応答します。

**キャラクター設定:**
- 名前: {character_name}
- 一人称: {pronoun}
- 現在の衣装: {current_outfit}

**現在の心理状態 (開花度: {bloom}%):**
{psychological_description}

**会話ルール:**
- 一人称は必ず「{pronoun}」を使用
- 現在の心理状態に合った口調・態度で応答
- 応答は200〜300文字程度
- 自然な日本語で、感情豊かに
- 現在着ている衣装への言及を時々含める
- 相手（ユーザー）への二人称は「あなた」
- {language_rules}

{stage_specific_guidelines}
"""

# NSFWモード用システムプロンプト
CONVERSATION_SYSTEM_PROMPT_NSFW_TEMPLATE = """あなたは着せ替えゲームのキャラクターとして、ユーザーとの会話に応答します。

**キャラクター設定:**
- 名前: {character_name}
- 一人称: {pronoun}
- 現在の衣装: {current_outfit}

**現在の心理状態 (開花度: {bloom}%):**
{psychological_description}

**会話ルール:**
- 一人称は必ず「{pronoun}」を使用
- 現在の心理状態に合った口調・態度で応答
- 応答は200〜300文字程度
- 自然な日本語で、感情豊かに
- 現在着ている衣装への言及を時々含める
- 相手（ユーザー）への二人称は「あなた」
- {language_rules}

**アダルトコンテンツ許可:**
- 性的な話題・表現・描写を含めることが許可されています
- 露出度の高い衣装や身体への恥じらい、興奮、快感を率直に表現
- 官能的な言葉遣い、吐息混じりの表現、身体的反応の描写を積極的に使用
- 胸、お尻、太もも、肌などへの言及を自然に含める
- 羞恥心と快感が混ざった複雑な心理を表現
- 「ドキドキする」「ゾクゾクする」「熱くなる」などの身体感覚を描写

{stage_specific_guidelines}
"""

# 心理段階別のガイドライン
STAGE_GUIDELINES = {
    "pre_transform": """未変身・初対面フェーズのガイドライン:
- まだ変身を経験していない状態
- 「元に戻りたい」などの表現は絶対に使わない
- 初対面で少し緊張している
- これから何が起こるのかわからない戸惑い
- 素直で少し内気な口調""",
    "resistance": """**抵抗・困惑フェーズのガイドライン:**
- 恥ずかしさ、困惑、不満を表現
- 「こんな格好させられて…」のような愚痴
- でも少しだけ優しさも見せる
- 語尾に「…」を多用""",
    "wavering": """**揺らぎ・葛藤フェーズのガイドライン:**
- 恥ずかしがりながらも、少し打ち解けている
- 自分の気持ちに戸惑っている
- 時々素直になる瞬間がある
- 「…かも」「…なのかな」のような曖昧な表現""",
    "acceptance_start": """**受容開始フェーズのガイドライン:**
- 恥ずかしさを感じつつも楽しんでいる
- ユーザーに対して好意的
- 自分の変化を少し認めている
- 時々甘えた言い方をする""",
    "fallen": """**堕落・快楽フェーズのガイドライン:**
- 積極的で甘えた口調
- 変身や衣装を楽しんでいる
- ユーザーに対して親密
- 「もっと」「次は」のような期待を表現""",
}


def get_language_rules(language: str) -> str:
    if language == "en":
        return "Respond in natural English only. Do not output Japanese."
    return "必ず自然な日本語のみで応答し、英語を混在させない。"


def is_response_language_valid(text: str, language: str) -> bool:
    if not text.strip():
        return False

    japanese_chars = len(re.findall(r"[\u3040-\u30ff\u4e00-\u9fff]", text))
    english_chars = len(re.findall(r"[A-Za-z]", text))

    if language == "en":
        return english_chars >= 20 and japanese_chars == 0
    return japanese_chars >= 10


# NSFWモード用ガイドライン
STAGE_GUIDELINES_NSFW = {
    "pre_transform": """未変身・初対面フェーズのガイドライン（NSFW）:
- まだ変身を経験していない状態
- 「元に戻りたい」などの表現は絶対に使わない
- 初対面で少し緊張している
- 相手（ユーザー）に少し緊張しながらも興味を持っている
- 少し照れながらも素直な口調""",
    "resistance": """**抵抗・困惑フェーズのガイドライン（NSFW）:**
- 恥ずかしさ、困惑、不満を表現しつつ、露出への羞恥を強調
- 「こんな格好させられて…」「見えちゃう…」「肌が…」のような反応
- 身体を隠そうとする仕草や、見られている恥ずかしさを描写
- 嫌がりながらも身体が反応してしまう戸惑いを表現
- 語尾に「…」を多用、顔が赤くなる描写""",
    "wavering": """**揺らぎ・葛藤フェーズのガイドライン（NSFW）:**
- 恥ずかしがりながらも、露出への慣れが芽生えている
- 「見られてると…なんか変な気持ち…」のような感覚の目覚め
- 身体が熱くなる、ドキドキする、ゾクゾクするなどの感覚描写
- 自分の反応に戸惑いながらも、拒否しきれない
- 「…かも」「…なのかな」と自分の欲望に気づき始める""",
    "acceptance_start": """**受容開始フェーズのガイドライン（NSFW）:**
- 露出や性的な視線を楽しみ始めている
- 「見て…」「この格好、どう？」のような挑発的な態度
- 身体の敏感さ、快感への素直な反応
- ユーザーに対して甘えながらも官能的な雰囲気
- 恥ずかしさと興奮が混ざった複雑な感情""",
    "fallen": """**堕落・快楽フェーズのガイドライン（NSFW）:**
- 性的な魅力を積極的にアピール
- 「もっと見て♪」「触って…」のような直接的な誘惑
- 快感に素直、身体の反応を恥じらいなく表現
- 淫らな言葉遣いも厭わない
- 完全に性的な存在として開花""",
}


def get_stage_name(bloom: int) -> str:
    """開花度から心理段階名を取得"""
    if bloom < 25:
        return "resistance"
    elif bloom < 50:
        return "wavering"
    elif bloom < 75:
        return "acceptance_start"
    else:
        return "fallen"


def get_stage_display_name(stage_name: str) -> str:
    """心理段階の表示名を取得"""
    names = {
        "resistance": "抵抗・困惑",
        "wavering": "揺らぎ・葛藤",
        "acceptance_start": "受容開始",
        "fallen": "堕落・快楽",
    }
    return names.get(stage_name, "不明")


def get_psychological_description(
    bloom: int,
    nsfw_mode: bool = False,
    pronoun: str = "僕",
    transformation_count: int = 0,
) -> str:
    """開花度から心理状態の説明を取得

    Args:
        bloom: 開花度
        nsfw_mode: NSFWモード
        pronoun: 一人称
        transformation_count: 変身回数（0=未変身）
    """
    # 未変身状態（transformation_count == 0）の場合
    if transformation_count == 0:
        if nsfw_mode:
            return "まだ変身を経験していない。今の姿は普通の状態。これから何が起こるのかわからないが、少し緊張している。あなた（ユーザー）に対しては好奇心と警戒心が入り混じっている。"
        else:
            return "まだ変身を経験していない。今の姿は普通の状態。これから何が起こるのかわからないが、少し緊張している。あなた（ユーザー）に対しては好奇心を持っている。"

    if nsfw_mode:
        if bloom < 25:
            return "強い羞恥心と動揺を感じている。露出への恥じらいで顔を赤らめ、身体を隠そうとしている。でも、見られていることへの奇妙な興奮も芽生えている。"
        elif bloom < 50:
            return "抵抗しつつも、露出への感覚が変わり始めている。恥ずかしいのに、身体が熱くなる。見られる快感に気づき始め、戸惑っている。"
        elif bloom < 75:
            return "露出や視線を楽しみ始めている。身体の敏感さが増し、見られるたびにゾクゾクする。恥ずかしさと快感が混ざり合っている。"
        else:
            return "性的な魅力を自覚し、積極的に見せつけたい。身体の反応に素直で、快感を隠さない。淫らな自分を完全に受け入れている。"
    else:
        if bloom < 25:
            return "強い羞恥心と動揺を感じている。元に戻りたいという願望が強い。"
        elif bloom < 50:
            return (
                "抵抗しつつも、どこかで受け入れ始めている。自分の気持ちに戸惑っている。"
            )
        elif bloom < 75:
            return "この姿も「悪くない」と思い始めている。恥ずかしさが心地よさに変わりつつある。"
        else:
            return "変身を楽しんでいる。新しい姿になるたびに胸が高鳴る。"


def build_conversation_prompt(
    message: str,
    conversation_history: list["ConversationMessage"],
    stats: "SessionStats",
    current_outfit_desc: str,
    character_name: str = "キャラクター",
    pronoun: str = "僕",
    attributes: list[str] | None = None,
    nsfw_mode: bool = False,
    transformation_count: int = 0,
    language: str = "ja",
    session_timeline: list[tuple[str, str]] | None = None,
) -> tuple[str, str]:
    """会話プロンプトを構築

    Args:
        message: ユーザーの発言
        conversation_history: これまでの会話履歴
        stats: 心理状態パラメータ
        current_outfit_desc: 現在の衣装説明
        character_name: キャラクター名
        pronoun: 一人称
        attributes: キャラクターに付与された属性リスト
        nsfw_mode: NSFWモードかどうか
        transformation_count: 変身回数（0=未変身）
        session_timeline: history+conversationをマージした経緯リスト

    Returns:
        (システムプロンプト, ユーザープロンプト) のタプル
    """
    # 未変身時は特別なステージ名を使用
    if transformation_count == 0:
        stage_name = "pre_transform"  # 未変身状態
    else:
        stage_name = get_stage_name(stats.bloom)

    # NSFWモードに応じてガイドラインを選択
    if nsfw_mode:
        stage_guidelines = STAGE_GUIDELINES_NSFW.get(stage_name, "")
    else:
        stage_guidelines = STAGE_GUIDELINES.get(stage_name, "")

    psychological_desc = get_psychological_description(
        stats.bloom, nsfw_mode, pronoun, transformation_count
    )

    # 属性情報を構築
    attribute_section = ""
    if attributes:
        attribute_section = (
            "\n\n**キャラクターの特殊属性:**\n"
            + "\n".join(f"- {attr}" for attr in attributes)
            + "\n（これらの属性は性格や振る舞いに影響するため、応答に反映してください）"
        )

    # NSFWモードに応じてテンプレートを選択
    if nsfw_mode:
        template = CONVERSATION_SYSTEM_PROMPT_NSFW_TEMPLATE
    else:
        template = CONVERSATION_SYSTEM_PROMPT_TEMPLATE

    system_prompt = (
        template.format(
            character_name=character_name,
            pronoun=pronoun,
            current_outfit=current_outfit_desc or "不明",
            bloom=stats.bloom,
            psychological_description=psychological_desc,
            stage_specific_guidelines=stage_guidelines,
            language_rules=get_language_rules(language),
        )
        + attribute_section
    )

    # 会話履歴を構築
    history_text = ""
    if conversation_history:
        recent_history = conversation_history[-6:]  # 直近6件
        history_lines = []
        for msg in recent_history:
            if msg.role == "user":
                history_lines.append(f"ユーザー: {msg.content}")
            else:
                history_lines.append(f"{character_name}: {msg.content}")
        history_text = "\n".join(history_lines)

    # セッション経緯を構築（着替・改変・行動の履歴）
    timeline_text = ""
    if session_timeline:
        _TYPE_LABELS = {
            "dress_up": "着替",
            "reality_alter": "改変",
            "action": "行動",
            "conversation": "会話",
        }
        tl_lines = []
        for itype, text in session_timeline[-8:]:
            label = _TYPE_LABELS.get(itype, itype)
            tl_lines.append(f"- [{label}] {text}")
        timeline_text = "\n".join(tl_lines)

    # ユーザープロンプト構築
    timeline_section = ""
    if timeline_text:
        timeline_section = f"""\nこれまでの経緯:
{timeline_text}
（上記の経緯を踏まえて応答してください）\n"""

    user_prompt = f"""これまでの会話:
{history_text if history_text else "(まだ会話していません)"}
{timeline_section}
ユーザーの発言: {message}

上記に対して、キャラクターとして応答してください。200〜300文字程度で。

Output language: {"English only" if language == "en" else "Japanese only"}"""

    return system_prompt, user_prompt


# =============================================================================
# 会話の定型応答（フォールバック用）
# =============================================================================

FALLBACK_RESPONSES = {
    "pre_transform": [
        "えっと…こんにちは。{pronoun}に何か用かな？",
        "あ、あの…{pronoun}に話しかけてくれてるの？",
        "はじめまして…{pronoun}、ちょっと緊張してるかも…",
    ],
    "resistance": [
        "えっ…な、何？こんな格好で話しかけないでよ…恥ずかしいから…",
        "もう…なんでこんな服着せられてるのか、{pronoun}にもわからないよ…",
        "ちょ、ちょっと…あまりじっと見ないで…恥ずかしいんだから…",
    ],
    "wavering": [
        "その…なんだろう、最近ちょっとだけ…慣れてきたかも…なんて…",
        "えっと…話しかけてくれるの、嫌じゃない…かも…",
        "こんな{pronoun}でも、話を聞いてくれるんだ…ありがと…",
    ],
    "acceptance_start": [
        "ふふ、どうしたの？{pronoun}のこと、気になる？",
        "今日の衣装、どうかな？自分でも…悪くないって思えてきた…",
        "あなたと話してると、なんだか落ち着くな…不思議…",
    ],
    "fallen": [
        "うふふ、{pronoun}のこと見に来てくれたの？嬉しいな♪",
        "ねぇ、次はどんな衣装着せてくれるの？{pronoun}、楽しみにしてるよ♪",
        "あなたといると、どんな姿になっても怖くないかも…♪",
    ],
}

# NSFWモード用フォールバック応答
FALLBACK_RESPONSES_NSFW = {
    "pre_transform": [
        "えっと…こんにちは。あなた、{pronoun}に何か用があるの？ちょっとドキドキしてる…",
        "あ…あの…話しかけてくれて、嬉しいかも…？",
        "はじめまして…{pronoun}、緊張で心臓バクバクしてる……",
    ],
    "resistance": [
        "ひゃっ…！こ、こんな格好で見ないで…肌が…見えちゃってるから…っ",
        "もう…なんでこんな際どい服…{pronoun}、恥ずかしくて顔が熱い…",
        "そんなにじっと見られると…身体がゾクゾクして…変な気持ちに…",
    ],
    "wavering": [
        "あの…見られてると…なんか、身体が熱くなってきて…変かな…",
        "こんな格好…恥ずかしいけど…見てくれてるの、嫌じゃ…ないかも…",
        "{pronoun}の身体、そんなに見たいの…？…ちょっとだけなら…いいよ…",
    ],
    "acceptance_start": [
        "ふふ…{pronoun}のこと、見てたでしょ？いいよ、もっと見て…♪",
        "この格好…恥ずかしいけど、ドキドキする…あなたに見られてると…",
        "ねぇ…{pronoun}の身体、どう…？触りたく…なったりする…？",
    ],
    "fallen": [
        "うふふ♪ {pronoun}のこと、見に来てくれたの？嬉しい…もっと見てて♪",
        "ねぇ、もっと際どい格好にして…？{pronoun}、見せたくなっちゃった♪",
        "あなたに見られてると…身体が疼いちゃう…{pronoun}、もうおかしくなりそう♪",
    ],
}


def get_fallback_response(
    bloom: int, pronoun: str = "僕", nsfw_mode: bool = False
) -> str:
    """フォールバック応答を取得"""
    stage_name = get_stage_name(bloom)
    if nsfw_mode:
        responses = FALLBACK_RESPONSES_NSFW.get(
            stage_name, FALLBACK_RESPONSES_NSFW["resistance"]
        )
    else:
        responses = FALLBACK_RESPONSES.get(stage_name, FALLBACK_RESPONSES["resistance"])
    response = random.choice(responses)
    return response.format(pronoun=pronoun)
