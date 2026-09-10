"""立ち絵(全身・単独・白/透過背景)の生成に共通する定数と生成関数。

Adventure の主人公・攻略対象の立ち絵と、キャラチャットの立ち絵が共用する。
Adventure 側の生成メソッド(_generate_portrait_unlocked 等)は run の state を
自前で読み書きするため据え置き、ここには run に依存しない部分だけを置く。
"""

from __future__ import annotations

import re
from typing import Any

from ..consts.novelai_models import is_v5_image_model, supports_character_references
from ..settings.config import settings
from .clothing_layers import (
    merge_negative_prompt,
    normalize_tag_for_match,
    split_tag_tokens,
)
from .cost_tracker import record_cost
from .identity_signature import has_explicit_adult_age
from .image_generation import image_service
from .prompts import enhance_prompt_for_novelai
from .providers import Provider


class PortraitGenerationError(RuntimeError):
    """立ち絵生成に失敗した(プロバイダーが画像を返さなかった等)。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def character_reference_strength(
    *, outfit_changed: bool, has_fresh_portrait: bool
) -> tuple[float, float]:
    """character reference の (strength, fidelity) を返す。

    参照画像が旧衣装の初期画像である場合のみ、衣装変更時に弱参照へ落とす。
    このターンの新衣装で描いた直後の立ち絵を参照する場合は弱めない。
    """
    if has_fresh_portrait or not outfit_changed:
        return 0.85, 1.0
    return 0.35, 0.55


# 参照画像を編集元として渡すプロバイダー(OpenRouter / ComfyUI)向けの同一性維持指示
REDRAW_REFERENCE_INSTRUCTION = (
    "Redraw the exact character from the attached image with the "
    "same face, hair, and identity, as described below.\n"
)


def character_reference_entry(
    image_bytes: bytes, *, outfit_changed: bool, has_fresh_portrait: bool
) -> dict[str, Any]:
    """NovelAI の character reference 1 件分（強度・忠実度込み）。"""
    strength, fidelity = character_reference_strength(
        outfit_changed=outfit_changed, has_fresh_portrait=has_fresh_portrait
    )
    return {
        "image": image_bytes,
        "type": "character",
        "strength": strength,
        "fidelity": fidelity,
    }


# 立ち絵専用の追加ネガティブ。full body + 透過/白背景の組み合わせは
# キャラクターシート風の複数ビュー・複数人を誘発しやすく、特に V5 で
# 同一人物が2人並ぶ事故が起きるため、単独1ビューを強制する
PORTRAIT_EXTRA_NEGATIVE = (
    "2girls, 2boys, 3girls, multiple girls, multiple boys, multiple views, "
    "reference sheet, character sheet, turnaround, variations, "
    "two people, multiple people, duplicate character, clone"
)

PORTRAIT_PROMPT_SUFFIX = ", solo, full body standing portrait, simple background, white background, no shadow"
# V5系モデルは透過背景をネイティブ生成できるため、白背景ではなく透過を指示する
# （フロント側の透過処理は既に透過を持つ画像を素通しする）
PORTRAIT_PROMPT_SUFFIX_V5 = (
    ", solo, full body standing portrait, transparent background, no shadow"
)


def portrait_prompt_suffix(image_model: str | None) -> str:
    """立ち絵用サフィックスをモデルに応じて返す（V5のみ透過背景指示）。"""
    return (
        PORTRAIT_PROMPT_SUFFIX_V5
        if is_v5_image_model(image_model)
        else PORTRAIT_PROMPT_SUFFIX
    )


def build_portrait_prompt(
    tags: str, image_model: str | None, *, nsfw_mode: bool = False
) -> str:
    """年齢・明示的な画風を尊重した立ち絵プロンプトを生成とプレビューで共用する。"""
    normalized = [normalize_tag_for_match(tag) for tag in split_tag_tokens(tags)]
    deformed = any(
        re.search(r"\b(?:chibi|super[- ]deformed)\b", tag) for tag in normalized
    )
    if (
        has_explicit_adult_age(tags)
        and not deformed
        and not {"adult proportions", "mature proportions"}.intersection(normalized)
    ):
        tags = f"{tags.rstrip(', ')}, adult proportions"
    return enhance_prompt_for_novelai(
        tags + portrait_prompt_suffix(image_model), nsfw_mode=nsfw_mode
    )


async def generate_portrait_bytes(
    *,
    tags: str,
    nsfw_mode: bool,
    provider: Provider | str,
    image_model: str | None,
    reference_bytes: bytes | None,
    extra_negative: str = "",
    seed: int | None = None,
    use_character_reference: bool = False,
) -> bytes:
    """タグから単独の全身立ち絵を 1 枚生成して PNG bytes を返す。

    NovelAI は txt2img。use_character_reference が真で参照画像があり、モデルが
    精密参照(character reference)に対応していれば 1 枚だけ弱参照で渡す(Anlas を
    消費するため、呼び出し側が利用者の確認を取ること)。それ以外は精密参照なし。
    OpenRouter / ComfyUI は参照画像があれば編集元にして同一性を保ち、無ければ
    txt2img で新規に描く(ComfyUI の txt2img はワークフローテンプレートが必要)。
    料金は cost_tracker に記録する。
    """
    provider_name = str(provider)
    prompt = build_portrait_prompt(tags, image_model, nsfw_mode=nsfw_mode)
    if provider_name == "novelai":
        negative = merge_negative_prompt(
            settings.novelai_negative_prompt,
            f"{PORTRAIT_EXTRA_NEGATIVE}, {extra_negative}"
            if extra_negative
            else PORTRAIT_EXTRA_NEGATIVE,
        )
        character_references = None
        if (
            use_character_reference
            and reference_bytes
            and supports_character_references(image_model)
        ):
            # 服装は変わり得るため弱めに参照する(Adventure の攻略対象立ち絵と同じ)
            character_references = [
                character_reference_entry(
                    reference_bytes, outfit_changed=True, has_fresh_portrait=False
                )
            ]
        result = await image_service.generate_image(
            prompt,
            image_bytes=None,
            provider_override="novelai",
            negative_prompt=negative,
            nsfw_mode=nsfw_mode,
            character_references=character_references,
            characters=None,
            seed=seed,
            size_override="portrait",
            novelai_model_override=image_model,
        )
    else:
        instruction = REDRAW_REFERENCE_INSTRUCTION if reference_bytes else ""
        result = await image_service.generate_image(
            instruction + prompt,
            image_bytes=reference_bytes,
            provider_override=provider_name,  # type: ignore[arg-type]
            nsfw_mode=nsfw_mode,
            size_override="portrait",
        )
    record_cost(result.cost_usd)
    if not result.images:
        raise PortraitGenerationError(
            "image_generation_failed", "立ち絵が生成されませんでした"
        )
    return result.images[0]
