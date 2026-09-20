"""変身タグの 3 軸分類を Jev (構造化判定モデル) で行う。

既存の tag_classifier はキーワード一致のルールだけで判定しており、語彙に無い
言い回しを取りこぼす。ここでは同じ 3 軸を Jev の choice / score で判定し、
confidence が足りない軸だけルールの結果をそのまま使う。

露出度は calculate_parameter_change 経由で羞恥・開花の増減に直結するため、
実際の挙動へ反映するのは JEV_LIVE_TARGETS に tags を入れたときだけ。

ルール側の関数 (classify_tags) は変更していない。回帰テストが固定している既定の
経路であり、Jev が使えないときの落とし先でもある。
"""

from __future__ import annotations

import logging
from typing import Any

from ..settings.config import settings
from .jev_client import ask, choice, score
from .tag_classifier import TAG_RULES, TransformationTags

logger = logging.getLogger(__name__)

_EXPOSURE_LEGEND = ("low", "medium", "high")
_AGE_OPTIONS = ("child", "student", "adult")


def _examples(axis: str, key: str, limit: int = 8) -> list[str]:
    """criteria に載せる実例をルールのキーワードから取る。"""
    return list(TAG_RULES[axis][key])[:limit]


JEV_TAG_QUESTIONS: dict[str, dict[str, Any]] = {
    "costume_category": choice(
        "state.instruction is what the player told the game to dress the character in. "
        "Which single category does the resulting outfit belong to? Pick the most "
        "specific category that fits.",
        {
            "underwear": {
                "what": "Underwear or lingerie worn as the outfit itself.",
                "examples": _examples("costume_category", "underwear"),
            },
            "swimsuit": {
                "what": "Swimwear.",
                "examples": _examples("costume_category", "swimsuit"),
            },
            "maid": {
                "what": "Maid uniforms.",
                "examples": _examples("costume_category", "maid"),
            },
            "gothic_lolita": {
                "what": "Gothic or Lolita fashion.",
                "examples": _examples("costume_category", "gothic_lolita"),
            },
            "cosplay": {
                "what": "Costumes of a character or a role, worn as a costume.",
                "not_for": "Everyday clothing, and the more specific categories above.",
                "examples": _examples("costume_category", "cosplay"),
            },
            "sports": {
                "what": "Sportswear and gym clothes.",
                "examples": _examples("costume_category", "sports"),
            },
            "uniform": {
                "what": "School or work uniforms.",
                "examples": _examples("costume_category", "uniform"),
            },
            "dress": {
                "what": "Dresses and formal wear.",
                "examples": _examples("costume_category", "dress"),
            },
            "other": {
                "what": "Everyday clothing, or anything none of the above covers.",
                "not_for": "Outfits that clearly belong to one of the categories above.",
            },
        },
    ),
    "exposure_level": score(
        "How much of the body does the outfit in state.instruction leave exposed?",
        [
            {
                "summary": "low",
                "signals": _examples("exposure_level", "low"),
            },
            {
                "summary": "medium",
                "signals": _examples("exposure_level", "medium"),
            },
            {
                "summary": "high",
                "signals": _examples("exposure_level", "high"),
            },
        ],
    ),
    "age_impression": choice(
        "What age does the outfit in state.instruction make the wearer look like? "
        "Judge the impression the outfit gives, not the character's real age.",
        {
            "child": {
                "what": "It makes the wearer look like a child.",
                "examples": _examples("age_impression", "child"),
            },
            "student": {
                "what": "It makes the wearer look like a school or university student.",
                "examples": _examples("age_impression", "student"),
            },
            "adult": {
                "what": "It makes the wearer look like a grown adult.",
                "examples": _examples("age_impression", "adult"),
            },
        },
    ),
}


def build_tag_state(instruction: str, *, appearance_desc: str = "") -> dict[str, Any]:
    """Jev へ渡す state。判定に要らない履歴は載せない。"""
    state: dict[str, Any] = {"instruction": instruction or ""}
    if appearance_desc:
        state["current_appearance"] = appearance_desc[:300]
    return state


async def classify_tags_with_jev(
    instruction: str,
    *,
    rule: TransformationTags,
    appearance_desc: str = "",
) -> TransformationTags | None:
    """Jev で 3 軸を判定する。呼べなければ None、軸ごとに足りなければルールを使う。"""
    decision = await ask(
        build_tag_state(instruction, appearance_desc=appearance_desc),
        JEV_TAG_QUESTIONS,
        what="tags",
    )
    if decision is None:
        return None

    costume_answer = decision.answer("costume_category")
    costume = (
        costume_answer.picked(settings.jev_min_confidence)
        if costume_answer is not None
        else None
    )

    exposure_answer = decision.answer("exposure_level")
    exposure = (
        exposure_answer.picked(settings.jev_min_confidence)
        if exposure_answer is not None
        else None
    )
    if exposure not in _EXPOSURE_LEGEND:
        exposure = None

    age_answer = decision.answer("age_impression")
    age = (
        age_answer.picked(settings.jev_min_confidence)
        if age_answer is not None
        else None
    )
    if age not in _AGE_OPTIONS:
        # choice の選択肢に unknown は置かず、確信が足りない場合を unknown に畳む
        age = "unknown" if age_answer is not None else None

    return TransformationTags(
        costume_category=costume or rule.costume_category,
        exposure_level=exposure or rule.exposure_level,
        age_impression=age or rule.age_impression,
    )


async def resolve_tags(
    instruction: str, *, appearance_desc: str = ""
) -> TransformationTags:
    """ルールで分類し、Jev が有効ならその結果を突き合わせる。

    JEV_LIVE_TARGETS に tags があるときだけ Jev の結果を採用する。それ以外は
    ルールの結果を返し、差分をログにだけ残す。
    """
    from .jev_client import log_shadow
    from .providers import jev_judge_enabled, jev_live
    from .tag_classifier import classify_tags

    rule = classify_tags(instruction)
    if not jev_judge_enabled():
        return rule

    jev = await classify_tags_with_jev(
        instruction, rule=rule, appearance_desc=appearance_desc
    )
    if jev is None:
        return rule

    log_shadow(
        "tags",
        {
            "rule_costume": rule.costume_category,
            "jev_costume": jev.costume_category,
            "rule_exposure": rule.exposure_level,
            "jev_exposure": jev.exposure_level,
            "rule_age": rule.age_impression,
            "jev_age": jev.age_impression,
            "agree_costume": rule.costume_category == jev.costume_category,
            "agree_exposure": rule.exposure_level == jev.exposure_level,
            "agree_age": rule.age_impression == jev.age_impression,
            "instr": repr(instruction[:80]),
        },
    )
    return jev if jev_live("tags") else rule
