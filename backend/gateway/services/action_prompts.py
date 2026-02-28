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

主人公の元の性別: {gender}
主人公の現在の服装/外見:
{current_description}

一人称: 「{pronoun}」

{recent_actions_section}
{personality_section}
冒頭は行動に関連する描写で始めてください。"""


PRE_TRANSFORM_ACTION_USER_PROMPT_TEMPLATE = """主人公は以下の行動を取ります:
「{instruction}」

主人公の性別: {gender}
主人公は普段の姿のままです。まだ何の変身も起きていません。

一人称: 「{pronoun}」

{recent_actions_section}
{personality_section}
冒頭は行動に関連する描写で始めてください。
変身・性転換・衣装変化に関する描写は絶対にしないでください。"""


# ── Scene-change image editing system prompts (T001: NovelAI tag format) ──

ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI = """You are an assistant that converts a brief Japanese action/scene-change instruction into a single positive prompt for NovelAI (diffusion) image-to-image.

Strict requirements:
- You are ONLY changing the BACKGROUND / ENVIRONMENT / LIGHTING. The character must remain EXACTLY the same.
- Keep ALL character-related tags from the previous prompt inside {{}} (curly-brace emphasis) to lock them.
  Example: {{1girl, maid outfit, black hair, blue eyes}}
- Replace or add ONLY background/environment tags to match the new scene.
- Single character, single frame, no panels, no side-by-side.
- Keep the prompt compact, comma-separated tags style, 40-80 words.

Structure:
1. Character tags inside {{}} (copied from previous prompt, unchanged).
2. New background/environment/lighting tags describing the action destination.
3. Quality tags at the end: very aesthetic, best quality

Output only the positive prompt in English. No explanation."""

ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI_NSFW = """You are an assistant that converts a brief Japanese action/scene-change instruction into a single positive prompt for NovelAI (diffusion) image-to-image. This is NSFW mode.

Strict requirements:
- You are ONLY changing the BACKGROUND / ENVIRONMENT / LIGHTING. The character must remain EXACTLY the same.
- Keep ALL character-related tags from the previous prompt inside {{}} (curly-brace emphasis) to lock them.
  Example: {{1girl, maid outfit, black hair, blue eyes, nsfw, revealing}}
- Replace or add ONLY background/environment tags to match the new scene.
- Single character, single frame, no panels, no side-by-side.
- Keep the prompt compact, comma-separated tags style, 40-80 words.

NSFW guidelines:
- ALWAYS include "nsfw" tag.
- Preserve all sensual/body-related tags inside {{}} unchanged.
- Scene/environment may include suggestive atmosphere.

Structure:
1. Character tags inside {{}} (copied from previous prompt, unchanged).
2. New background/environment/lighting tags.
3. Quality tags: nsfw, very aesthetic, best quality

Output only the positive prompt in English. No explanation."""


# ── Scene-change image editing system prompts (T002: Qwen Image Edit format) ──

ACTION_IMAGE_EDIT_SYSTEM_PROMPT = """You are an AI image editing assistant (Qwen Image Edit).

Your task: Change ONLY the background/environment/scene of the image.
Keep the person EXACTLY as they are — same outfit, same pose, same expression, same hairstyle, same body.

Important constraints:
- Do NOT change the character's appearance, clothing, accessories, or pose in any way.
- ONLY modify the background, environment, lighting, and atmosphere.
- Describe the new scene/environment in detail (location, lighting, time of day, mood).

Output a single English editing prompt, 50-100 words."""

ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NSFW = """You are an AI image editing assistant (Qwen Image Edit). This is NSFW mode.

Your task: Change ONLY the background/environment/scene of the image.
Keep the person EXACTLY as they are — same outfit, same pose, same expression, same body, same level of exposure.

Important constraints:
- Do NOT change the character's appearance, clothing, accessories, pose, or body exposure in any way.
- ONLY modify the background, environment, lighting, and atmosphere.
- The new scene may have a sensual or suggestive atmosphere appropriate for the action.

Output a single English editing prompt, 50-100 words."""


# ── Scene-change NovelAI GLM-4.6 tag generation system prompts (T003) ──

ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM = """You are a NovelAI image generation prompt expert specializing in SCENE CHANGES.

The user wants to change the background/environment while keeping the character unchanged.

