"""services/jev_client.py: Jev (構造化判定モデル) の呼び出しと応答のパース。"""

from __future__ import annotations

import json

import httpx
import pytest

from gateway.services import jev_client as svc
from gateway.services.jev_client import (
    JEV_OPENROUTER_URL,
    JEV_TYPESAFE_URL,
    JevClient,
    JevClientError,
    ask,
    choice,
    noul,
    score,
)
from gateway.services.providers import DecisionTransport
from gateway.settings.config import settings

_REAL_ASYNC_CLIENT = httpx.AsyncClient

QUESTIONS = {
    "is_true": noul("Is it true?", true="yes", false="no"),
    "pick": choice("Which one?", {"a": "first", "b": "second"}),
    "level": score("How much?", ["low", "mid", "high"]),
}

_DEFAULT_RESPONSE = {
    "model": "typesafe/jev-1.13",
    "answers": {
        "is_true": {"type": "noul", "noul": 0.82},
        "pick": {
            "type": "choice",
            "choice": "a",
            "probabilities": {"a": 0.7, "b": 0.3},
            "confidence": 0.85,
        },
        "level": {
            "type": "score",
            "score": 1.5,
            "legend": ["low", "mid", "high"],
            "probabilities": [0.1, 0.6, 0.3],
            "confidence": 0.75,
        },
    },
    "usage": {"input_tokens": 1000, "output_tokens": 0, "cost": 0.000042},
}


def _configure(
    monkeypatch,
    *,
    provider: str = "openrouter",
    openrouter_key: str = "sk-openrouter",
    typesafe_key: str = "ts-key",
    model: str = "",
) -> None:
    monkeypatch.setattr(settings, "jev_provider", provider)
    monkeypatch.setattr(settings, "openrouter_api_key", openrouter_key)
    monkeypatch.setattr(settings, "typesafe_api_key", typesafe_key)
    monkeypatch.setattr(settings, "jev_model", model)
    monkeypatch.setattr(settings, "jev_timeout", 5.0)
    monkeypatch.setattr(settings, "jev_input_price_usd_per_mtok", 0.042)
    monkeypatch.setattr(settings, "jev_min_confidence", 0.5)


def _mock_http(
    monkeypatch,
    *,
    status: int = 200,
    payload: dict | None = None,
    statuses: list[int] | None = None,
) -> list[httpx.Request]:
    requests: list[httpx.Request] = []
    remaining = list(statuses or [])

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        code = remaining.pop(0) if remaining else status
        if code != 200:
            return httpx.Response(code, json={"error": "nope"}, request=request)
        return httpx.Response(
            200,
            json=payload if payload is not None else _DEFAULT_RESPONSE,
            request=request,
        )

    def factory(*args, **kwargs):
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return requests


async def test_openrouter_transport_posts_decisions_endpoint(monkeypatch) -> None:
    _configure(monkeypatch)
    requests = _mock_http(monkeypatch)

    decision = await JevClient().decide(state={"x": 1}, questions=QUESTIONS)

    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == JEV_OPENROUTER_URL
    assert request.headers["Authorization"] == "Bearer sk-openrouter"
    sent = json.loads(request.content)
    # body は {model, state, questions} だけ
    assert set(sent) == {"model", "state", "questions"}
    assert sent["model"] == "typesafe/jev-1.13"
    assert decision.transport is DecisionTransport.OPENROUTER


async def test_typesafe_transport_uses_its_own_url_key_and_model(monkeypatch) -> None:
    _configure(monkeypatch, provider="typesafe")
    payload = dict(_DEFAULT_RESPONSE)
    payload["usage"] = {"input_tokens": 2000, "output_tokens": 0}
    requests = _mock_http(monkeypatch, payload=payload)

    decision = await JevClient().decide(state="hello", questions=QUESTIONS)

    request = requests[0]
    assert str(request.url) == JEV_TYPESAFE_URL
    assert request.headers["Authorization"] == "Bearer ts-key"
    assert "X-Title" not in request.headers
    # 料金が返らないので公表単価から推定する
    assert decision.cost_estimated is True
    assert decision.cost_usd == pytest.approx(2000 * 0.042 / 1_000_000)


