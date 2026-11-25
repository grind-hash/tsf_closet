"""NovelAI 画像生成モデルの定義（唯一の情報源）。

ユーザー設定で選択可能なモデルと、各モデルに対応する
インペイントモデル・SDK 用ベースモデル・V5 判定をここに集約する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..settings.config import settings

# 精密参照の送信形式。モデルごとの対応は NovelAIImageModelInfo に持たせる
PreciseReferenceFormat = Literal["v4_5", "v5"]


@dataclass(frozen=True)
class NovelAIImageModelInfo:
    """NovelAI 画像モデル1件分のメタ情報。

    - inpaint_model: マスク付き生成時に使うモデル名
    - sdk_base_model: GenerateImageParams.model に渡す値。
      V5 モデルでも対応する v4.5 モデル名を入れ、実際の送信モデルは
      リクエスト直前に req.model を上書きして差し替える。novelai-sdk は
      V5 Full / Curated の名前を受け付けるが、節約モードの名前は受け付けず、
      精密参照も v4.5 系でしか組み立てないため、この方式を続けている。
    - family: "full" (NSFW 用) | "curated" (非 NSFW 用)
    - is_economy: 節約モード（steps 固定・独自ネガティブ不可）の蒸留モデルか
    - precise_reference_format: 精密参照の送信形式。"v4_5"（SDK 経由・忠実度あり）、
      "v5"（衣装参照あり・強度 5.0 まで・忠実度なし）、None（精密参照に非対応）
    """

    name: str
    inpaint_model: str
    sdk_base_model: str
    is_v5: bool
    family: str
    is_economy: bool = False
    precise_reference_format: PreciseReferenceFormat | None = "v4_5"


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
        precise_reference_format="v5",
    ),
    # V5 Full の節約モード（NovelAI の Medium effort）。steps 14・Euler Ancestral 固定で、
    # 独自ネガティブとプリセット変更は不可。節約版インペイントのモデル名が未確認のため、
    # インペイントは通常の V5 Full インペイントを使う
    "nai-diffusion-5-full-medium": NovelAIImageModelInfo(
        name="nai-diffusion-5-full-medium",
        inpaint_model="nai-diffusion-5-full-inpainting",
        sdk_base_model="nai-diffusion-4-5-full",
        is_v5=True,
        family="full",
        is_economy=True,
        # 節約モードは NovelAI 側で精密参照に対応していない
        precise_reference_format=None,
    ),
    # V5 Curated のインペイントは nai-diffusion-4-5-curated-inpainting を使う。
    # NovelAI 本家 UI が V5 Curated 選択時にこのモデルを用いる挙動を踏襲した意図的な設定。
    "nai-diffusion-5-curated": NovelAIImageModelInfo(
        name="nai-diffusion-5-curated",
        inpaint_model="nai-diffusion-4-5-curated-inpainting",
        sdk_base_model="nai-diffusion-4-5-curated",
        is_v5=True,
        family="curated",
        precise_reference_format="v5",
    ),
}

# ユーザー設定で選択可能なモデル（NSFW ON 用 / OFF 用）
NSFW_IMAGE_MODEL_OPTIONS = (
    "nai-diffusion-4-5-full",
    "nai-diffusion-5-full",
    "nai-diffusion-5-full-medium",
)
SFW_IMAGE_MODEL_OPTIONS = ("nai-diffusion-4-5-curated", "nai-diffusion-5-curated")

DEFAULT_NSFW_IMAGE_MODEL = "nai-diffusion-4-5-full"
DEFAULT_SFW_IMAGE_MODEL = "nai-diffusion-4-5-curated"

# 精密参照の種別（UI の選択肢）。衣装（costume）は V5 形式のみ
PRECISE_REFERENCE_TYPES = ("character&style", "character", "style", "costume")
PreciseReferenceType = Literal["character&style", "character", "style", "costume"]
# 精密参照の強度の上限（送信形式ごと）
PRECISE_REFERENCE_STRENGTH_MAX: dict[str, float] = {"v4_5": 1.0, "v5": 5.0}

# 節約モードの固定値。steps は NovelAI 側で 14 固定、UC プリセットは公式 UI の
# heavy（SDK 上の名前は "strong"）固定で、独自ネガティブは送らない
NOVELAI_ECONOMY_STEPS = 14
NOVELAI_ECONOMY_UC_PRESET = "strong"

# Pydantic の入力検証に使うモデル名の Literal。各 schemas で列挙を書き直さず
# ここから import する。レジストリ / 選択肢との整合は import 時に検証する
NovelAIImageModel = Literal[
    "nai-diffusion-4-5-full",
    "nai-diffusion-4-5-curated",
    "nai-diffusion-5-full",
    "nai-diffusion-5-full-medium",
    "nai-diffusion-5-curated",
]
NsfwImageModel = Literal[
    "nai-diffusion-4-5-full",
    "nai-diffusion-5-full",
    "nai-diffusion-5-full-medium",
]
SfwImageModel = Literal["nai-diffusion-4-5-curated", "nai-diffusion-5-curated"]

assert set(NovelAIImageModel.__args__) == set(NOVELAI_IMAGE_MODELS)  # type: ignore[attr-defined]
assert NsfwImageModel.__args__ == NSFW_IMAGE_MODEL_OPTIONS  # type: ignore[attr-defined]
assert SfwImageModel.__args__ == SFW_IMAGE_MODEL_OPTIONS  # type: ignore[attr-defined]
assert PreciseReferenceType.__args__ == PRECISE_REFERENCE_TYPES  # type: ignore[attr-defined]


def is_v5_image_model(name: str | None) -> bool:
    """モデル名が V5 系かどうかを返す。未知名・None は False。"""
    if not name:
        return False
    info = NOVELAI_IMAGE_MODELS.get(name)
    return info.is_v5 if info else False


def is_economy_image_model(name: str | None) -> bool:
    """モデル名が節約モードの蒸留モデルかどうかを返す。未知名・None は False。"""
    if not name:
        return False
    info = NOVELAI_IMAGE_MODELS.get(name)
    return info.is_economy if info else False


def precise_reference_format(name: str | None) -> PreciseReferenceFormat | None:
    """モデル名から精密参照の送信形式を返す。精密参照に非対応のモデルは None。

    未知名・None は v4.5 相当として "v4_5" を返す。
    """
    if not name:
        return "v4_5"
    info = NOVELAI_IMAGE_MODELS.get(name)
    return info.precise_reference_format if info else "v4_5"


def supports_character_references(name: str | None) -> bool:
    """精密参照（character reference）を送れるモデルかどうかを返す。

    V4.5 系と V5 Full / Curated は True、V5 Full の節約モードは False。
    未知名・None は v4.5 相当として True。
    """
    return precise_reference_format(name) is not None


def resolve_v5_reference_caption(reference_type: str, include_outfit: bool) -> str:
    """V5 の精密参照で director_reference_descriptions に入れる base_caption を返す。

    キャラ系の2種は「衣装も参照する」で caption が分かれる。絵柄・衣装は無視する。
    未知の種別はキャラクター＆絵柄として扱う。
    """
    if reference_type == "character":
        return "character_mainoutfit" if include_outfit else "character"
    if reference_type == "style":
        return "style"
    if reference_type == "costume":
        return "costume"
    return "character&style" if include_outfit else "character&style_anyoutfit"


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
