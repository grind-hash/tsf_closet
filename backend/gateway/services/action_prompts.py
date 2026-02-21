"""Action mode prompt templates.

Prompt definitions for the "action" instruction type that generates
scene-transition text without outfit changes, following the same
psychological-stage pattern as reality_prompts.py (R-005).
"""

from __future__ import annotations


def _get_action_stage(bloom: int) -> str:
    """Return a brief psychological-state description for the system prompt.

    Args:
        bloom: Bloom value (0-100)

    Returns:
        A description of the character's current mental state
    """
    if bloom < 25:
        return (
            "The protagonist is still confused and embarrassed about their "
            "transformed appearance. They feel self-conscious in public."
        )
    if bloom < 50:
        return (
            "The protagonist is wavering -- still embarrassed, but starting "
            "to accept their new appearance. Their heart races in social situations."
        )
    if bloom < 75:
        return (
            "The protagonist has largely accepted their new appearance. "
            "They may even enjoy the attention, though occasional doubts surface."
        )
    return (
        "The protagonist fully embraces their transformed self. "
        "They enjoy going out and being seen."
    )


# ── Post-transformation templates (transformation_count >= 1) ──

ACTION_SYSTEM_PROMPT_TEMPLATE = """あなたは物語の主人公の心の声を書く作家です。
主人公は変身した姿のまま「行動」しています。服装は変わりませんが、場面が転換します。

キャラクターの一人称視点で、行動中の心境をモノローグ形式で表現してください。

{stage_description}

**文字数指示: 300～500文字で詳細に描写してください。**
以下の要素を含めてください:
- 行動先での周囲の反応や視線
- 変身した姿のまま行動することへの心境
- 場面描写（場所の雰囲気、空気感）
- 内面の葛藤や発見

自然な日本語で、感情豊かに書いてください。"""


ACTION_SYSTEM_PROMPT_NSFW_TEMPLATE = """あなたは官能小説家です。主人公の心の声を書きます。
主人公は変身した姿のまま「行動」しています。服装は変わりませんが、場面が転換します。

キャラクターの一人称視点で、行動中の心境をモノローグ形式で表現してください。

{stage_description}

**文字数指示: 300～500文字で詳細に描写してください。**
以下の要素を含めてください:
- 周囲の視線が体のラインや露出部分に集まる感覚
- 官能的な身体感覚（風が肌に触れる、布地が擦れるなど）
- 見られていることへの羞恥と高揚
- 場面描写と内面の欲望

官能的で自然な日本語で、感情豊かに書いてください。"""


# ── Pre-transformation templates (transformation_count == 0) ──

PRE_TRANSFORM_ACTION_SYSTEM_PROMPT = """あなたは物語の主人公の心の声を書く作家です。
主人公はまだ変身しておらず、普段の姿のまま行動しています。

キャラクターの一人称視点で、日常の行動中の心境をモノローグ形式で表現してください。

**文字数指示: 300～500文字で詳細に描写してください。**
以下の要素を含めてください:
- 行動先の場面描写（場所の雰囲気、空気感）
- 日常の中で感じる気持ちや思考
- 周囲の人々や環境との関わり
- 何気ない瞬間の内面的な発見や感情

重要: 主人公はまだ変身していません。変身に関する描写は一切入れないでください。
普通の日常行動として自然に描写してください。

自然な日本語で、感情豊かに書いてください。"""


PRE_TRANSFORM_ACTION_SYSTEM_PROMPT_NSFW = """あなたは官能小説家です。主人公の心の声を書きます。
主人公はまだ変身しておらず、普段の姿のまま行動しています。

キャラクターの一人称視点で、日常の行動中の心境をモノローグ形式で表現してください。

**文字数指示: 300～500文字で詳細に描写してください。**
以下の要素を含めてください:
- 行動先での官能的な空気感や雰囲気
- 日常に潜む色気や身体的な感覚
- 周囲の人々への意識
- 何気ない瞬間の感覚的な描写

重要: 主人公はまだ変身していません。変身に関する描写は一切入れないでください。
普通の日常行動として官能的に描写してください。

官能的で自然な日本語で、感情豊かに書いてください。"""


