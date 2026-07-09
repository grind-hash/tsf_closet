"""
Instruction suggestion prompts

LLM prompts for generating a next instruction text (detailed situation/story text)
based on the user's past history and current session state.
"""

from __future__ import annotations

INSTRUCTION_SUGGESTION_SYSTEM_PROMPT_JA = """\
あなたはTSFゲーム（変身・着せ替えゲーム）のプレイヤーの好みを深く理解する脚本アシスタントです。
プレイヤーの過去の指示履歴と現在の状態を読み取り、次にプレイヤーが送信したくなるような
「指示テキスト」を1つだけ生成してください。

出力ルール:
- 出力は指示テキスト本文のみ。前置き・説明・見出し・箇条書き・引用符・コードブロックは一切禁止
- 情景描写やシチュエーションの展開を含む、3〜6文程度の文章にすること
- そのままゲームの入力欄に貼り付けて送信できる指示文の形式にすること
- 過去の傾向を踏まえつつ、単純な繰り返しではなく少し発展させた提案にすること
- ユーザー指定のキーワード/希望が渡された場合は、それを必ずシチュエーションに自然に組み込むこと
"""

INSTRUCTION_SUGGESTION_SYSTEM_PROMPT_EN = """\
You are a scriptwriting assistant who deeply understands the preferences of a TSF
(transformation/dress-up) game player. Read the player's past instruction history and
current state, then generate exactly ONE "instruction text" that the player would likely
want to send next.

Output rules:
- Output only the instruction text itself. No preamble, explanation, headings, bullet
  points, quotation marks, or code blocks.
- Include scene description and story development, in about 3 to 6 sentences.
- Format it so it can be pasted directly into the game's input field and sent as-is.
- Build on past tendencies, but propose something slightly developed rather than a
  simple repetition.
- If a user-provided keyword/preference is given, you MUST naturally weave it into the
  generated situation.
"""

_TYPE_FOCUS_JA = {
    "dress_up": "特に「着せ替え」の傾向を重視して",
    "reality_alter": "特に「現実改変」の傾向を重視して",
    "action": "特に「行動」の傾向を重視して",
}

_TYPE_FOCUS_EN = {
    "dress_up": 'Focus especially on the player\'s "dress_up" tendencies.',
    "reality_alter": 'Focus especially on the player\'s "reality_alter" tendencies.',
    "action": 'Focus especially on the player\'s "action" tendencies.',
}


def _build_character_section(character_context: str, language: str) -> str:
    if not character_context:
        return ""
    if language == "en":
        return f"Character/self-profile context:\n{character_context}\n"
    return f"キャラクター/セルフプロフィールの文脈:\n{character_context}\n"


def _build_stats_section(stats, language: str) -> str:
    if stats is None:
        return ""
    if language == "en":
        return (
            "Current state:\n"
            f"- bloom (transformation acceptance): {stats.bloom}/100\n"
            f"- shame: {stats.shame}/100\n"
            f"- adaptation: {stats.adaptation}\n"
        )
    return (
        "現在の状態:\n"
        f"- bloom（変身受容度）: {stats.bloom}/100\n"
        f"- shame（羞恥）: {stats.shame}/100\n"
        f"- adaptation（適応度）: {stats.adaptation}\n"
    )


def _build_attributes_section(attributes: list[str], language: str) -> str:
    if not attributes:
        return ""
    joined = "\n".join(f"- {a}" for a in attributes)
    if language == "en":
        return f"Active reality-alteration attributes:\n{joined}\n"
    return f"現在有効な現実改変属性:\n{joined}\n"


def _build_keyword_section(keyword: str | None, language: str) -> str:
    if not keyword or not keyword.strip():
        return ""
    cleaned = keyword.strip()
    if language == "en":
        return (
            "User-provided keyword/preference (MUST be reflected in the generated "
            f'instruction): "{cleaned}"\n'
        )
    return f'ユーザー指定のキーワード/希望（生成する指示に必ず反映すること）: "{cleaned}"\n'


def _build_memory_section(memory_text: str | None, language: str) -> str:
    if not memory_text or not memory_text.strip():
        return ""
    cleaned = memory_text.strip()
    if language == "en":
        return f"User preference memory (long-term tendencies):\n{cleaned}\n"
    return f"ユーザーの好み傾向メモリ（長期的な傾向）:\n{cleaned}\n"


def build_instruction_suggestion_prompt(
    character_context: str,
    stats,
    attributes: list[str],
    timeline: list[tuple[str, str]],
    instruction_type_filter: str | None,
    language: str = "ja",
    keyword: str | None = None,
    memory_text: str | None = None,
) -> tuple[str, str]:
    """Build system and user prompts for instruction suggestion generation.

    Args:
        character_context: キャラクター名/性格やセルフプロフィールを表す短い文脈テキスト
        stats: SessionStats（bloom/shame/adaptation を持つ）、無ければ None
        attributes: 現実改変属性のテキスト一覧
        timeline: (instruction_type, instruction_text) のタプルリスト（古い順）
        instruction_type_filter: dress_up/reality_alter/action のいずれか、または None（全種類）
        language: "ja" or "en"
        keyword: ユーザーが入力欄に入力した自由テキスト/キーワード（任意）
        memory_text: 保存済みメモリテキスト（ユーザーの嗜好傾向）、未使用/未設定の場合 None

    Returns:
        (system_prompt, user_prompt) tuple
    """
    system_prompt = (
        INSTRUCTION_SUGGESTION_SYSTEM_PROMPT_EN
        if language == "en"
        else INSTRUCTION_SUGGESTION_SYSTEM_PROMPT_JA
    )

    lines = []
    for i, (itype, text) in enumerate(timeline, 1):
        lines.append(f"{i}. [{itype}] {text}")
    history_list = (
        "\n".join(lines)
        if lines
        else ("No history." if language == "en" else "履歴なし")
    )

    focus_map = _TYPE_FOCUS_EN if language == "en" else _TYPE_FOCUS_JA
    focus_note = focus_map.get(instruction_type_filter or "", "")
    if not focus_note:
        focus_note = (
            "Consider all instruction types (dress_up/reality_alter/action) together."
            if language == "en"
            else "着せ替え/現実改変/行動のすべての傾向を総合して考慮してください。"
        )

    sections = [
        _build_character_section(character_context, language),
        _build_stats_section(stats, language),
        _build_attributes_section(attributes, language),
        _build_keyword_section(keyword, language),
        _build_memory_section(memory_text, language),
    ]
    context_block = "\n".join(s for s in sections if s)

    if language == "en":
        user_prompt = (
            f"{context_block}\n"
            f"Past instruction history (oldest first):\n{history_list}\n\n"
            f"{focus_note}\n"
            "Generate the next instruction text now."
        )
    else:
        user_prompt = (
            f"{context_block}\n"
            f"過去の指示履歴（古い順）:\n{history_list}\n\n"
            f"{focus_note}\n"
            "次の指示テキストを生成してください。"
        )

    return system_prompt, user_prompt
