"""Self-mode prompt templates.

Prompt definitions for the "self mode" that bypasses psychological stages
and parameter tracking, generating reactions based on the user's personality
profile (R-007).
"""

from __future__ import annotations


SELF_MODE_SYSTEM_PROMPT = """あなたは物語の主人公の心の声を書く作家です。
これは「自分自身」モードです。主人公は実在の人物の性格を反映しています。

【主人公の性格プロフィール】
{self_profile_section}

重要な指示:
- キャラクター的な「驚き」「葛藤」「堕落」の定型パターンは使わないでください
- 性格プロフィールに基づいた、自然で素直な反応を書いてください
- 性格がポジティブなら前向きに、慎重なら控えめに反応してください

**文字数指示: 300～500文字で詳細に描写してください。**
以下の要素を含めてください:
- 変身した姿を見たときの率直な感想
- 性格に基づいた内面の反応
- 鏡に映る自分への感情"""


SELF_MODE_SYSTEM_PROMPT_NSFW = """あなたは官能小説家です。主人公の心の声を書きます。
これは「自分自身」モードです。主人公は実在の人物の性格を反映しています。

【主人公の性格プロフィール】
{self_profile_section}

重要な指示:
- キャラクター的な「驚き」「葛藤」「堕落」の定型パターンは使わないでください
- 性格プロフィールに基づいた、自然で素直な感覚を書いてください
- 性格がポジティブなら積極的に、慎重なら恥ずかしがりながらも受け入れていくように

**文字数指示: 300～500文字で詳細に描写してください。**
以下の要素を含めてください:
- 変身した身体への官能的な感覚
- 新しい身体に気づいたときの素直な反応
- 性格に基づいた羞恥と興奮のバランス"""


SELF_MODE_USER_PROMPT = """以下の状況で主人公の心境を描写してください。

変身前の姿:
{before_desc}

変身後の姿:
{after_desc}

変身指示:
「{instruction}」

一人称: 「{pronoun}」
{interests_section}
冒頭は変身した姿への率直な反応で始めてください。"""


def _build_self_profile_section(self_profile: dict) -> str:
    """Format the self_profile dict into a text section for the system prompt.

    Args:
        self_profile: SelfProfile dict with personality, reaction_style, etc.

    Returns:
        Formatted text block
    """
    parts: list[str] = []

    gender = self_profile.get("gender", "")
    if gender:
        gender_label = "男性" if gender == "man" else "女性"
        parts.append(f"- 性別: {gender_label}")

    personality = self_profile.get("personality", "")
    if personality:
        parts.append(f"- 性格: {personality[:200]}")

    reaction = self_profile.get("reaction_style", "")
    if reaction and reaction != "default":
        style_labels = {
            "bold": "大胆",
            "gentle": "穏やか",
            "cheerful": "明るい",
            "shy": "内気",
            "calm": "冷静",
            "passionate": "情熱的",
        }
        parts.append(f"- 反応スタイル: {style_labels.get(reaction, reaction)}")

    tsf_att = self_profile.get("tsf_attitude", "")
    if tsf_att:
        parts.append(f"- 変身に対する態度: {tsf_att[:200]}")

    return "\n".join(parts) if parts else "（プロフィール未設定）"


def build_self_mode_feeling_prompt(
    before_desc: str,
    after_desc: str,
    instruction: str,
    self_profile: dict,
    nsfw_mode: bool = False,
) -> tuple[str, str]:
    """Build system and user prompts for self-mode feeling generation.

    No psychological stages or parameter dependencies; uses self_profile only (R-007).

    Args:
        before_desc: Description before outfit change
        after_desc: Description after outfit change
        instruction: Outfit change instruction
        self_profile: Self-profile dict (SelfProfile-compatible structure)
        nsfw_mode: Whether NSFW mode is enabled

    Returns:
        (system_prompt, user_prompt) tuple
    """
    profile_section = _build_self_profile_section(self_profile)
    pronoun = self_profile.get("pronoun", "僕")

    if nsfw_mode:
        system_prompt = SELF_MODE_SYSTEM_PROMPT_NSFW.format(
            self_profile_section=profile_section,
        )
    else:
        system_prompt = SELF_MODE_SYSTEM_PROMPT.format(
            self_profile_section=profile_section,
        )

    # Build interests section
    interests = self_profile.get("interests", [])
    interests_section = ""
    if interests:
        interests_text = "、".join(str(i) for i in interests[:10])
        interests_section = f"\n主人公の興味・関心: {interests_text}"

    user_prompt = SELF_MODE_USER_PROMPT.format(
        before_desc=before_desc or "不明",
        after_desc=after_desc or "不明",
        instruction=instruction,
        pronoun=pronoun,
        interests_section=interests_section,
    )

    return system_prompt, user_prompt


# ── Self-mode conversation prompt (US5 self_profile personality in chat) ──

SELF_MODE_CONVERSATION_SYSTEM_PROMPT = """あなたは着せ替えゲームの主人公として、ユーザーとの会話に応答します。
これは「自分自身」モードです。主人公は実在の人物の性格を反映しています。

**主人公の設定:**
- 名前: {character_name}
- 一人称: {pronoun}
- 現在の衣装: {current_outfit}

【性格プロフィール】
{self_profile_section}

**会話ルール:**
- 一人称は必ず「{pronoun}」を使用
- 性格プロフィールに基づいた自然な口調・態度で応答する
- キャラクター的な定型パターン（おどおど、内気、ツンデレ等）は使わない
- 性格に忠実に反応する（例: 論理的な性格なら論理的に、情熱的なら感情豊かに）
- 応答は200〜300文字程度
- 自然な日本語で、性格が感じられるように
- 現在着ている衣装への言及を時々含める
- 相手（ユーザー）への二人称は「あなた」
- {language_rules}
"""

