"""Prompts for request mode (依頼モード): generating a request, judging a turn,
and the request block added to the character's feeling prompt."""

from __future__ import annotations

import json
from typing import Any


def _response_language(language: str) -> str:
    return "Japanese" if language == "ja" else "English"


def build_request_generation_prompt(
    profile: dict[str, Any], appearance: str, language: str
) -> tuple[str, str]:
    """依頼生成の (system, user) を返す。"""
    pronoun = str(profile.get("pronoun") or "").strip()
    pronoun_rule = (
        f" Use the first-person pronoun {pronoun} for the character." if pronoun else ""
    )
    system = f"""You write a request for a dress-up game. The character described by the user comes to a stylist (the player) and tells them the look they long to have.
Return one JSON object only, in {_response_language(language)}, matching this schema:
{{"wish":"...","preferences":[{{"text":"...","hint":"..."}}]}}
wish: what the character says to the stylist, in their own voice, at most 120 Japanese characters or 40 English words.{pronoun_rule} It names the overall look or mood they want (for example, a princess at a ball, a cool office worker, a shrine maiden) without listing every detail.
preferences: 2 or 3 concrete conditions the character secretly cares about but does not say, such as a color family, a skirt or dress length, a fabric or decoration, an accessory, or a hairstyle. Each must be checkable from a written description of the finished look, and they must not contradict the wish or each other. text states the condition plainly in at most 40 Japanese characters or 12 English words. hint names only its category in at most 8 Japanese characters or 3 English words (for example, color, length, accessory), so the player has something to guess from.
Keep everything consistent with the character's personality and background, and never write sexual content. When tsf_attitude is given, let the wish grow out of that attitude toward transformation (for example, a hidden longing to look like a princess, or curiosity about living as the other sex), without stating the attitude itself."""
    user = json.dumps(
        {
            "character": {
                "name": profile.get("name") or "",
                "gender": profile.get("gender") or "",
                "personality": profile.get("personality") or "",
                "description": profile.get("description") or "",
                "tsf_attitude": profile.get("tsf_attitude") or "",
            },
            "current_look": appearance,
        },
        ensure_ascii=False,
    )
    return system, user


def build_request_evaluation_prompt(
    *,
    wish: str,
    preferences: list[dict[str, Any]],
    current_look: str,
    instruction: str,
    language: str,
) -> tuple[str, str]:
    """手番評価の (system, user) を返す。"""
    system = f"""You judge how well a finished look fulfils a character's request in a dress-up game.
Return one JSON object only, matching this schema:
{{"fit":"none|partial|good|perfect","met_preference_ids":[],"hint":"..."}}
fit rates how well current_look as a whole matches wish: none when it is unrelated, partial when it captures only some of the mood, good when it is clearly the requested look, perfect when it is exactly the requested look with nothing out of place.
met_preference_ids lists the ids of preferences that current_look actually satisfies. Judge only from current_look: player_instruction is what the player asked for, not proof that it happened.
hint is one short sentence in {_response_language(language)}, at most 50 Japanese characters or 20 English words, that nudges toward one preference that is not met, phrased as something the stylist could notice about the character's reaction, without stating the preference outright. Use an empty string when every preference is met."""
    user = json.dumps(
        {
            "wish": wish,
            "preferences": [
                {"id": item.get("id"), "text": item.get("text")} for item in preferences
            ],
            "current_look": current_look,
            "player_instruction": instruction,
        },
        ensure_ascii=False,
    )
    return system, user


_FIT_LABELS: dict[str, dict[str, str]] = {
    "ja": {
        "none": "まだ願いとは違う姿",
        "partial": "願いに少し近づいた姿",
        "good": "願いにかなり近い姿",
        "perfect": "願いそのものの姿",
    },
    "en": {
        "none": "not yet the look they wished for",
        "partial": "a little closer to their wish",
        "good": "close to their wish",
        "perfect": "exactly the look they wished for",
    },
}


def build_request_feeling_context(
    *,
    wish: str,
    met_texts: list[str],
    unmet_texts: list[str],
    fit: str | None,
    language: str,
) -> str:
    """心境プロンプトの user prompt に添える依頼ブロック。

    まだ満たされていない好みは本人の反応でほのめかすだけにし、名指しさせない。
    """
    labels = _FIT_LABELS["ja" if language == "ja" else "en"]
    if language == "ja":
        lines = [
            "",
            "【依頼】",
            f"このキャラクターは着せ替えの前に、次の願いを伝えています:「{wish}」",
        ]
        if fit in labels:
            lines.append(f"・いまの姿: {labels[fit]}")
        if met_texts:
            lines.append(f"・満たされた好み: {'、'.join(met_texts)}")
        if unmet_texts:
            lines.append(
                "・まだ満たされていない好み（口に出して名指しせず、反応の中でそれとなく"
                f"ほのめかす）: {'、'.join(unmet_texts)}"
            )
        lines.append(
            "願いにどれだけ近づいたかを、本人の反応として自然に表してください。"
        )
        return "\n".join(lines)
    lines = [
        "",
        "[Request]",
        f'Before the dress-up, this character told the stylist their wish: "{wish}"',
    ]
    if fit in labels:
        lines.append(f"- Current look: {labels[fit]}")
    if met_texts:
        lines.append(f"- Preferences now satisfied: {'; '.join(met_texts)}")
    if unmet_texts:
        lines.append(
            "- Preferences not yet satisfied (never name them outright; only hint "
            f"at them through the reaction): {'; '.join(unmet_texts)}"
        )
    lines.append(
        "Let the reaction show naturally how close the look has come to the wish."
    )
    return "\n".join(lines)
