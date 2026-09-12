"""現実世界の情報(天気・Web 検索)の取得の単体テスト。"""

from __future__ import annotations

import json

import httpx
import pytest

from gateway.services import real_world_lookup as svc
from gateway.services.real_world_lookup import (
    RealWorldLookupError,
    SearchInfo,
    SearchSource,
    WeatherInfo,
    format_search,
    format_weather,
    wmo_label,
)

_REAL_ASYNC_CLIENT = httpx.AsyncClient

_DEFAULT_TAVILY_RESPONSE = {
    "answer": "要約です",
    "results": [
        {"title": "記事A", "url": "https://example.com/a", "content": "本文A"},
        {"title": "記事B", "url": "https://example.com/b", "content": "本文B"},
    ],
}


@pytest.fixture(autouse=True)
def _reset_caches():
    svc.reset_caches()
    yield
    svc.reset_caches()


def _configure(monkeypatch, *, weather: bool = True, search: bool = True) -> None:
    monkeypatch.setattr(svc.settings, "weather_location", "Tokyo" if weather else "")
    monkeypatch.setattr(svc.settings, "tavily_api_key", "tvly-test" if search else "")


def _mock_http(
    monkeypatch,
    *,
    forecast_status: int = 200,
    tavily_json: dict | None = None,
) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        host = request.url.host
        if host == "geocoding-api.open-meteo.com":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"name": "東京", "latitude": 35.68, "longitude": 139.69}
                    ]
                },
                request=request,
            )
        if host == "api.open-meteo.com":
            return httpx.Response(
                forecast_status,
                json={
                    "timezone": "Asia/Tokyo",
                    "current": {
                        "temperature_2m": 29.4,
                        "relative_humidity_2m": 60,
                        "apparent_temperature": 31.0,
                        "precipitation": 0.0,
                        "weather_code": 1,
                        "wind_speed_10m": 12.3,
                    },
                },
                request=request,
            )
        if host == "api.tavily.com":
            return httpx.Response(
                200,
                json=tavily_json
                if tavily_json is not None
                else _DEFAULT_TAVILY_RESPONSE,
                request=request,
            )
        return httpx.Response(404, request=request)

    def factory(*args, **kwargs):
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return requests


def _weather(**overrides) -> WeatherInfo:
    values = {
        "location": "東京",
        "location_raw": "Tokyo",
        "weather_code": 1,
        "label_ja": "晴れ",
        "label_en": "Mainly clear",
        "temperature_c": 29.4,
        "apparent_c": 31.0,
        "humidity_pct": 60,
        "precipitation_mm": 0.0,
        "wind_kmh": 12.3,
    }
    values.update(overrides)
    return WeatherInfo(**values)


# ---------------------------------------------------------------------------
# 純関数・設定
# ---------------------------------------------------------------------------


def test_wmo_label() -> None:
    assert wmo_label(0) == ("快晴", "Clear sky")
    assert "雨" in wmo_label(61)[0]
    assert wmo_label(999) == ("不明", "Unknown")


def test_configuration_reports_presence_only(monkeypatch) -> None:
    _configure(monkeypatch)
    assert svc.real_world_configuration() == {
        "web_search_configured": True,
        "weather_configured": True,
    }
    _configure(monkeypatch, weather=False, search=False)
    assert svc.real_world_configuration() == {
        "web_search_configured": False,
        "weather_configured": False,
    }


def test_format_weather_ja_and_en() -> None:
    info = _weather()
    assert (
        format_weather(info, "ja")
        == "東京: 晴れ 29.4°C (体感 31.0°C) 湿度60% 降水0.0mm 風12km/h"
    )
    # 英語は設定値そのままの地名を使う
    assert format_weather(info, "en") == (
        "Tokyo: Mainly clear 29.4°C (feels like 31.0°C), humidity 60%, "
        "precipitation 0.0mm, wind 12km/h"
    )
    minimal = _weather(
        apparent_c=None, humidity_pct=None, precipitation_mm=None, wind_kmh=None
    )
    assert format_weather(minimal, "ja") == "東京: 晴れ 29.4°C"


