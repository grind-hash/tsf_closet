"""AI箱庭の「物語の厚み」の文の組み立て(表示とプロンプト)。

状態に残した種類と参照から、記憶・名残の文を言語ごとに作り、生成プロンプトへ渡す
英語の指示ブロック(適応・世界の適応・名残・記憶・物語の弧・違和感と調査)を作る。
"""

from __future__ import annotations

from typing import Any

from ..consts.hakoniwa import HAKONIWA_RULE_MAP
from ..consts.hakoniwa_story import (
    ADAPTATION_STAGE_GUIDANCE,
    ADAPTATION_STAGE_NAMES,
    ARC_CLIMAX_INSTRUCTION,
    ARC_CONTINUE_INSTRUCTION,
    ARC_TITLES,
    DISSONANCE_CONTEXT,
    INVESTIGATION_FOCUS,
    MEMORY_TEXTS,
    PLAYER_ADDRESS_NAMED,
    PLAYER_ADDRESS_UNNAMED,
    PLAYER_ADDRESS_WORDS,
    PLAYER_DIRECT_TALK,
    REMNANT_TEXTS,
    WORLD_ADAPTATION_STAGE_GUIDANCE,
    WORLD_ADAPTATION_STAGE_NAMES,
)
from . import hakoniwa_play as play
from . import hakoniwa_story as story
from .hakoniwa_logic import is_male_in_feminine_form, resident_name


def _lang(language: str) -> str:
    return "ja" if language == "ja" else "en"


def _name_of(state: dict[str, Any], resident_id: str | None, language: str) -> str:
    resident = next(
        (item for item in state.get("residents", []) if item["id"] == resident_id),
        None,
    )
    return resident_name(resident, language) if resident else "?"


def _rule_name(entry: dict[str, Any], language: str) -> str:
    if entry.get("rule_name"):
        return str(entry["rule_name"])
    card = HAKONIWA_RULE_MAP.get(str(entry.get("rule_id") or ""))
    return card["text"][_lang(language)]["name"] if card else "?"


# --- 表示用の文 ---


def memory_text(
    state: dict[str, Any],
    entry: dict[str, Any],
    language: str,
    name_language: str | None = None,
) -> str:
    """記憶の文。プロンプトでは英語の文に出力言語の住民名を入れる(name_language)。"""
    templates = MEMORY_TEXTS.get(str(entry.get("kind") or ""))
    if templates is None:
        return ""
    delta = int(entry.get("delta") or 0)
    names = name_language or language
    return templates[_lang(language)].format(
        partner=_name_of(state, entry.get("partner_id"), names),
        change=str(entry.get("change") or ""),
        title=str(entry.get("title") or ""),
        delta=f"+{delta}" if delta > 0 else str(delta),
        rule=_rule_name(entry, names),
    )


def memories_view(
    state: dict[str, Any], resident_id: str, language: str
) -> list[dict[str, Any]]:
    return [
        {
            "day": int(entry.get("day") or 1),
            "kind": str(entry.get("kind") or ""),
            "text": memory_text(state, entry, language),
        }
        for entry in story.resident_memories(state, resident_id)
        if entry.get("kind") in MEMORY_TEXTS
    ]


def remnant_text(
    state: dict[str, Any],
    remnant: dict[str, Any],
    language: str,
    name_language: str | None = None,
) -> str:
    texts = REMNANT_TEXTS.get(
        str(remnant.get("kind") or ""), REMNANT_TEXTS["transform"]
    )
    entry = texts.get(str(remnant.get("variant") or ""), texts["faint"])
    return entry[_lang(language)].format(
        partner=_name_of(state, remnant.get("partner_id"), name_language or language)
    )


def remnant_view(
    state: dict[str, Any], resident: dict[str, Any], language: str
) -> dict[str, Any] | None:
    remnant = story.resident_remnant(resident)
    if remnant is None:
        return None
    return {
        "kind": remnant.get("kind"),
        "text": remnant_text(state, remnant, language),
        "days_left": int(remnant.get("days_left") or 0),
    }


# --- プロンプトの住民情報への注記 ---


def adaptation_note(state: dict[str, Any], resident: dict[str, Any]) -> str:
    adaptation = story.resident_adaptation(state, resident)
    if adaptation is None:
        return ""
    stage = int(adaptation.get("stage") or 0)
    subject = "the swapped body" if adaptation.get("kind") == "swap" else "the new look"
    return f" Adaptation to {subject}: stage '{ADAPTATION_STAGE_NAMES[stage]}'."


