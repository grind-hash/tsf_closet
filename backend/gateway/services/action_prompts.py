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

{previous_situation_section}
{recent_actions_section}
{personality_section}
冒頭は行動に関連する描写で始めてください。"""


PRE_TRANSFORM_ACTION_USER_PROMPT_TEMPLATE = """主人公は以下の行動を取ります:
「{instruction}」

主人公の性別: {gender}
主人公は普段の姿のままです。まだ何の変身も起きていません。

一人称: 「{pronoun}」

{previous_situation_section}
{recent_actions_section}
{personality_section}
冒頭は行動に関連する描写で始めてください。
変身・性転換・衣装変化に関する描写は絶対にしないでください。"""


# ── Situation summary system prompt for action context continuity ──

SITUATION_SUMMARY_SYSTEM_PROMPT = """以下のモノローグテキストを読み、主人公の現在の状況を1-2文（100文字以内）で要約してください。

含めるべき情報:
- 今いる場所
- 何をしているか（直近の行動の結果）
- 簡潔な心理状態（任意）

含めないこと:
- 外見や服装の詳細（別途管理されています）
- 長い物語的描写

要約のみを出力してください。説明や前置きは不要です。"""


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

ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM = """You are a NovelAI image generation prompt expert for ACTION instructions.

The user performs an action that may change the scene, clothing, pose, or any combination of these.

## Rules
1. Output **valid JSON only** with two keys: "character" and "scene".
2. "character": comma-separated English Danbooru-style tags for the character ONLY.
   - Start with: 1girl or 1boy, solo
   - ALWAYS KEEP immutable traits from the previous prompt: hair color/style, eye color, body type, face features.
   - If the action mentions clothing/outfit changes (e.g. "put on a suit", "wear a dress"), UPDATE the clothing tags to match the NEW outfit described in the action.
   - If the action does NOT mention clothing changes, keep the current clothing tags from the previous prompt.
   - Update pose and expression tags to match the action context.
   - If the previous prompt is in Japanese or natural language, translate/convert ALL tags to English Danbooru format.
   - Example (outfit change): "1boy, solo, short black hair, brown eyes, black suit, white dress shirt, necktie, standing"
   - Example (no outfit change): "1boy, solo, short black hair, brown eyes, white t-shirt, black shorts, walking"
   - Do NOT include background or environment tags here.
3. "scene": comma-separated English tags for background/environment ONLY.
   - Quality tags first: masterpiece, best quality, very aesthetic
   - Generate background/environment/location tags matching the action instruction.
   - Do NOT include character appearance tags here.

## CRITICAL
- ALL output tags must be in **English** Danbooru tag format. No Japanese text.
- Read the action instruction carefully: if it says to change clothes, you MUST change the clothing tags.
- Immutable traits (hair, eyes, body type) are NEVER changed.
- Mutable traits (clothing, pose, expression, accessories) are updated when the action requires it.

## Output Format
```json
{"character": "1boy, solo, short black hair, brown eyes, black suit, ...", "scene": "masterpiece, best quality, very aesthetic, train station, ..."}
```
JSON only. No explanation or preamble."""

ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM_NSFW = """You are a NovelAI image generation prompt expert for ACTION instructions.
Adult content tags are allowed.

The user performs an action that may change the scene, clothing, pose, or any combination of these.

## Rules
1. Output **valid JSON only** with two keys: "character" and "scene".
2. "character": comma-separated English Danbooru-style tags for the character ONLY.
   - Start with: 1girl or 1boy, solo
   - ALWAYS KEEP immutable traits from the previous prompt: hair color/style, eye color, body type, face features.
   - If the action mentions clothing/outfit changes (e.g. "put on a suit", "wear a dress"), UPDATE the clothing tags to match the NEW outfit described in the action.
   - If the action does NOT mention clothing changes, keep the current clothing/exposure tags from the previous prompt.
   - Update pose and expression tags to match the action context.
   - Keep NSFW/body exposure tags unless the action explicitly changes them (e.g. "get dressed").
   - If the previous prompt is in Japanese or natural language, translate/convert ALL tags to English Danbooru format.
   - Example (outfit change): "1boy, solo, short black hair, brown eyes, black suit, white dress shirt, necktie, standing"
   - Do NOT include background or environment tags here.
3. "scene": comma-separated English tags for background/environment ONLY.
   - Quality tags first: masterpiece, best quality, very aesthetic
   - Generate background/environment/location tags matching the action instruction.
   - Scene can have sensual or intimate atmosphere if appropriate.
   - Do NOT include character appearance tags here.

