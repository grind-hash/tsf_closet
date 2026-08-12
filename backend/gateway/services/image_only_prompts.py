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