ACTION_USER_PROMPT_TEMPLATE = """主人公は以下の行動を取ります:
「{instruction}」

主人公の現在の服装/外見:
{current_description}

一人称: 「{pronoun}」

{recent_actions_section}
{personality_section}
冒頭は行動に関連する描写で始めてください。"""


PRE_TRANSFORM_ACTION_USER_PROMPT_TEMPLATE = """主人公は以下の行動を取ります:
「{instruction}」

主人公は普段の姿のままです。まだ何の変身も起きていません。

一人称: 「{pronoun}」

{recent_actions_section}
{personality_section}
冒頭は行動に関連する描写で始めてください。
変身・性転換・衣装変化に関する描写は絶対にしないでください。"""


def build_action_prompt(
    instruction: str,
    current_description: str,
    pronoun: str = "僕",
    bloom: int = 0,
    nsfw_mode: bool = False,
    personality: str = "",
    description: str = "",
    recent_actions: list[str] | None = None,
    transformation_count: int = 0,
) -> tuple[str, str]:
    """Build system and user prompts for the action instruction type.

    When transformation_count == 0, uses pre-transformation templates that
    describe normal daily life without any transformation references.
    When transformation_count >= 1, uses the standard post-transformation
    templates with bloom-based psychological stages.

    Args:
        instruction: The action the user wants the character to take
        current_description: Vision-LLM description of current appearance
        pronoun: First-person pronoun
        bloom: Bloom value (0-100)
        nsfw_mode: Whether NSFW mode is enabled
        personality: Character personality text
        description: Character description text
        recent_actions: List of recent action instructions for context
        transformation_count: Number of transformations so far (0 = pre-transform)

    Returns:
        (system_prompt, user_prompt) tuple
    """
    is_pre_transform = transformation_count == 0

    # Select system prompt template
    if is_pre_transform:
        if nsfw_mode:
            system_prompt = PRE_TRANSFORM_ACTION_SYSTEM_PROMPT_NSFW
        else:
            system_prompt = PRE_TRANSFORM_ACTION_SYSTEM_PROMPT
    else:
        stage_desc = _get_action_stage(bloom)
        if nsfw_mode:
            system_prompt = ACTION_SYSTEM_PROMPT_NSFW_TEMPLATE.format(
                stage_description=stage_desc,
            )
        else:
            system_prompt = ACTION_SYSTEM_PROMPT_TEMPLATE.format(
                stage_description=stage_desc,
            )

    # Add personality section to system prompt
    if personality:
        truncated = personality[:500] if len(personality) > 500 else personality
        personality_sys = f"\n\n【このキャラクターの性格】\n- 性格: {truncated}\n"
        if description:
            desc_truncated = (
                description[:500] if len(description) > 500 else description
            )
            personality_sys += f"- 説明: {desc_truncated}\n"
        personality_sys += "- このキャラクターの性格特性に合わせて、語調・反応・思考パターンを調整してください。"
        system_prompt += personality_sys

    # Build recent actions section
    recent_actions_section = ""
    if recent_actions:
        recent_list = "\n".join(f"- {a}" for a in recent_actions[-5:])
        recent_actions_section = (
            f"これまでの行動履歴:\n{recent_list}\n"
            "（上記の行動と重複しない新しい場面を描写してください）"
        )

    # Build personality section for user prompt
    personality_section = ""
    if personality:
        personality_section = f"キャラクターの性格: {personality[:200]}"

    # Select user prompt template
    if is_pre_transform:
        user_prompt = PRE_TRANSFORM_ACTION_USER_PROMPT_TEMPLATE.format(
            instruction=instruction,
            pronoun=pronoun,
            recent_actions_section=recent_actions_section,
            personality_section=personality_section,
        )
    else:
        user_prompt = ACTION_USER_PROMPT_TEMPLATE.format(
            instruction=instruction,
            current_description=current_description or "不明",
            pronoun=pronoun,
            recent_actions_section=recent_actions_section,
            personality_section=personality_section,
        )

    return system_prompt, user_prompt
