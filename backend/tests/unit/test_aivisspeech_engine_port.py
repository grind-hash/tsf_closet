"""Tests for the user-configurable speech synthesis engine port.

The default port (10101) can be taken by another program, so the port is a user
setting. Only the port is configurable: scheme and host stay under
AIVIS_ENGINE_BASE_URL so container deployments keep working.
"""

from unittest.mock import AsyncMock

import httpx
import pytest

from gateway.services.aivisspeech_service import AivisSpeechService


def _patch_base_url(monkeypatch, value: str) -> None:
    monkeypatch.setattr(
        "gateway.services.aivisspeech_service.settings.aivis_engine_base_url",
        value,
        raising=False,
    )


def _patch_user_settings(monkeypatch, user_settings: dict) -> None:
    # gateway.services re-exports the singleton, so patch the instance itself.
    from gateway.services.settings_service import settings_service

    monkeypatch.setattr(
        settings_service,
        "get_user_settings",
        AsyncMock(return_value=user_settings),
    )


def test_default_engine_port_reads_the_base_url(monkeypatch) -> None:
    _patch_base_url(monkeypatch, "http://127.0.0.1:10101")

    assert AivisSpeechService._default_engine_port() == 10101


def test_default_engine_port_falls_back_to_the_scheme_port(monkeypatch) -> None:
    _patch_base_url(monkeypatch, "https://tts.example.com")

    assert AivisSpeechService._default_engine_port() == 443


def test_build_base_url_replaces_only_the_port(monkeypatch) -> None:
    _patch_base_url(monkeypatch, "http://aivis:10101")

    assert AivisSpeechService._build_base_url(50021) == "http://aivis:50021"


def test_build_base_url_brackets_ipv6_hosts(monkeypatch) -> None:
    _patch_base_url(monkeypatch, "http://[::1]:10101")

    assert AivisSpeechService._build_base_url(50021) == "http://[::1]:50021"


@pytest.mark.asyncio
async def test_resolve_engine_port_prefers_the_user_setting(monkeypatch) -> None:
    _patch_base_url(monkeypatch, "http://127.0.0.1:10101")
    _patch_user_settings(monkeypatch, {"tts_engine_port": 50021})
    service = AivisSpeechService()

    assert await service.resolve_engine_port() == 50021
    assert await service.resolve_base_url() == "http://127.0.0.1:50021"


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", [None, 0, 65536, -1, "50021", True])
async def test_resolve_engine_port_falls_back_when_unset_or_invalid(
    monkeypatch, stored
) -> None:
    _patch_base_url(monkeypatch, "http://127.0.0.1:10101")
    _patch_user_settings(monkeypatch, {"tts_engine_port": stored})
    service = AivisSpeechService()

    assert await service.resolve_engine_port() == 10101


@pytest.mark.asyncio
async def test_resolve_engine_port_falls_back_when_settings_lookup_fails(
    monkeypatch,
) -> None:
    from gateway.services.settings_service import settings_service

    _patch_base_url(monkeypatch, "http://127.0.0.1:10101")
    monkeypatch.setattr(
        settings_service,
        "get_user_settings",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    service = AivisSpeechService()

    assert await service.resolve_engine_port() == 10101


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"name": "AivisSpeech Engine", "brand_name": "AivisSpeech"}, "AivisSpeech"),
        ({"name": "Compatible Engine", "brand_name": "Compatible"}, "Compatible"),
        ({"name": "Some Engine"}, "Some Engine"),
        ({}, None),
        ([], None),
    ],
)
async def test_fetch_engine_brand_reads_the_engine_manifest(payload, expected) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/engine_manifest"
        return httpx.Response(200, json=payload, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        brand = await AivisSpeechService._fetch_engine_brand(
            client, "http://127.0.0.1:10101"
        )

    assert brand == expected


@pytest.mark.asyncio
async def test_fetch_engine_brand_returns_none_when_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        brand = await AivisSpeechService._fetch_engine_brand(
            client, "http://127.0.0.1:10101"
        )

    assert brand is None
