"""services/character_chat_jev.py: 調べ物の必要性ゲートと規約スクリーニング。"""

from __future__ import annotations

from gateway.services.character_chat_jev import (
    POLICY_ACTION_THRESHOLD,
    ChatIntentGate,
    apply_intent_gate,
    build_intent_state,
    shadow_fields,
)
from gateway.services.character_chat_models import CharacterChatPlan
from gateway.settings.config import settings

_ALLOWED = {"allowed_kinds": ["web_search", "weather", "recent_sessions"]}


def _plan(*lookups: dict) -> CharacterChatPlan:
    return CharacterChatPlan.model_validate(
        {"lookups": list(lookups)}, context=_ALLOWED
    )


def _kinds(plan: CharacterChatPlan) -> list[str]:
    return [lookup.kind for lookup in plan.lookups]


def test_state_keeps_the_latest_message_and_optional_today() -> None:
    state = build_intent_state(
        character_kind="base",
        character_name="サクラ",
        recent_messages=[{"role": "user", "content": "こんにちは"}],
        latest_message="今日の天気は？",
        available_real_world_lookups=["weather"],
    )
    assert "today" not in state
    assert state["latest_message"] == "今日の天気は？"

    dated = build_intent_state(
        character_kind="base",
        character_name="サクラ",
        recent_messages=[],
        latest_message="流行は？",
        available_real_world_lookups=["web_search"],
        today="2026-09-19",
    )
    assert dated["today"] == "2026-09-19"


def test_gate_drops_lookups_the_judge_calls_unnecessary(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_low", 0.3)
    plan = _plan(
        {"kind": "web_search", "query": "gal fashion 2026"},
        {"kind": "weather"},
        {"kind": "recent_sessions"},
    )
    gate = ChatIntentGate(wants_web_search=0.05, wants_weather=0.9)

    gated = apply_intent_gate(plan, gate, gate_lookups=True, gate_policy=True)

    # 過去プレイの調べ物はゲートの対象外
    assert _kinds(gated) == ["weather", "recent_sessions"]


def test_gate_does_not_add_lookups_the_planner_did_not_ask_for(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_low", 0.3)
    plan = _plan({"kind": "recent_sessions"})
    gate = ChatIntentGate(wants_web_search=0.99, wants_weather=0.99)

    gated = apply_intent_gate(plan, gate, gate_lookups=True, gate_policy=True)

    # 検索キーワードは Jev には作れないので、増やすことはしない
    assert _kinds(gated) == ["recent_sessions"]


def test_policy_hit_marks_the_search_refused() -> None:
    plan = _plan({"kind": "web_search", "query": "something"})
    gate = ChatIntentGate(
        wants_web_search=0.9,
        policy={"adult_search_risk": POLICY_ACTION_THRESHOLD + 0.05},
    )

    gated = apply_intent_gate(plan, gate, gate_lookups=True, gate_policy=True)

    assert gated.lookups[0].refused is True


def test_policy_below_the_action_threshold_changes_nothing() -> None:
    plan = _plan({"kind": "web_search", "query": "something"})
    gate = ChatIntentGate(wants_web_search=0.9, policy={"adult_search_risk": 0.4})

    gated = apply_intent_gate(plan, gate, gate_lookups=True, gate_policy=True)

    assert gated.lookups[0].refused is False


def test_shadow_mode_changes_nothing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_low", 0.3)
    plan = _plan({"kind": "web_search", "query": "something"}, {"kind": "weather"})
    gate = ChatIntentGate(
        wants_web_search=0.01,
        wants_weather=0.01,
        policy={"adult_search_risk": 0.99},
    )

    gated = apply_intent_gate(plan, gate, gate_lookups=False, gate_policy=False)

    assert gated is plan
    assert gated.lookups[0].refused is False


def test_missing_gate_leaves_the_plan_untouched() -> None:
    plan = _plan({"kind": "web_search", "query": "something"})
    assert apply_intent_gate(plan, None, gate_lookups=True, gate_policy=True) is plan


def test_gate_never_clears_a_refusal_the_planner_already_set() -> None:
    plan = _plan({"kind": "web_search", "query": "something", "refused": True})
    gate = ChatIntentGate(wants_web_search=0.0, policy={"adult_search_risk": 0.0})

    gated = apply_intent_gate(plan, gate, gate_lookups=True, gate_policy=True)

    # 既存の判定を覆さない。落とすこともしない
    assert _kinds(gated) == ["web_search"]
    assert gated.lookups[0].refused is True


def test_shadow_fields_report_agreement(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jev_low", 0.3)
    plan = _plan({"kind": "web_search", "query": "something"})
    gate = ChatIntentGate(wants_web_search=0.9, wants_weather=0.1)

    fields = shadow_fields(plan, gate)

    assert fields["planner_web"] is True
    assert fields["agree_web"] is True
    assert fields["agree_weather"] is True
    assert shadow_fields(plan, None) == {"jev": "none"}
