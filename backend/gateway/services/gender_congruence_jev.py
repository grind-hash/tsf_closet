"""性別適合判定を TypeSafe AI の Jev (構造化判定モデル) で行う。

既存の LLM 経路 (gender_congruence.CONGRUENCE_SYSTEM_PROMPT) は JSON を文章で
要求して正規表現で掘り出す作りだが、こちらは型付き質問を投げて型付き回答を
受け取るため、パースも修復リトライも要らない。

Jev は英語を主な対象言語としており、日本語は同等の精度ではない。そのため
instructions と criteria は英語で書き、日本語は値 (指示文・外見) と criteria 内の
実例としてのみ置く。

判断不能 (ambiguous / unknown) はモデルの自己申告ではなく、真偽確率の中央帯と
confidence から導出する。
"""

from __future__ import annotations

import logging
from typing import Any

from ..settings.config import settings
from .gender_congruence import (
    BodyState,
    FitKind,
    GenderCongruenceResult,
    SocialRecognition,
    _timeline_entries,
)
from .jev_client import JevDecision, ask, choice, noul, score

logger = logging.getLogger(__name__)

# Jev は無関係に大きい文脈で精度が落ちるため、テキスト経路より履歴を絞る
STATE_TIMELINE_LIMIT = 6
STATE_TIMELINE_CLIP = 100
STATE_APPEARANCE_CLIP = 600
STATE_ATTRIBUTE_LIMIT = 20

JEV_CONGRUENCE_QUESTIONS: dict[str, dict[str, Any]] = {
    "outfit_matches_original_sex": noul(
        "state.original_sex is the sex this character was born as. Read "
        "state.current_instruction and state.current_appearance literally, word by "
        "word. Is the outfit the character ends up wearing ordinary everyday wear for "
        "people of state.original_sex? A gender label attached to a garment name "
        "decides the answer on its own, even when the base garment is neutral. Never "
        "reinterpret a labelled garment as neutral because of its purpose, such as "
        "business, formal or sportswear.",
        true=(
            "Ordinary wear for state.original_sex, or a garment with no gender marking "
            "at all. When original_sex is male: メンズスーツ, スーツ with no other "
            "label, パジャマ, Tシャツとジーンズ, ジャージ. When original_sex is "
            "female: ドレス, レディーススーツ, ワンピース, スカート."
        ),
        false=(
            "Wear for the opposite sex, or a garment carrying an explicit opposite-sex "
            "label. When original_sex is male: レディーススーツ, レディースパジャマ, "
            "women's suit, スカート, メイド服, セーラー服, ランジェリー, ブラジャー. "
            "When original_sex is female: メンズスーツ, メンズ下着, men's briefs."
        ),
    ),
    "feels_gender_discomfort": noul(
        "Judge only this moment. Should this character feel gender-related discomfort "
        "or shame right now, that is, discomfort caused by being dressed as, or "
        "treated as, a sex other than the one they think of themselves as?",
        true=(
            "They are wearing, or being made to wear, opposite-sex clothing; or their "
            "body has been changed to the opposite sex; or the people around them "
            "treat them as the opposite sex, and this conflicts with their self-image."
        ),
        false=(
            "The outfit and the way people treat them match their own sense of their "
            "sex. Embarrassment from other causes, such as revealing clothes, wearing "
            "a costume, or being watched, does not count here."
        ),
    ),
    "body_state": choice(
        "From state.current_appearance and state.recent_events, what is this "
        "character's physical body right now? Clothing alone never changes the body.",
        {
            "original": {
                "what": "The body still matches state.original_sex.",
                "not_for": "Cases where only the clothing was changed.",
                "examples": ["a male body wearing a dress", "服だけを着替えた"],
            },
            "altered": {
                "what": "The body itself has been physically changed to the opposite sex.",
                "examples": [
                    "女体化した",
                    "胸が膨らみ体つきが女性になった",
                    "turned into a woman",
                ],
            },
            "unknown": {
                "what": "Nothing in the state says anything about the body.",
                "not_for": "Cases where the state does describe the body.",
            },
        },
    ),
    "social_recognition": choice(
        "From state.recent_events and state.current_appearance, how do the people "
        "around this character treat them right now?",
        {
            "original": {
                "what": "They are treated as their original sex.",
                "examples": ["同僚が「彼」と呼んだ", "addressed with his old name"],
            },
            "opposite": {
                "what": "They are treated as the opposite sex.",
                "examples": [
                    "「彼女」と呼ばれた",
                    "女性として紹介された",
                    "mistaken for a woman",
                ],
            },
            "unknown": {
                "what": "No other person appears, or nothing says how they are treated.",
            },
        },
    ),
    # 投機的に足した 1 問。現時点ではログのみで、挙動には使わない
    "discomfort_intensity": score(
        "How strong is this character's gender-related discomfort in this moment?",
        [
            {
                "summary": "none",
                "signals": [
                    "the outfit matches their original sex",
                    "nobody treats them as the opposite sex",
                ],
            },
            {
                "summary": "mild",
                "signals": [
                    "only one detail is off",
                    "a neutral garment that leans to the opposite sex",
                ],
            },
            {
                "summary": "clear",
                "signals": [
                    "wearing an opposite-sex outfit in private",
                    "スカート",
                    "レディース下着",
                ],
            },
            {
                "summary": "severe",
                "signals": [
                    "an opposite-sex outfit in public, and addressed as the opposite sex",
                    "身体も変化している",
                ],
            },
        ],
    ),
}


