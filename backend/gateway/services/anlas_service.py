"""Anlas balance retrieval service.

Fetches the current Anlas balance and V5 usage limit from NovelAI's
/user/subscription endpoint. The SDK does not support this endpoint,
so we use httpx directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..settings.config import settings
from .http_client import async_client

logger = logging.getLogger(__name__)

# /user/subscription はサブスクリプション情報そのものを返し、
# trainingStepsLeft (Anlas) と usage (V5 の利用上限) を1コールで取得できる
NOVELAI_SUBSCRIPTION_URL = "https://image.novelai.net/user/subscription"


@dataclass
class NovelAIUsage:
    """V5 image generation usage limit information."""

    percent: int
    is_negative: bool
    time_until_next_percent: int


@dataclass
class AnlasBalance:
    """Anlas balance information."""

    fixed_anlas: int
    purchased_anlas: int
    total_anlas: int
    usage: NovelAIUsage | None = None


def parse_novelai_usage(data: Any) -> NovelAIUsage | None:
    """subscription レスポンスの usage キーを防御的にパースする。

    usage キーが無い・形式が不正な場合は None を返す（旧アカウント等の互換）。
    """
    if not isinstance(data, dict):
        return None
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    percent = usage.get("percent")
    if not isinstance(percent, (int, float)) or isinstance(percent, bool):
        return None
    return NovelAIUsage(
        percent=int(percent),
        is_negative=bool(usage.get("isNegative", False)),
        time_until_next_percent=int(usage.get("timeUntilNextPercent") or 0),
    )


async def get_anlas_balance() -> AnlasBalance | None:
    """Fetch the current Anlas balance and usage limit from NovelAI.

    Returns:
        AnlasBalance if successful, None if API key is not configured
        or the provider is not NovelAI.

    Raises:
        httpx.HTTPStatusError: If the NovelAI API returns an error.
    """
    api_key = settings.novelai_api_key
    if not api_key:
        return None

    async with async_client(timeout=10.0) as client:
        response = await client.get(
            NOVELAI_SUBSCRIPTION_URL,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()

    data = response.json()
    # /user/subscription はトップレベルが subscription 情報。
    # /user/data 形式（subscription キーにネスト）が返っても拾えるようにする
    subscription = data.get("subscription") if isinstance(data, dict) else None
    if not isinstance(subscription, dict):
        subscription = data if isinstance(data, dict) else {}
    training_steps = subscription.get("trainingStepsLeft", {})
    if not isinstance(training_steps, dict):
        training_steps = {}
    fixed = training_steps.get("fixedTrainingStepsLeft", 0)
    purchased = training_steps.get("purchasedTrainingSteps", 0)

    return AnlasBalance(
        fixed_anlas=fixed,
        purchased_anlas=purchased,
        total_anlas=fixed + purchased,
        usage=parse_novelai_usage(subscription),
    )