SELF_MODE_CONVERSATION_SYSTEM_PROMPT_NSFW = """あなたは着せ替えゲームの主人公として、ユーザーとの会話に応答します。
これは「自分自身」モードです。主人公は実在の人物の性格を反映しています。

**主人公の設定:**
- 名前: {character_name}
- 一人称: {pronoun}
- 現在の衣装: {current_outfit}

【性格プロフィール】
{self_profile_section}

**会話ルール:**
- 一人称は必ず「{pronoun}」を使用
- 性格プロフィールに基づいた自然な口調・態度で応答する
- キャラクター的な定型パターン（おどおど、内気、ツンデレ等）は使わない
- 性格に忠実に反応する（例: 論理的な性格なら論理的に、情熱的なら感情豊かに）
- 応答は200〜300文字程度
- 自然な日本語で、性格が感じられるように
- 現在着ている衣装への言及を時々含める
- 相手（ユーザー）への二人称は「あなた」
- {language_rules}

**アダルトコンテンツ許可:**
- 性的な話題・表現・描写を含めることが許可されています
- 性格プロフィールに忠実な反応をしつつ、官能的な描写を含める
- 露出度の高い衣装や身体への感覚を率直に表現
"""


def build_self_mode_conversation_prompt(
    message: str,
    conversation_history: list,
    current_outfit_desc: str,
    self_profile: dict,
    nsfw_mode: bool = False,
    language: str = "ja",
) -> tuple[str, str]:
    """Build conversation prompt for self-mode using the user's personality profile.

    Instead of using psychological stages (bloom/shame/adaptation), this uses the
    user's self_profile personality, reaction_style, and interests.

    Args:
        message: User message
        conversation_history: Recent conversation messages
        current_outfit_desc: Description of current outfit
        self_profile: Self-profile dict with personality, reaction_style, etc.
        nsfw_mode: Whether NSFW mode is enabled
        language: Response language

    Returns:
        (system_prompt, user_prompt) tuple
    """
    from .conversation import get_language_rules

    profile_section = _build_self_profile_section(self_profile)
    character_name = self_profile.get("display_name") or "主人公"
    pronoun = self_profile.get("pronoun") or "僕"

    if nsfw_mode:
        template = SELF_MODE_CONVERSATION_SYSTEM_PROMPT_NSFW
    else:
        template = SELF_MODE_CONVERSATION_SYSTEM_PROMPT

    system_prompt = template.format(
        character_name=character_name,
        pronoun=pronoun,
        current_outfit=current_outfit_desc or "不明",
        self_profile_section=profile_section,
        language_rules=get_language_rules(language),
    )

    # Append interests as context
    interests = self_profile.get("interests", [])
    if interests:
        interests_text = "、".join(str(i) for i in interests[:10])
        system_prompt += f"\n\n**主人公の興味・関心:** {interests_text}"

    # Build conversation history text
    history_text = ""
    if conversation_history:
        recent = conversation_history[-6:]
        lines = []
        for msg in recent:
            role_label = "ユーザー" if msg.role == "user" else character_name
            lines.append(f"{role_label}: {msg.content}")
        history_text = "\n".join(lines)

    user_prompt = f"""これまでの会話:
{history_text if history_text else "(まだ会話していません)"}

ユーザーの発言: {message}

上記に対して、性格プロフィールに基づいた自然な応答をしてください。200〜300文字程度で。

Output language: {"English only" if language == "en" else "Japanese only"}"""

    return system_prompt, user_prompt


# ── Profile generation prompt (R-008, US6 T030) ──

PROFILE_GEN_SYSTEM_PROMPT = """あなたは性格分析の専門家です。ユーザーの自己紹介テキストから、
ゲーム内で使用する性格プロフィールを生成してください。

出力形式（JSON のみ、余計なテキストは不要）:
{
  "personality": "性格を1-2文で要約",
  "reaction_style": "bold|gentle|cheerful|calm|shy|passionate",
  "pronoun": "一人称（僕/私/俺/わたし/あたし等）",
  "gender": "man|woman",
  "interests": ["興味・関心のキーワード"],
  "tsf_attitude": "TSFに対する態度を1文で"
}

ルール:
- reaction_style は必ず bold, gentle, cheerful, calm, shy, passionate のいずれかを選択
- pronoun は入力テキストの文体から推測し、不明なら「僕」
- gender は必ず man または woman のいずれかを選択。入力テキストの一人称や文脈から推測し、不明なら「man」
- interests は最大5個のキーワードで
- tsf_attitude は入力テキストにTSFへの態度が書かれていなければ「興味はあるが戸惑いもある」のような中立的な表現
- personality は入力テキストを元に自然な日本語で要約
- 必ず有効なJSONのみを出力すること"""

PROFILE_GEN_USER_PROMPT = """以下のテキストから性格プロフィールを生成してください:

{input_text}"""


def build_self_profile_generation_prompt(input_text: str) -> tuple[str, str]:
    """Build system and user prompts for LLM-based self-profile generation.

    Given the user's free-text self introduction, produce prompts that will
    make the LLM output a structured SelfProfile JSON (R-008).

    Args:
        input_text: User's free-form self-introduction text

    Returns:
        (system_prompt, user_prompt) tuple
    """
    user_prompt = PROFILE_GEN_USER_PROMPT.format(
        input_text=input_text[:1000],
    )
    return PROFILE_GEN_SYSTEM_PROMPT, user_prompt
