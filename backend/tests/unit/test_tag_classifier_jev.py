"""services/tag_classifier_jev.py: Jev による変身タグ分類とルールとの併用。"""

from __future__ import annotations

import gateway.services.tag_classifier_jev as svc
from gateway.services.jev_client import JevAnswer, JevDecision
from gateway.services.providers import DecisionTransport
from gateway.services.tag_classifier import TransformationTags, classify_tags
from gateway.settings.config import settings


def _decision(
    *,
    costume: str | None = "maid",
    costume_confidence: float = 0.9,
    exposure_position: int | None = 2,
    exposure_confidence: float = 0.9,
    age: str | None = "adult",
    age_confidence: float = 0.9,
) -> JevDecision:
    answers: dict[str, JevAnswer] = {}
    if costume is not None:
        answers["costume_category"] = JevAnswer(
            id="costume_category",
            kind="choice",
            option=costume,
            confidence=costume_confidence,
        )
    if exposure_position is not None:
        legend = ("low", "medium", "high")[exposure_position]
        answers["exposure_level"] = JevAnswer(
            id="exposure_level",
            kind="score",
            score_value=float(exposure_position),
            position=exposure_position,
            legend=legend,
            confidence=exposure_confidence,
        )
    if age is not None:
        answers["age_impression"] = JevAnswer(
            id="age_impression", kind="choice", option=age, confidence=age_confidence
        )
    return JevDecision(
        answers=answers,
        model="typesafe/jev-1.13",
        transport=DecisionTransport.OPENROUTER,
    )


def _stub_ask(monkeypatch, decision: JevDecision | None) -> list[dict]:
    calls: list[dict] = []

    async def _ask(state, questions, *, what, timeout=None):
        calls.append({"state": state, "what": what})
        return decision

    monkeypatch.setattr(svc, "ask", _ask)
    return calls


def _enable(monkeypatch, *, live: str = "") -> None:
    monkeypatch.setattr(settings, "jev_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-openrouter")
    monkeypatch.setattr(settings, "jev_live_targets", live)
    monkeypatch.setattr(settings, "jev_min_confidence", 0.5)


_RULE = TransformationTags(
    costume_category="other", exposure_level="medium", age_impression="unknown"
)


async def test_state_only_carries_the_instruction(monkeypatch) -> None:
    _enable(monkeypatch)
    calls = _stub_ask(monkeypatch, _decision())

    await svc.classify_tags_with_jev("メイド服に着替える", rule=_RULE)

    assert calls[0]["what"] == "tags"
    assert calls[0]["state"] == {"instruction": "メイド服に着替える"}


async def test_confident_answers_replace_every_axis(monkeypatch) -> None:
    _enable(monkeypatch)
    _stub_ask(monkeypatch, _decision())

    tags = await svc.classify_tags_with_jev("メイド服に着替える", rule=_RULE)

    assert tags == TransformationTags(
        costume_category="maid", exposure_level="high", age_impression="adult"
    )


async def test_low_confidence_axes_keep_the_rule_result(monkeypatch) -> None:
    _enable(monkeypatch)
    _stub_ask(
        monkeypatch,
        _decision(costume_confidence=0.2, exposure_confidence=0.1, age_confidence=0.2),
    )

    tags = await svc.classify_tags_with_jev("メイド服に着替える", rule=_RULE)

    assert tags.costume_category == "other"
    assert tags.exposure_level == "medium"
    # 年齢印象だけは、確信が足りないことを unknown として表せる
    assert tags.age_impression == "unknown"


async def test_unreachable_judge_returns_none(monkeypatch) -> None:
    _enable(monkeypatch)
    _stub_ask(monkeypatch, None)

    assert await svc.classify_tags_with_jev("x", rule=_RULE) is None


async def test_resolve_tags_uses_rules_when_the_judge_is_off(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_provider", "off")
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-openrouter")
    calls = _stub_ask(monkeypatch, _decision())

    tags = await svc.resolve_tags("水着に着替える")

    assert tags == classify_tags("水着に着替える")
    assert calls == []


async def test_resolve_tags_shadow_keeps_the_rule_result(monkeypatch) -> None:
    _enable(monkeypatch, live="")
    calls = _stub_ask(monkeypatch, _decision(costume="cosplay", exposure_position=0))

    tags = await svc.resolve_tags("水着に着替える")

    # 判定は呼ぶが、挙動は変えない
    assert len(calls) == 1
    assert tags == classify_tags("水着に着替える")


async def test_resolve_tags_live_prefers_the_judge(monkeypatch) -> None:
    _enable(monkeypatch, live="tags")
    _stub_ask(monkeypatch, _decision(costume="cosplay", exposure_position=0))

    tags = await svc.resolve_tags("水着に着替える")

    assert tags.costume_category == "cosplay"
    assert tags.exposure_level == "low"
