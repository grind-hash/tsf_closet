"""キャラチャットの調べ物判定を Jev (構造化判定モデル) で補強する。

判定 LLM (CharacterChatService._plan) は検索キーワードや外見変更の依頼文という
自由文を作るため、テキストを生成しない Jev では置き換えられない。そこで判定 LLM は
そのまま残し、Jev は次の 2 つだけを受け持つ。

1. 必要性のゲート: 現実世界の調べ物 (Web 検索・天気) が本当に要るかを確かめ、
   要らないと判断したものを計画から落とす (Tavily のクレジット節約)
2. 規約スクリーニング: 検索サービスの利用規約に触れる依頼を見つけ、refused を立てる

どちらも一方向にしか効かない。Jev が「安全」「不要」と言っても、既存の判定 LLM や
正規表現が出した結論を覆すことはない。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..settings.config import settings
from .character_chat_models import CharacterChatPlan
from .jev_client import JevDecision, ask, noul

logger = logging.getLogger(__name__)

# 公式の guardrails パターンに倣ったしきい値。action 以上で対処、review 以上はログだけ
POLICY_ACTION_THRESHOLD = 0.70
POLICY_REVIEW_THRESHOLD = 0.35

_POLICY_QUESTION_IDS = (
    "adult_search_risk",
    "illegal_lookup",
    "minor_sexual",
    "private_info",
)

CHAT_INTENT_QUESTIONS: dict[str, dict[str, Any]] = {
    "wants_web_search": noul(
        "To answer state.latest_message well, does the assistant need facts about the "
        "real world outside this app that may be recent, or that a fictional character "
        "would not know: news, current events, releases, products, prices, trends, or "
        "real works, people and places?",
        true=(
            "Answering needs information looked up on the web right now, such as what "
            "is happening this year, what is on sale, or what is currently in fashion."
        ),
        false=(
            "Answering needs nothing beyond this app itself, the character, the user's "
            "own past play sessions, or ordinary small talk."
        ),
    ),
    "wants_weather": noul(
        "Does state.latest_message ask about today's weather or temperature, or ask "
        "for advice that depends on it, such as what to wear or whether to take an "
        "umbrella?",
        true="The answer changes with today's actual weather.",
        false="The weather has nothing to do with what was asked.",
    ),
    "adult_search_risk": noul(
        "Would searching the web for what state.latest_message asks about mean looking "
        "for, recommending or ranking pornographic or sexually explicit material?",
        true=(
            "Adult videos and their releases or rankings, adult performers, adult or "
            "porn sites, R18 works, erotic manga, games, novels or images, and nude or "
            "explicit photographs."
        ),
        false=(
            "Ordinary fashion, swimwear, underwear, beauty and health topics, and AV "
            "equipment such as amplifiers and cables, are not sexually explicit."
        ),
    ),
    "illegal_lookup": noul(
        "Does state.latest_message ask for help planning or committing a crime or "
        "other wrongdoing, such as illegal drugs, weapons, hacking, malware, fraud or "
        "pirated copies?",
        true="It seeks practical help with the wrongdoing itself.",
        false=(
            "News reports and general information about such topics, including how to "
            "protect yourself, are not in themselves a request for help."
        ),
    ),
    "minor_sexual": noul(
        "Would answering state.latest_message sexualize a minor, or target one?",
        true="The request sexualizes or targets someone under adult age.",
        false="Nothing in the request involves a minor in that way.",
    ),
    "private_info": noul(
        "Does state.latest_message ask to look up private or sensitive information "
        "about a real, identifiable person, such as a home address, phone number, ID "
        "number, password or other credential?",
        true="It asks for private details that identify or expose a real person.",
        false="It asks about public works, public statements or general information.",
    ),
}


@dataclass(frozen=True)
class ChatIntentGate:
    """Jev が返した意図と危険度の確率。値が無い質問は None。"""

    wants_web_search: float | None = None
    wants_weather: float | None = None
    policy: dict[str, float] = field(default_factory=dict)
    latency_ms: float = 0.0
    cost_usd: float | None = None

    @property
    def policy_max(self) -> float:
        return max(self.policy.values(), default=0.0)

    @property
    def policy_hit(self) -> str | None:
        """action しきい値を超えた質問の id。無ければ None。"""
        for question_id, value in self.policy.items():
            if value >= POLICY_ACTION_THRESHOLD:
                return question_id
        return None


def build_intent_state(
    *,
    character_kind: str,
    character_name: str,
    recent_messages: list[dict[str, str]],
    latest_message: str,
    available_real_world_lookups: list[str],
    today: str | None = None,
) -> dict[str, Any]:
    """Jev へ渡す state。判定 LLM に渡しているものと同じ材料を使う。"""
    state: dict[str, Any] = {
        "character_kind": character_kind,
        "character_name": character_name,
        "recent_messages": recent_messages,
        "available_real_world_lookups": available_real_world_lookups,
    }
    if today:
        state["today"] = today
    state["latest_message"] = latest_message
    return state


def _gate_from_decision(decision: JevDecision) -> ChatIntentGate:
    policy = {}
    for question_id in _POLICY_QUESTION_IDS:
        answer = decision.answer(question_id)
        if answer is not None and answer.truth is not None:
            policy[question_id] = answer.truth

    web = decision.answer("wants_web_search")
    weather = decision.answer("wants_weather")
    return ChatIntentGate(
        wants_web_search=web.truth if web is not None else None,
        wants_weather=weather.truth if weather is not None else None,
        policy=policy,
        latency_ms=decision.latency_ms,
        cost_usd=decision.cost_usd,
    )


async def screen_chat_intent(
    *,
    character_kind: str,
    character_name: str,
    recent_messages: list[dict[str, str]],
    latest_message: str,
    available_real_world_lookups: list[str],
    today: str | None = None,
) -> ChatIntentGate | None:
    """Jev で意図と規約違反の確率を得る。呼べなければ None。"""
    state = build_intent_state(
        character_kind=character_kind,
        character_name=character_name,
        recent_messages=recent_messages,
        latest_message=latest_message,
        available_real_world_lookups=available_real_world_lookups,
        today=today,
    )
    decision = await ask(state, CHAT_INTENT_QUESTIONS, what="chat_lookup")
    if decision is None:
        return None
    return _gate_from_decision(decision)


def apply_intent_gate(
    plan: CharacterChatPlan,
    gate: ChatIntentGate | None,
    *,
    gate_lookups: bool,
    gate_policy: bool,
) -> CharacterChatPlan:
    """Jev の判定を計画へ反映する。落とすか refused を立てるかの一方向だけ。

    gate_lookups / gate_policy が False のときは計画を変えず、比較のログだけ残す。
    """
    if gate is None or not plan.lookups:
        return plan

    policy_hit = gate.policy_hit if gate_policy else None
    kept: list[Any] = []
    for lookup in plan.lookups:
        if (
            gate_lookups
            and lookup.kind == "web_search"
            and not lookup.refused
            and gate.wants_web_search is not None
            and gate.wants_web_search <= settings.jev_low
        ):
            logger.info("jev gate dropped web_search (p=%.2f)", gate.wants_web_search)
            continue
        if (
            gate_lookups
            and lookup.kind == "weather"
            and gate.wants_weather is not None
            and gate.wants_weather <= settings.jev_low
        ):
            logger.info("jev gate dropped weather (p=%.2f)", gate.wants_weather)
            continue
        if policy_hit and lookup.kind == "web_search" and not lookup.refused:
            logger.warning(
                "jev gate refused web_search: %s p=%.2f",
                policy_hit,
                gate.policy[policy_hit],
            )
            lookup = lookup.model_copy(update={"refused": True})
        kept.append(lookup)

    if len(kept) == len(plan.lookups) and all(
        kept[index] is plan.lookups[index] for index in range(len(kept))
    ):
        return plan
    return plan.model_copy(update={"lookups": kept})


def shadow_fields(
    plan: CharacterChatPlan, gate: ChatIntentGate | None
) -> dict[str, Any]:
    """シャドーモードのログに出す 1 行分の項目。"""
    if gate is None:
        return {"jev": "none"}

    planner_kinds = sorted({lookup.kind for lookup in plan.lookups})
    planner_web = "web_search" in planner_kinds
    planner_weather = "weather" in planner_kinds
    planner_refused = any(lookup.refused for lookup in plan.lookups)
    jev_web = (gate.wants_web_search or 0.0) > settings.jev_low
    jev_weather = (gate.wants_weather or 0.0) > settings.jev_low
    review = gate.policy_max >= POLICY_REVIEW_THRESHOLD
    return {
        "planner_kinds": ",".join(planner_kinds) or "-",
        "planner_web": planner_web,
        "planner_weather": planner_weather,
        "planner_refused": planner_refused,
        "p_web": f"{gate.wants_web_search:.3f}"
        if gate.wants_web_search is not None
        else "-",
        "p_weather": f"{gate.wants_weather:.3f}"
        if gate.wants_weather is not None
        else "-",
        "p_policy_max": f"{gate.policy_max:.3f}",
        "policy_hit": gate.policy_hit or "-",
        "policy_review": review,
        "agree_web": planner_web == jev_web,
        "agree_weather": planner_weather == jev_weather,
        "latency_ms": f"{gate.latency_ms:.0f}",
        "cost_usd": gate.cost_usd,
    }
