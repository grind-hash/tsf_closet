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


class DecisionTransport(StrEnum):
    """構造化判定 (TypeSafe AI Jev) の通り道。

    生成プロバイダー (Provider) とは独立した軸。Jev はテキストを生成せず
    chat/completions でも呼べないため、Provider には含めない。
    """

    OFF = "off"
    OPENROUTER = "openrouter"
    TYPESAFE = "typesafe"


# 判定結果を実際の挙動へ反映してよい対象の識別子
JEV_TARGETS: tuple[str, ...] = (
    "congruence",
    "chat_lookup",
    "search_policy",
    "tags",
)


def resolve_decision_transport(override: object = None) -> DecisionTransport:
    """Jev の呼び出し経路。JEV_PROVIDER に従い、未知の値は off に落とす。"""
    text = str(override or settings.jev_provider or "").strip().lower()
    try:
        return DecisionTransport(text)
    except ValueError:
        if text:
            logger.warning("Unknown JEV_PROVIDER '%s', treating as off", text)
        return DecisionTransport.OFF


def jev_judge_enabled() -> bool:
    """Jev を呼んでよいか。

    API キーがあることは利用の根拠にしない。JEV_PROVIDER が明示的に設定され、
    かつ選んだ経路のキーが揃っているときだけ True を返す。
    """
    transport = resolve_decision_transport()
    if transport is DecisionTransport.OPENROUTER:
        return bool(settings.openrouter_api_key)
    if transport is DecisionTransport.TYPESAFE:
        return bool(settings.typesafe_api_key)
    return False


def jev_live(target: str) -> bool:
    """この判定対象で Jev の答えを実際の挙動へ反映してよいか。

    JEV_LIVE_TARGETS が空なら全てシャドー(ログのみ)。``all`` で全対象を反映する。
    """
    raw = str(settings.jev_live_targets or "").strip().lower()
    if not raw:
        return False
    if raw == "all":
        return True
    wanted = {item.strip() for item in raw.split(",") if item.strip()}
    return target in wanted


def cost_tracking_enabled() -> bool:
    """料金表示を出すべき構成か。従量課金の外部 API を 1 つでも使うなら True。"""
    return (
        resolve_image_provider() is Provider.OPENROUTER
        or resolve_image_description_provider() is Provider.OPENROUTER
        or resolve_text_provider() is Provider.OPENROUTER
        or jev_judge_enabled()
    )
