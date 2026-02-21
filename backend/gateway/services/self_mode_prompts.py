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


# ── Profile generation prompt (R-008, US6 T030) ──

PROFILE_GEN_SYSTEM_PROMPT = """あなたは性格分析の専門家です。ユーザーの自己紹介テキストから、
ゲーム内で使用する性格プロフィールを生成してください。

出力形式（JSON のみ、余計なテキストは不要）:
{
  "personality": "性格を1-2文で要約",
  "reaction_style": "bold|gentle|cheerful|calm|shy|passionate",
  "pronoun": "一人称（僕/私/俺/わたし/あたし等）",
  "interests": ["興味・関心のキーワード"],
  "tsf_attitude": "TSFに対する態度を1文で"
}

ルール:
- reaction_style は必ず bold, gentle, cheerful, calm, shy, passionate のいずれかを選択
- pronoun は入力テキストの文体から推測し、不明なら「僕」
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
