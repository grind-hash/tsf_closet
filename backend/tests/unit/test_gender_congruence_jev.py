"""services/gender_congruence_jev.py: Jev の回答を性別適合の結果へ写す規則。"""

from __future__ import annotations

from gateway.services.gender_congruence import (
    GenderCongruenceResult,
    evaluate_gender_congruence_rule,
)
from gateway.services.gender_congruence_jev import (
    STATE_TIMELINE_CLIP,
    STATE_TIMELINE_LIMIT,
    build_congruence_state,
    map_decision_to_result,
)
from gateway.services.jev_client import JevAnswer, JevDecision
from gateway.services.providers import DecisionTransport
from gateway.settings.config import settings


def _decision(
    *,
    outfit: float | None = 0.9,
    discomfort: float | None = 0.1,
    body: str | None = "original",
    body_confidence: float = 0.9,
    social: str | None = "original",
    social_confidence: float = 0.9,
    intensity: str | None = "none",
) -> JevDecision:
    answers: dict[str, JevAnswer] = {}
    if outfit is not None:
        answers["outfit_matches_original_sex"] = JevAnswer(
            id="outfit_matches_original_sex", kind="noul", truth=outfit
        )
    if discomfort is not None:
        answers["feels_gender_discomfort"] = JevAnswer(
            id="feels_gender_discomfort", kind="noul", truth=discomfort
        )
    if body is not None:
        answers["body_state"] = JevAnswer(
            id="body_state", kind="choice", option=body, confidence=body_confidence
        )
    if social is not None:
        answers["social_recognition"] = JevAnswer(
            id="social_recognition",
            kind="choice",
            option=social,
            confidence=social_confidence,
        )
    if intensity is not None:
        answers["discomfort_intensity"] = JevAnswer(
            id="discomfort_intensity",
            kind="score",
            score_value=0.0,
            position=0,
            legend=intensity,
            confidence=0.9,
        )
    return JevDecision(
        answers=answers,
        model="typesafe/jev-1.13",
        transport=DecisionTransport.OPENROUTER,
    )


_RULE = evaluate_gender_congruence_rule(
    instruction="スカートをはく", original_gender="man"
)


def test_state_uses_english_keys_and_trims_history() -> None:
    timeline = [("dress_up", "あ" * 300)] * 20
    state = build_congruence_state(
        instruction="レディーススーツに着替える",
        original_gender="man",
        appearance_desc="x" * 1000,
        session_timeline=timeline,
        attributes=[f"attr{i}" for i in range(40)],
        instruction_type="dress_up",
    )

    assert state["original_sex"] == "male"
    assert state["current_instruction"] == "レディーススーツに着替える"
    assert len(state["current_appearance"]) == 600
    assert len(state["session_attributes"]) == 20
    assert len(state["recent_events"]) == STATE_TIMELINE_LIMIT
    assert len(state["recent_events"][0]["text"]) == STATE_TIMELINE_CLIP


def test_original_sex_follows_gender() -> None:
    state = build_congruence_state(instruction="x", original_gender="woman")
    assert state["original_sex"] == "female"


def test_high_probability_is_congruent_low_is_incongruent() -> None:
    high = map_decision_to_result(_decision(outfit=0.95), rule_result=_RULE)
    assert high is not None
    assert high.fit == "congruent"
    assert high.should_feel_gender_discomfort is False
    assert high.source == "jev"

    low = map_decision_to_result(
        _decision(outfit=0.05, discomfort=0.95), rule_result=_RULE
    )
    assert low is not None
    assert low.fit == "incongruent"
    assert low.should_feel_gender_discomfort is True


def test_middle_band_is_ambiguous_and_keeps_the_rule_verdict() -> None:
    rule = GenderCongruenceResult(fit="ambiguous", should_feel_gender_discomfort=True)
    result = map_decision_to_result(
        _decision(outfit=0.5, discomfort=0.01), rule_result=rule
    )

    assert result is not None
    assert result.fit == "ambiguous"
    # 判断がつかないときは安全側のルールに従う
    assert result.should_feel_gender_discomfort is True


def test_thresholds_follow_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_high", 0.9)
    monkeypatch.setattr(settings, "jev_low", 0.1)

    assert map_decision_to_result(_decision(outfit=0.8), rule_result=_RULE).fit == (
        "ambiguous"
    )
    assert map_decision_to_result(_decision(outfit=0.95), rule_result=_RULE).fit == (
        "congruent"
    )


def test_low_confidence_choices_become_unknown(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_min_confidence", 0.5)
    result = map_decision_to_result(
        _decision(
            body="altered",
            body_confidence=0.2,
            social="opposite",
            social_confidence=0.95,
        ),
        rule_result=_RULE,
    )

    assert result is not None
    assert result.body_state == "unknown"
    assert result.social_recognition == "opposite"


def test_missing_outfit_answer_returns_none() -> None:
    assert map_decision_to_result(_decision(outfit=None), rule_result=_RULE) is None


def test_reason_is_machine_readable_and_bounded() -> None:
    result = map_decision_to_result(_decision(), rule_result=_RULE)
    assert result is not None
    assert result.reason.startswith("jev: outfit=0.90")
    assert "intensity=none" in result.reason
    assert len(result.reason) <= 200
