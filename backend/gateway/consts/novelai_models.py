"""NovelAI 画像生成モデルの定義（唯一の情報源）。

ユーザー設定で選択可能なモデルと、各モデルに対応する
インペイントモデル・SDK 用ベースモデル・V5 判定をここに集約する。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..settings.config import settings


@dataclass(frozen=True)
class NovelAIImageModelInfo:
    """NovelAI 画像モデル1件分のメタ情報。

    - inpaint_model: マスク付き生成時に使うモデル名
    - sdk_base_model: GenerateImageParams.model に渡す値。
      novelai-sdk の Literal 制約 (v4.5 まで) を満たす必要があるため、
      V5 モデルでは対応する v4.5 モデル名を入れ、実際の送信モデルは
      リクエスト直前に req.model を上書きして差し替える。
    - family: "full" (NSFW 用) | "curated" (非 NSFW 用)
    """

    name: str
    inpaint_model: str
    sdk_base_model: str
    is_v5: bool
    family: str


NOVELAI_IMAGE_MODELS: dict[str, NovelAIImageModelInfo] = {
    # v4.5 系のインペイントモデルは env（NOVELAI_INPAINT_MODEL 等）の
    # カスタマイズを従来どおり尊重する
    "nai-diffusion-4-5-full": NovelAIImageModelInfo(
        name="nai-diffusion-4-5-full",
        inpaint_model=settings.novelai_inpaint_model,
        sdk_base_model="nai-diffusion-4-5-full",
        is_v5=False,
        family="full",
    ),
    "nai-diffusion-4-5-curated": NovelAIImageModelInfo(
        name="nai-diffusion-4-5-curated",
        inpaint_model=settings.novelai_curated_inpaint_model,
        sdk_base_model="nai-diffusion-4-5-curated",
        is_v5=False,
        family="curated",
    ),
    "nai-diffusion-5-full": NovelAIImageModelInfo(
        name="nai-diffusion-5-full",
        inpaint_model="nai-diffusion-5-full-inpainting",
        sdk_base_model="nai-diffusion-4-5-full",
        is_v5=True,
        family="full",
    ),
    # V5 Curated のインペイントは nai-diffusion-4-5-curated-inpainting を使う。
    # NovelAI 本家 UI が V5 Curated 選択時にこのモデルを用いる挙動を踏襲した意図的な設定。
    "nai-diffusion-5-curated": NovelAIImageModelInfo(
        name="nai-diffusion-5-curated",
        inpaint_model="nai-diffusion-4-5-curated-inpainting",
        sdk_base_model="nai-diffusion-4-5-curated",
        is_v5=True,
        family="curated",
    ),
}

# ユーザー設定で選択可能なモデル（NSFW ON 用 / OFF 用）
NSFW_IMAGE_MODEL_OPTIONS = ("nai-diffusion-4-5-full", "nai-diffusion-5-full")
SFW_IMAGE_MODEL_OPTIONS = ("nai-diffusion-4-5-curated", "nai-diffusion-5-curated")

DEFAULT_NSFW_IMAGE_MODEL = "nai-diffusion-4-5-full"
DEFAULT_SFW_IMAGE_MODEL = "nai-diffusion-4-5-curated"


def is_v5_image_model(name: str | None) -> bool:
    """モデル名が V5 系かどうかを返す。未知名・None は False。"""
    if not name:
        return False
    info = NOVELAI_IMAGE_MODELS.get(name)
    return info.is_v5 if info else False


def get_image_model_info(name: str, *, nsfw_mode: bool) -> NovelAIImageModelInfo:
    """モデル名からメタ情報を解決する。

    レジストリ未登録の名前（env でカスタム指定されたモデル等）は
    v4.5 相当として扱い、インペイントモデルと SDK ベースモデルを
    nsfw_mode に応じた env 設定から補完する。
    """
    info = NOVELAI_IMAGE_MODELS.get(name)
    if info is not None:
        return info
    if nsfw_mode:
        return NovelAIImageModelInfo(
            name=name,
            inpaint_model=settings.novelai_inpaint_model,
            sdk_base_model=DEFAULT_NSFW_IMAGE_MODEL,
            is_v5=False,
            family="full",
        )
    return NovelAIImageModelInfo(
        name=name,
        inpaint_model=settings.novelai_curated_inpaint_model,
        sdk_base_model=DEFAULT_SFW_IMAGE_MODEL,
        is_v5=False,
        family="curated",
    )


def resolve_user_image_model(user_settings: dict, nsfw_mode: bool) -> str:
    """ユーザー設定辞書と NSFW モードから実効モデル名を決める。

    キー欠落時（旧データ・テスト用モック）は従来どおり env 既定の v4.5 系に倒す。
    """
    if nsfw_mode:
        return user_settings.get("novelai_image_model") or settings.novelai_model
    return (
        user_settings.get("novelai_curated_image_model")
        or settings.novelai_curated_model
    )
