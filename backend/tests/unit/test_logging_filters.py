"""Tests for the log filters that keep timer-driven polling out of the logs."""

import logging

import httpx
import pytest

from gateway.settings.config import (
    HealthCheckAccessFilter,
    SuppressedHttpLogFilter,
    quiet_http_logs,
)


def _access_record(path: str) -> logging.LogRecord:
    # uvicorn.access logs with (client_addr, method, full_path, http_version,
    # status_code) as args.
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:50000", "GET", path, "1.1", 200),
        exc_info=None,
    )


def test_filter_drops_the_speech_engine_status_poll() -> None:
    log_filter = HealthCheckAccessFilter()

    assert log_filter.filter(_access_record("/api/aivisspeech/status")) is False
    assert log_filter.filter(_access_record("/api/aivisspeech/status?t=1")) is False


def test_filter_keeps_other_endpoints() -> None:
    log_filter = HealthCheckAccessFilter()

    assert log_filter.filter(_access_record("/api/aivisspeech/speakers")) is True
    assert log_filter.filter(_access_record("/api/game/play")) is True


def test_filter_handles_records_without_access_log_args() -> None:
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Application startup complete.",
        args=None,
        exc_info=None,
    )

    assert HealthCheckAccessFilter().filter(record) is True


def _httpx_records(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "httpx"]


@pytest.mark.asyncio
async def test_quiet_http_logs_suppresses_only_the_wrapped_request(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request)

    httpx_logger = logging.getLogger("httpx")
    log_filter = SuppressedHttpLogFilter()
    httpx_logger.addFilter(log_filter)
    try:
        with caplog.at_level(logging.INFO, logger="httpx"):
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport) as client:
                with quiet_http_logs():
                    await client.get("http://127.0.0.1:10101/version")
                assert _httpx_records(caplog) == []

                # 抜けた後は通常どおり記録される
                await client.get("http://127.0.0.1:10101/speakers")
                assert len(_httpx_records(caplog)) == 1
    finally:
        httpx_logger.removeFilter(log_filter)


def test_suppressed_http_log_filter_passes_records_by_default() -> None:
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP Request: %s %s",
        args=("GET", "http://127.0.0.1:10101/version"),
        exc_info=None,
    )

    assert SuppressedHttpLogFilter().filter(record) is True