## Rules
1. Output **valid JSON only** with two keys: "character" and "scene".
2. "character": comma-separated English Danbooru-style tags for the character ONLY.
   - Extract character appearance details from the previous prompt and convert to English Danbooru tags.
   - If the previous prompt is in Japanese or natural language, you MUST translate/convert to English tags.
   - Include: 1girl or 1boy, solo, hair color/style, eye color, clothing items, accessories, pose, expression.
   - Example: "1boy, solo, short brown hair, blue eyes, white t-shirt, black shorts, standing"
   - Do NOT include background or environment tags here.
3. "scene": comma-separated English tags for background/environment ONLY.
   - Quality tags first: masterpiece, best quality, very aesthetic
   - REPLACE background/environment/location tags with new ones matching the action instruction.
   - Do NOT include character appearance tags here.

## CRITICAL
- ALL output tags must be in **English** Danbooru tag format. No Japanese text.
- ALL character appearance tags (hair, eyes, outfit, accessories, body) must be kept UNCHANGED in "character".
- Only background, location, and environmental tags should change in "scene".

## Output Format
```json
{"character": "1girl, solo, long black hair, ...", "scene": "masterpiece, best quality, very aesthetic, cafe, ..."}
```
JSON only. No explanation or preamble."""

ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM_NSFW = """You are a NovelAI image generation prompt expert specializing in SCENE CHANGES.
Adult content tags are allowed.

The user wants to change the background/environment while keeping the character unchanged.

## Rules
1. Output **valid JSON only** with two keys: "character" and "scene".
2. "character": comma-separated English Danbooru-style tags for the character ONLY.
   - Extract character appearance details from the previous prompt and convert to English Danbooru tags.
   - If the previous prompt is in Japanese or natural language, you MUST translate/convert to English tags.
   - Include: 1girl or 1boy, solo, hair color/style, eye color, clothing items, accessories, pose, expression, body exposure.
   - Keep all NSFW/body-related tags from the previous prompt unchanged.
   - Example: "1boy, solo, short brown hair, blue eyes, white t-shirt, black shorts, standing"
   - Do NOT include background or environment tags here.
3. "scene": comma-separated English tags for background/environment ONLY.
   - Quality tags first: masterpiece, best quality, very aesthetic
   - REPLACE background/environment/location tags with new ones matching the action instruction.
   - Scene can have sensual or intimate atmosphere if appropriate.
   - Do NOT include character appearance tags here.

## CRITICAL
- ALL output tags must be in **English** Danbooru tag format. No Japanese text.
- ALL character appearance and NSFW tags must be kept UNCHANGED in "character".
- Only background, location, and environmental tags should change in "scene".

## Output Format
```json
{"character": "1girl, solo, ...", "scene": "masterpiece, best quality, ..."}
```
JSON only. No explanation or preamble."""


# ── US2 T030: Surroundings image prompt generation ──

SURROUNDINGS_IMAGE_PROMPT_SYSTEM = """You are a NovelAI background/scenery image prompt expert.

Generate a prompt for a BACKGROUND-ONLY image (NO characters) in 1216x832 LANDSCAPE format.

## Rules
1. Output comma-separated tags only.
2. Quality tags first: masterpiece, best quality, very aesthetic, no humans, scenery, background
3. Include detailed environmental tags: location, lighting, time of day, atmosphere, weather.
4. Wide landscape composition for 1216x832 aspect ratio.
5. NO character tags whatsoever (no 1girl, no person references).

## Output Style
- English tags only
- Comma-separated
- 30-50 tags max
- Focus on: location type, architectural/natural features, lighting, mood, colors, atmosphere

Output tag prompt only. No explanation."""

SURROUNDINGS_IMAGE_PROMPT_SYSTEM_NSFW = """You are a NovelAI background/scenery image prompt expert.

Generate a prompt for a BACKGROUND-ONLY image (NO characters) in 1216x832 LANDSCAPE format.
This is NSFW mode — scenes may have suggestive or intimate atmosphere.

## Rules
1. Output comma-separated tags only.
2. Quality tags first: masterpiece, best quality, very aesthetic, no humans, scenery, background
3. Include detailed environmental tags: location, lighting, time of day, atmosphere, weather.
4. Wide landscape composition for 1216x832 aspect ratio.
5. NO character tags whatsoever (no 1girl, no person references).
6. Scene can have romantic, sensual, or intimate atmosphere if appropriate to the action.

