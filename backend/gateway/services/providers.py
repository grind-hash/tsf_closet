"""生成プロバイダー（selfhost / openrouter / novelai）の判定を一元化する。

IMAGE_PROVIDER / FEELING_PROVIDER / IMAGE_DESCRIPTION_PROVIDER は文字列設定で、
大文字小文字の揺れや未知の値がありうる。判定は必ずここを通し、各所で
``settings.*_provider`` を直接比較しない。値は ``StrEnum`` なので、既存の
``== "novelai"`` のような文字列比較や f-string への埋め込みもそのまま使える。
"""

from __future__ import annotations

import logging
from enum import StrEnum

from ..settings.config import settings

logger = logging.getLogger(__name__)


class Provider(StrEnum):
    SELFHOST = "selfhost"
    OPENROUTER = "openrouter"
    NOVELAI = "novelai"


KNOWN_PROVIDERS: tuple[str, ...] = tuple(provider.value for provider in Provider)


def normalize_provider(
    value: object,
    *,
    default: Provider = Provider.SELFHOST,
    warn: bool = False,
) -> Provider:
    """設定値や上書き値を Provider に正規化する。未知の値は default に落とす。"""
    text = str(value or "").strip().lower()
    try:
        return Provider(text)
    except ValueError:
        if warn and text:
            logger.warning(
                "Unknown provider '%s', falling back to '%s'", value, default.value
            )
        return default


def resolve_image_provider(override: object = None) -> Provider:
    """画像生成のプロバイダー。override が無ければ IMAGE_PROVIDER に従う。"""
    return normalize_provider(override or settings.image_provider)


def resolve_text_provider(override: object = None) -> Provider:
    """テキスト生成（心境・Adventure・補助判定）のプロバイダー。FEELING_PROVIDER に従う。"""
    return normalize_provider(override or settings.feeling_provider)


def resolve_image_description_provider(override: object = None) -> Provider:
    """画像説明（Vision）のプロバイダー。IMAGE_DESCRIPTION_PROVIDER に従う。"""
    return normalize_provider(override or settings.image_description_provider)