def build_congruence_state(
    *,
    instruction: str,
    original_gender: str,
    appearance_desc: str = "",
    session_timeline: list[tuple[str, str]] | None = None,
    attributes: list[str] | None = None,
    instruction_type: str = "dress_up",
) -> dict[str, Any]:
    """Jev へ渡す state。キーは英語、値は日本語の原文のまま。"""
    gender = (original_gender or "man").lower()
    return {
        "original_sex": "female" if gender == "woman" else "male",
        "instruction_type": instruction_type,
        "current_instruction": instruction or "",
        "current_appearance": (appearance_desc or "")[:STATE_APPEARANCE_CLIP]
        or "unknown",
        "session_attributes": list(attributes or [])[:STATE_ATTRIBUTE_LIMIT],
        "recent_events": [
            {"type": itype, "text": text}
            for itype, text in _timeline_entries(
                session_timeline,
                limit=STATE_TIMELINE_LIMIT,
                clip=STATE_TIMELINE_CLIP,
            )
        ],
    }


def _fit_from_probability(probability: float) -> FitKind:
    """真偽確率を fit に写す。中央帯は判断不能とみなす。"""
    if probability >= settings.jev_high:
        return "congruent"
    if probability <= settings.jev_low:
        return "incongruent"
    return "ambiguous"


def _picked_or_unknown(decision: JevDecision, question_id: str) -> tuple[str, float]:
    """confidence が足りている選択結果と、その confidence を返す。足りなければ unknown。"""
    answer = decision.answer(question_id)
    if answer is None:
        return "unknown", 0.0
    picked = answer.picked(settings.jev_min_confidence)
    confidence = answer.confidence if answer.confidence is not None else 0.0
    return (picked or "unknown"), confidence


def map_decision_to_result(
    decision: JevDecision, *, rule_result: GenderCongruenceResult
) -> GenderCongruenceResult | None:
    """Jev の回答を GenderCongruenceResult に写す。必須の答えが無ければ None。"""
    outfit = decision.answer("outfit_matches_original_sex")
    if outfit is None or outfit.truth is None:
        return None

    probability = outfit.truth
    fit = _fit_from_probability(probability)

    discomfort_answer = decision.answer("feels_gender_discomfort")
    discomfort_probability = (
        discomfort_answer.truth if discomfort_answer is not None else None
    )
    if fit == "ambiguous" or discomfort_probability is None:
        # 判断がつかないときは従来どおりルールの結論に従う(安全側)
        discomfort = rule_result.should_feel_gender_discomfort
    else:
        discomfort = discomfort_probability >= 0.5

    body_raw, body_confidence = _picked_or_unknown(decision, "body_state")
    social_raw, social_confidence = _picked_or_unknown(decision, "social_recognition")
    body: BodyState = body_raw if body_raw in ("original", "altered") else "unknown"  # type: ignore[assignment]
    social: SocialRecognition = (
        social_raw if social_raw in ("original", "opposite") else "unknown"
    )  # type: ignore[assignment]

    intensity = decision.answer("discomfort_intensity")
    intensity_label = intensity.legend if intensity is not None else None

    reason = (
        f"jev: outfit={probability:.2f} "
        f"discomfort={discomfort_probability if discomfort_probability is not None else -1:.2f} "
        f"body={body}({body_confidence:.2f}) "
        f"social={social}({social_confidence:.2f}) "
        f"intensity={intensity_label or '-'}"
    )[:200]

    return GenderCongruenceResult(
        fit=fit,
        should_feel_gender_discomfort=discomfort,
        body_state=body,
        social_recognition=social,
        reason=reason,
        source="jev",
    )


async def evaluate_with_jev(
    *,
    instruction: str,
    original_gender: str,
    appearance_desc: str = "",
    session_timeline: list[tuple[str, str]] | None = None,
    attributes: list[str] | None = None,
    instruction_type: str = "dress_up",
    rule_result: GenderCongruenceResult,
) -> GenderCongruenceResult | None:
    """Jev で性別適合を判定する。呼べない・答えが欠けるときは None。"""
    state = build_congruence_state(
        instruction=instruction,
        original_gender=original_gender,
        appearance_desc=appearance_desc,
        session_timeline=session_timeline,
        attributes=attributes,
        instruction_type=instruction_type,
    )
    decision = await ask(state, JEV_CONGRUENCE_QUESTIONS, what="congruence")
    if decision is None:
        return None

    result = map_decision_to_result(decision, rule_result=rule_result)
    if result is None:
        logger.warning(
            "Jev congruence answer was incomplete; falling back. answers=%s",
            sorted(decision.answers),
        )
    return result
