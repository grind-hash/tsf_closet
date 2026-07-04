"""Anlas balance retrieval service.

Fetches the current Anlas balance from NovelAI's /user/data endpoint.
The SDK does not support this endpoint, so we use httpx directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from ..settings.config import settings

logger = logging.getLogger(__name__)

NOVELAI_USER_DATA_URL = "https://image.novelai.net/user/data"


@dataclass
class AnlasBalance:
    """Anlas balance information."""

    fixed_anlas: int
    purchased_anlas: int
    total_anlas: int


async def get_anlas_balance() -> Optional[AnlasBalance]:
    """Fetch the current Anlas balance from NovelAI.

    Returns:
        AnlasBalance if successful, None if API key is not configured
        or the provider is not NovelAI.

    Raises:
        httpx.HTTPStatusError: If the NovelAI API returns an error.
    """
    api_key = settings.novelai_api_key
    if not api_key:
        return None

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            NOVELAI_USER_DATA_URL,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()

    data = response.json()
    subscription = data.get("subscription", {})
    training_steps = subscription.get("trainingStepsLeft", {})
    fixed = training_steps.get("fixedTrainingStepsLeft", 0)
    purchased = training_steps.get("purchasedTrainingSteps", 0)

    return AnlasBalance(
        fixed_anlas=fixed,
        purchased_anlas=purchased,
        total_anlas=fixed + purchased,
    )
