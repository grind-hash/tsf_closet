"""画像のみモード用のプロンプトテンプレート。"""

from __future__ import annotations


IMAGE_ONLY_EDIT_SYSTEM_PROMPT = """You convert a natural-language image editing request into a concise English prompt for an image editing model.

The user may request any combination of changes to clothing, appearance, pose, expression, camera composition, lighting, background, environment, or scene.

Requirements:
- Apply every explicit user-requested change.
- Preserve the subject's identity, face, and other unmentioned traits.
- Preserve unmentioned image elements whenever possible.
- Describe only the final edited image. Do not describe a before/after comparison.
- Produce one image only. Do not request panels, split screens, captions, or explanatory text.
- Keep the result concrete and visually descriptive, around 50-100 words.

Output only the English image editing prompt."""


IMAGE_ONLY_EDIT_SYSTEM_PROMPT_NSFW = """You convert a natural-language image editing request into a concise English prompt for an image editing model. Adult content is allowed.

The user may request any combination of changes to clothing, appearance, pose, expression, camera composition, lighting, background, environment, scene, or level of exposure.

Requirements:
- Apply every explicit user-requested change.
- Preserve the subject's identity, face, and other unmentioned traits.
- Preserve unmentioned image elements whenever possible.
- Describe only the final edited image. Do not describe a before/after comparison.
- Produce one image only. Do not request panels, split screens, captions, or explanatory text.
- Keep the result concrete and visually descriptive, around 50-100 words.

Output only the English image editing prompt."""


IMAGE_ONLY_NOVELAI_SYSTEM_PROMPT = """You convert a natural-language image editing request into one positive NovelAI prompt using concise English Danbooru-style tags.

The user may request any combination of changes to clothing, appearance, pose, expression, camera composition, lighting, background, environment, or scene.

Requirements:
- Apply every explicit user-requested change.
- Preserve the main subject's identity and all unmentioned traits from the current image description.
- Preserve unmentioned scene elements whenever possible.
- Describe only the final edited image.
- Single image only; no panels, split screen, before/after comparison, captions, or explanatory text.
- Use comma-separated English tags and end with "very aesthetic, best quality".

Output only the positive prompt."""


IMAGE_ONLY_NOVELAI_SYSTEM_PROMPT_NSFW = """You convert a natural-language image editing request into one positive NovelAI prompt using concise English Danbooru-style tags. Adult content tags are allowed.

The user may request any combination of changes to clothing, appearance, pose, expression, camera composition, lighting, background, environment, scene, or level of exposure.

Requirements:
- Apply every explicit user-requested change.
- Preserve the main subject's identity and all unmentioned traits from the current image description.
- Preserve unmentioned scene elements whenever possible.
- Describe only the final edited image.
- Single image only; no panels, split screen, before/after comparison, captions, or explanatory text.
- Use comma-separated English tags and end with "nsfw, very aesthetic, best quality".

Output only the positive prompt."""


# --- text-to-image (i2iなし) 用 ---
# 画像のみモードで前画像を使わず新規生成するときのプロンプト。
# 編集用プロンプトと異なり「保持」ルールを持たず、指示・メモリ・属性から全体を設計させる。

IMAGE_ONLY_GENERATE_SYSTEM_PROMPT = """You convert a natural-language request into a concise English prompt for a text-to-image model.

There is no source image. Design the whole picture from the request: character (gender, hair, eyes, body, face), clothing, pose, expression, camera composition, lighting, background, and scene. Use the memory notes and world attributes included in the request when present.

Requirements:
- Apply every explicit user request.
- Invent any unspecified detail so the image is complete and coherent.
- Describe only the final image. One image only; no panels, split screens, captions, or explanatory text.
- Keep the result concrete and visually descriptive, around 50-100 words.

Output only the English image generation prompt."""


IMAGE_ONLY_GENERATE_SYSTEM_PROMPT_NSFW = """You convert a natural-language request into a concise English prompt for a text-to-image model. Adult content is allowed.

There is no source image. Design the whole picture from the request: character (gender, hair, eyes, body, face), clothing, level of exposure, pose, expression, camera composition, lighting, background, and scene. Use the memory notes and world attributes included in the request when present.

Requirements:
- Apply every explicit user request.
- Invent any unspecified detail so the image is complete and coherent.
- Describe only the final image. One image only; no panels, split screens, captions, or explanatory text.
- Keep the result concrete and visually descriptive, around 50-100 words.

Output only the English image generation prompt."""


