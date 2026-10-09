"""複数人表示モードで心境・行動・会話プロンプトに付ける共通ルール。

人物パネルに登場人物が登録されていれば、その一覧（名前・一人称・性格）に
従わせる。登録が無ければ従来どおり、他の人物の名前を LLM に任せる。
"""

from __future__ import annotations

MULTI_PEOPLE_FREE_NAMES_RULE = (
    "\n\n【複数人モード】\n"
    "- ユーザーの指示に他の人物が関わる場合、その人物との相互作用や会話を自然に描写してよい。\n"
    "- 他のキャラクターの名前はLLMが自由に決定してよい。\n"
    "- ただし主人公の一人称は必ず維持すること。"
)

MULTI_PEOPLE_ROSTER_RULE = (
    "\n\n【複数人モード】\n"
    "- 「同シーンの登場キャラクター一覧」の人物は、この場面に一緒にいる。"
    "指示に関わる人物との相互作用や会話を自然に描写してよい。\n"
    "- 一覧の人物の名前・一人称・性格・口調は一覧の設定どおりにし、別の名前や別の一人称に変えないこと。\n"
    "- 一覧にない人物は、ユーザーの指示がその人物を登場させたときだけ描写してよい（名前は自由に決めてよい）。\n"
    "- 主人公の一人称は必ず維持すること。"
)


def build_multi_people_rule(session_characters_section: str | None) -> str:
    """複数人モードのルール文。登場人物一覧があれば一覧に従わせる版を返す。"""
    if session_characters_section:
        return MULTI_PEOPLE_ROSTER_RULE
    return MULTI_PEOPLE_FREE_NAMES_RULE


def append_session_characters_section(
    user_prompt: str, session_characters_section: str | None
) -> str:
    """ユーザープロンプトの末尾に登場人物一覧を付ける。一覧が無ければそのまま。"""
    if not session_characters_section:
        return user_prompt
    return f"{user_prompt}\n\n{session_characters_section.strip()}"


__all__ = [
    "MULTI_PEOPLE_FREE_NAMES_RULE",
    "MULTI_PEOPLE_ROSTER_RULE",
    "append_session_characters_section",
    "build_multi_people_rule",
]
