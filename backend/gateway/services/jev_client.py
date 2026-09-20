"""TypeSafe AI の構造化判定モデル (Jev) のクライアント。

Jev はテキストを生成せず、評価対象 (state) と型付き質問 (questions) を送ると
型付き回答を返す。OpenAI 互換の chat/completions では呼べないため、生成用の
LLMService / Provider とは別系統に置く。経路は 2 つあり、body はどちらも同じ
``{model, state, questions}``。違うのは URL・キー・既定モデルと、応答に料金が
含まれるかだけ。

- openrouter: POST /api/alpha/decisions。usage.cost (USD) が返る。alpha のため変更されうる
- typesafe:   POST /v1/systemone。料金は返らないため入力トークンから推定する

質問は 3 種類。
- noul:   「これは真か」。0..1 の確率を返す
- choice: 選択肢から 1 つ。確率分布と confidence を返す
- score:  順序付きルーブリック上の位置。確率分布と confidence を返す

同じ state を共有する質問は 1 回の呼び出しにまとめる。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from ..settings.config import settings
from .cost_tracker import record_cost
from .http_client import async_client, retry_once_on_rate_limit
from .providers import DecisionTransport, jev_judge_enabled, resolve_decision_transport

logger = logging.getLogger(__name__)

JEV_OPENROUTER_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"

_DEFAULT_MODELS: dict[DecisionTransport, str] = {
    DecisionTransport.OPENROUTER: "typesafe/jev-1.13",
    DecisionTransport.TYPESAFE: "jev-latest",
}

QuestionKind = Literal["noul", "choice", "score"]

# 応答のフィールド名は経路とバージョンで揺れうるため、候補を順に探す
_TRUTH_KEYS = ("noul", "truth", "value", "probability", "p")
_OPTION_KEYS = ("choice", "option", "value", "label")
_SCORE_KEYS = ("score", "value", "position", "index")

# 実レスポンスの形を 1 度だけ DEBUG に残すためのフラグ
_raw_logged = False


class JevClientError(RuntimeError):
    """Jev 呼び出しに失敗した。呼び出し側は必ず従来経路へ倒すこと。"""


def noul(
    instructions: str, *, true: str | None = None, false: str | None = None
) -> dict[str, Any]:
    """真偽を確率で問う質問。criteria は true / false の境目を説明する。"""
    question: dict[str, Any] = {"type": "noul", "instructions": instructions}
    criteria: dict[str, str] = {}
    if true is not None:
        criteria["true"] = true
    if false is not None:
        criteria["false"] = false
    if criteria:
        question["criteria"] = criteria
    return question


def choice(instructions: str, criteria: Mapping[str, Any]) -> dict[str, Any]:
    """選択肢から 1 つ選ばせる質問。criteria は選択肢名 -> 説明の写像。"""
    return {"type": "choice", "instructions": instructions, "criteria": dict(criteria)}


def score(instructions: str, criteria: Sequence[Any]) -> dict[str, Any]:
    """順序付きルーブリック上の位置を問う質問。criteria は低い順の配列。"""
    return {"type": "score", "instructions": instructions, "criteria": list(criteria)}


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _first_float(raw: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        if key in raw:
            value = _as_float(raw[key])
            if value is not None:
                return value
    return None


def _first_str(raw: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _probabilities(raw: Any, legend: Sequence[str]) -> dict[str, float]:
    """確率分布を名前付きの写像にそろえる。score は配列で返るため legend で名付ける。"""
    if isinstance(raw, Mapping):
        out: dict[str, float] = {}
        for key, value in raw.items():
            number = _as_float(value)
            if number is not None:
                out[str(key)] = number
        return out
    if isinstance(raw, Sequence) and not isinstance(raw, str | bytes):
        out = {}
        for index, value in enumerate(raw):
            number = _as_float(value)
            if number is None:
                continue
            name = legend[index] if index < len(legend) else str(index)
            out[str(name)] = number
        return out
    return {}


@dataclass(frozen=True)
class JevAnswer:
    """1 つの質問への回答。型ごとに埋まるフィールドが違う。"""

    id: str
    kind: QuestionKind
    truth: float | None = None  # noul: 真である確率 (0..1)
    option: str | None = None  # choice: 選ばれた選択肢
    score_value: float | None = None  # score: ルーブリック上の位置 (小数)
    position: int | None = None  # score: 位置を四捨五入した添字
    legend: str | None = None  # score: position に対応するラベル
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float | None = None  # choice / score のみ

    def is_true(self, threshold: float = 0.5) -> bool:
        """noul の確率がしきい値以上か。確率が無ければ False。"""
        return self.truth is not None and self.truth >= threshold

    def picked(self, min_confidence: float) -> str | None:
        """confidence が足りていれば選択結果を返す。足りなければ None。"""
        value = self.option if self.kind == "choice" else self.legend
        if value is None:
            return None
        if self.confidence is not None and self.confidence < min_confidence:
            return None
        return value


@dataclass(frozen=True)
class JevDecision:
    """1 回の呼び出しの結果。"""

    answers: dict[str, JevAnswer]
    model: str
    transport: DecisionTransport
    input_tokens: int = 0
    cost_usd: float | None = None
    cost_estimated: bool = False
    latency_ms: float = 0.0

    def answer(self, question_id: str) -> JevAnswer | None:
        return self.answers.get(question_id)


def _question_kind(question: Any) -> QuestionKind:
    if isinstance(question, Mapping):
        kind = str(question.get("type") or "").strip().lower()
        if kind in ("noul", "choice", "score"):
            return kind  # type: ignore[return-value]
    return "noul"


def _question_legend(question: Any) -> list[str]:
    """score 質問の criteria からラベル列を作る。要素が辞書なら summary を使う。"""
    if not isinstance(question, Mapping):
        return []
    criteria = question.get("criteria")
    if not isinstance(criteria, Sequence) or isinstance(criteria, str | bytes):
        return []
    labels: list[str] = []
    for index, item in enumerate(criteria):
        if isinstance(item, Mapping):
            labels.append(str(item.get("summary") or index))
        else:
            labels.append(str(item))
    return labels


def _parse_answer(question_id: str, question: Any, raw: Any) -> JevAnswer | None:
    if not isinstance(raw, Mapping):
        return None

    kind = str(raw.get("type") or "").strip().lower()
    if kind not in ("noul", "choice", "score"):
        kind = _question_kind(question)

    legend_all = _question_legend(question)
    legend_from_response = raw.get("legend")
    if isinstance(legend_from_response, Sequence) and not isinstance(
        legend_from_response, str | bytes
    ):
        legend_all = [str(item) for item in legend_from_response]

    probabilities = _probabilities(raw.get("probabilities"), legend_all)
    confidence = _first_float(raw, ("confidence",))

    if kind == "noul":
        truth = _first_float(raw, _TRUTH_KEYS)
        if truth is None:
            truth = probabilities.get("true")
        if truth is None:
            return None
        return JevAnswer(
            id=question_id,
            kind="noul",
            truth=truth,
            probabilities=probabilities,
            confidence=confidence,
        )

    if kind == "choice":
        option = _first_str(raw, _OPTION_KEYS)
        if option is None and probabilities:
            option = max(probabilities.items(), key=lambda item: item[1])[0]
        if option is None:
            return None
        return JevAnswer(
            id=question_id,
            kind="choice",
            option=option,
            probabilities=probabilities,
            confidence=confidence,
        )

    value = _first_float(raw, _SCORE_KEYS)
    if value is None:
        return None
    position = int(round(value))
    if legend_all:
        position = max(0, min(position, len(legend_all) - 1))
    label = legend_all[position] if 0 <= position < len(legend_all) else None
    return JevAnswer(
        id=question_id,
        kind="score",
        score_value=value,
        position=position,
        legend=label,
        probabilities=probabilities,
        confidence=confidence,
    )


class JevClient:
    """Jev への HTTP 呼び出し。設定は呼び出し時に読む (テストで差し替えられるように)。"""

    def __init__(
        self,
        *,
        transport: DecisionTransport | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._transport = transport
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    @property
    def transport(self) -> DecisionTransport:
        return self._transport or resolve_decision_transport()

    @property
    def model(self) -> str:
        if self._model:
            return self._model
        if settings.jev_model:
            return settings.jev_model
        return _DEFAULT_MODELS.get(self.transport, "jev-latest")

    @property
    def timeout(self) -> float:
        return self._timeout or settings.jev_timeout

    def _api_key_for(self, transport: DecisionTransport) -> str:
        if self._api_key:
            return self._api_key
        if transport is DecisionTransport.TYPESAFE:
            return settings.typesafe_api_key
        return settings.openrouter_api_key

    def _url_for(self, transport: DecisionTransport) -> str:
        if transport is DecisionTransport.TYPESAFE:
            return JEV_TYPESAFE_URL
        return JEV_OPENROUTER_URL

    def _headers_for(self, transport: DecisionTransport) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key_for(transport)}",
            "Content-Type": "application/json",
        }
        if transport is DecisionTransport.OPENROUTER:
            headers["HTTP-Referer"] = "http://localhost:8000"
            headers["X-Title"] = "TSF Game"
        return headers

    async def decide(
        self,
        *,
        state: Mapping[str, Any] | Sequence[str] | str,
        questions: Mapping[str, Mapping[str, Any]],
        timeout: float | None = None,
    ) -> JevDecision:
        """state を共有する複数の質問を 1 回で評価する。失敗は JevClientError。"""
        transport = self.transport
        if transport is DecisionTransport.OFF:
            raise JevClientError("Jev is disabled (JEV_PROVIDER=off)")
        if not self._api_key_for(transport):
            raise JevClientError(f"API key is not configured for transport {transport}")
        if not questions:
            raise JevClientError("no questions given")

        model = self.model
        payload = {"model": model, "state": state, "questions": dict(questions)}
        url = self._url_for(transport)
        headers = self._headers_for(transport)
        started = time.monotonic()

        async def _post() -> dict[str, Any]:
            async with async_client(timeout=timeout or self.timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()

        try:
            data = await retry_once_on_rate_limit(
                _post, wait_seconds=2.0, what="jev decision"
            )
        except Exception as exc:
            raise JevClientError(
                f"Jev request failed ({transport}): {type(exc).__name__}: {exc}"
            ) from exc

        latency_ms = (time.monotonic() - started) * 1000
        return self._build_decision(
            data, questions, transport=transport, model=model, latency_ms=latency_ms
        )

    def _build_decision(
        self,
        data: Any,
        questions: Mapping[str, Mapping[str, Any]],
        *,
        transport: DecisionTransport,
        model: str,
        latency_ms: float,
    ) -> JevDecision:
        global _raw_logged
        if not _raw_logged:
            # 応答の実形 (フィールド名) を 1 度だけ確認できるようにする
            logger.debug("jev raw response: %s", data)
            _raw_logged = True

        if not isinstance(data, Mapping):
            raise JevClientError(f"unexpected response type: {type(data).__name__}")

        raw_answers = data.get("answers")
        if not isinstance(raw_answers, Mapping):
            raise JevClientError("response has no answers object")

        answers: dict[str, JevAnswer] = {}
        for question_id, question in questions.items():
            parsed = _parse_answer(question_id, question, raw_answers.get(question_id))
            if parsed is not None:
                answers[question_id] = parsed

        usage = data.get("usage") if isinstance(data.get("usage"), Mapping) else {}
        input_tokens = int(
            _as_float(usage.get("input_tokens"))
            or _as_float(usage.get("prompt_tokens"))
            or 0
        )
        cost = _as_float(usage.get("cost"))
        estimated = False
        if cost is None:
            # TypeSafe 直接 API は料金を返さないため、公表単価から推定する
            cost = input_tokens * settings.jev_input_price_usd_per_mtok / 1_000_000
            estimated = True
        record_cost(cost)

        return JevDecision(
            answers=answers,
            model=str(data.get("model") or model),
            transport=transport,
            input_tokens=input_tokens,
            cost_usd=cost,
            cost_estimated=estimated,
            latency_ms=latency_ms,
        )


jev_client = JevClient()


async def ask(
    state: Mapping[str, Any] | Sequence[str] | str,
    questions: Mapping[str, Mapping[str, Any]],
    *,
    what: str,
    timeout: float | None = None,
) -> JevDecision | None:
    """Jev へ 1 回問い合わせる。無効・失敗のときは None を返し、例外は送出しない。

    what はログ用の識別子 ("congruence" など)。
    """
    if not jev_judge_enabled():
        return None
    try:
        decision = await jev_client.decide(
            state=state, questions=questions, timeout=timeout
        )
    except JevClientError as exc:
        logger.warning("Jev decision failed (%s): %s", what, exc)
        return None
    except Exception as exc:
        logger.warning(
            "Jev decision failed (%s): %s: %s", what, type(exc).__name__, exc
        )
        return None

    logger.debug(
        "jev decision what=%s model=%s latency_ms=%.0f cost_usd=%s estimated=%s",
        what,
        decision.model,
        decision.latency_ms,
        decision.cost_usd,
        decision.cost_estimated,
    )
    return decision


def log_shadow(target: str, fields: Mapping[str, Any]) -> None:
    """シャドーモードの比較を 1 行で残す。接頭辞 jev_shadow で grep できるようにする。"""
    parts = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("jev_shadow feature=%s %s", target, parts)


__all__ = [
    "JEV_OPENROUTER_URL",
    "JEV_TYPESAFE_URL",
    "JevAnswer",
    "JevClient",
    "JevClientError",
    "JevDecision",
    "ask",
    "choice",
    "jev_client",
    "log_shadow",
    "noul",
    "score",
]
