"""AI箱庭の生成プロンプト。

実装済みの掟・入れ替わり・衣装・変身・気分・親密度のみを扱い、
英語の指示の末尾で出力言語を指定する。
"""

from __future__ import annotations

from typing import Any

from ..consts.hakoniwa import (
    CUSTOM_RULE_PRIORITY_NOTE,
    DEFAULT_AREA_ID,
    HAKONIWA_AREA_MAP,
    HAKONIWA_CUSTOM_RULE_PROMPT_MAX,
    HAKONIWA_EVENT_LINES_RANGE,
    HAKONIWA_FURNITURE_MAP,
    HAKONIWA_PERSONALITY_PROMPT_MAX,
    HAKONIWA_RECENT_EVENTS_CONTEXT,
    HAKONIWA_RECENT_NARRATION_SNIPPET,
    HAKONIWA_RULE_MAP,
    HAKONIWA_TAGS_MAX_COUNT,
    HAKONIWA_TRANSFORM_DESC_PROMPT_MAX,
    RULE_PRIORITY_NOTE,
    WORLD_BRIEF,
)
from .hakoniwa_logic import (
    active_custom_rules,
    appearance_kind,
    body_gender,
    is_feminine_transformation,
    is_male_in_feminine_form,
    resident_gender,
    resident_name,
    resident_text,
    swap_partner_id,
)
from .session_request_prompts import ADULT_CONTENT_RULE

DIALOGUE_CRAFT_GUIDANCE = (
    "Build the dialogue as: an opening line that starts the scene, the main "
    "exchange, back-and-forth reactions, and a small punchline or a hint of what "
    "comes next. Do not trade short one-word replies; every line should carry a "
    "feeling or a piece of information."
)

MALE_CONFUSION_GUIDANCE = (
    "In particular, {name} is originally a man and is strongly bewildered and "
    "flustered at being in a feminine form. Depict it richly in both lines and "
    "narration: the strangeness of the body (a different center of gravity and "
    "height, not being used to long hair or a skirt), the voice and eye level "
    "feeling wrong, embarrassment at being treated as a woman, and feelings that "
    "waver between wanting to change back and being swayed by unexpected "
    "sensations or compliments. Do not have him accept it calmly as if nothing "
    "happened."
)

MALE_OUTFIT_GUIDANCE = (
    "In particular, {name} is a man wearing feminine clothes while his own body "
    "stays male. Depict his embarrassment richly in both lines and narration: not "
    "being used to a skirt or dress (the hem, the draft, how to sit and walk), "
    "self-consciousness at others' eyes and at being treated like a woman, and "
    "feelings that waver between wanting to take it off and being swayed by "
    "unexpected compliments. Do not infer changes to sex, height or voice from "
    "feminine clothing alone; honor any explicit transformation details. Do not "
    "have him accept it calmly."
)


def male_confusion_guidance(
    state: dict[str, Any], resident: dict[str, Any], name: str
) -> str:
    """本来は男性の住民への戸惑いの指示。体が女性になっているか、服だけかで書き分ける。"""
    if body_gender(state, resident) == "female":
        return MALE_CONFUSION_GUIDANCE.format(name=name)
    return MALE_OUTFIT_GUIDANCE.format(name=name)


NO_MALE_ROMANCE_RULE = (
    "Never depict romantic or sexual feelings or acts between two residents who "
    "both currently have male bodies; keep such pairs to friendship. A resident "
    "who was originally male but now has a female body is not covered by this."
)

RISQUE_REACTION_GUIDANCE = (
    "In particular, {name}'s look is revealing and daring. Depict the reactions "
    "richly: {name} shows embarrassment and agitation, trying to cover up or "
    "looking away, yet a complicated, not entirely displeased expression shows "
    "when complimented. Even everyday motions like walking or sitting make {name} "
    "unusually conscious of the look. Others react concretely in words and "
    "actions: not knowing where to look, pretending not to look, teasing, honest "
    "praise, lending a jacket or changing seats. Do not brush it off and return "
    "to an ordinary day."
)

