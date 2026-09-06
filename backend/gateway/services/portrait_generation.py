"""立ち絵(全身・単独・白/透過背景)の生成に共通する定数と生成関数。

Adventure の主人公・攻略対象の立ち絵と、キャラチャットの立ち絵が共用する。
Adventure 側の生成メソッド(_generate_portrait_unlocked 等)は run の state を
自前で読み書きするため据え置き、ここには run に依存しない部分だけを置く。
"""

from __future__ import annotations

from typing import Any

from ..consts.novelai_models import is_v5_image_model
from ..settings.config import settings
from .clothing_layers import merge_negative_prompt
from .cost_tracker import record_cost
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


async def generate_portrait_bytes(
    *,
    tags: str,
    nsfw_mode: bool,
    provider: Provider | str,
    image_model: str | None,
    reference_bytes: bytes | None,
    extra_negative: str = "",
    seed: int | None = None,
) -> bytes:
    """タグから単独の全身立ち絵を 1 枚生成して PNG bytes を返す。

    NovelAI は txt2img(精密参照は使わない。Anlas を消費しない)。
    OpenRouter / ComfyUI は参照画像があれば編集元にして同一性を保ち、無ければ
    txt2img で新規に描く(ComfyUI の txt2img はワークフローテンプレートが必要)。
    料金は cost_tracker に記録する。
    """
    provider_name = str(provider)
    prompt = enhance_prompt_for_novelai(
        tags + portrait_prompt_suffix(image_model), nsfw_mode=nsfw_mode
    )
    if provider_name == "novelai":
        negative = merge_negative_prompt(
            settings.novelai_negative_prompt,
            f"{PORTRAIT_EXTRA_NEGATIVE}, {extra_negative}"
            if extra_negative
            else PORTRAIT_EXTRA_NEGATIVE,
        )
        result = await image_service.generate_image(
            prompt,
            image_bytes=None,
            provider_override="novelai",
            negative_prompt=negative,
            nsfw_mode=nsfw_mode,
            character_references=None,
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