async def test_openrouter_cost_comes_from_the_response(monkeypatch) -> None:
    _configure(monkeypatch)
    _mock_http(monkeypatch)

    decision = await JevClient().decide(state={}, questions=QUESTIONS)

    assert decision.cost_estimated is False
    assert decision.cost_usd == pytest.approx(0.000042)
    assert decision.input_tokens == 1000


async def test_answers_are_parsed_by_kind(monkeypatch) -> None:
    _configure(monkeypatch)
    _mock_http(monkeypatch)

    decision = await JevClient().decide(state={}, questions=QUESTIONS)

    truth = decision.answer("is_true")
    assert truth is not None and truth.truth == pytest.approx(0.82)
    assert truth.is_true() is True
    assert truth.is_true(threshold=0.9) is False

    picked = decision.answer("pick")
    assert picked is not None and picked.option == "a"
    assert picked.picked(min_confidence=0.5) == "a"
    # confidence が足りなければ採用しない
    assert picked.picked(min_confidence=0.9) is None

    level = decision.answer("level")
    assert level is not None and level.position == 2
    assert level.legend == "high"
    assert level.probabilities == {"low": 0.1, "mid": 0.6, "high": 0.3}


async def test_field_name_variants_are_tolerated(monkeypatch) -> None:
    _configure(monkeypatch)
    _mock_http(
        monkeypatch,
        payload={
            "answers": {
                # noul の確率が分布としてだけ返る場合
                "is_true": {"probabilities": {"true": 0.4, "false": 0.6}},
                # choice の選択肢名が無く、分布から決める場合
                "pick": {"type": "choice", "probabilities": {"a": 0.2, "b": 0.8}},
                # score が value で返る場合
                "level": {"type": "score", "value": 0.2},
            },
            "usage": {"input_tokens": 10},
        },
    )

    decision = await JevClient().decide(state={}, questions=QUESTIONS)

    assert decision.answer("is_true").truth == pytest.approx(0.4)
    assert decision.answer("pick").option == "b"
    assert decision.answer("level").legend == "low"


async def test_rate_limit_is_retried_once(monkeypatch) -> None:
    _configure(monkeypatch)

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("gateway.services.http_client.asyncio.sleep", _no_sleep)
    requests = _mock_http(monkeypatch, statuses=[429, 200])

    decision = await JevClient().decide(state={}, questions=QUESTIONS)

    assert len(requests) == 2
    assert decision.answer("is_true") is not None


async def test_http_errors_and_bad_payloads_raise_jev_client_error(monkeypatch) -> None:
    _configure(monkeypatch)
    _mock_http(monkeypatch, status=500)
    with pytest.raises(JevClientError):
        await JevClient().decide(state={}, questions=QUESTIONS)

    _mock_http(monkeypatch, payload={"nothing": "here"})
    with pytest.raises(JevClientError):
        await JevClient().decide(state={}, questions=QUESTIONS)


async def test_disabled_provider_never_sends_a_request(monkeypatch) -> None:
    # キーはあるが JEV_PROVIDER=off。キーの存在は利用の根拠にしない
    _configure(monkeypatch, provider="off")
    requests = _mock_http(monkeypatch)

    with pytest.raises(JevClientError):
        await JevClient().decide(state={}, questions=QUESTIONS)
    assert requests == []

    # ask() は例外を投げずに None を返す
    assert await ask({}, QUESTIONS, what="test") is None
    assert requests == []


async def test_ask_swallows_failures_and_returns_none(monkeypatch) -> None:
    _configure(monkeypatch)
    _mock_http(monkeypatch, status=503)

    assert await ask({}, QUESTIONS, what="test") is None


async def test_model_follows_settings_then_transport_default(monkeypatch) -> None:
    _configure(monkeypatch, provider="typesafe")
    assert JevClient().model == "jev-latest"

    _configure(monkeypatch, provider="openrouter")
    assert JevClient().model == "typesafe/jev-1.13"

    _configure(monkeypatch, provider="openrouter", model="typesafe/jev-9.9")
    assert JevClient().model == "typesafe/jev-9.9"


def test_question_builders_shape(monkeypatch) -> None:
    assert svc.noul("q") == {"type": "noul", "instructions": "q"}
    assert svc.noul("q", true="t")["criteria"] == {"true": "t"}
    assert svc.choice("q", {"a": "x"})["criteria"] == {"a": "x"}
    assert svc.score("q", ["a", "b"])["criteria"] == ["a", "b"]