def world_adaptation_note(state: dict[str, Any], resident: dict[str, Any]) -> str:
    entry = story.world_adaptation_entry(state, resident)
    if entry is None:
        return ""
    subject = "the swapped look" if entry["kind"] == "swap" else "the current look"
    return (
        f" The people around them, adapting to {subject}: stage "
        f"'{WORLD_ADAPTATION_STAGE_NAMES[entry['stage']]}'."
    )


def remnant_note(state: dict[str, Any], resident: dict[str, Any], language: str) -> str:
    remnant = story.resident_remnant(resident)
    if remnant is None:
        return ""
    text = remnant_text(state, remnant, "en", language)
    note = f" Back to normal, but a remnant lingers: {text}."
    if int(remnant.get("days_left") or 0) <= 1:
        note += " That remnant is already fading."
    return note


def story_notes(state: dict[str, Any], resident: dict[str, Any], language: str) -> str:
    """住民情報の行に足す、適応・世界の適応・名残の注記(名前は出力言語)。"""
    return (
        adaptation_note(state, resident)
        + world_adaptation_note(state, resident)
        + remnant_note(state, resident, language)
    )


def adapted_male_guidance(name: str) -> str:
    """適応が進んだ、本来は男性の住民への和らいだ戸惑いの指示。"""
    return (
        f"{name} is originally a man. The bewilderment is easing, but when treated as a "
        "woman, or when a feminine gesture slips out without thinking, a little "
        "embarrassment or wavering still shows."
    )


def adaptation_stage(state: dict[str, Any], resident: dict[str, Any]) -> int | None:
    adaptation = story.resident_adaptation(state, resident)
    return int(adaptation.get("stage") or 0) if adaptation else None


# --- 出来事のプロンプトの指示ブロック ---


def adaptation_focus_text(
    state: dict[str, Any], group: tuple[dict[str, Any], ...], language: str
) -> str:
    lines = []
    for resident in group:
        adaptation = story.resident_adaptation(state, resident)
        if adaptation is None:
            continue
        stage = int(adaptation.get("stage") or 0)
        subject = (
            "the swapped body" if adaptation.get("kind") == "swap" else "the new look"
        )
        lines.append(
            f"{resident_name(resident, language)} is at the adaptation stage "
            f"'{ADAPTATION_STAGE_NAMES[stage]}' toward {subject}. "
            f"{ADAPTATION_STAGE_GUIDANCE[stage]}"
        )
    if not lines:
        return ""
    return "\n\n[Important: follow each adaptation stage]\n" + "\n".join(lines)


def world_adaptation_focus_text(
    state: dict[str, Any], group: tuple[dict[str, Any], ...], language: str
) -> str:
    lines = []
    for resident in group:
        entry = story.world_adaptation_entry(state, resident)
        if entry is None:
            continue
        name = resident_name(resident, language)
        world_stage = entry["stage"]
        subject = "swapped look" if entry["kind"] == "swap" else "new look"
        lines.append(
            f"The world's adaptation to {name}'s {subject} is at the stage "
            f"'{WORLD_ADAPTATION_STAGE_NAMES[world_stage]}'. "
            f"{WORLD_ADAPTATION_STAGE_GUIDANCE[world_stage]}"
        )
        personal = adaptation_stage(state, resident)
        if personal is None:
            continue
        if personal <= 1 and world_stage >= 2:
            lines.append(
                f"{name} is still bewildered while everyone already treats the look as "
                "normal; let the feeling of being left behind show."
            )
        elif personal >= 2 and world_stage <= 1:
            lines.append(
                f"{name} has already accepted the look while the people around still "
                "make a fuss; let them smile wryly or calm the others down."
            )
    if not lines:
        return ""
    return "\n\n[Important: follow how the world is adapting]\n" + "\n".join(lines)


def memories_context_text(
    state: dict[str, Any], residents: tuple[dict[str, Any], ...] | list, language: str
) -> str:
    blocks = []
    for resident in residents:
        entries = story.resident_memories(state, resident["id"])
        items = [
            f"- (day {int(entry.get('day') or 1)}) "
            f"{memory_text(state, entry, 'en', language)}"
            for entry in entries
            if entry.get("kind") in MEMORY_TEXTS
        ]
        if items:
            blocks.append(
                f"{resident_name(resident, language)} remembers:\n" + "\n".join(items)
            )
    if not blocks:
        return ""
    return (
        "\n\nResidents' memories:\n"
        + "\n".join(blocks)
        + "\n(These are past events the residents actually lived through. When it fits "
        "the scene, they may mention or bring up these past events in lines or "
        "narration. There is no need to touch on them every time.)"
    )