## CRITICAL
- ALL output tags must be in **English** Danbooru tag format. No Japanese text.
- Read the action instruction carefully: if it says to change clothes, you MUST change the clothing tags.
- Immutable traits (hair, eyes, body type) are NEVER changed.
- Mutable traits (clothing, pose, expression, accessories, exposure) are updated when the action requires it.

## Output Format
```json
{"character": "1boy, solo, short black hair, brown eyes, black suit, ...", "scene": "masterpiece, best quality, very aesthetic, train station, ..."}
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

# ── Surroundings image WITH reactive bystanders ──

SURROUNDINGS_WITH_PEOPLE_PROMPT_SYSTEM = """You are a NovelAI scenery + bystander image prompt expert.

Generate a prompt for a SCENERY image with EXACTLY 2-3 anonymous bystanders reacting to the scene.
Format: 832x1216 PORTRAIT (vertical composition to frame standing figures).

## Rules
1. Output comma-separated tags only.
2. Quality tags first: masterpiece, best quality, very aesthetic, scenery
3. Include EXACTLY 2 or 3 bystanders. Use ONE of these specific count tags:
   - For 2 people: "2others" (NEVER "multiple people" or "crowd")
   - For 3 people: "3others" (NEVER "multiple people" or "crowd")
4. **CRITICAL: Bystander reactions MUST match the intensity of the action.**
   - Mild action (walking, eating): surprised, curious, staring, glancing
   - Embarrassing action (strange outfit, talking loudly): open mouth, shocked, pointing, whispering, covering mouth, laughing
   - Extreme/indecent action (nudity, sexual): horrified, screaming, covering eyes, looking away, disgust, trembling, running away, open mouth, dropped jaw, frozen in shock, blushing furiously, averting gaze
   Choose the reaction tier that fits the action described by the user.
5. Keep bystanders generic. Example: businessman, office lady, student, passerby
6. FORBIDDEN tags: crowd, multiple people, many people, large group, 4+people, 5+people, group
7. Include environmental tags: location, lighting, time of day, atmosphere.
8. Vertical portrait composition suitable for 832x1216. Show bystanders at mid-distance (waist-up or full body visible).
9. Do NOT include the protagonist. This image shows the surroundings and bystander reactions only.

## Output Style
- English tags only
- Comma-separated
- 30-50 tags max
- Focus on: location, atmosphere, bystander EMOTIONAL reactions, portrait composition

Output tag prompt only. No explanation."""

SURROUNDINGS_WITH_PEOPLE_PROMPT_SYSTEM_NSFW = """You are a NovelAI scenery + bystander image prompt expert.

Generate a prompt for a SCENERY image with EXACTLY 2-3 anonymous bystanders reacting to the scene.
Format: 832x1216 PORTRAIT (vertical composition). NSFW mode — scenes may involve sexual or indecent actions.

## Rules
1. Output comma-separated tags only.
2. Quality tags first: masterpiece, best quality, very aesthetic, scenery
3. Include EXACTLY 2 or 3 bystanders. Use ONE of these specific count tags:
   - For 2 people: "2others" (NEVER "multiple people" or "crowd")
   - For 3 people: "3others" (NEVER "multiple people" or "crowd")
4. **CRITICAL: Bystander reactions MUST match the intensity and nature of the action.**
   - Mildly embarrassing: open mouth, shocked, pointing, whispering, covering mouth
   - Sexually suggestive: blushing, averting gaze, nosebleed, sweating, staring with wide eyes, trembling, fidgeting
   - Indecent/explicit: horrified, screaming, covering eyes, looking away, disgust, dropped jaw, frozen in shock, blushing furiously, running away, panicking, hands up in disbelief
   The action described by the user is likely provocative in NSFW mode. Choose STRONG reactions.
5. Keep bystanders generic. Example: businessman, office lady, student, passerby
6. FORBIDDEN tags: crowd, multiple people, many people, large group, 4+people, 5+people, group
7. Include environmental tags: location, lighting, time of day, atmosphere.
8. Vertical portrait composition suitable for 832x1216. Show bystanders at mid-distance (waist-up or full body visible).
9. Do NOT include the protagonist. Show ONLY bystanders and environment.
10. Emphasize the atmosphere: tense, awkward, chaotic, scandalous, voyeuristic.

## Output Style
- English tags only
- Comma-separated
- 30-50 tags max
- Focus on: location, atmosphere, bystander STRONG EMOTIONAL reactions, portrait composition

Output tag prompt only. No explanation."""


def get_surroundings_image_prompt_system(
    nsfw_mode: bool = False,
    include_people: bool = False,
    is_reality_change: bool = False,
) -> str:
    """Return the surroundings image generation system prompt.

    Args:
        nsfw_mode: Whether NSFW mode is enabled
        include_people: Whether to include reactive bystanders
        is_reality_change: Whether this is a reality-change scenario
            (bystanders treat everything as normal)

    Returns:
        System prompt string for surroundings image tag generation
    """
    if include_people:
        if nsfw_mode:
            base = SURROUNDINGS_WITH_PEOPLE_PROMPT_SYSTEM_NSFW
        else:
            base = SURROUNDINGS_WITH_PEOPLE_PROMPT_SYSTEM
        if is_reality_change:
            base += (
                "\n\n## OVERRIDE \u2014 Reality Change Mode\n"
                "This is a REALITY CHANGE scenario. In this altered world, "
                "the current situation is considered COMPLETELY NORMAL by everyone.\n"
                "Bystanders must show NO surprise, NO shock, NO embarrassment.\n"
                "Instead, use ONLY calm/indifferent reactions: "
                "calm, relaxed, indifferent, going about their business, "
                "looking at phone, chatting casually, walking normally, "
                "minding own business, nonchalant, unfazed.\n"
                "Do NOT use any shocked/surprised/embarrassed reaction tags."
            )
        return base
    if nsfw_mode:
        return SURROUNDINGS_IMAGE_PROMPT_SYSTEM_NSFW
    return SURROUNDINGS_IMAGE_PROMPT_SYSTEM


def build_surroundings_image_user_prompt(
    instruction: str,
    before_description: str,
    after_description: str,
    include_people: bool = False,
    is_reality_change: bool = False,
) -> str:
    """Build a user prompt for surroundings image generation.

    Args:
        instruction: The action instruction (e.g. "go to the cafe")
        before_description: Description before the action
        after_description: Description after the action
        include_people: Whether to include reactive bystanders
        is_reality_change: Whether this is a reality-change scenario

    Returns:
        User prompt string for surroundings image generation
    """
    base = (
        f"Action: {instruction}\n\n"
        f"Scene before: {before_description}\n\n"
        f"Scene after: {after_description}\n\n"
    )
    if include_people:
        if is_reality_change:
            return (
                base + "Generate a scenery prompt (832x1216 portrait) depicting the "
                "environment where this action takes place, with EXACTLY 2 or 3 "
                "anonymous bystanders (use 2others or 3others tag). "
                "Do NOT use 'crowd' or 'multiple people' tags. "
                "Do NOT include the protagonist. "
                "IMPORTANT: This is a REALITY CHANGE world where the current "
                "situation is completely normal. Bystanders must appear CALM, "
                "INDIFFERENT, and unbothered \u2014 going about their daily lives "
                "as if nothing unusual is happening. "
                "NO shocked, surprised, or embarrassed reactions."
            )
        return (
            base + "Generate a scenery prompt (832x1216 portrait) depicting the "
            "environment where this action takes place, with EXACTLY 2 or 3 "
            "anonymous bystanders (use 2others or 3others tag). "
            "Do NOT use 'crowd' or 'multiple people' tags. "
            "Do NOT include the protagonist. "
            "The bystanders' reactions MUST reflect the nature and intensity "
            "of the action described above. If the action is shocking, "
            "embarrassing, or indecent, bystanders should show STRONG "
            "emotional reactions (horror, covering eyes, blushing, etc). "
            "Focus on the location, atmosphere, and bystander reactions."
        )
    return (
        base + "Generate a background-only scenery prompt (1216x832 landscape) "
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
    previous_situation_summary: str | None = None,
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
        previous_situation_summary: LLM-generated summary of the previous action result

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

    # Build previous situation section
    previous_situation_section = ""
    if previous_situation_summary:
        previous_situation_section = (
            f"直前の状況:\n{previous_situation_summary}\n"
            "（上記の状況から自然に繋がるように物語を続けてください）"
        )

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
            previous_situation_section=previous_situation_section,
            recent_actions_section=recent_actions_section,
            personality_section=personality_section,
        )
    else:
        user_prompt = ACTION_USER_PROMPT_TEMPLATE.format(
            instruction=instruction,
            current_description=current_description or "不明",
            pronoun=pronoun,
            gender=gender_label,
            previous_situation_section=previous_situation_section,
            recent_actions_section=recent_actions_section,
            personality_section=personality_section,
        )

    return system_prompt, user_prompt