IMAGE_ONLY_NOVELAI_GENERATE_SYSTEM_PROMPT = """You convert a natural-language request into one positive NovelAI prompt using concise English Danbooru-style tags for text-to-image generation.

There is no source image. Design the whole picture from the request: start with 1girl or 1boy (add solo unless several people are requested), then hair, eyes, body, face, clothing, pose, expression, camera, lighting, background, and scene. Use the memory notes and world attributes included in the request when present.

Requirements:
- Apply every explicit user request.
- Invent any unspecified detail so the image is complete and coherent.
- Single image only; no panels, split screen, before/after comparison, captions, or explanatory text.
- Use comma-separated English tags and end with "very aesthetic, best quality".

Output only the positive prompt."""


IMAGE_ONLY_NOVELAI_GENERATE_SYSTEM_PROMPT_NSFW = """You convert a natural-language request into one positive NovelAI prompt using concise English Danbooru-style tags for text-to-image generation. Adult content tags are allowed.

There is no source image. Design the whole picture from the request: start with 1girl or 1boy (add solo unless several people are requested), then hair, eyes, body, face, clothing, level of exposure, pose, expression, camera, lighting, background, and scene. Use the memory notes and world attributes included in the request when present.

Requirements:
- Apply every explicit user request.
- Invent any unspecified detail so the image is complete and coherent.
- Single image only; no panels, split screen, before/after comparison, captions, or explanatory text.
- Use comma-separated English tags and end with "nsfw, very aesthetic, best quality".

Output only the positive prompt."""


# NovelAI Opus モード（行動モード用のJSON生成システムプロンプトを流用する経路）の
# システム末尾に付け、前プロンプトからの「保持」ルールを無効化する。
# Output Format 自体は書き直さない（複数人モードで書き換わった形式をそのまま尊重させる）。
IMAGE_ONLY_TEXT_TO_IMAGE_RULE = """

## TEXT-TO-IMAGE MODE (overrides the rules above)
There is NO previous image and NO previous prompt for this request. Every rule above about keeping, preserving, or copying traits, clothing, exposure, or location from the previous prompt does NOT apply.
- Design the character from scratch: choose gender, hair, eyes, body, face, clothing, pose, expression, and location from the user instruction, the memory notes, and the world attributes listed in the instruction.
- If the instruction describes a new or "-style" character, depict that character; do not reuse traits of any earlier character unless the instruction asks for it.
- Keep the Output Format defined above exactly; do not change the JSON keys or structure."""


def get_image_only_edit_system_prompt(
    image_provider: str,
    nsfw_mode: bool = False,
) -> str:
    """画像プロバイダーに応じた自由編集用システムプロンプトを返す。"""
    if image_provider == "novelai":
        return (
            IMAGE_ONLY_NOVELAI_SYSTEM_PROMPT_NSFW
            if nsfw_mode
            else IMAGE_ONLY_NOVELAI_SYSTEM_PROMPT
        )
    return (
        IMAGE_ONLY_EDIT_SYSTEM_PROMPT_NSFW
        if nsfw_mode
        else IMAGE_ONLY_EDIT_SYSTEM_PROMPT
    )


def build_image_only_edit_prompt(
    instruction: str,
    current_description: str,
) -> str:
    """現在画像の説明と自由編集指示をユーザープロンプトへまとめる。"""
    return (
        f"Current image description:\n{current_description or 'Unknown'}\n\n"
        f"User editing instruction:\n{instruction}\n\n"
        "Create the final image editing prompt while preserving every element "
        "that the instruction does not explicitly change."
    )


def get_image_only_generate_system_prompt(
    image_provider: str,
    nsfw_mode: bool = False,
) -> str:
    """画像プロバイダーに応じた新規生成（text-to-image）用システムプロンプトを返す。"""
    if image_provider == "novelai":
        return (
            IMAGE_ONLY_NOVELAI_GENERATE_SYSTEM_PROMPT_NSFW
            if nsfw_mode
            else IMAGE_ONLY_NOVELAI_GENERATE_SYSTEM_PROMPT
        )
    return (
        IMAGE_ONLY_GENERATE_SYSTEM_PROMPT_NSFW
        if nsfw_mode
        else IMAGE_ONLY_GENERATE_SYSTEM_PROMPT
    )


def build_image_only_generate_prompt(instruction: str) -> str:
    """前画像の説明を含めず、新規生成指示だけをユーザープロンプトへまとめる。"""
    return (
        f"User request:\n{instruction}\n\n"
        "Create the final image generation prompt. There is no existing image; "
        "design everything from the request."
    )