def arc_title(state: dict[str, Any], arc: dict[str, Any], language: str) -> str:
    """プロンプト用の弧の題名(英語の文に、出力言語の住民名を入れる)。"""
    ids = list(arc.get("resident_ids") or [])
    template = ARC_TITLES.get(str(arc.get("kind") or ""), "{a}")
    return template.format(
        a=_name_of(state, ids[0] if ids else None, language),
        b=_name_of(state, ids[1] if len(ids) > 1 else None, language),
    )


def arcs_context_text(state: dict[str, Any], language: str) -> str:
    arcs = story.active_arcs(state)
    if not arcs:
        return ""
    lines = [
        f"- “{arc_title(state, arc, language)}” (carried by "
        + ", ".join(
            _name_of(state, rid, language) for rid in arc.get("resident_ids") or []
        )
        + ")"
        for arc in arcs
    ]
    return (
        "\n\nOngoing stories:\n"
        + "\n".join(lines)
        + "\n(These small stories continue over several days. Even when this event is "
        "not part of one, you may keep them faintly in mind as the world's mood.)"
    )


def arc_focus_text(
    state: dict[str, Any], arc_id: str | None, climax: bool, language: str
) -> str:
    arc = story.arc_by_id(state, arc_id)
    if arc is None or arc.get("status") != "active":
        return ""
    names = ", ".join(
        _name_of(state, rid, language) for rid in arc.get("resident_ids") or []
    )
    log = arc.get("log") or []
    synopsis = (
        "The story so far: "
        + " -> ".join(f"“{item.get('title', '')}”" for item in log)
        + "."
        if log
        else "This story starts moving today."
    )
    instruction = ARC_CLIMAX_INSTRUCTION if climax else ARC_CONTINUE_INSTRUCTION
    return (
        f"\n\n[Important: write this as part of the story “{arc_title(state, arc, language)}”]\n"
        f"Carried by: {names}. {synopsis}\n{instruction}"
    )


def player_address_rule(
    state: dict[str, Any], language: str, *, direct: bool = False
) -> str:
    """住民がプレイヤーをどう呼ぶか。

    名前(世界の設定)があればその名前で、無ければ肩書きを作らずに話させる。
    direct は一言・タッチ・会話のように住民がプレイヤーへ直接話す場面で、
    話している相手が同居人ではないことも添える(同居人の呼び方一覧に引きずられて、
    同居人へ挨拶してしまうのを防ぐ)。
    """
    words = PLAYER_ADDRESS_WORDS[_lang(language)]
    name = play.player_name(state)
    if name:
        rule = PLAYER_ADDRESS_NAMED.format(
            name=name,
            honorific=words["honorific"].format(name=name),
            title=words["title"],
        )
    else:
        rule = PLAYER_ADDRESS_UNNAMED.format(
            you=words["you"], indirect=words["indirect"], title=words["title"]
        )
    return f"{PLAYER_DIRECT_TALK} {rule}" if direct else rule


def acknowledged_player_rule(state: dict[str, Any], language: str) -> str:
    """公認のあと(住民がプレイヤーの存在を知っている)の出来事に添える、プレイヤーの呼び方。"""
    if not story.dissonance_enabled(state) or not state.get("dissonance_acknowledged"):
        return ""
    return " " + player_address_rule(state, language)


def dissonance_context_text(state: dict[str, Any]) -> str:
    if not story.dissonance_enabled(state):
        return ""
    if state.get("dissonance_acknowledged"):
        return "\n" + DISSONANCE_CONTEXT["acknowledged"]
    stage = story.dissonance_stage(story.dissonance_value(state))
    if stage == "stirring":
        return "\n" + DISSONANCE_CONTEXT["stirring"]
    if stage in ("probing", "confrontation"):
        return "\n" + DISSONANCE_CONTEXT["probing"]
    return ""


def investigation_focus_text(
    state: dict[str, Any], group: tuple[dict[str, Any], ...], language: str
) -> str:
    if not story.is_investigation_group(state, group):
        return ""
    lead = story.investigator(state)
    return INVESTIGATION_FOCUS.format(
        name=resident_name(lead, language) if lead else "one of the main characters"
    )


def male_guidance_is_softened(state: dict[str, Any], resident: dict[str, Any]) -> bool:
    """本来は男性で女性的な姿の住民が、適応「慣れかけ」以上に進んでいるか。"""
    stage = adaptation_stage(state, resident)
    return (
        stage is not None and stage >= 2 and is_male_in_feminine_form(state, resident)
    )
