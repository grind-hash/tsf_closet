"""外部モデル単位の共有直列実行ゲート。"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class ModelExecutionGate:
    """同一モデルへの同時リクエストをプロセス内で直列化する。"""

    def __init__(self) -> None:
        self._locks: defaultdict[tuple[str, str, str], asyncio.Lock] = defaultdict(
            asyncio.Lock
        )

    @asynccontextmanager
    async def hold(
        self, category: str, provider: str, model: str
    ) -> AsyncIterator[None]:
        # OpenRouter は従量課金のクラウドAPIで同時リクエストを受け付けるため
        # 直列化しない。ゲートはローカルGPU(selfhost)とNovelAIの保護が目的
        if provider == "openrouter":
            yield
            return
        key = (category, provider, model)
        started = time.monotonic()
        async with self._locks[key]:
            waited = time.monotonic() - started
            logger.debug(
                "Model queue acquired: category=%s provider=%s model=%s wait=%.3fs",
                category,
                provider,
                model,
                waited,
            )
            if waited >= 0.05:
                logger.info(
                    "Model queue acquired: category=%s provider=%s model=%s wait=%.3fs",
                    category,
                    provider,
                    model,
                    waited,
                )
            try:
                yield
            except asyncio.CancelledError:
                logger.warning(
                    "Model execution cancelled: category=%s provider=%s model=%s",
                    category,
                    provider,
                    model,
                )
                raise
            except Exception:
                logger.exception(
                    "Model execution failed: category=%s provider=%s model=%s",
                    category,
                    provider,
                    model,
                )
                raise


model_execution_gate = ModelExecutionGate()
