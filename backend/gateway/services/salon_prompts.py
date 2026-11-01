"""Prompts for the salon management mode: the customer's review at checkout."""

from __future__ import annotations

import json
from typing import Any

from ..consts.salon import SALON_GOOD_SATISFACTION, SALON_LOW_SATISFACTION
from .session_request_prompts import ADULT_CONTENT_RULE


def _response_language(language: str) -> str:
    return "Japanese" if language == "ja" else "English"


def build_salon_review_prompt(
    *,
    profile: dict[str, Any],
    wish: str,
    satisfaction: int,
    fulfilled: bool,
    final_look: str,
    language: str,
    keeps_look: bool = False,
    sensitive: bool = False,
    experience_feeling: str = "",
) -> tuple[str, str]:
    """会計のとき、お客様本人の口調で書く口コミの (system, user) を返す。

    keeps_look なら、この姿のまま過ごして翌週もこの姿で来ることを口コミに滲ませる。
    sensitive(成人向けの依頼)なら性的な内容を許し、体験の心境があれば踏まえさせる。
    """
    pronoun = str(profile.get("pronoun") or "").strip()
    pronoun_rule = (
        f" Use the first-person pronoun {pronoun} if the customer refers to themselves."
        if pronoun
        else ""
    )
    content_rule = (
        f"Sexual content is allowed. {ADULT_CONTENT_RULE}"
        if sensitive
        else "Never write sexual content."
    )
    system = f"""You write a short review that a customer leaves after a visit to a dress-up salon, in the customer's own voice and personality.
Reply in {_response_language(language)}, with one or two sentences, at most 80 Japanese characters or 30 English words.{pronoun_rule}
Let the tone follow how the visit went: satisfaction is 0 to 100, and wish_fulfilled tells whether the wish came true. Mention one concrete detail of final_look.
Never mention scores, numbers, or game mechanics. {content_rule} Output only the review, without quotation marks."""
    if keeps_look:
        system += """
keeps_this_look is true: the customer loved this look so much that they will stay in it and come back next week still wearing it. Let the review show that wish to keep it."""
    if experience_feeling:
        system += """
experience is how the customer felt while doing what they longed for in this look, right after the styling. Let the review look back on that experience."""
    user = json.dumps(
        {
            "customer": {
                "name": profile.get("name") or "",
                "personality": profile.get("personality") or "",
                "tsf_attitude": profile.get("tsf_attitude") or "",
            },
            "wish": wish,
            "satisfaction": satisfaction,
            "wish_fulfilled": fulfilled,
            "final_look": final_look,
            "keeps_this_look": keeps_look,
            **({"experience": experience_feeling} if experience_feeling else {}),
        },
        ensure_ascii=False,
    )
    return system, user


_FALLBACK_REVIEWS: dict[str, dict[str, str]] = {
    "ja": {
        "fulfilled": "願いどおりの姿にしてもらえました。また来たいです。",
        "good": "素敵な時間でした。次はもっと近づけたらうれしいです。",
        "fair": "少し思っていたのと違ったけれど、楽しかったです。",
        "poor": "今回は、思い描いていた姿とは遠かったかな……。",
    },
    "en": {
        "fulfilled": "I got exactly the look I wished for. I will be back.",
        "good": "A lovely time. I hope we get even closer next time.",
        "fair": "Not quite what I imagined, but I had fun.",
        "poor": "This time it was far from what I had pictured...",
    },
}


def fallback_salon_review(satisfaction: int, fulfilled: bool, language: str) -> str:
    """口コミの生成に失敗したときの定型文。会計そのものは止めない。"""
    reviews = _FALLBACK_REVIEWS["ja" if language == "ja" else "en"]
    if fulfilled:
        return reviews["fulfilled"]
    if satisfaction >= SALON_GOOD_SATISFACTION:
        return reviews["good"]
    if satisfaction >= SALON_LOW_SATISFACTION:
        return reviews["fair"]
    return reviews["poor"]


def returning_visit_summary(language: str) -> str:
    """前回の施術の姿のまま来たお客様のセッションの、最初の履歴に置く一文。"""
    if language == "ja":
        return "前回の施術の姿のまま、サロンへ来店した"
    return "Came back to the salon in the look from the last visit"
