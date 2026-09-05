"""services/http_client.py: クライアント生成の差し替え可能性とレート制限リトライ。"""

from __future__ import annotations

import httpx
import pytest

from gateway.services import http_client
from gateway.services.http_client import (
    async_client,
    is_rate_limited,
    retry_once_on_rate_limit,
)


def test_async_client_sets_timeout_and_honours_monkeypatched_httpx(monkeypatch):
    client = async_client(timeout=3.0)
    assert isinstance(client, httpx.AsyncClient)
    assert client.timeout == httpx.Timeout(3.0)

    sentinel = object()
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: sentinel)
    assert async_client(timeout=1.0) is sentinel


def test_is_rate_limited_checks_status_or_message():
    request = httpx.Request("GET", "https://example.test")
    too_many = httpx.HTTPStatusError(
        "limited", request=request, response=httpx.Response(429, request=request)
    )
    forbidden = httpx.HTTPStatusError(
        "forbidden", request=request, response=httpx.Response(403, request=request)
    )
    assert is_rate_limited(too_many)
    assert not is_rate_limited(forbidden)
    assert is_rate_limited(RuntimeError("NovelAI API error: 429"))
    assert not is_rate_limited(RuntimeError("boom"))


@pytest.fixture
def no_sleep(monkeypatch):
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(http_client.asyncio, "sleep", fake_sleep)
    return waits


async def test_retry_returns_first_success_without_waiting(no_sleep):
    calls: list[int] = []

    async def operation() -> str:
        calls.append(1)
        return "ok"

    assert await retry_once_on_rate_limit(operation, wait_seconds=5, what="x") == "ok"
    assert calls == [1]
    assert no_sleep == []


async def test_retry_waits_and_retries_once_on_rate_limit(no_sleep):
    attempts: list[int] = []

    async def operation() -> str:
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("status 429")
        return "second"

    result = await retry_once_on_rate_limit(operation, wait_seconds=7, what="x")

    assert result == "second"
    assert attempts == [1, 1]
    assert no_sleep == [7]


async def test_retry_reraises_other_errors_and_second_failures(no_sleep):
    async def always_fails() -> str:
        raise RuntimeError("status 429")

    async def other_error() -> str:
        raise ValueError("unrelated")

    with pytest.raises(RuntimeError):
        await retry_once_on_rate_limit(always_fails, wait_seconds=1, what="x")
    assert no_sleep == [1]

    with pytest.raises(ValueError):
        await retry_once_on_rate_limit(other_error, wait_seconds=1, what="x")
    assert no_sleep == [1]


async def test_retry_only_catches_listed_exception_types(no_sleep):
    async def operation() -> str:
        raise RuntimeError("status 429")

    with pytest.raises(RuntimeError):
        await retry_once_on_rate_limit(
            operation, wait_seconds=1, what="x", exceptions=(ValueError,)
        )
    assert no_sleep == []