def test_format_search_has_no_urls_and_admits_not_found() -> None:
    found = SearchInfo(
        query="q",
        answer="要約です",
        sources=[
            SearchSource(title="記事A", url="https://example.com/a", snippet="本文A"),
            SearchSource(title="", url="", snippet="本文だけ"),
        ],
    )
    text = format_search(found, "ja")
    assert text == "要約: 要約です\n- 記事A: 本文A\n- 本文だけ"
    assert "https://" not in text

    missing = SearchInfo(
        query="q", answer="The ranking is not specified.", sources=[], found=False
    )
    missing_text = format_search(missing, "ja")
    assert "答えになる情報は見つかりませんでした" in missing_text
    assert "推測で答えず、分からないと正直に述べてください" in missing_text
    # 検索エンジン自身の返答も伝える
    assert "検索エンジンの要約: The ranking is not specified." in missing_text
    assert "Do not guess" in format_search(
        SearchInfo(query="q", answer="", sources=[], found=False), "en"
    )


# ---------------------------------------------------------------------------
# 天気(Open-Meteo)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_weather_returns_none_without_location(monkeypatch) -> None:
    _configure(monkeypatch, weather=False)
    requests = _mock_http(monkeypatch)
    assert await svc.fetch_weather() is None
    assert requests == []


@pytest.mark.asyncio
async def test_fetch_weather_parses_and_caches(monkeypatch) -> None:
    _configure(monkeypatch)
    requests = _mock_http(monkeypatch)

    info = await svc.fetch_weather()
    assert info is not None
    assert info.location == "東京"
    assert info.location_raw == "Tokyo"
    assert info.label_ja == "晴れ"
    assert info.temperature_c == pytest.approx(29.4)
    assert info.humidity_pct == 60
    assert [request.url.host for request in requests] == [
        "geocoding-api.open-meteo.com",
        "api.open-meteo.com",
    ]

    # TTL 内の 2 回目は geocode も forecast も呼ばない
    again = await svc.fetch_weather()
    assert again is info
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_fetch_weather_refetches_when_location_changes(monkeypatch) -> None:
    _configure(monkeypatch)
    requests = _mock_http(monkeypatch)
    await svc.fetch_weather()
    monkeypatch.setattr(svc.settings, "weather_location", "Osaka")
    info = await svc.fetch_weather()
    assert info is not None
    assert info.location_raw == "Osaka"
    assert len(requests) == 4


@pytest.mark.asyncio
async def test_fetch_weather_raises_on_http_error(monkeypatch) -> None:
    _configure(monkeypatch)
    _mock_http(monkeypatch, forecast_status=503)
    with pytest.raises(httpx.HTTPStatusError):
        await svc.fetch_weather()


# ---------------------------------------------------------------------------
# Web 検索(Tavily)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tavily_search_sends_basic_depth_and_auth(monkeypatch) -> None:
    _configure(monkeypatch)
    requests = _mock_http(monkeypatch)

    info = await svc.tavily_search("秋 ファッション 2026", language="ja")

    assert info.found is True
    assert info.answer == "要約です"
    assert [source.title for source in info.sources] == ["記事A", "記事B"]
    assert info.sources[0].url == "https://example.com/a"
    assert len(requests) == 1
    request = requests[0]
    assert request.headers["Authorization"] == "Bearer tvly-test"
    body = json.loads(request.content)
    assert body["query"] == "秋 ファッション 2026"
    # basic は 1 回 1 クレジット
    assert body["search_depth"] == "basic"
    assert body["max_results"] == 5
    assert body["topic"] == "general"
    assert body["include_answer"] is True
    # 日本語の会話では日本の情報を優先する。公開日の絞り込みは使わない
    assert body["country"] == "japan"
    assert "time_range" not in body


