"""外部 API 向け HTTP クライアントの生成と、レート制限時の再試行。

``httpx.AsyncClient`` の生成はすべてここを通す。timeout は必ず明示させ、
プーリングや共通ヘッダーを足したくなったときに 1 か所で済むようにする。
テストが ``httpx.AsyncClient`` を差し替えられるよう、生成は呼び出し時に
``httpx`` モジュールの属性を参照する。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")


def async_client(*, timeout: float | httpx.Timeout, **kwargs: Any) -> httpx.AsyncClient:
    """timeout を明示した ``httpx.AsyncClient`` を作る（``async with`` で使う）。"""
    return httpx.AsyncClient(timeout=timeout, **kwargs)


def is_rate_limited(exc: BaseException) -> bool:
    """例外がレート制限（HTTP 429）由来かどうか。

    ``httpx.HTTPStatusError`` はステータスで判定し、各サービスがメッセージに
    ステータスを埋め込んで投げ直す独自例外は文字列で判定する。
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429
    return "429" in str(exc)


async def retry_once_on_rate_limit(
    operation: Callable[[], Awaitable[T]],
    *,
    wait_seconds: float,
    what: str,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """``operation`` がレート制限で失敗したら ``wait_seconds`` 待って 1 回だけやり直す。

    レート制限以外の失敗と、2 回目の失敗はそのまま送出する。
    """
    try:
        return await operation()
    except exceptions as exc:
        if not is_rate_limited(exc):
            raise
        logger.warning(
            "429 detected during %s, retrying once after %ss", what, wait_seconds
        )
        await asyncio.sleep(wait_seconds)
        return await operation()
