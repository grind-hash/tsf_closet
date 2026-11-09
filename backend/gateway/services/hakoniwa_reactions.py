"""AI箱庭: 掟を切り替えた直後の住民の短い反応(定型文。年代記には残さない)。

話し手は、いま見ている場所(area_id)にいる住民を優先する。入れ替わりは当事者の二人に固定。
戻り値 {area, lines: [{resident_id, text}]} は、部屋で一時の場面として再生する。
"""

from __future__ import annotations

import random
from typing import Any

from ..consts.hakoniwa_play import RULE_REACTION_TEMPLATES
from .hakoniwa_logic import (
    body_gender,
    custom_rule,
    resident_gender,
    resident_name,
    resident_text,
)


def _lang(language: str) -> str:
    return "ja" if language == "ja" else "en"


def _line(
    resident: dict[str, Any],
    key: str,
    language: str,
    **values: str,
) -> dict[str, str]:
    lang = _lang(language)
    pronoun = resident_text(resident, lang)["pronoun"] or (
        "私" if lang == "ja" else "I"
    )
    text = RULE_REACTION_TEMPLATES[key][lang].format(pronoun=pronoun, **values)
    return {"resident_id": resident["id"], "text": text}


def _candidates(state: dict[str, Any], area_id: str | None) -> list[dict[str, Any]]:
    """話し手の候補。見ている場所に誰かいればその住民、いなければ全員。"""
    residents = list(state.get("residents", []))
    here = [item for item in residents if item.get("current_area") == area_id]
    return here or residents


def _swap_lines(
    before: dict[str, Any], after: dict[str, Any], active: bool, language: str
) -> list[dict[str, str]]:
    pair_ids = (after if active else before).get("swap_pair") or []
    by_id = {item["id"]: item for item in after.get("residents", [])}
    pair = [by_id[pid] for pid in pair_ids if pid in by_id]
    if len(pair) != 2:
        return []
    a, b = pair
    lines: list[dict[str, str]] = []
    if active:
        # 男性が女性の体になった側の戸惑いを先に出す
        ordered = sorted(
            ((a, b), (b, a)),
            key=lambda item: (
                not (
                    resident_gender(item[0]) == "male"
                    and resident_gender(item[1]) == "female"
                )
            ),
        )
        for resident, partner in ordered:
            male_in_female = (
                resident_gender(resident) == "male"
                and resident_gender(partner) == "female"
            )
            lines.append(
                _line(
                    resident,
                    "swap_start_male" if male_in_female else "swap_start",
                    language,
                    partner=resident_name(partner, _lang(language)),
                )
            )
        return lines
    first_said = False
    for resident, partner in ((a, b), (b, a)):
        if resident_gender(resident) == "male" and resident_gender(partner) == "female":
            lines.append(_line(resident, "swap_end_male", language))
        elif not first_said:
            lines.append(_line(resident, "swap_end_first", language))
            first_said = True
        else:
            lines.append(_line(resident, "swap_end_second", language))
    return lines


def rule_reactions(
    before: dict[str, Any],
    after: dict[str, Any],
    card_id: str,
    active: bool,
    language: str,
    area_id: str | None,
    rng: random.Random,
) -> dict[str, Any] | None:
    """掟の切り替え直後の反応。切り替えで何も変わらなかったときは None。"""
    if before.get("active_rules") == after.get("active_rules"):
        return None
    lines: list[dict[str, str]] = []
    if card_id == "swap":
        lines = _swap_lines(before, after, active, language)
    candidates = _candidates(after, area_id)
    if not lines and active and card_id == "dress":
        male = next(
            (item for item in candidates if body_gender(after, item) == "male"), None
        )
        female = next(
            (item for item in candidates if body_gender(after, item) == "female"),
            None,
        )
        if male is not None:
            lines.append(_line(male, "dress_male", language))
        if female is not None:
            lines.append(_line(female, "dress_female", language))
    if not lines and candidates:
        speaker = rng.choice(candidates)
        rule = custom_rule(after, card_id)
        if active and card_id == "ojousama":
            lines.append(_line(speaker, "ojousama", language))
        elif active and rule is not None:
            key = (
                "custom_look"
                if str(rule.get("appearance_tags") or "").strip()
                else "custom"
            )
            lines.append(_line(speaker, key, language, rule=str(rule["name"])))
        else:
            lines.append(
                _line(speaker, "other_start" if active else "other_end", language)
            )
    if not lines:
        return None
    by_id = {item["id"]: item for item in after.get("residents", [])}
    areas = [by_id[line["resident_id"]].get("current_area") for line in lines]
    area = area_id if area_id in areas else areas[0]
    return {"area": area, "lines": lines}