@pytest.mark.asyncio
async def test_tavily_search_english_omits_country(monkeypatch) -> None:
    _configure(monkeypatch)
    requests = _mock_http(monkeypatch)
    await svc.tavily_search("autumn fashion 2026", language="en")
    assert "country" not in json.loads(requests[0].content)


@pytest.mark.asyncio
async def test_tavily_search_requires_api_key(monkeypatch) -> None:
    _configure(monkeypatch, search=False)
    requests = _mock_http(monkeypatch)
    with pytest.raises(RealWorldLookupError):
        await svc.tavily_search("q")
    assert requests == []


@pytest.mark.asyncio
async def test_tavily_search_drops_low_relevance_results(monkeypatch) -> None:
    """番組表のような「新しいだけで無関係」な結果をスコアで落とす。"""
    _configure(monkeypatch)
    _mock_http(
        monkeypatch,
        tavily_json={
            "answer": "要約",
            "results": [
                {
                    "title": "関連あり",
                    "url": "https://ok",
                    "content": "本文",
                    "score": 0.82,
                },
                {
                    "title": "番組表",
                    "url": "https://ng",
                    "content": "本文",
                    "score": 0.11,
                },
                {"title": "スコア無し", "url": "https://na", "content": "本文"},
            ],
        },
    )
    info = await svc.tavily_search("q")
    assert info.found is True
    # 低スコアは落ち、スコアが返らないものは残す
    assert [source.title for source in info.sources] == ["関連あり", "スコア無し"]
    assert info.sources[0].score == pytest.approx(0.82)


@pytest.mark.asyncio
async def test_tavily_search_reports_not_found_when_all_dropped(monkeypatch) -> None:
    _configure(monkeypatch)
    _mock_http(
        monkeypatch,
        tavily_json={
            "answer": "The ranking is not specified in the data.",
            "results": [
                {
                    "title": "無関係",
                    "url": "https://ng",
                    "content": "本文",
                    "score": 0.05,
                }
            ],
        },
    )
    info = await svc.tavily_search("2026 夏アニメ 人気キャラ")
    assert info.found is False
    assert info.sources == []


@pytest.mark.asyncio
async def test_tavily_search_caps_and_flattens_text(monkeypatch) -> None:
    """外部の文面は 1 行に潰して長さを切る(プロンプトの見出しや箇条書きに見せない)。"""
    _configure(monkeypatch)
    _mock_http(
        monkeypatch,
        tavily_json={
            "answer": "あ" * 1000,
            "results": [
                {
                    "title": "タ" * 200,
                    "url": "https://example.com/long",
                    "content": "一行目\n\n## 見出しのふり\n" + "い" * 500,
                }
            ],
        },
    )
    info = await svc.tavily_search("q")
    source = info.sources[0]
    assert len(source.title) <= svc.TITLE_MAX_CHARS
    assert source.title.endswith("…")
    assert len(source.snippet) <= svc.SNIPPET_MAX_CHARS
    assert "\n" not in source.snippet
    assert source.snippet.startswith("一行目 ## 見出しのふり")
    assert len(info.answer) <= svc.ANSWER_MAX_CHARS


@pytest.mark.asyncio
async def test_tavily_search_discards_non_http_urls(monkeypatch) -> None:
    _configure(monkeypatch)
    _mock_http(
        monkeypatch,
        tavily_json={
            "answer": "",
            "results": [
                {"title": "危険", "url": "javascript:alert(1)", "content": "本文"},
                {"title": "", "url": "https://example.com/no-title", "content": "本文"},
                # 題名も本文も無い結果は素材にならないので捨てる
                {"title": "", "url": "https://example.com/empty", "content": ""},
            ],
        },
    )
    info = await svc.tavily_search("q")
    assert [(source.title, source.url) for source in info.sources] == [
        ("危険", ""),
        # 題名が無ければ URL を見出しにする
        ("https://example.com/no-title", "https://example.com/no-title"),
    ]
