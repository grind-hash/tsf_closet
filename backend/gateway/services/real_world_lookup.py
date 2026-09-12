"""現実世界の情報(天気・Web 検索)の取得。

キャラチャットの案内役キャラ(セレナ)が、判定 LLM の計画に従って使う。
天気は Open-Meteo(API キー不要。WEATHER_LOCATION の地点)、Web 検索は Tavily
(TAVILY_API_KEY)を使い、未設定なら使えない。取得の失敗は例外で返し、
会話を続けるかどうかは呼び出し側が決める。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ..settings.config import settings
from .http_client import async_client

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TAVILY_URL = "https://api.tavily.com/search"
OPEN_METEO_TIMEOUT = 5.0
TAVILY_TIMEOUT = 15.0
WEATHER_CACHE_TTL_SEC = 1800.0
SEARCH_MAX_RESULTS = 5
# basic は 1 回 1 クレジット(advanced は 2 クレジット)
SEARCH_DEPTH = "basic"
# Tavily の関連度スコア(0-1)がこれ未満の結果は素材にしない。
# 番組表のような「新しいだけで無関係」なページを落とすため
SEARCH_MIN_SCORE = 0.4
TITLE_MAX_CHARS = 80
ANSWER_MAX_CHARS = 400
SNIPPET_MAX_CHARS = 200
FORECAST_CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,"
    "precipitation,weather_code,wind_speed_10m"
)

# WMO weather interpretation codes (Open-Meteo の weather_code)
_WMO_LABELS: dict[int, tuple[str, str]] = {
    0: ("快晴", "Clear sky"),
    1: ("晴れ", "Mainly clear"),
    2: ("薄曇り", "Partly cloudy"),
    3: ("曇り", "Overcast"),
    45: ("霧", "Fog"),
    48: ("霧氷", "Depositing rime fog"),
    51: ("弱い霧雨", "Light drizzle"),
    53: ("霧雨", "Moderate drizzle"),
    55: ("強い霧雨", "Dense drizzle"),
    56: ("弱い着氷性霧雨", "Light freezing drizzle"),
    57: ("強い着氷性霧雨", "Dense freezing drizzle"),
    61: ("弱い雨", "Slight rain"),
    63: ("雨", "Moderate rain"),
    65: ("強い雨", "Heavy rain"),
    66: ("弱い着氷性の雨", "Light freezing rain"),
    67: ("強い着氷性の雨", "Heavy freezing rain"),
    71: ("弱い雪", "Slight snow"),
    73: ("雪", "Moderate snow"),
    75: ("強い雪", "Heavy snow"),
    77: ("霧雪", "Snow grains"),
    80: ("弱いにわか雨", "Slight rain showers"),
    81: ("にわか雨", "Moderate rain showers"),
    82: ("激しいにわか雨", "Violent rain showers"),
    85: ("弱いにわか雪", "Slight snow showers"),
    86: ("強いにわか雪", "Heavy snow showers"),
    95: ("雷雨", "Thunderstorm"),
    96: ("雷雨(弱い雹)", "Thunderstorm with slight hail"),
    99: ("雷雨(強い雹)", "Thunderstorm with heavy hail"),
}


class RealWorldLookupError(RuntimeError):
    """外部 API の呼び出しに失敗した。"""


@dataclass(slots=True)
class WeatherInfo:
    # location はジオコーディング結果の表示名(日本語)、location_raw は設定値そのもの
    location: str
    location_raw: str
    weather_code: int
    label_ja: str
    label_en: str
    temperature_c: float
    apparent_c: float | None = None
    humidity_pct: int | None = None
    precipitation_mm: float | None = None
    wind_kmh: float | None = None

    def label(self, language: str) -> str:
        return self.label_en if language == "en" else self.label_ja

    def display_location(self, language: str) -> str:
        if language == "en":
            return self.location_raw or self.location
        return self.location or self.location_raw


@dataclass(slots=True)
class SearchSource:
    title: str
    # http / https 以外の URL は空文字にする
    url: str
    snippet: str
    # Tavily が返す関連度(0-1)。返らない場合は None
    score: float | None = None


@dataclass(slots=True)
class SearchInfo:
    query: str
    answer: str
    sources: list[SearchSource]
    # 検索は走ったが、関連する出典が得られなかったとき False
    found: bool = True


# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------


def web_search_configured() -> bool:
    return bool(settings.tavily_api_key)


def weather_configured() -> bool:
    return bool(settings.weather_location)


def real_world_configuration() -> dict[str, bool]:
    """設定画面が「ON にしても効かない」ことを示すためのフラグ。キーや地点の値は返さない。"""
    return {
        "web_search_configured": web_search_configured(),
        "weather_configured": weather_configured(),
    }


# ---------------------------------------------------------------------------
# 純関数
# ---------------------------------------------------------------------------


def wmo_label(code: int) -> tuple[str, str]:
    return _WMO_LABELS.get(int(code), ("不明", "Unknown"))


def _single_line(value: Any) -> str:
    # 改行を潰し、検索結果の文面がプロンプト上の見出しや箇条書きに見えないようにする
    return " ".join(str(value or "").split())


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _safe_url(value: Any) -> str:
    url = str(value or "").strip()
    return url if urlparse(url).scheme in ("http", "https") else ""


def format_weather(info: WeatherInfo, language: str) -> str:
    """プロンプト用の 1 行。例: 東京: 晴れ 29.4°C (体感 31.0°C) 湿度60% 降水0.0mm 風12km/h"""
    en = language == "en"
    head = f"{info.label(language)} {info.temperature_c:.1f}°C"
    if info.apparent_c is not None:
        head += (
            f" (feels like {info.apparent_c:.1f}°C)"
            if en
            else f" (体感 {info.apparent_c:.1f}°C)"
        )
    parts = [head]
    if info.humidity_pct is not None:
        parts.append(
            f"humidity {info.humidity_pct}%" if en else f"湿度{info.humidity_pct}%"
        )
    if info.precipitation_mm is not None:
        parts.append(
            f"precipitation {info.precipitation_mm:.1f}mm"
            if en
            else f"降水{info.precipitation_mm:.1f}mm"
        )
    if info.wind_kmh is not None:
        parts.append(
            f"wind {info.wind_kmh:.0f}km/h" if en else f"風{info.wind_kmh:.0f}km/h"
        )
    separator = ", " if en else " "
    return f"{info.display_location(language)}: {separator.join(parts)}"


def format_search(info: SearchInfo, language: str) -> str:
    """プロンプト用の本文(見出しは呼び出し側で付ける)。URL は含めない。"""
    en = language == "en"
    if not info.found:
        # 素材が無いことを伏せると、モデルが知っている名前で穴を埋める
        missing = (
            "The search ran but found nothing that answers this. Do not guess: "
            "say plainly that you do not know."
            if en
            else "検索しましたが、答えになる情報は見つかりませんでした。"
            "推測で答えず、分からないと正直に述べてください。"
        )
        if info.answer:
            label = "Search engine summary: " if en else "検索エンジンの要約: "
            missing = f"{missing}\n{label}{info.answer}"
        return missing
    lines: list[str] = []
    if info.answer:
        lines.append(("Summary: " if en else "要約: ") + info.answer)
    for source in info.sources[:SEARCH_MAX_RESULTS]:
        parts = [part for part in (source.title, source.snippet) if part]
        lines.append("- " + ": ".join(parts))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 外部 I/O
# ---------------------------------------------------------------------------

_geocode_cache: dict[str, tuple[float, float, str]] = {}
_weather_cache: WeatherInfo | None = None
_weather_cached_at: float = 0.0
_weather_lock: asyncio.Lock | None = None


def reset_caches() -> None:
    """テスト用。プロセス内キャッシュを空にする。"""
    global _weather_cache, _weather_cached_at, _weather_lock
    _geocode_cache.clear()
    _weather_cache = None
    _weather_cached_at = 0.0
    _weather_lock = None


def _get_weather_lock() -> asyncio.Lock:
    global _weather_lock
    if _weather_lock is None:
        _weather_lock = asyncio.Lock()
    return _weather_lock


def _cached_weather(location: str) -> WeatherInfo | None:
    if (
        _weather_cache is not None
        and _weather_cache.location_raw == location
        and time.monotonic() - _weather_cached_at < WEATHER_CACHE_TTL_SEC
    ):
        return _weather_cache
    return None


async def geocode(location: str) -> tuple[float, float, str]:
    """都市名を (緯度, 経度, 表示名) に解決する。結果はプロセス内に保持する。"""
    key = location.strip().lower()
    cached = _geocode_cache.get(key)
    if cached is not None:
        return cached
    async with async_client(timeout=OPEN_METEO_TIMEOUT) as client:
        response = await client.get(
            GEOCODE_URL,
            params={"name": location, "count": 1, "language": "ja", "format": "json"},
        )
        response.raise_for_status()
    data = response.json()
    results = data.get("results") if isinstance(data, dict) else None
    if not results or not isinstance(results[0], dict):
        raise RealWorldLookupError(f"location not found: {location}")
    first = results[0]
    resolved = (
        float(first["latitude"]),
        float(first["longitude"]),
        str(first.get("name") or location),
    )
    _geocode_cache[key] = resolved
    return resolved


def _parse_forecast(data: Any, *, location: str, location_raw: str) -> WeatherInfo:
    if not isinstance(data, dict):
        raise RealWorldLookupError("unexpected forecast response")
    current = data.get("current")
    if not isinstance(current, dict):
        raise RealWorldLookupError("forecast response has no current block")
    temperature = _optional_float(current.get("temperature_2m"))
    if temperature is None:
        raise RealWorldLookupError("forecast response has no temperature")
    code_value = current.get("weather_code")
    code = int(code_value) if isinstance(code_value, int | float) else -1
    label_ja, label_en = wmo_label(code)
    humidity = _optional_float(current.get("relative_humidity_2m"))
    return WeatherInfo(
        location=location,
        location_raw=location_raw,
        weather_code=code,
        label_ja=label_ja,
        label_en=label_en,
        temperature_c=temperature,
        apparent_c=_optional_float(current.get("apparent_temperature")),
        humidity_pct=round(humidity) if humidity is not None else None,
        precipitation_mm=_optional_float(current.get("precipitation")),
        wind_kmh=_optional_float(current.get("wind_speed_10m")),
    )


async def fetch_weather() -> WeatherInfo | None:
    """WEATHER_LOCATION の現在の天気。未設定なら None。TTL 内はキャッシュを返す。"""
    global _weather_cache, _weather_cached_at
    location = settings.weather_location.strip()
    if not location:
        return None
    cached = _cached_weather(location)
    if cached is not None:
        return cached
    async with _get_weather_lock():
        cached = _cached_weather(location)
        if cached is not None:
            return cached
        latitude, longitude, name = await geocode(location)
        async with async_client(timeout=OPEN_METEO_TIMEOUT) as client:
            response = await client.get(
                FORECAST_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": FORECAST_CURRENT_FIELDS,
                    "timezone": "auto",
                },
            )
            response.raise_for_status()
        info = _parse_forecast(response.json(), location=name, location_raw=location)
        _weather_cache = info
        _weather_cached_at = time.monotonic()
        return info


async def tavily_search(query: str, *, language: str = "ja") -> SearchInfo:
    """Tavily で検索し、関連度の低い結果を落として素材にする。

    送るのは検索語だけ。日本語の会話では日本の情報を優先させる(country は
    topic が general のときだけ有効な指定)。
    """
    api_key = settings.tavily_api_key
    if not api_key:
        raise RealWorldLookupError("TAVILY_API_KEY is not configured")
    payload: dict[str, Any] = {
        "query": query,
        "max_results": SEARCH_MAX_RESULTS,
        "search_depth": SEARCH_DEPTH,
        "include_answer": True,
        "topic": "general",
    }
    if language != "en":
        payload["country"] = "japan"
    async with async_client(timeout=TAVILY_TIMEOUT) as client:
        response = await client.post(
            TAVILY_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RealWorldLookupError("unexpected search response")
    sources: list[SearchSource] = []
    dropped = 0
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        url = _safe_url(item.get("url"))
        title = _truncate(_single_line(item.get("title")), TITLE_MAX_CHARS)
        content = _single_line(item.get("content"))
        if not title and not content:
            continue
        score = _optional_float(item.get("score"))
        # スコアが返るときだけ足切りする。無関係な新着ページを素材にしない
        if score is not None and score < SEARCH_MIN_SCORE:
            dropped += 1
            continue
        sources.append(
            SearchSource(
                title=title or _truncate(url, TITLE_MAX_CHARS),
                url=url,
                snippet=_truncate(content, SNIPPET_MAX_CHARS),
                score=score,
            )
        )
        if len(sources) >= SEARCH_MAX_RESULTS:
            break
    answer = _truncate(_single_line(data.get("answer")), ANSWER_MAX_CHARS)
    logger.info(
        "Real-world web search: query=%s kept=%d dropped_low_relevance=%d",
        query,
        len(sources),
        dropped,
    )
    return SearchInfo(
        query=query,
        answer=answer,
        sources=sources,
        # 出典が残らなかったときは「検索したが見つからなかった」として扱う
        found=bool(sources),
    )