_RISQUE_MARKERS = (
    "bikini",
    "microkini",
    "lingerie",
    "underwear",
    "panties",
    "cleavage",
    "revealing",
    "see-through",
    "sexy",
    "seductive",
    "skimpy",
    "topless",
    "bottomless",
    "naked",
    "nude",
    "swimsuit",
    "miniskirt",
    "hot pants",
    "fishnet",
    "garter",
    "corset",
    "babydoll",
    "negligee",
    "露出",
    "際ど",
    "セクシー",
    "色っぽ",
    "えっち",
    "エッチ",
    "水着",
    "ビキニ",
    "下着",
    "ランジェリー",
    "透け",
    "胸元",
    "大胆な",
    "はだけ",
)

RULE_FOCUS_RETRY_NOTE = (
    "\n\n[Repeated, mandatory] Putting what the rule above prescribes at the center "
    "of the scene is an absolute condition. An everyday event that does not touch "
    "the rule, or a scene that only comments on the rule, is not acceptable. Output "
    "a scene in which the main characters actually live by the rule, in the "
    "specified JSON format."
)


def response_language(language: str) -> str:
    return "Japanese" if language == "ja" else "English"


def gender_address_rules(language: str) -> str:
    rules = (
        "Gender and form-of-address rules: each resident's gender is stated in the "
        "resident information. Pronouns in narration and any gender-dependent "
        "description must match each resident's gender setting. A body swap or a "
        "transformation changes only the body, not the mind: every resident keeps "
        "their own first-person pronoun, speech style and way of addressing others "
        "(a man in a woman's body still says his usual first person, and vice versa)."
    )
    if language == "ja":
        rules += (
            " Never call a female resident 「くん」; use 「さん」「ちゃん」 or another "
            "suitable form for the relationship. Use 「くん」 only for male residents. "
            "Write natural Japanese only and never mix in simplified Chinese "
            "characters (write 視線・鏡・風・見る・違う・顔, not 视线・镜・风・见る・违う・颜)."
        )
    return rules


def content_rule(nsfw: bool) -> str:
    if nsfw:
        return (
            "All residents are adults. When a rule written by the player includes "
            "adult themes, depict them faithfully to the rule's wording. "
            f"{ADULT_CONTENT_RULE}"
        )
    return (
        "All residents are adults. Keep every description non-explicit: no sexual "
        "acts or nudity; express such themes through reactions and emotions only."
    )


def is_risque_text(text: str) -> bool:
    haystack = f" {str(text or '').lower()} "
    return any(marker in haystack for marker in _RISQUE_MARKERS)


def appearance_is_risque(state: dict[str, Any], resident: dict[str, Any]) -> bool:
    if appearance_kind(state, resident) != "transform":
        return False
    transformation = resident.get("transformation") or {}
    return is_risque_text(
        f"{transformation.get('tags', '')} {transformation.get('description', '')}"
    )


def _gender_label(gender: str) -> str:
    return "man" if gender == "male" else "woman"


def world_brief(state: dict[str, Any]) -> str:
    brief = WORLD_BRIEF
    if state.get("active_rules"):
        brief += RULE_PRIORITY_NOTE
        if active_custom_rules(state):
            brief += CUSTOM_RULE_PRIORITY_NOTE
    return brief