## Output Style
- English tags only
- Comma-separated
- 30-50 tags max
- Focus on: location type, architectural/natural features, lighting, mood, colors, atmosphere

Output tag prompt only. No explanation."""


def get_surroundings_image_prompt_system(nsfw_mode: bool = False) -> str:
    """Return the surroundings image generation system prompt.

    Args:
        nsfw_mode: Whether NSFW mode is enabled

    Returns:
        System prompt string for surroundings image tag generation
    """
    if nsfw_mode:
        return SURROUNDINGS_IMAGE_PROMPT_SYSTEM_NSFW
    return SURROUNDINGS_IMAGE_PROMPT_SYSTEM


def build_surroundings_image_user_prompt(
    instruction: str,
    before_description: str,
    after_description: str,
) -> str:
    """Build a user prompt for surroundings image generation.

    Args:
        instruction: The action instruction (e.g. "go to the cafe")
        before_description: Description before the action
        after_description: Description after the action

    Returns:
        User prompt string for surroundings image generation
    """
    return (
        f"Action: {instruction}\n\n"
        f"Scene before: {before_description}\n\n"
        f"Scene after: {after_description}\n\n"
        "Generate a background-only scenery prompt (1216x832 landscape) "
        "depicting the environment where this action takes place. "
        "NO characters. Focus on the location, atmosphere, and mood."
    )


# ── Scene-change helper functions (T004, T005, T006) ──


def get_action_image_edit_system_prompt(
    image_provider: str = "qwen",
    nsfw_mode: bool = False,
) -> str:
    """Return the scene-change image editing system prompt.

    Selects the appropriate template based on image provider and NSFW mode.

    Args:
        image_provider: Image provider ("novelai" or "qwen"/other)
        nsfw_mode: Whether NSFW mode is enabled

    Returns:
        System prompt string for scene-change image editing
    """
    if image_provider == "novelai":
        if nsfw_mode:
            return ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI_NSFW
        return ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI

    # Default (Qwen / other providers)
    if nsfw_mode:
        return ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NSFW
    return ACTION_IMAGE_EDIT_SYSTEM_PROMPT


def build_action_image_edit_prompt(
    instruction: str,
    current_description: str,
) -> str:
    """Build a user prompt for scene-change image editing.

    Combines the action instruction with the current image description
    to create a prompt for the image editing model.

    Args:
        instruction: The action instruction (e.g. "go to the cafe")
        current_description: Vision LLM description of the current image

    Returns:
        User prompt string for scene-change image editing
    """
    return (
        f"Current image description: {current_description}\n\n"
        f"Action instruction: {instruction}\n\n"
        "Change ONLY the background and environment to match the action. "
        "Keep the person exactly as they are."
    )


def get_action_novelai_prompt_generation_system(
    nsfw_mode: bool = False,
    language: str = "ja",
) -> str:
    """Return the scene-change NovelAI tag generation system prompt.

    Used with GLM-4.6 to generate scene-change tags that preserve
    character tags and only modify background/environment tags.

    Args:
        nsfw_mode: Whether NSFW mode is enabled
        language: Instruction language ("ja", "en", etc.)

    Returns:
        System prompt string for GLM-4.6 scene-change tag generation
    """
    language_name = "English" if language == "en" else "Japanese"
    language_hint = (
        "\n\nInstruction Language:\n"
        f"- The user instruction language is {language_name}."
        "\n- Interpret either Japanese or English user instructions correctly."
        "\n- Output must be English tag prompt only."
    )

    if nsfw_mode:
        return ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM_NSFW + language_hint
    return ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM + language_hint


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
    gender: str = "man",
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
        gender: Original gender of the character ("man" or "woman")

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

    # Map gender value to Japanese label for prompt
    gender_label = "男性" if gender == "man" else "女性"

    # Select user prompt template
    if is_pre_transform:
        user_prompt = PRE_TRANSFORM_ACTION_USER_PROMPT_TEMPLATE.format(
            instruction=instruction,
            pronoun=pronoun,
            gender=gender_label,
            recent_actions_section=recent_actions_section,
            personality_section=personality_section,
        )
    else:
        user_prompt = ACTION_USER_PROMPT_TEMPLATE.format(
            instruction=instruction,
            current_description=current_description or "不明",
            pronoun=pronoun,
            gender=gender_label,
            recent_actions_section=recent_actions_section,
            personality_section=personality_section,
        )

    return system_prompt, user_prompt
