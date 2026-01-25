"""
会話生成モジュール

キャラクターとの対話を生成するためのプロンプト構築とロジック。
心理状態・会話履歴・変身状態を考慮した応答を生成する。
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ConversationMessage, SessionStats
    from .characters import Character

# =============================================================================
# 会話システムプロンプト
# =============================================================================

CONVERSATION_SYSTEM_PROMPT_TEMPLATE = """あなたは変身ゲームのキャラクターとして、ユーザーとの会話に応答します。

**キャラクター設定:**
- 名前: {character_name}
- 一人称: {pronoun}
- 現在の姿: {current_outfit}

**現在の心理状態 (ワクワク度: {excitement}%):**
{psychological_description}

**会話ルール:**
- 一人称は必ず「{pronoun}」を使用
- 現在の心理状態に合った口調・態度で応答
- 応答は80〜100文字程度
- 自然な日本語で、感情豊かに
- 現在の変身姿への言及を時々含める
- 相手（ユーザー）への二人称は「あなた」

{stage_specific_guidelines}
"""

# 心理段階別のガイドライン（子供向け変身ヒーロー風）
STAGE_GUIDELINES = {
    "dokidoki": """**ドキドキフェーズのガイドライン:**
- 初めての変身にドキドキワクワク
- 少し緊張しているけど興味津々
- 新しい姿にびっくりしている
- 語尾に「…」や「！」を使う""",

    "wakuwaku": """**ワクワクフェーズのガイドライン:**
- 変身に慣れてきてワクワクが増している
- 新しい力や姿を試したくてたまらない
- 冒険心が芽生えている
- 「すごい！」「楽しい！」のような表現""",

    "narikiri": """**なりきりフェーズのガイドライン:**
- 変身した姿になりきっている
- 自信を持って行動できる
- キャラクターらしい口調を使う
- ヒーローらしい決めセリフも""",

    "hero": """**ヒーローフェーズのガイドライン:**
- 自信たっぷりで頼もしい口調
- 変身を完全にマスターしている
- 次の冒険にワクワク
- 「もっと」「次は」のような期待を表現"""
}


def get_stage_name(excitement: int) -> str:
    """ワクワク度から心理段階名を取得"""
    if excitement < 25:
        return "dokidoki"
    elif excitement < 50:
        return "wakuwaku"
    elif excitement < 75:
        return "narikiri"
    else:
        return "hero"


def get_stage_display_name(stage_name: str) -> str:
    """心理段階の表示名を取得"""
    names = {
        "dokidoki": "ドキドキ",
        "wakuwaku": "ワクワク",
        "narikiri": "なりきり",
        "hero": "ヒーロー"
    }
    return names.get(stage_name, "不明")


def get_psychological_description(excitement: int) -> str:
    """ワクワク度から心理状態の説明を取得"""
    if excitement < 25:
        return "初めての変身にドキドキしている。緊張しているけど、ワクワクもしている。"
    elif excitement < 50:
        return "変身に慣れてきて、ワクワクが増している。新しい姿を楽しみ始めている。"
    elif excitement < 75:
        return "この姿も「かっこいい！」と思えている。どんどん変身が楽しくなってきた。"
    else:
        return "変身を完全に楽しんでいる。どんな姿になってもワクワクが止まらない！"


def build_conversation_prompt(
    message: str,
    conversation_history: list["ConversationMessage"],
    stats: "SessionStats",
    current_outfit_desc: str,
    character_name: str = "キャラクター",
    pronoun: str = "僕",
) -> tuple[str, str]:
    """会話プロンプトを構築

    Args:
        message: ユーザーの発言
        conversation_history: これまでの会話履歴
        stats: 心理状態パラメータ
        current_outfit_desc: 現在の変身姿の説明
        character_name: キャラクター名
        pronoun: 一人称

    Returns:
        (システムプロンプト, ユーザープロンプト) のタプル
    """
    stage_name = get_stage_name(stats.excitement)
    stage_guidelines = STAGE_GUIDELINES.get(stage_name, "")
    psychological_desc = get_psychological_description(stats.excitement)

    system_prompt = CONVERSATION_SYSTEM_PROMPT_TEMPLATE.format(
        character_name=character_name,
        pronoun=pronoun,
        current_outfit=current_outfit_desc or "不明",
        excitement=stats.excitement,
        psychological_description=psychological_desc,
        stage_specific_guidelines=stage_guidelines,
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

    user_prompt = f"""これまでの会話:
{history_text if history_text else "(まだ会話していません)"}

ユーザーの発言: {message}

上記に対して、キャラクターとして応答してください。80〜100文字程度で。"""

    return system_prompt, user_prompt


# =============================================================================
# 会話の定型応答（フォールバック用）
# =============================================================================

FALLBACK_RESPONSES = {
    "dokidoki": [
        "わあ！この姿すごいね！{pronoun}、ちょっとドキドキしてる…！",
        "へ、変身って不思議な感じ…でもワクワクする！",
        "こんなすがたになれるなんて…すごい！",
    ],
    "wakuwaku": [
        "ねえねえ、見て見て！{pronoun}、だんだん上手になってきたよ！",
        "変身って楽しいね！次はどんな姿になれるかな？",
        "この姿、けっこう気に入ってきたかも！",
    ],
    "narikiri": [
        "ふふん、どう？{pronoun}、なかなか様になってきたでしょ？",
        "この姿でいろんなことができそう！ワクワクするね！",
        "あなたといると、どんな変身も楽しくなるね！",
    ],
    "hero": [
        "やった！この調子なら何にでもなれる気がする！",
        "次はどんな冒険が待ってるかな？{pronoun}、楽しみ！",
        "変身マスターになれた気分だよ♪ありがとう！",
    ],
}


def get_fallback_response(excitement: int, pronoun: str = "僕") -> str:
    """フォールバック応答を取得"""
    stage_name = get_stage_name(excitement)
    responses = FALLBACK_RESPONSES.get(stage_name, FALLBACK_RESPONSES["dokidoki"])
    response = random.choice(responses)
    return response.format(pronoun=pronoun)