def active_rules_text(state: dict[str, Any], language: str) -> str:
    lines: list[str] = []
    by_id = {resident["id"]: resident for resident in state["residents"]}
    custom_by_id = {rule["id"]: rule for rule in state.get("custom_rules", [])}
    has_custom = False
    for card_id in state.get("active_rules", []):
        custom = custom_by_id.get(card_id)
        if custom is not None:
            has_custom = True
            text = str(custom["text"])[:HAKONIWA_CUSTOM_RULE_PROMPT_MAX]
            lines.append(f"- Player-written rule '{custom['name']}': {text}")
            continue
        card = HAKONIWA_RULE_MAP.get(card_id)
        if card is None:
            continue
        text = card["prompt"]
        if card_id == "swap" and state.get("swap_pair"):
            a_id, b_id = state["swap_pair"]
            text = text.format(
                a=resident_name(by_id[a_id], language) if a_id in by_id else a_id,
                b=resident_name(by_id[b_id], language) if b_id in by_id else b_id,
            )
        lines.append(f"- {text}")
    if not lines:
        return "(No rules are active right now.)"
    if has_custom:
        lines.append(
            "(Player-written rules are absolute laws of this world and every "
            "resident obeys them. Show concretely, through actions and lines, how "
            "each rule appears in daily life. Do not swap the rule's subject for a "
            "harmless complaint such as clothes being inconvenient.)"
        )
    return "\n".join(lines)


def current_appearance_summary(
    state: dict[str, Any], resident: dict[str, Any]
) -> str | None:
    kind = appearance_kind(state, resident)
    if kind == "transform":
        transformation = resident.get("transformation") or {}
        description = str(transformation.get("description") or "")[
            :HAKONIWA_TRANSFORM_DESC_PROMPT_MAX
        ]
        return f"a look transformed into: '{description}'"
    if kind == "dress":
        return "wearing a dress"
    return None


def appearance_note(state: dict[str, Any], resident: dict[str, Any]) -> str:
    summary = current_appearance_summary(state, resident)
    if summary is None:
        return ""
    if resident_gender(resident) == "male" and is_male_in_feminine_form(
        state, resident
    ):
        if body_gender(state, resident) == "female":
            return f" Currently {summary}; originally a man, now in a woman's body."
        return f" Currently {summary}; his body stays male despite the feminine outfit."
    return f" Currently {summary}."


def _swap_note(state: dict[str, Any], resident: dict[str, Any], language: str) -> str:
    partner_id = swap_partner_id(state, resident["id"])
    if not partner_id:
        return ""
    partner = next(
        (item for item in state["residents"] if item["id"] == partner_id), None
    )
    if partner is None:
        return ""
    note = f" Has swapped bodies with {resident_name(partner, language)}."
    if resident_gender(resident) == "male" and body_gender(state, resident) == "female":
        note += " Originally a man, now in a woman's body."
    elif (
        resident_gender(resident) == "female" and body_gender(state, resident) == "male"
    ):
        note += " Originally a woman, now in a man's body."
    return note


def residents_text(state: dict[str, Any], language: str) -> str:
    names = {item["id"]: resident_name(item, language) for item in state["residents"]}
    lines = []
    for resident in state["residents"]:
        text = resident_text(resident, language)
        affinities = ", ".join(
            f"affinity toward {names.get(other, other)} {value}"
            for other, value in resident["affinities"].items()
        )
        personality = str(text["personality"])[:HAKONIWA_PERSONALITY_PROMPT_MAX]
        pronoun = (
            f" First-person pronoun: {text['pronoun']}." if text["pronoun"] else ""
        )
        lines.append(
            f"- {text['name']} ({_gender_label(resident_gender(resident))}, "
            f"{text['age']}, {text['job']}): {personality}{pronoun} "
            f"Mood {resident['mood']}/100. {affinities}."
            f"{_swap_note(state, resident, language)}"
            f"{appearance_note(state, resident)}"
        )
    return "\n".join(lines)


def recent_events_text(state: dict[str, Any]) -> str:
    recent = state["events"][-HAKONIWA_RECENT_EVENTS_CONTEXT:]
    if not recent:
        return "(none yet)"
    lines = []
    for event in recent:
        title = str(event.get("title") or "")
        narration = str(event.get("narration") or "").strip()
        if narration:
            lines.append(
                f"- {title} ({narration[:HAKONIWA_RECENT_NARRATION_SNIPPET]}...)"
            )
        else:
            lines.append(f"- {title}")
    return "\n".join(lines)


