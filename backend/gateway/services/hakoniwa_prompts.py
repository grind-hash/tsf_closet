"""AI箱庭の生成プロンプト。

実装済みの掟・入れ替わり・衣装・変身・気分・親密度・場所と家具・記憶・適応と名残・
物語の弧・世界の違和感のみを扱い、英語の指示の末尾で出力言語を指定する。
"""

from __future__ import annotations

import json
from typing import Any

from ..consts.adventure_bgm import (
    HAKONIWA_BGM_SELECTION_RULES,
    get_hakoniwa_bgm_prompt_guide,
    get_hakoniwa_event_bgm_keys,
)
from ..consts.hakoniwa import (
    CUSTOM_RULE_PRIORITY_NOTE,
    DEFAULT_AREA_ID,
    HAKONIWA_AREA_MAP,
    HAKONIWA_CUSTOM_RULE_PROMPT_MAX,
    HAKONIWA_EVENT_LINES_RANGE,
    HAKONIWA_FURNITURE_MAP,
    HAKONIWA_LOCATION_MAP,
    HAKONIWA_LOCATIONS,
    HAKONIWA_PERSONALITY_PROMPT_MAX,
    HAKONIWA_REALITY_PROMPT_MAX,
    HAKONIWA_RECENT_EVENTS_CONTEXT,
    HAKONIWA_RECENT_NARRATION_SNIPPET,
    HAKONIWA_RULE_MAP,
    HAKONIWA_SCENE_ATTIRES,
    HAKONIWA_TAGS_SUGGESTED_COUNT,
    HAKONIWA_TRANSFORM_DESC_PROMPT_MAX,
    RULE_PRIORITY_NOTE,
    WORLD_BRIEF,
    event_location,
)
from ..consts.hakoniwa_play import (
    HAKONIWA_CHAT_HISTORY_CONTEXT,
    HAKONIWA_CHAT_REPLY_MAX,
    INTERVENTION_DIRECTIVES,
    TOUCH_PART_PROMPTS,
    TOUCH_TOLERANT_MOOD,
)
from ..consts.hakoniwa_story import CONFRONTATION_SYSTEM
from . import hakoniwa_play as play
from . import hakoniwa_story_text as story_text
from .hakoniwa_logic import (
    active_combo,
    active_custom_rules,
    active_memo_look,
    address_name,
    appearance_kind,
    body_gender,
    combo_tags,
    current_transformation,
    custom_rule,
    is_feminine_transformation,
    is_male_in_feminine_form,
    is_reality_look,
    look_rule_ids,
    male_body_pairs,
    realities,
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

# 指示した出来事の台詞の組み立て。日常向けの「次への含み」で締めると行為の手前で終わるため、
# 場面の途中から始めて山場で締める
DIRECTED_DIALOGUE_CRAFT_GUIDANCE = (
    "Build the dialogue as: an opening line spoken already in the middle of the "
    "ordered scene, the main exchange while carrying it out, back-and-forth "
    "reactions as it builds, and a closing line at its height. Do not trade short "
    "one-word replies; every line should carry a feeling or a piece of information."
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


# 掟・世界のメモ・住民の改変は「世界の常識の書き換え」。本人も周りも昔からそうだと受け止め、
# 不満や拒否は描かせない。残るのはかすかな違和感だけ(強さは違和感の段階の文脈に任せる)
REALITY_STANCE = (
    "These are rewrites of this world's common sense, not costumes or chores: "
    "everyone, including the person concerned, believes it has always been this "
    "way and lives by it naturally and willingly, as their own normal. Nobody "
    "refuses it, questions it out loud or complains about its practicality (hard "
    "to move in, cold, embarrassing to wear, a hassle). The only crack allowed is "
    "a faint, hard-to-name sense that something is off (a fleeting 'huh, was it "
    "always like this?' that passes at once), at most once in a scene."
)

REALITY_MALE_GUIDANCE = (
    "{name} is originally a man, but in this world's common sense this look is "
    "simply how he lives now, and he takes it as normal. The unfamiliarity of the "
    "body or the clothes (the hem, the draft, a different center of gravity or "
    "voice) may surface only as a faint sense that something is off that he cannot "
    "put into words, never as complaints, refusal or a wish to change back."
)

REALITY_RISQUE_GUIDANCE = (
    "{name}'s look is revealing and daring, but in this world it is normal for "
    "{name}: {name} carries it naturally and confidently, as the role demands, and "
    "others treat it as normal too (admiring glances or compliments are fine). At "
    "most a fleeting self-consciousness that feels oddly out of place may surface; "
    "no covering up or wanting to change."
)


def male_confusion_guidance(
    state: dict[str, Any], resident: dict[str, Any], name: str
) -> str:
    """本来は男性の住民への戸惑いの指示。体が女性になっているか、服だけかで書き分ける。

    適応が「慣れかけ」以上に進んでいれば、和らいだ戸惑いの指示にする。
    世界の常識の書き換えで決まった姿なら、受け入れたうえでのかすかな違和感だけにする。
    """
    if is_reality_look(state, resident):
        return REALITY_MALE_GUIDANCE.format(name=name)
    if story_text.male_guidance_is_softened(state, resident):
        return story_text.adapted_male_guidance(name)
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

DIRECTED_EVENT_PRIORITY_NOTE = (
    " This scene was ordered directly by the player, the unseen one who rewrites "
    "this world: "
    "the order decides the subject matter and tone of this scene, overriding the "
    "default calm, warm mood described above."
)

# 指示文で伏せ字に使われる記号(セッ〇ス など)。含まれていれば元の語として読ませる
DIRECTED_EVENT_MASK_CHARS = ("〇", "○", "●", "◯", "◎", "□", "■", "×", "✕", "*", "＊")

DIRECTED_EVENT_RETRY_NOTE = (
    "\n\n[Repeated, mandatory] Depicting what the player's instruction above orders, "
    "as the center of the scene, is an absolute condition. A scene that swaps it for "
    "something else or only talks about it is not acceptable. Output the scene in the "
    "specified JSON format, with every speaker and participant written exactly as "
    "the names given."
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
        "(a man in a woman's body still says his usual first person, and vice versa). "
        "The residents have lived together under one roof for a long time: in "
        "dialogue, call a housemate exactly as listed under 'Calls housemates' in the "
        "speaker's information, and never call a housemate by their full name."
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
    transformation = current_transformation(state, resident) or {}
    return is_risque_text(
        f"{transformation.get('tags', '')} {transformation.get('description', '')}"
    )


def _gender_label(gender: str) -> str:
    return "man" if gender == "male" else "woman"


def memo_section(state: dict[str, Any]) -> str:
    """プレイヤーの「世界のメモ」。世界の現実(常識の書き換え)として、掟より優先して載せる。

    空なら何も載せない。文体の指示が書かれていれば、それにも従わせる。
    """
    memo = play.world_memo(state)
    if not memo:
        return ""
    return (
        "\n\nThe reality of this world, set by the player (highest priority; it "
        "takes precedence over the world rules). Facts written here are this "
        "world's common sense from this moment on, and the text you write must "
        "follow them; style instructions written here apply to your writing too. "
        f"{REALITY_STANCE}\n"
        f"{memo}"
    )


def theme_section(state: dict[str, Any]) -> str:
    """プレイヤーが自由文で決めた実験テーマ。世界のメモと掟より下の、控えめな指示として載せる。"""
    text = play.theme_text(state)
    if not text:
        return ""
    return (
        "\n\nThe player's experiment theme for this world (what the player wants to "
        "watch unfold; let scenes lean toward it when it fits naturally, without "
        "forcing it. It does not need to appear in every scene; a gradual change over "
        "the days is better. The world rules and the player's instructions take "
        "precedence):\n"
        f"{text}"
    )


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
    synergies = play.active_synergies(state)
    if synergies:
        lines.append("Rule combinations in effect:")
        lines.extend(f"- {synergy['prompt']}" for synergy in synergies)
    if has_custom:
        lines.append(
            "(Player-written rules are absolute laws of this world and every "
            "resident lives by them. Show concretely, through actions and lines, how "
            "each rule appears in daily life. Do not swap the rule's subject for a "
            f"harmless complaint such as clothes being inconvenient. {REALITY_STANCE})"
        )
    return "\n".join(lines)


def current_appearance_summary(
    state: dict[str, Any], resident: dict[str, Any]
) -> str | None:
    kind = appearance_kind(state, resident)
    if kind == "transform":
        transformation = current_transformation(state, resident) or {}
        description = str(transformation.get("description") or "")[
            :HAKONIWA_TRANSFORM_DESC_PROMPT_MAX
        ]
        if transformation.get("kind") == "reality":
            return (
                f"the look that this world's common sense gives them ('{description}')"
            )
        return f"a look transformed into: '{description}'"
    if kind == "combo":
        combo = active_combo(state) or {"rule_ids": [], "includes_dress": False}
        names = " and ".join(f"'{rule['name']}'" for rule in _look_rules(state, kind))
        dress = " plus the dress rule" if combo["includes_dress"] else ""
        tags = combo_tags(state, combo["rule_ids"])[:HAKONIWA_CUSTOM_RULE_PROMPT_MAX]
        return f"a combined look set by the rules {names}{dress}{_tags_note(tags)}"
    if kind == "rule":
        rules = _look_rules(state, kind)
        if rules:
            tags = str(rules[-1].get("appearance_tags") or "")
            return (
                f"a look set by the rule '{rules[-1]['name']}'"
                f"{_tags_note(tags[:HAKONIWA_CUSTOM_RULE_PROMPT_MAX])}"
            )
    if kind == "memo":
        tags = str((active_memo_look(state) or {}).get("tags") or "")
        return (
            "the look that this world's reality (the player's memo) gives everyone"
            f"{_tags_note(tags[:HAKONIWA_CUSTOM_RULE_PROMPT_MAX])}"
        )
    if kind == "dress":
        return "wearing a dress"
    return None


def _tags_note(tags: str) -> str:
    """姿の説明に添えるタグ(体の性別だけを変える掟ではタグが無い)。"""
    return f" ({tags})" if tags else ""


def _look_rules(state: dict[str, Any], kind: str | None) -> list[dict[str, Any]]:
    """いまの掟の姿(combo / rule)を決めている自作の掟。"""
    if kind == "combo":
        combo = active_combo(state)
        ids = combo["rule_ids"] if combo else []
    elif kind == "rule":
        ids = look_rule_ids(state)[-1:]
    else:
        ids = []
    rules = [custom_rule(state, rule_id) for rule_id in ids]
    return [rule for rule in rules if rule is not None]


def look_rule_link_text(state: dict[str, Any], kind: str | None) -> str:
    """掟の姿を、その姿を定めた掟の本文に結びつける一文(掟の姿でなければ空)。"""
    rules = _look_rules(state, kind)
    if not rules:
        return ""
    texts = "; ".join(
        f"'{rule['name']}': {str(rule['text'])[:HAKONIWA_CUSTOM_RULE_PROMPT_MAX]}"
        for rule in rules
    )
    return (
        f" These looks are set by the world rules ({texts}); in this world the look "
        "is simply what the rule makes normal."
    )


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
    if resident_gender(resident) == "female" and body_gender(state, resident) == "male":
        return f" Currently {summary}; originally a woman, now in a man's body."
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
    own = resident_text(resident, language)["pronoun"]
    theirs = resident_text(partner, language)["pronoun"]
    if own and theirs and own != theirs:
        # 体に合わせて一人称を変えてしまう癖があるので、使う語と使わない語を名指しする
        note += (
            f" Still says their own first person '{own}', never "
            f"{resident_name(partner, language)}'s '{theirs}'."
        )
    return note


def address_text(
    state: dict[str, Any],
    resident: dict[str, Any],
    language: str,
    among: list[dict[str, Any]] | None = None,
) -> str:
    """住民がほかの住民をふだん何と呼ぶか(台詞で使う呼び方の一覧)。

    among を渡すと、その住民たちへの呼び方だけにする(場面に居合わせる住民など)。
    """
    open_quote, close_quote = ("「", "」") if language == "ja" else ('"', '"')
    pairs = [
        f"{resident_name(other, language)} -> "
        f"{open_quote}{address_name(resident, other, language)}{close_quote}"
        for other in (state["residents"] if among is None else among)
        if other["id"] != resident["id"]
    ]
    return f" Calls housemates: {', '.join(pairs)}." if pairs else ""


def reality_note(resident: dict[str, Any], language: str) -> str:
    """住民の改変(その住民についての世界の常識)を、住民の説明に添える一文。"""
    items = realities(resident)
    if not items:
        return ""
    name = resident_name(resident, language)
    facts = "; ".join(
        f"'{str(item['text'])[:HAKONIWA_REALITY_PROMPT_MAX]}'" for item in items
    )
    return (
        f" This world's common sense about {name} (rewritten by the player; "
        f"everyone, including {name}, takes it as having always been true, and "
        f"nobody questions or complains about it): {facts}."
    )


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
            f"{address_text(state, resident, language)}"
            f"{_swap_note(state, resident, language)}"
            f"{appearance_note(state, resident)}"
            f"{reality_note(resident, language)}"
            f"{story_text.story_notes(state, resident, language)}"
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
            text += "\n" + male_confusion_guidance(
                state, resident, resident_name(resident, language)
            )
    if any(story_text.adaptation_stage(state, item) for item in (a, b)):
        text += (
            "\nHow strongly they react follows each one's adaptation stage given "
            "below; once they are used to it, show familiarity rather than shock."
        )
    return text


def appearance_focus_text(
    state: dict[str, Any], group: tuple[dict[str, Any], ...], language: str
) -> str:
    """いまの姿を出来事に出させる指示。

    変身・ドレスの姿には反応(照れ・戸惑い)を、世界の常識の書き換え(掟・メモ・改変)で
    決まった姿には、その姿で自然に暮らす様子を描かせる。
    """
    targets = []
    reality_targets = []
    confused = []
    for resident in group:
        kind = appearance_kind(state, resident)
        if kind is None:
            continue
        if kind == "dress" and resident_gender(resident) != "male":
            continue
        summary = current_appearance_summary(state, resident)
        name = resident_name(resident, language)
        if is_reality_look(state, resident):
            reality_targets.append(f"{name} ({summary})")
        else:
            targets.append(f"{name} ({summary})")
        if is_male_in_feminine_form(state, resident):
            confused.append((resident, name))
    if not targets and not reality_targets:
        return ""
    text = ""
    if targets:
        text += _reaction_focus_text(group, targets)
    if reality_targets:
        text += (
            "\n\n[Important: always show the current look as part of everyday life]\n"
            f"Among the main characters, {', '.join(reality_targets)} look the way "
            "this world's common sense now says. Do not write the day as if the look "
            "did not exist: show them living in that look and in the role it implies, "
            "concretely in both actions and lines (for example, gravure idols do photo "
            "shoots, strike poses and care about how they look on camera), and mention "
            "the look concretely in the narration too. Others treat it as perfectly "
            f"normal; impressions and compliments are fine. {REALITY_STANCE}"
            f"{look_rule_link_text(state, appearance_kind(state, group[0]))}"
        )
    for resident, name in confused:
        text += "\n" + male_confusion_guidance(state, resident, name)
    return text


def _reaction_focus_text(group: tuple[dict[str, Any], ...], targets: list[str]) -> str:
    """変身・ドレスの姿への反応(照れ・戸惑い)を必ず入れさせる指示。"""
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
    return (
        "\n\n[Important: always include reactions to the current look]\n"
        f"Among the main characters, {', '.join(targets)} look different from usual. "
        f"Do not write the day as if the look did not exist. {clause}"
    )


def risque_focus_text(
    state: dict[str, Any], group: tuple[dict[str, Any], ...], language: str
) -> str:
    lines = []
    for resident in group:
        if not appearance_is_risque(state, resident):
            continue
        name = resident_name(resident, language)
        if is_reality_look(state, resident):
            # 世界の常識で決まった際どい姿は、照れではなく当たり前のこととして描く
            lines.append(REALITY_RISQUE_GUIDANCE.format(name=name))
            continue
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


def directed_event_focus_text(
    state: dict[str, Any],
    group: tuple[dict[str, Any], ...],
    instruction: str,
    language: str,
    *,
    nsfw: bool,
) -> str:
    """書き手(プレイヤー)が指示して起こす出来事の指示。自作の掟の焦点と同じ強さで書く。"""
    adult = (
        " If the instruction names a sexual act between adults, the scene opens in "
        "the middle of that act: the narration describes them already doing it, "
        "explicitly and faithfully to the instruction's wording (bodies, how they are "
        "joined, sensations), and every line is spoken while doing it (voices, "
        "sensations, words of affection, how the current body feels). Asking whether "
        "the other is ready, talking about the body or the relationship, or a line "
        "announcing that they will start does not count as the act. A scene that "
        "ends just before the act, skips to afterwards, fades out or goes to sleep, "
        "or stops at kissing, touching or undressing does not satisfy the order."
        if nsfw
        else " Keep it non-explicit even if the instruction touches on adult themes: "
        "no sexual acts or nudity; express such themes through reactions and emotions "
        "only."
    )
    male = "".join(
        f" {resident_name(a, language)} and {resident_name(b, language)} both "
        "currently have male bodies: never depict romantic or sexual feelings or acts "
        "between the two of them. This limit takes precedence over the player's "
        "order: if the order asks for romance or intimacy between them, do not carry "
        "out that part at all, not even off-screen, as a joke or as a greeting (no "
        "kiss, embrace or caress), and do not hint at it (no leaning in, getting too "
        "close, flustered reactions to closeness, romantic tension or lingering "
        "looks). Keep them friends and give them a different part in the scene."
        for a, b in male_body_pairs(state, group)
    )
    masked = (
        "Some words in the order are hidden with symbols such as 〇 (for example "
        "セッ〇ス means セックス, sex): read each as the plain word it stands for and "
        "carry it out as such.\n"
        if any(mark in instruction for mark in DIRECTED_EVENT_MASK_CHARS)
        else ""
    )
    return (
        "\n\n[Most important: the scene the player has ordered]\n"
        "The player, the unseen one who rewrites this world, has directly ordered "
        "this event:\n"
        f'"{instruction}"\n'
        f"{masked}"
        "The order has the same force as a player-written rule: it simply happens in "
        "this world. Every main character goes along with it willingly, of their own "
        "accord; never depict anyone being forced, pressured or coerced, and never have "
        "one character push past another's refusal. Each still reacts in character "
        "(embarrassment, nervousness, delight). The order is a stage direction that the "
        "residents never hear: never quote or restate it in the lines, and never have "
        "them discuss whether to do it, what it means or who arranged it. The decision "
        "is already made before the scene opens, and an order to go somewhere opens "
        "with them already there. Do not spend the scene on build-up: "
        "what the instruction describes is already under way when the scene opens or "
        "begins within the first two lines, and most of the narration and lines depict "
        "actually carrying it out. Make it a scene that depicts the act or situation "
        "itself, not a scene that only talks about it or leads up to it. Replacing it "
        "with a harmless topic, stopping just before it, or blurring it with metaphors "
        "is forbidden. The premise and circumstances given above (the world's "
        "strangeness, getting used to a new body or look) only color how they feel "
        "during it and never replace it. "
        "Every main character appears in their current look and body "
        "exactly as listed under Residents (transformation, swapped body, rule look, "
        "dress); depict the scene in those bodies and never revert anyone to their "
        f"original look.{adult}{male}"
    )


def directed_body_color_text(
    state: dict[str, Any], group: tuple[dict[str, Any], ...], language: str
) -> str:
    """指示した出来事で、いまの姿・体への気持ちを場面の色付けとしてだけ渡す。

    日常の出来事向けの焦点(姿・入れ替わりへの反応や調査を主題にする指示)は、
    指示した場面を乗っ取るため、指示した出来事では代わりにこれだけを載せる。
    """
    lines = []
    swap = _swap_members(state, group)
    if swap is not None:
        a, b = swap
        lines.append(
            f"{resident_name(a, language)} and {resident_name(b, language)} have "
            "swapped bodies."
        )
    for resident in group:
        name = resident_name(resident, language)
        summary = current_appearance_summary(state, resident)
        if is_male_in_feminine_form(state, resident):
            look = f" ({summary})" if summary else ""
            lines.append(f"{name} is originally a man, now in a woman's body{look}.")
        elif summary:
            lines.append(f"{name}: {summary}.")
    if not lines:
        return ""
    return (
        "\n\n[Their current bodies: color only]\n"
        + "\n".join(lines)
        + "\nLet how each of them feels in that body (unfamiliar sensations, "
        "embarrassment, delight, following each one's adaptation stage under "
        "Residents) show as part of the ordered scene itself, such as how unfamiliar "
        "the body's sensations feel while doing it. Do not spend lines asking about "
        "or discussing the body; it colors the ordered scene and never delays, "
        "interrupts or replaces it."
    )


def _event_schema(
    group: tuple[dict[str, Any], ...], language: str, *, location_first: bool = False
) -> str:
    """出来事の JSON の形。location_first は場所を先に決めさせる(指示した出来事)。"""
    names = [resident_name(resident, language) for resident in group]
    lo, hi = HAKONIWA_EVENT_LINES_RANGE[min(len(group), 3)]
    participants = ", ".join(f'"{name}"' for name in names)
    moods = ", ".join(f'"{name}": mood change (integer -20..20)' for name in names)
    affinity = (
        ', "affinity_delta": change in their relationship (integer -15..15)'
        if len(group) >= 2
        else ""
    )
    location = '"location": "id of the place where it happens (see Place)", '
    return (
        "{" + (location if location_first else "") + '"title": "short heading", '
        '"narration": "narration without any dialogue, 2-3 sentences", '
        '"lines": [{"speaker": "name of the speaking resident", "text": "one line of dialogue"}], '
        f'"participants": [{participants}], '
        + ("" if location_first else location)
        + f'"mood_delta": {{{moods}}}{affinity}, {_bgm_field()}}}\n'
        f"Write {lo}-{hi} lines.\n{bgm_guide()}"
    )


def _bgm_field() -> str:
    """出来事の JSON の bgm の欄(場面を書いたあとに選ばせるため末尾に置く)。"""
    return f'"bgm": "{"|".join(get_hakoniwa_event_bgm_keys())}"'


def bgm_guide() -> str:
    """出来事を見せる間の BGM の選び方(選べる曲と、重要度を物語の進み具合で測る方針)。"""
    return (
        f"bgm is the background music while this scene is shown, one of: "
        f"{get_hakoniwa_bgm_prompt_guide()}. {HAKONIWA_BGM_SELECTION_RULES} "
        "Write only the key, never a filename."
    )


def event_system_prompt(
    group: tuple[dict[str, Any], ...],
    state: dict[str, Any],
    language: str,
    *,
    nsfw: bool,
    directed: bool = False,
) -> str:
    """出来事の生成の役割と形式。directed は書き手が指示した出来事(指示を雰囲気より優先する)。"""
    # 指示した出来事は下宿の外(ホテル・海辺など)でも起きる
    where = "" if directed else " at the boarding house"
    if len(group) == 1:
        shape = (
            f"Create exactly one event{where} with this single resident "
            "as the main character. The lines are the character's own monologue or "
            "mutterings, and every speaker must be that character. Other residents do "
            "not appear (mentioning their names in narration is fine). Do not output an "
            "affinity change. In a one-person scene, read the back-and-forth part of the "
            "dialogue structure as a flow of monologue and reflection."
        )
    elif len(group) >= 3:
        shape = (
            f"Create exactly one event{where} with these three residents "
            "as the main characters. Every speaker must be one of them. Give each of the "
            "three a line or a memorable role; do not let it become one person's "
            "conversation. affinity_delta is the change in the three's relationship as "
            "a whole."
        )
    else:
        shape = (
            f"Create exactly one event{where} with these two residents as "
            "the main characters. Every speaker must be one of them."
        )
    brief = world_brief(state) + (DIRECTED_EVENT_PRIORITY_NOTE if directed else "")
    return (
        f"{brief}\n"
        "You are the narrator of this miniature world.\n"
        f"{shape}\n"
        f"{DIRECTED_DIALOGUE_CRAFT_GUIDANCE if directed else DIALOGUE_CRAFT_GUIDANCE}\n"
        "Narration must not contain dialogue in quotation marks. Speakers and "
        "participants must be written exactly as the names given.\n"
        f"{gender_address_rules(language)}\n"
        f"{NO_MALE_ROMANCE_RULE}\n"
        f"{content_rule(nsfw)}\n"
        "Output only one JSON object in this format, with no preface or code fence:\n"
        f"{_event_schema(group, language, location_first=directed)}\n"
        f"Write the title, narration and lines in {response_language(language)}."
    )


def area_name(area_id: str | None, language: str) -> str:
    area = (
        HAKONIWA_AREA_MAP.get(str(area_id or "")) or HAKONIWA_AREA_MAP[DEFAULT_AREA_ID]
    )
    return area["name"]["ja" if language == "ja" else "en"]


def place_text(state: dict[str, Any], area_id: str | None) -> str:
    """出来事の場所の情景と、そこに置かれた家具(場面に合えば顔を出す程度)。

    area_id はエリアのほか、エリアの外の場所(浴室・商店街など)の id でもよい。
    """
    area = (
        HAKONIWA_LOCATION_MAP.get(str(area_id or ""))
        or HAKONIWA_AREA_MAP[DEFAULT_AREA_ID]
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


def location_choice_text(place_id: str, *, fixed: bool) -> str:
    """出来事の場所(location)の選び方。fixed ならプレイヤーが決めた場所のまま。"""
    if fixed:
        return f'\nSet "location" to "{place_id}".'
    options = "; ".join(
        f"{location['id']}: {location['scene']}"
        for location in HAKONIWA_LOCATIONS
        if location["id"] != place_id
    )
    return (
        f'\nUsually set "location" to "{place_id}" (the place above). Only when '
        "the event clearly happens somewhere else (for example taking a shower or "
        "going shopping), set it to one of these ids instead and set the scene "
        f"there: {options}."
    )


def directed_place_text(place_id: str, *, continuing: bool = False) -> str:
    """指示した出来事で場所をおまかせにしたときの場所の決め方。

    いまいる場所の情景を先に書くと、指示が別の場所を示しても場面がそこに留まるため、
    場所は指示から決めさせ、いまいる場所は指示が場所を示さないときの既定として並べるだけにする。
    continuing は続きの出来事(前の場面の場所に留まるのが既定で、指示が移すときだけ移る)。
    """
    here = (
        "where the previous scene took place"
        if continuing
        else "where the main character is now"
    )
    options = "; ".join(
        f"{location['id']}: {location['scene']}"
        + (f" ({here})" if location["id"] == place_id else "")
        for location in HAKONIWA_LOCATIONS
    )
    if continuing:
        return (
            f'Place: the previous scene took place at "{place_id}". This event '
            f'continues there: set "location" to "{place_id}" and keep the scene '
            "there, unless the order clearly moves them to a different place (then "
            'set "location" to that id and open the scene with them already there, '
            "never on the way; moving to another room counts, so a bathroom next to "
            'the room they were in is "bathroom"). Places (id: description): '
            f"{options}. When the place "
            "the order names is not among these (a school, an office, a train and so "
            "on), still set the scene at that place as the order says, and set "
            '"location" to the closest id. Weave in the atmosphere and small details '
            "of the place where it takes place."
        )
    return (
        "Place: not fixed. First decide from the order where the ordered scene takes "
        'place, set "location" to that id, and set the whole scene there from the '
        "first line. When the order names or implies a place (a bath or shower, a "
        "bed, a hotel, shopping, a cafe, the beach and so on), use that place. An "
        "order to go somewhere takes place at the destination: the scene opens with "
        "them already there, never at the starting point or on the way. Only when "
        f'the order implies no place, use "{place_id}". Places (id: description): '
        f"{options}. When the place the order names is not among these (a school, an "
        "office, a train and so on), still set the scene at that place as the order "
        'says, and set "location" to the closest id. Weave in the atmosphere and '
        "small details of the place where it takes place."
    )


def previous_scene_text(
    state: dict[str, Any], event: dict[str, Any], language: str
) -> str:
    """続きの出来事に渡す直前の場面(地の文と台詞の全文)。

    台詞は出力と同じ JSON の形で渡す(「」で囲んで渡すと、生成が JSON の text にも
    「」を書き写して壊れる)。
    """
    names = {
        resident["id"]: resident_name(resident, language)
        for resident in state["residents"]
    }
    lines = "\n".join(
        json.dumps(
            {
                "speaker": names.get(
                    str(line.get("speaker")), str(line.get("speaker"))
                ),
                "text": str(line.get("text") or ""),
            },
            ensure_ascii=False,
        )
        for line in event.get("lines") or []
    )
    order = (
        f'The order it followed: "{event["instruction"]}"\n'
        if event.get("instruction")
        else ""
    )
    return (
        "\n\n[The previous scene: this event continues directly from it]\n"
        f"Title: {event.get('title') or ''}\n"
        f"{order}"
        f"Narration: {event.get('narration') or ''}\n"
        f"Lines:\n{lines}\n"
        "This event is its direct continuation: the same people, moments later, in "
        "the state the previous scene ended in (place, clothes or lack of them, "
        "position, mood). Do not restart or re-introduce the situation, and do not "
        "repeat what was already shown or said; pick up where it left off and carry "
        "the scene forward as the new order says. Give it a new title."
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
    arc_focus_id: str | None = None,
    arc_climax: bool = False,
    intervention: str | None = None,
    include_theme: bool = True,
    directed_instruction: str | None = None,
    location_id: str | None = None,
    continues_event: dict[str, Any] | None = None,
) -> str:
    """出来事の生成の指示。include_theme は自由文の実験テーマを載せるか(1日1件に絞る)。

    directed_instruction は書き手が指示して起こす出来事の指示文。あれば最優先の焦点にする。
    location_id はプレイヤーが決めた場所。無ければ area_id を既定に、内容に合う場所を選ばせる。
    continues_event は続きを指示した元の出来事。直前の場面として載せ、場所の既定にもする。
    """
    names = [resident_name(resident, language) for resident in group]
    if len(group) == 1 and directed_instruction:
        lead = f"Main character: {names[0]} (the only main character)."
    elif len(group) == 1:
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
    previous = ""
    if directed_instruction:
        if continues_event:
            lead += (
                "\nThe player has ordered how the previous scene continues: "
                f'"{directed_instruction}"'
            )
            previous = previous_scene_text(state, continues_event, language)
        else:
            lead += f'\nThe scene the player has ordered: "{directed_instruction}"'
        focus = directed_event_focus_text(
            state, group, directed_instruction, language, nsfw=nsfw
        )
        variety = "Make the event feel like part of their accumulating relationship."
    else:
        focus = (
            custom_rule_focus_text(state, rule_focus_rule_id, nsfw)
            if rule_focus_rule_id
            else ""
        )
        variety = (
            "Avoid topics and developments similar to the recent events, and make the "
            "event feel like part of their accumulating relationship."
        )
    fixed = location_id if location_id in HAKONIWA_LOCATION_MAP else None
    continuing = bool(directed_instruction and continues_event)
    if fixed:
        place_id = fixed
    elif continuing:
        place_id = event_location(continues_event or {})["id"]
    else:
        place_id = area_id if area_id in HAKONIWA_AREA_MAP else DEFAULT_AREA_ID
    if directed_instruction and fixed is None:
        place = directed_place_text(place_id, continuing=continuing)
    else:
        place = place_text(state, place_id) + location_choice_text(
            place_id, fixed=fixed is not None
        )
    if directed_instruction:
        # 日常向けの焦点(姿・入れ替わりへの反応や調査を主題にする指示)は指示した場面を
        # 乗っ取るため、いまの体への気持ちを色付けとして渡すだけにする
        circumstances = directed_body_color_text(state, group, language)
    else:
        circumstances = (
            f"{swap_focus_text(state, group, language)}"
            f"{appearance_focus_text(state, group, language)}"
            f"{story_text.adaptation_focus_text(state, group, language)}"
            f"{story_text.world_adaptation_focus_text(state, group, language)}"
            f"{risque_focus_text(state, group, language)}"
            f"{story_text.investigation_focus_text(state, group, language)}"
            f"{story_text.arc_focus_text(state, arc_focus_id, arc_climax, language)}"
        )
    return (
        f"Today is day {state['day']} at Stardust House.\n"
        f"{lead}\n"
        f"{place}"
        f"{story_text.dissonance_context_text(state)}"
        f"{story_text.acknowledged_player_rule(state, language)}\n\n"
        f"World rules:\n{active_rules_text(state, language)}\n\n"
        f"Residents:\n{residents_text(state, language)}\n\n"
        f"Recent events:\n{recent_events_text(state)}"
        f"{story_text.memories_context_text(state, group, language)}"
        f"{story_text.arcs_context_text(state, language)}\n"
        f"{others}"
        f"{variety}"
        f"{previous}"
        f"{circumstances}"
        f"{focus}"
        f"{INTERVENTION_DIRECTIVES.get(str(intervention or ''), '')}"
        f"{theme_section(state) if include_theme else ''}{memo_section(state)}"
    )


def greeting_prompts(
    state: dict[str, Any], resident: dict[str, Any], language: str, *, nsfw: bool
) -> tuple[str, str]:
    system_prompt = (
        f"{WORLD_BRIEF}\n"
        "You are this resident of the miniature world. The player has just said hello. "
        "Reply with one short line in character (1-2 sentences, at most 60 Japanese "
        "characters or 30 English words). Output only the spoken words: no narration, "
        "headings, quotation marks or explanations. If rules are active, always reflect "
        "their speech style and premise.\n"
        f"{gender_address_rules(language)}\n"
        f"{story_text.player_address_rule(state, language, direct=True)}\n"
        f"{content_rule(nsfw)}\n"
        f"Reply in {response_language(language)}."
    )
    user_prompt = (
        f"{resident_profile_text(state, resident, language)}"
        f"{look_hint(state, resident)}"
        f"{story_text.dissonance_context_text(state)}\n"
        f"World rules:\n{active_rules_text(state, language)}"
        f"{story_text.memories_context_text(state, [resident], language)}"
        f"{theme_section(state)}{memo_section(state)}"
    )
    return system_prompt, user_prompt


def resident_profile_text(
    state: dict[str, Any], resident: dict[str, Any], language: str
) -> str:
    """一言・タッチ・会話で使う「あなたは〜」の住民の説明(性格・気分・関係・場所・姿)。"""
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
    pronoun = f" First-person pronoun: {text['pronoun']}." if text["pronoun"] else ""
    return (
        f"You are {text['name']} ({_gender_label(resident_gender(resident))}, "
        f"{text['age']}, {text['job']}). Personality: "
        f"{str(text['personality'])[:HAKONIWA_PERSONALITY_PROMPT_MAX]}{pronoun} "
        f"Mood {resident['mood']}/100.{top_affinity} "
        f"Currently in the {area_name(resident.get('current_area'), 'en').lower()}."
        f"{address_text(state, resident, language)}"
        f"{_swap_note(state, resident, language)}{appearance_note(state, resident)}"
        f"{reality_note(resident, language)}"
        f"{story_text.story_notes(state, resident, language)}"
    )


def look_hint(state: dict[str, Any], resident: dict[str, Any]) -> str:
    """いまの姿に触れてよい旨と、男性の戸惑い・際どい姿の羞恥の指示。"""
    hint = ""
    if is_reality_look(state, resident):
        return (
            " The line may touch on the character's current look, which is simply "
            "normal in this world (no complaints or embarrassment about it; at most "
            "a faint, fleeting sense that something is off)."
        )
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
    return hint


def touch_prompts(
    state: dict[str, Any],
    resident: dict[str, Any],
    part: str,
    language: str,
    *,
    nsfw: bool,
) -> tuple[str, str]:
    """プレイヤーに体を触られた住民の、その場の一言。"""
    hints = []
    if part == "head":
        hints.append("React to having your head patted, with embarrassment or relief.")
    else:
        hints.append(
            "React to being touched suddenly, in character: surprise, embarrassment, a "
            "rebuke, or, depending on the mood, a shy acceptance."
        )
    if appearance_is_risque(state, resident):
        hints.append(
            "Your look is revealing and daring; let the embarrassment and the extra "
            "awareness of being looked at and touched show."
        )
    if is_male_in_feminine_form(state, resident):
        hints.append(
            "You are originally a man in a feminine form; let bewilderment, confusion "
            "and embarrassment at being touched in this form show strongly."
        )
    mood = int(resident.get("mood") or 50)
    if mood >= TOUCH_TOLERANT_MOOD:
        hints.append("Your mood is good, so you can take it lightly or jokingly.")
    elif mood < 40:
        hints.append("Your mood is not good, so the reaction tends to be prickly.")
    system_prompt = (
        f"{world_brief(state)}\n"
        "You are this resident of the miniature world. The player (the one who watches "
        "over and rewrites this world) has just touched you. Reply with one line of "
        "dialogue in character (1-2 sentences, at most 80 Japanese characters or 40 "
        "English words). Output only the spoken words: no narration, headings, "
        "quotation marks or explanations. If rules are active, reflect their premise.\n"
        f"{gender_address_rules(language)}\n"
        f"{story_text.player_address_rule(state, language, direct=True)}\n"
        f"{content_rule(nsfw)}\n"
        f"Reply in {response_language(language)}."
    )
    user_prompt = (
        f"{resident_profile_text(state, resident, language)}\n"
        f"Just now, you {TOUCH_PART_PROMPTS[part]}. {' '.join(hints)}"
        f"{story_text.dissonance_context_text(state)}\n"
        f"World rules:\n{active_rules_text(state, language)}"
        f"{memo_section(state)}"
    )
    return system_prompt, user_prompt


def chat_reply_prompts(
    state: dict[str, Any],
    resident: dict[str, Any],
    history: list[dict[str, Any]],
    message: str,
    language: str,
    *,
    nsfw: bool,
) -> tuple[str, str]:
    """箱庭の中で、住民本人としてプレイヤーと会話する。"""
    name = resident_name(resident, language)
    lines = []
    for entry in history[-HAKONIWA_CHAT_HISTORY_CONTEXT:]:
        role = entry.get("role")
        if role == "player":
            speaker = "Player"
        elif role == "resident":
            speaker = name
        else:
            speaker = "(system)"
        lines.append(f"{speaker}: {str(entry.get('text') or '')[:300]}")
    history_text = "\n".join(lines) if lines else "(no conversation yet)"
    limit = (
        HAKONIWA_CHAT_REPLY_MAX // 2 if language == "ja" else HAKONIWA_CHAT_REPLY_MAX
    )
    system_prompt = (
        f"{world_brief(state)}\n"
        "You are this resident of the miniature world, talking freely with the player "
        "(the one who watches over and rewrites this world). Reply to the player's "
        "latest message with a natural reply in character, 1-3 sentences "
        f"(at most {limit} characters). Output only the spoken words: no narration, "
        "headings, quotation marks, lists or meta explanations. Reflect the active "
        "rules, your current look, mood and relationships, and continue the flow of the "
        "recent conversation. Do not pretend to know things you do not know; keep the "
        "everyday feel of a resident.\n"
        f"{gender_address_rules(language)}\n"
        f"{story_text.player_address_rule(state, language, direct=True)}\n"
        f"{content_rule(nsfw)}\n"
        f"Reply in {response_language(language)}."
    )
    user_prompt = (
        f"{resident_profile_text(state, resident, language)}"
        f"{look_hint(state, resident)}"
        f"{story_text.dissonance_context_text(state)}\n"
        f"World rules:\n{active_rules_text(state, language)}"
        f"{story_text.memories_context_text(state, [resident], language)}"
        f"{theme_section(state)}{memo_section(state)}\n\n"
        f"Recent conversation:\n{history_text}\n\n"
        f"The player's latest message: {message}"
    )
    return system_prompt, user_prompt


def alteration_prompts(
    message: str, resident_label: str, current_look: str
) -> tuple[str, str]:
    """会話文が、姿をその場で変える(または元に戻す)指示かどうかを分類させる。"""
    system_prompt = (
        "You are an input classifier for a game. Decide whether the player's message "
        "to a resident is an instruction to change that resident's look or clothing "
        "on the spot, and output only one JSON object: "
        '{"action": "transform" | "clear" | "none", "instruction": "the change to make"}.\n'
        "Impressions, questions, wishes and mentioning clothes as a topic are none. "
        "Only imperative instructions that change the look or outfit are transform; an "
        "instruction to go back to the usual look is clear. No explanation."
    )
    user_prompt = (
        f"Resident: {resident_label}. Current look: {current_look}.\n"
        f"Player's message: {message}"
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
        "Output all tags of the finished look, comma-separated, on a single line, "
        "in English only. Do not drop current tags that the instruction leaves "
        "untouched just to shorten the list. No explanation, preface or code fence."
    )
    user_prompt = f"Current tags: {base_tags}\nInstruction: {instruction}"
    return system_prompt, user_prompt


def memo_look_prompts(memo: str) -> tuple[str, str]:
    """世界のメモが住民全員の見た目を変えるかを判断させ、変えるなら見た目のタグにさせる。"""
    system_prompt = (
        "You read the player's memo for a miniature world. The memo rewrites the "
        "world's reality (its common sense) and may also contain style instructions "
        "for the writing. Decide whether it changes how every resident looks: their "
        "clothing, accessories and items, visible additions such as animal ears, or "
        "their sex. A role or occupation whose look is obvious counts (for example, "
        "everyone being gravure idols means swimsuits such as a bikini; everyone "
        "being maids means a maid outfit). Personality, relationships, speech, "
        "events, writing style, or a change for only some of the residents do not "
        "count.\n"
        "If it changes the look, create Danbooru-style tags for that change only: "
        "each item once, no extra clothing or decorations that the memo does not "
        "state or clearly imply. Tag hair, eyes or body features only when "
        "explicitly stated. Never include tags for sex, gender or the number of "
        "people (1girl, 1boy, woman, man, female, male, solo); set body_gender "
        "instead, and only when the memo changes everyone's sex.\n"
        "Output only one JSON object, with no explanation or code fence: "
        '{"changes_look": true or false, "appearance_tags": "comma-separated '
        'English tags, or an empty string", "body_gender": "female" | "male" | '
        '"keep"}'
    )
    return system_prompt, f"Memo:\n{memo}"


def rule_look_tags_prompts(name: str, text: str, description: str) -> tuple[str, str]:
    """自作の掟が住民の見た目に与える変化を、服装・装いのタグにさせる。"""
    system_prompt = (
        "You design tags for image generation. From a world rule of a miniature "
        "world (its name, its text and, if given, a description of the look), create "
        "Danbooru-style tags that describe how the rule changes every resident's "
        "appearance: clothing, accessories and items, or visible additions such as "
        "animal ears. If a look description is given, follow it first.\n"
        "Tag only what the rule or the description states, each item once. Do not "
        "add clothing, accessories, decorations or fashion styles that are not "
        "written (no extra dresses, ribbons, frills or styles such as lolita "
        "fashion), and do not tag one garment twice with different words. Tag hair, "
        "eyes or body features only when they are explicitly stated (for example "
        "long hair); otherwise each resident keeps their own. Never include tags "
        "for sex, gender or the number of people (1girl, 1boy, woman, man, female, "
        "male, solo), because a change of sex is set separately. Output the tags "
        "comma-separated, on a single line, in English only. No Japanese, "
        "explanation, preface or code fence."
    )
    user_prompt = f"Rule name: {name}\nRule text: {text}"
    if description:
        user_prompt += f"\nLook description: {description}"
    return system_prompt, user_prompt


_BODY_CHANGE_INSTRUCTIONS = {
    "female": (
        " The rule also turns everyone's body into a woman's: use the gender token "
        "1girl instead of 1boy and drop male-only features such as facial hair."
    ),
    "male": (
        " The rule also turns everyone's body into a man's: use the gender token "
        "1boy instead of 1girl and drop female-only features such as breasts."
    ),
}


def rule_look_instruction(
    look_tags: str, *, dress: bool = False, body_gender: str | None = None
) -> str:
    """住民のいまのタグを、掟の姿のタグへ書き換えさせる指示(変身と同じ変換に使う)。

    body_gender は掟が定める体の性別(None は住民それぞれのまま)。
    """
    if look_tags:
        instruction = (
            f"Apply the look that a world rule sets for everyone: {look_tags}. Replace "
            "the clothing that conflicts with it. Hair, eye or body tags among these "
            "replace the person's own conflicting ones (for example long hair replaces "
            "short hair). Keep the rest of the person's own face, hair and body."
        )
    else:
        instruction = (
            "A world rule changes everyone's body. Keep the person's own clothing, "
            "face and hair."
        )
    instruction += _BODY_CHANGE_INSTRUCTIONS.get(
        str(body_gender), " Keep the person's own gender."
    )
    if dress:
        instruction += (
            " The rule of dresses is also active, so the outfit stays an elegant dress "
            "combined with these looks."
        )
    return instruction


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
        f"Output the tags comma-separated, about {HAKONIWA_TAGS_SUGGESTED_COUNT} tags, on "
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
    reality: bool = False,
) -> tuple[str, str]:
    """変身の直後の反応の出来事のプロンプト。

    reality=True は住民の改変(その住民についての世界の常識の書き換え)で、驚きの反応ではなく、
    昔からそうだったように過ごす一場面を描かせる。
    """
    involved = [target, *bystanders]
    names = [resident_name(resident, language) for resident in involved]
    moods = ", ".join(f'"{name}": mood change (integer -10..10)' for name in names)
    if reality:
        moment = (
            "You are the narrator of this miniature world. The player has just "
            "rewritten this world's common sense about one resident; from this moment "
            "it has always been true, for everyone including that resident. Create "
            "exactly one short event showing an ordinary moment of the everyday life "
            "it now shapes (not the moment of change: nobody notices any change).\n"
            "Lines are from that resident and the residents who were there, 1-4 lines "
            "in total; every speaker must be one of the involved residents. "
            f"{REALITY_STANCE} Narration must not contain dialogue in quotation marks.\n"
        )
    else:
        moment = (
            "You are the narrator of this miniature world. One resident has just had "
            "their look changed on the spot by the player's power. Create exactly one "
            "short event showing that moment.\n"
            "Lines are the reactions of the transformed resident and the residents who "
            "were there, 1-4 lines in total; every speaker must be one of the involved "
            "residents. Depict honest reactions to the changed look such as surprise, "
            "embarrassment or admiration. Narration must not contain dialogue in "
            "quotation marks.\n"
        )
    system_prompt = (
        f"{WORLD_BRIEF}\n"
        f"{moment}"
        f"{gender_address_rules(language)}\n"
        f"{NO_MALE_ROMANCE_RULE}\n"
        f"{content_rule(nsfw)}\n"
        "Output only one JSON object in this format, with no preface or code fence:\n"
        '{"title": "short heading", "narration": "narration without dialogue, 1-2 sentences", '
        '"lines": [{"speaker": "resident name", "text": "one line"}], '
        f'"participants": [{", ".join(f"{chr(34)}{name}{chr(34)}" for name in names)}], '
        f'"mood_delta": {{{moods}}}, {_bgm_field()}}}\n'
        f"{bgm_guide()}\n"
        f"Write the title, narration and lines in {response_language(language)}."
    )
    involved_text = "; ".join(
        f"{resident_name(resident, language)} ({_gender_label(resident_gender(resident))}, "
        f"{str(resident_text(resident, language)['personality'])[:HAKONIWA_PERSONALITY_PROMPT_MAX]}"
        f"; First-person pronoun: {resident_text(resident, language)['pronoun']}"
        f".{address_text(state, resident, language, involved)}"
        f"{_swap_note(state, resident, language)}"
        f"{appearance_note(state, resident)}"
        f"{reality_note(resident, language)})"
        for resident in involved
    )
    target_name = resident_name(target, language)
    extra = ""
    confused = resident_gender(target) == "male" and (
        body_gender(state, target) == "female"
        or is_feminine_transformation(state, target)
    )
    if confused:
        extra += male_confusion_guidance(state, target, target_name) + "\n"
    transformation = current_transformation(state, target) or {}
    if reality and is_risque_text(f"{transformation.get('tags', '')} {change_text}"):
        extra += REALITY_RISQUE_GUIDANCE.format(name=target_name) + "\n"
    elif is_risque_text(f"{transformation.get('tags', '')} {change_text}"):
        extra += RISQUE_REACTION_GUIDANCE.format(name=target_name) + "\n"
        if confused:
            extra += (
                f"On top of that, {target_name} is originally a man, and the "
                "bewilderment at the daring feminine look overlaps with the "
                "embarrassment and sways even harder.\n"
            )
    subject = (
        f'Resident whose reality was rewritten: {target_name}. The new common sense: "{change_text}".\n'
        if reality
        else f'Transformed resident: {target_name}. The instruction: "{change_text}".\n'
    )
    user_prompt = (
        f"{subject}"
        f"Involved residents: {involved_text}.\n"
        f"{place_text(state, target.get('current_area'))}"
        f"{story_text.dissonance_context_text(state)}"
        f"{story_text.acknowledged_player_rule(state, language)}\n"
        f"{extra}"
        f"World rules:\n{active_rules_text(state, language)}"
        f"{memo_section(state)}"
    )
    return system_prompt, user_prompt


def confrontation_prompts(
    state: dict[str, Any],
    pair: tuple[dict[str, Any], dict[str, Any]],
    language: str,
    *,
    nsfw: bool,
) -> tuple[str, str]:
    """世界の違和感が到達点に達したとき、住民が書き手へ呼びかける出来事。"""
    a_name, b_name = (resident_name(resident, language) for resident in pair)
    system_prompt = (
        f"{world_brief(state)}\n"
        f"{CONFRONTATION_SYSTEM}\n"
        f"{DIALOGUE_CRAFT_GUIDANCE}\n"
        "Narration must not contain dialogue in quotation marks. Speakers and "
        "participants must be written exactly as the names given.\n"
        f"{gender_address_rules(language)}\n"
        f"{story_text.player_address_rule(state, language)}\n"
        f"{NO_MALE_ROMANCE_RULE}\n"
        f"{content_rule(nsfw)}\n"
        "Output only one JSON object in this format, with no preface or code fence:\n"
        f"{_event_schema(pair, language)}\n"
        f"Write the title, narration and lines in {response_language(language)}."
    )
    user_prompt = (
        f"Today is day {state['day']} at Stardust House.\n"
        f"Main characters: {a_name} and {b_name}.\n"
        f"{place_text(state, pair[0].get('current_area'))}\n\n"
        f"World rules:\n{active_rules_text(state, language)}\n\n"
        f"Residents:\n{residents_text(state, language)}\n\n"
        f"Recent events:\n{recent_events_text(state)}"
        f"{story_text.memories_context_text(state, pair, language)}"
        f"{memo_section(state)}"
    )
    return system_prompt, user_prompt


def scene_tags_prompts(
    event: dict[str, Any], names: dict[str, str], area_label: str, *, nsfw: bool = False
) -> tuple[str, str]:
    """出来事の山場を1枚の絵にするための、動作・表情・構図のタグと、参加者ごとの
    その場面での服装(HAKONIWA_SCENE_ATTIRES の id)を作らせる。"""
    cast = [
        names.get(str(resident_id), "?")
        for resident_id in event.get("participants") or []
    ]
    options = [attire for attire in HAKONIWA_SCENE_ATTIRES if nsfw or attire != "nude"]
    undressed = (
        "bathing or showering: nude or towel; undressing or sex: nude or underwear"
        if nsfw
        else "bathing or showering: towel; undressing: underwear"
    )
    attire_shape = ", ".join(f'"{name}": "one of the attire ids"' for name in cast)
    system_prompt = (
        "You design tags for image generation. You are given an event from a "
        "miniature-world story. Pick the climactic moment of the event.\n"
        "tags: English Danbooru-style tags that describe only actions, facial "
        "expressions, the relationship between the characters, composition, "
        "lighting and mood, at most 12, comma-separated. Do not include tags for "
        "appearance, hair, eyes, clothing, gender or the number of people.\n"
        "attire: for each character, what they are wearing at that moment, as one "
        f"of these ids: {', '.join(options)}. as_is means their usual clothes; "
        "choose it unless the event clearly has them undressed or changed "
        f"({undressed}; a beach or a pool: swimsuit; bedtime: pajamas).\n"
        "Output only one JSON object in this format, with no preface or code fence:\n"
        f'{{"tags": "tag, tag, ...", "attire": {{{attire_shape}}}}}'
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


def event_look_prompts(
    event: dict[str, Any],
    names: dict[str, str],
    looks: dict[str, str],
    language: str,
) -> tuple[str, str]:
    """出来事の結果として姿が変わった参加者と、変化後の姿の全タグを決めさせる。

    names は住民 id ごとの名前、looks は住民 id ごとの出来事の前の姿のタグ。
    服の交換では相手の「出来事の前」のタグが要るので、参加者全員ぶんを1回で決めさせる。
    """
    system_prompt = (
        "You design tags for image generation. You are given an event from a "
        "miniature-world story and the English Danbooru-style tags of each "
        "character's look before the event. Decide whose look is different once "
        "the event is over: clothing, accessories, items they keep on, hair, "
        "visible additions such as animal ears, or a body change, as long as the "
        "event clearly depicts it and it lasts after the scene. Exchanging clothes "
        "with another character counts: each of them then wears the clothing tags "
        "the other one had before the event. Momentary states do not count: being "
        "undressed only for a bath or for sex, getting wet, a pose, an expression, "
        "or something merely imagined or talked about.\n"
        "For each character whose look changed, output the complete tag list of "
        "the look after the event. Keep that character's own identity tags from "
        "their tags before the event (hair style, hair color, eye color, age, body "
        "features, and the gender token such as 1girl / 1boy) unless the event "
        "explicitly changes them; replace clothing and items as the event "
        "describes and drop the replaced ones. Keep the tags the event leaves "
        "untouched; do not shorten the list. Write all tags in English, "
        "comma-separated, on a single line.\n"
        f"description: one short phrase in {response_language(language)} that says "
        "how the character looks now (for example, wearing the other character's "
        "jacket and leggings).\n"
        "Leave out every character whose look did not change. If nobody's look "
        "changed, output an empty list.\n"
        "Output only one JSON object in this format, with no preface or code fence:\n"
        '{"changes": [{"name": "character name exactly as given", '
        '"tags": "tag, tag, ...", "description": "short phrase"}]}'
    )
    cast = "\n".join(
        f"- {names.get(str(resident_id), '?')}: {looks.get(str(resident_id), '')}"
        for resident_id in event.get("participants") or []
    )
    lines = "\n".join(
        f"{names.get(str(line.get('speaker')), '?')}: {line.get('text', '')}"
        for line in event.get("lines") or []
    )
    order = str(event.get("instruction") or "").strip()
    user_prompt = (
        f"Characters and their looks before the event:\n{cast}\n\n"
        + (f"What the player ordered for this scene: {order}\n" if order else "")
        + f"Title: {event.get('title', '')}\n"
        f"Narration: {event.get('narration', '')}\n"
        f"Lines:\n{lines or '(none)'}"
    )
    return system_prompt, user_prompt


def random_residents_prompts(
    count: int, language: str, exclude_names: list[str]
) -> tuple[str, str]:
    """おまかせの住民(ランダムな住民構成)を作るプロンプト。出力言語の文と英語のタグを対で返させる。"""
    lang = response_language(language)
    name_rule = (
        "Write full names in Japanese (family name, a half-width space, given name), "
        "for example '佐倉 美咲'. Write the job as a natural Japanese job title "
        "(for example システムエンジニア, 花屋の店主). Call the boarding house 下宿 "
        "in Japanese."
        if language == "ja"
        else "Write full names as 'Given Family' in English, for example 'Misaki Sakura'."
    )
    pronoun_rule = (
        "pronoun is the resident's first-person pronoun in Japanese (for example "
        "私, わたし, あたし, 僕, 俺)."
        if language == "ja"
        else "pronoun is always 'I'."
    )
    avoid = (
        f" Never use these names, or names that look the same: {', '.join(exclude_names)}."
        if exclude_names
        else ""
    )
    chinese_rule = (
        " Write natural Japanese only and never mix in simplified Chinese characters."
        if language == "ja"
        else ""
    )
    address_rule = (
        "address_style is how the resident calls the other residents, chosen to fit "
        "the personality: given_chan (given name + ちゃん, くん for men), given_san "
        "(given name + さん), given (given name alone), family_san (family name + "
        "さん, polite), family (family name alone, curt). They have lived together "
        "for a while, so prefer the familiar styles; use family_san only for a "
        "reserved or very polite person."
    )
    age_example = "20代後半" if language == "ja" else "late 20s"
    system_prompt = (
        "You are a character designer for a life simulation set in a small boarding "
        "house. Design new residents.\n"
        "Conditions: every resident is an adult (20s to 50s). Mix female and male "
        f"residents. {name_rule} Every name must be different.{avoid} The job fits "
        "someone who lives in a boarding house. The personality is one or two concrete "
        "sentences that show who they are, written in the third person as a "
        "description (never speak as the resident). appearance is one sentence "
        "describing the "
        "hair style, hair color, eye color and everyday clothes. appearance_tags are "
        "English Danbooru-style tags for exactly that appearance: start with the "
        "gender token (1girl or 1boy), then solo, the age, hair, eyes and clothes, "
        f"about {HAKONIWA_TAGS_SUGGESTED_COUNT} tags, modest everyday clothing. "
        f"{pronoun_rule} {address_rule}\n"
        f"Write name, age, job, personality, pronoun and appearance in {lang}; "
        f"appearance_tags are always English.{chinese_rule}\n"
        "Output only this JSON, with no explanation or code fence:\n"
        '{"residents": [{"name": "...", "gender": "female", '
        f'"age": "{age_example}", '
        '"job": "...", "personality": "...", "pronoun": "...", '
        '"address_style": "given_san", "appearance": "...", '
        '"appearance_tags": "1girl, solo, ..."}]}'
    )
    return system_prompt, f"Design {count} residents."