def _swap_members(
    state: dict[str, Any], group: tuple[dict[str, Any], ...]
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    pair = state.get("swap_pair")
    if "swap" not in state.get("active_rules", []) or not pair:
        return None
    by_id = {resident["id"]: resident for resident in group}
    if pair[0] in by_id and pair[1] in by_id:
        return (by_id[pair[0]], by_id[pair[1]])
    return None


def swap_focus_text(
    state: dict[str, Any], group: tuple[dict[str, Any], ...], language: str
) -> str:
    members = _swap_members(state, group)
    if members is None:
        return ""
    a, b = members
    a_name, b_name = resident_name(a, language), resident_name(b, language)
    text = (
        "\n\n[Most important: make the reaction to the body swap the theme]\n"
        f"{a_name} and {b_name}, the main characters, have swapped appearances "
        "(bodies). Do not write an event where they just do chores normally; make "
        "their reaction to being swapped the theme itself. Concretely depict at least "
        "two of: differences in bodily sensation (height, eye level, stamina, hair "
        "length); surprise at hearing the other's voice come out; double takes at the "
        "other's reflection in a mirror or window; the other body's habits slipping "
        "out, or one's own habits showing in the other's body; awkwardness at having "
        "to use the other's clothes or belongings; having to do the other's job. They "
        "express confusion, embarrassment or curiosity frankly in their lines. Show "
        "the reaction in both narration and lines, and at least one line must mention "
        "bodily sensation or appearance."
    )
    others = [
        resident_name(resident, language)
        for resident in group
        if resident["id"] not in {a["id"], b["id"]}
    ]
    if others:
        text += (
            f" {', '.join(others)} is not part of the swap but reacts up close to the "
            "two's mismatch."
        )
    for resident in (a, b):
        if (
            resident_gender(resident) == "male"
            and body_gender(state, resident) == "female"
        ):
            text += "\n" + MALE_CONFUSION_GUIDANCE.format(
                name=resident_name(resident, language)
            )
    return text


def appearance_focus_text(
    state: dict[str, Any], group: tuple[dict[str, Any], ...], language: str
) -> str:
    targets = []
    confused = []
    for resident in group:
        kind = appearance_kind(state, resident)
        if kind is None:
            continue
        if kind == "dress" and resident_gender(resident) != "male":
            continue
        summary = current_appearance_summary(state, resident)
        name = resident_name(resident, language)
        targets.append(f"{name} ({summary})")
        if is_male_in_feminine_form(state, resident):
            confused.append((resident, name))
    if not targets:
        return ""
    if len(group) == 1:
        clause = (
            "As a reaction to the look, include at least one self-aware line from the "
            "character (embarrassment, pride, bewilderment, grumbling or a mutter), "
            "and mention the look concretely in the narration too."
        )
    else:
        clause = (
            "As a reaction to the look, include at least one line that is either the "
            "character's own self-aware remark (embarrassment, pride, bewilderment, "
            "grumbling) or another main character commenting on it (impression, "
            "remark, compliment), and mention the look concretely in the narration too."
        )
    text = (
        "\n\n[Important: always include reactions to the current look]\n"
        f"Among the main characters, {', '.join(targets)} look different from usual. "
        f"Do not write the day as if the look did not exist. {clause}"
    )
    for resident, name in confused:
        text += "\n" + male_confusion_guidance(state, resident, name)
    return text


def risque_focus_text(
    state: dict[str, Any], group: tuple[dict[str, Any], ...], language: str
) -> str:
    lines = []
    for resident in group:
        if not appearance_is_risque(state, resident):
            continue
        name = resident_name(resident, language)
        lines.append(RISQUE_REACTION_GUIDANCE.format(name=name))
        if is_male_in_feminine_form(state, resident):
            lines.append(
                f"On top of that, {name} is originally a man, and the bewilderment at "
                "being in a daring feminine form overlaps with the embarrassment and "
                "sways even harder."
            )
    if not lines:
        return ""
    if len(group) == 1:
        lines.append(
            "This scene has only one character, so focus on the character's reaction "
            "to their own reflection and their inner turmoil rather than others' "
            "reactions."
        )
    return "\n\n[Important: thicken the reactions to the daring look]\n" + "\n".join(
        lines
    )


def custom_rule_focus_text(state: dict[str, Any], rule_id: str, nsfw: bool) -> str:
    rules = [rule for rule in active_custom_rules(state) if rule["id"] == rule_id]
    if not rules:
        return ""
    rule_lines = "\n".join(
        f"- Rule '{rule['name']}': {str(rule['text'])[:HAKONIWA_CUSTOM_RULE_PROMPT_MAX]}"
        for rule in rules
    )
    adult = (
        " If the rule prescribes sexual matters between adults, depict the prescribed "
        "acts themselves and the residents' feelings and conversation faithfully to "
        "the rule's wording as the center of the scene, without replacing them with "
        "comments or metaphors."
        if nsfw
        else " Keep it non-explicit even if the rule touches on adult themes."
    )
    return (
        "\n\n[Most important: this event is a scene of living by the rule]\n"
        f"The following player-written rule is the center of this scene.\n{rule_lines}\n"
        "Put how the main characters actually carry out and feel about what the rule "
        "prescribes at the center of their actions and lines. Make it a scene that "
        "depicts the act or state the rule imposes, not a scene that only discusses "
        "the rule. Replacing it with a harmless topic such as clothes being hard to "
        "move in, or blurring it with metaphors, is forbidden."
        f"{adult} Show concretely, in both narration and lines, how the rule shapes "
        "this scene."
    )


def _event_schema(group: tuple[dict[str, Any], ...], language: str) -> str:
    names = [resident_name(resident, language) for resident in group]
    lo, hi = HAKONIWA_EVENT_LINES_RANGE[min(len(group), 3)]
    participants = ", ".join(f'"{name}"' for name in names)
    moods = ", ".join(f'"{name}": mood change (integer -20..20)' for name in names)
    affinity = (
        ', "affinity_delta": change in their relationship (integer -15..15)'
        if len(group) >= 2
        else ""
    )
    return (
        '{"title": "short heading", '
        '"narration": "narration without any dialogue, 2-3 sentences", '
        '"lines": [{"speaker": "name of the speaking resident", "text": "one line of dialogue"}], '
        f'"participants": [{participants}], '
        f'"mood_delta": {{{moods}}}{affinity}}}\n'
        f"Write {lo}-{hi} lines."
    )


def event_system_prompt(
    group: tuple[dict[str, Any], ...],
    state: dict[str, Any],
    language: str,
    *,
    nsfw: bool,
) -> str:
    if len(group) == 1:
        shape = (
            "Create exactly one event at the boarding house with this single resident "
            "as the main character. The lines are the character's own monologue or "
            "mutterings, and every speaker must be that character. Other residents do "
            "not appear (mentioning their names in narration is fine). Do not output an "
            "affinity change. In a one-person scene, read the back-and-forth part of the "
            "dialogue structure as a flow of monologue and reflection."
        )
    elif len(group) >= 3:
        shape = (
            "Create exactly one event at the boarding house with these three residents "
            "as the main characters. Every speaker must be one of them. Give each of the "
            "three a line or a memorable role; do not let it become one person's "
            "conversation. affinity_delta is the change in the three's relationship as "
            "a whole."
        )
    else:
        shape = (
            "Create exactly one event at the boarding house with these two residents as "
            "the main characters. Every speaker must be one of them."
        )
    return (
        f"{world_brief(state)}\n"
        "You are the narrator of this miniature world.\n"
        f"{shape}\n"
        f"{DIALOGUE_CRAFT_GUIDANCE}\n"
        "Narration must not contain dialogue in quotation marks. Speakers and "
        "participants must be written exactly as the names given.\n"
        f"{gender_address_rules(language)}\n"
        f"{NO_MALE_ROMANCE_RULE}\n"
        f"{content_rule(nsfw)}\n"
        "Output only one JSON object in this format, with no preface or code fence:\n"
        f"{_event_schema(group, language)}\n"
        f"Write the title, narration and lines in {response_language(language)}."
    )


def area_name(area_id: str | None, language: str) -> str:
    area = (
        HAKONIWA_AREA_MAP.get(str(area_id or "")) or HAKONIWA_AREA_MAP[DEFAULT_AREA_ID]
    )
    return area["name"]["ja" if language == "ja" else "en"]


def place_text(state: dict[str, Any], area_id: str | None) -> str:
    """出来事の場所の情景と、そこに置かれた家具(場面に合えば顔を出す程度)。"""
    area = (
        HAKONIWA_AREA_MAP.get(str(area_id or "")) or HAKONIWA_AREA_MAP[DEFAULT_AREA_ID]
    )
    text = f"Place: {area['scene']}"
    layout = (state.get("furniture_layout") or {}).get(area["id"]) or []
    items = [
        HAKONIWA_FURNITURE_MAP[item]["description"]
        for item in layout
        if item in HAKONIWA_FURNITURE_MAP
    ]
    if items:
        text += (
            f" Placed here: {', '.join(items)}. These may appear naturally when they "
            "fit the scene; there is no need to force them in."
        )
    return text + (
        " The event takes place here; weave in the atmosphere and small details of "
        "this place."
    )


def event_user_prompt(
    state: dict[str, Any],
    group: tuple[dict[str, Any], ...],
    language: str,
    *,
    nsfw: bool,
    rule_focus_rule_id: str | None = None,
    others_today: list[list[str]] | None = None,
    area_id: str | None = None,
) -> str:
    names = [resident_name(resident, language) for resident in group]
    if len(group) == 1:
        lead = (
            f"Main character: {names[0]} (the only main character). Depict time alone, "
            "small discoveries or reflection, centered on the character's monologue."
        )
    elif len(group) >= 3:
        lead = f"Main characters: {', '.join(names)}. All three take part."
    else:
        lead = f"Main characters: {names[0]} and {names[1]}."
    others = ""
    if others_today:
        groups_text = "; ".join(" & ".join(item) for item in others_today if item)
        if groups_text:
            others = (
                f"Other events today feature: {groups_text}. Choose a topic and situation "
                "different from what those groups would likely do.\n"
            )
    focus = (
        custom_rule_focus_text(state, rule_focus_rule_id, nsfw)
        if rule_focus_rule_id
        else ""
    )
    return (
        f"Today is day {state['day']} at Stardust House.\n"
        f"{lead}\n"
        f"{place_text(state, area_id)}\n\n"
        f"World rules:\n{active_rules_text(state, language)}\n\n"
        f"Residents:\n{residents_text(state, language)}\n\n"
        f"Recent events:\n{recent_events_text(state)}\n"
        f"{others}"
        "Avoid topics and developments similar to the recent events, and make the "
        "event feel like part of their accumulating relationship."
        f"{swap_focus_text(state, group, language)}"
        f"{appearance_focus_text(state, group, language)}"
        f"{risque_focus_text(state, group, language)}"
        f"{focus}"
    )


def greeting_prompts(
    state: dict[str, Any], resident: dict[str, Any], language: str, *, nsfw: bool
) -> tuple[str, str]:
    names = {item["id"]: resident_name(item, language) for item in state["residents"]}
    text = resident_text(resident, language)
    top_affinity = ""
    if resident.get("affinities"):
        other_id, value = max(
            resident["affinities"].items(), key=lambda item: abs(item[1])
        )
        top_affinity = (
            f" The relationship that stands out is with {names.get(other_id, other_id)} "
            f"(affinity {value})."
        )
    hint = ""
    if appearance_kind(state, resident) or swap_partner_id(state, resident["id"]):
        hint = " The line may touch on the character's current look."
        if is_male_in_feminine_form(state, resident):
            if body_gender(state, resident) == "female":
                hint += (
                    " Being originally a man now in a woman's body, let bewilderment, "
                    "embarrassment or the strangeness of the body show in the line."
                )
            else:
                hint += (
                    " His body stays male; express embarrassment about the feminine "
                    "outfit, without inventing bodily changes caused by the clothes."
                )
        if appearance_is_risque(state, resident):
            hint += (
                " The look is revealing; embarrassment or restless self-awareness of "
                "being looked at may show."
            )
    pronoun = f" First-person pronoun: {text['pronoun']}." if text["pronoun"] else ""
    system_prompt = (
        f"{WORLD_BRIEF}\n"
        "You are this resident of the miniature world. The player has just said hello. "
        "Reply with one short line in character (1-2 sentences, at most 60 Japanese "
        "characters or 30 English words). Output only the spoken words: no narration, "
        "headings, quotation marks or explanations. If rules are active, always reflect "
        "their speech style and premise.\n"
        f"{gender_address_rules(language)}\n"
        f"{content_rule(nsfw)}\n"
        f"Reply in {response_language(language)}."
    )
    user_prompt = (
        f"You are {text['name']} ({_gender_label(resident_gender(resident))}, "
        f"{text['age']}, {text['job']}). Personality: "
        f"{str(text['personality'])[:HAKONIWA_PERSONALITY_PROMPT_MAX]}{pronoun} "
        f"Mood {resident['mood']}/100.{top_affinity} "
        f"Currently in the {area_name(resident.get('current_area'), 'en').lower()}."
        f"{_swap_note(state, resident, language)}{appearance_note(state, resident)}"
        f"{hint}\n"
        f"World rules:\n{active_rules_text(state, language)}"
    )
    return system_prompt, user_prompt


def transform_tags_prompts(instruction: str, base_tags: str) -> tuple[str, str]:
    system_prompt = (
        "You design tags for image generation. You are given English tags for a "
        "character's current look and an instruction (often in Japanese) that changes "
        "the look or outfit on the spot. Output the complete Danbooru-style tag list for "
        "the look after the change.\n"
        "Rules: always keep identity tags from the current tags (hair style, hair "
        "color, eye color, age, and the gender token such as 1girl / 1boy) unless the "
        "instruction explicitly changes them. If the instruction changes the sex or "
        "gender, replace the gender token accordingly. Replace clothing and items as "
        "instructed and drop the replaced clothing tags. For a partial change (only the "
        "hair, only an accessory), you may keep the untouched clothing tags.\n"
        f"Output all tags of the finished look, comma-separated, at most "
        f"{HAKONIWA_TAGS_MAX_COUNT} tags, on a single line, in English only. No "
        "explanation, preface or code fence."
    )
    user_prompt = f"Current tags: {base_tags}\nInstruction: {instruction}"
    return system_prompt, user_prompt


def appearance_tags_prompts(
    description: str, gender: str, *, dress: bool
) -> tuple[str, str]:
    token = "1boy" if gender == "male" else "1girl"
    scene = (
        "the formal dress the resident wears under the Rule of Dresses"
        if dress
        else "the resident's usual everyday look"
    )
    system_prompt = (
        "You design tags for image generation. You are given a description (often in "
        f"Japanese) of a resident's appearance. Output complete English Danbooru-style "
        f"tags for {scene}.\n"
        f"Rules: always include the gender token ({token}). Tag the hair style, hair "
        "color, eye color and other features, and the clothing. You may fill in "
        "details not written in the description with plausible, modest choices.\n"
        f"Output the tags comma-separated, at most {HAKONIWA_TAGS_MAX_COUNT} tags, on "
        "a single line. No explanation, preface or code fence."
    )
    return system_prompt, f"Appearance description: {description}"


def transform_reaction_prompts(
    state: dict[str, Any],
    target: dict[str, Any],
    change_text: str,
    bystanders: list[dict[str, Any]],
    language: str,
    *,
    nsfw: bool,
) -> tuple[str, str]:
    involved = [target, *bystanders]
    names = [resident_name(resident, language) for resident in involved]
    moods = ", ".join(f'"{name}": mood change (integer -10..10)' for name in names)
    system_prompt = (
        f"{WORLD_BRIEF}\n"
        "You are the narrator of this miniature world. One resident has just had their "
        "look changed on the spot by the player's power. Create exactly one short event "
        "showing that moment.\n"
        "Lines are the reactions of the transformed resident and the residents who were "
        "there, 1-4 lines in total; every speaker must be one of the involved residents. "
        "Depict honest reactions to the changed look such as surprise, embarrassment or "
        "admiration. Narration must not contain dialogue in quotation marks.\n"
        f"{gender_address_rules(language)}\n"
        f"{NO_MALE_ROMANCE_RULE}\n"
        f"{content_rule(nsfw)}\n"
        "Output only one JSON object in this format, with no preface or code fence:\n"
        '{"title": "short heading", "narration": "narration without dialogue, 1-2 sentences", '
        '"lines": [{"speaker": "resident name", "text": "one line"}], '
        f'"participants": [{", ".join(f"{chr(34)}{name}{chr(34)}" for name in names)}], '
        f'"mood_delta": {{{moods}}}}}\n'
        f"Write the title, narration and lines in {response_language(language)}."
    )
    involved_text = "; ".join(
        f"{resident_name(resident, language)} ({_gender_label(resident_gender(resident))}, "
        f"{str(resident_text(resident, language)['personality'])[:HAKONIWA_PERSONALITY_PROMPT_MAX]}"
        f"; First-person pronoun: {resident_text(resident, language)['pronoun']}"
        f"{_swap_note(state, resident, language)}"
        f"{appearance_note(state, resident)})"
        for resident in involved
    )
    target_name = resident_name(target, language)
    extra = ""
    confused = resident_gender(target) == "male" and (
        body_gender(state, target) == "female" or is_feminine_transformation(target)
    )
    if confused:
        extra += male_confusion_guidance(state, target, target_name) + "\n"
    transformation = target.get("transformation") or {}
    if is_risque_text(f"{transformation.get('tags', '')} {change_text}"):
        extra += RISQUE_REACTION_GUIDANCE.format(name=target_name) + "\n"
        if confused:
            extra += (
                f"On top of that, {target_name} is originally a man, and the "
                "bewilderment at the daring feminine look overlaps with the "
                "embarrassment and sways even harder.\n"
            )
    user_prompt = (
        f'Transformed resident: {target_name}. The instruction: "{change_text}".\n'
        f"Involved residents: {involved_text}.\n"
        f"{place_text(state, target.get('current_area'))}\n"
        f"{extra}"
        f"World rules:\n{active_rules_text(state, language)}"
    )
    return system_prompt, user_prompt


def scene_tags_prompts(
    event: dict[str, Any], names: dict[str, str], area_label: str
) -> tuple[str, str]:
    """出来事の山場を1枚の絵にするための、動作・表情・構図のタグを作らせる。"""
    system_prompt = (
        "You design tags for image generation. You are given an event from a "
        "miniature-world story. Pick the climactic moment of the event and output "
        "English Danbooru-style tags that describe only actions, facial expressions, "
        "the relationship between the characters, composition, lighting and mood. "
        "Do not include tags for appearance, hair, eyes, clothing, gender or the "
        "number of people.\n"
        "Output at most 12 tags, comma-separated, on a single line. No explanation, "
        "preface or code fence."
    )
    lines = "\n".join(
        f"{names.get(str(line.get('speaker')), '?')}: {line.get('text', '')}"
        for line in event.get("lines") or []
    )
    user_prompt = (
        f"Title: {event.get('title', '')}\n"
        f"Place: {area_label}\n"
        f"Narration: {event.get('narration', '')}\n"
        f"Lines:\n{lines or '(none)'}"
    )
    return system_prompt, user_prompt
