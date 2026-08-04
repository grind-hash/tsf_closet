"""TSF Bloomer 育成サービス用プロンプトビルダー。"""

from __future__ import annotations

from typing import Any

from ..consts.bloomer_consts import AXIS_KEYS


def _response_lang(language: str) -> str:
    return "Japanese" if language == "ja" else "English"


def _axis_summary(axes: dict[str, int], growth: dict[str, int]) -> str:
    parts = []
    for key in AXIS_KEYS:
        base = axes.get(key, 0)
        grown = growth.get(key, 0)
        parts.append(f"{key}:{base + grown}")
    return ", ".join(parts)


def _run_context(run: Any) -> str:
    import json

    axes: dict[str, int] = json.loads(run.axes_json) if run.axes_json else {}
    growth: dict[str, int] = json.loads(run.growth_json) if run.growth_json else {}
    decisions: dict[str, str] = (
        json.loads(run.decisions_json) if run.decisions_json else {}
    )
    return (
        f"Character: {run.name}\n"
        f"Day {run.day}/{run.max_days}, Stage {run.stage}, NSFW stage {run.nsfw_stage}\n"
        f"Mood: {run.mood}/100, Stamina: {run.stamina}/100, Trust: {run.trust}/100\n"
        f"Axes: {_axis_summary(axes, growth)}\n"
        f"Outfit: {run.equipped_outfit or 'none'}\n"
        f"Key decisions: {decisions or 'none'}"
    )


# ---------------------------------------------------------------------------
# アクション反応（通常）
# ---------------------------------------------------------------------------

ACTION_REACTION_SYSTEM = """\
You are writing the response of a character in a quiet one-on-one raising story.
Write 1–3 vivid sentences (under 200 characters) from the character's perspective.
Use {lang}. No JSON. No meta-commentary.
The character is a feminized/transformed person.
Mood ({mood}/100) and trust ({trust}/100) shape tone: high trust → warmer; low mood → flat or reluctant.
Never decide the player’s actions or feelings."""

TALK_REACTION_SYSTEM = """\
You are writing the reply of a character in a quiet one-on-one story.
The player has spoken to the character. Write the character's reply (1–3 sentences, under 220 characters).
Use {lang}. No JSON. Stay in character.
Mood ({mood}/100) and trust ({trust}/100) shape tone: high trust → opens up; low mood → brief or evasive.
Never decide the player’s feelings or continue the player’s side of the dialogue."""


def build_action_reaction_prompt(
    run: Any, action_key: str, language: str, user_text: str | None = None
) -> tuple[str, str]:
    if action_key == "talk" and user_text:
        system = TALK_REACTION_SYSTEM.format(
            lang=_response_lang(language), mood=run.mood, trust=run.trust
        )
        user = (
            f"{_run_context(run)}\n\n"
            f'Player said: "{user_text}"\n\n'
            "Write the character's reply."
        )
    else:
        system = ACTION_REACTION_SYSTEM.format(
            lang=_response_lang(language), mood=run.mood, trust=run.trust
        )
        user = (
            f"{_run_context(run)}\n\nAction performed: {action_key}\n\n"
            "Write the character's reaction."
        )
    return system, user


# ---------------------------------------------------------------------------
# 拒否ライン
# ---------------------------------------------------------------------------

REFUSAL_SYSTEM = """\
You are a narrator for a tamagotchi-like raising game.
Write a short refusal line (1 sentence, under 120 characters) from the character.
Use {lang}. No JSON. Tone matches mood ({mood}/100) and trust ({trust}/100).
Low mood → sharp refusal; mid → hesitant; low trust → cold."""


def build_refusal_prompt(run: Any, action_key: str, language: str) -> tuple[str, str]:
    system = REFUSAL_SYSTEM.format(
        lang=_response_lang(language), mood=run.mood, trust=run.trust
    )
    user = (
        f"{_run_context(run)}\n\nRefused action: {action_key}\n\n"
        "Write the character's refusal line."
    )
    return system, user


# ---------------------------------------------------------------------------
# 夜の総括
# ---------------------------------------------------------------------------

NIGHTLY_SUMMARY_SYSTEM = """\
You are the narrator of a tamagotchi-like raising game.
Write a short nightly reflection monologue (2–3 sentences, under 280 characters) for the character.
Use {lang}. Tone reflects the day's events and current mood ({mood}/100), trust ({trust}/100).
No JSON. No meta-commentary. Past tense."""


def build_nightly_summary_prompt(
    run: Any, events_today: list[dict[str, Any]], language: str
) -> tuple[str, str]:
    system = NIGHTLY_SUMMARY_SYSTEM.format(
        lang=_response_lang(language), mood=run.mood, trust=run.trust
    )
    event_lines = "\n".join(
        f"- {e.get('kind')}: {e.get('action_key') or ''}" for e in events_today
    )
    user = (
        f"{_run_context(run)}\n\nToday's events:\n{event_lines or '(none)'}\n\n"
        "Write the character's nightly reflection."
    )
    return system, user


# ---------------------------------------------------------------------------
# ステージアップ
# ---------------------------------------------------------------------------

STAGE_UP_SYSTEM = """\
You are the narrator of a tamagotchi-like raising game.
Write a short, evocative stage-up scene (2–3 sentences, under 300 characters) for the character.
Use {lang}. The character has just reached Stage {stage}.
Convey change — subtle growth, heightened awareness, a new facet revealed.
No JSON. No meta-commentary."""


def build_stage_up_prompt(run: Any, new_stage: int, language: str) -> tuple[str, str]:
    system = STAGE_UP_SYSTEM.format(lang=_response_lang(language), stage=new_stage)
    user = f"{_run_context(run)}\n\nWrite the stage-up scene for Stage {new_stage}."
    return system, user


# ---------------------------------------------------------------------------
# エンディング
# ---------------------------------------------------------------------------

ENDING_SYSTEM = """\
You are the narrator of a tamagotchi-like raising game.
Write the ending scene (3–5 sentences, under 400 characters) for key: {ending_key}.
Use {lang}. Reflect the full arc of the run — the choices made, the trust built or lost.
No JSON. No meta-commentary. Past/present tense mix is fine."""


def build_ending_prompt(run: Any, ending_key: str, language: str) -> tuple[str, str]:
    import json

    decisions: dict = json.loads(run.decisions_json) if run.decisions_json else {}
    system = ENDING_SYSTEM.format(lang=_response_lang(language), ending_key=ending_key)
    user = (
        f"{_run_context(run)}\n"
        f"Ending key: {ending_key}\n"
        f"Day reached: {run.day}/{run.max_days}\n"
        f"Decisions: {decisions or 'none'}\n\n"
        "Write the ending scene."
    )
    return system, user


# ---------------------------------------------------------------------------
# 画像タグ生成
# ---------------------------------------------------------------------------

IMAGE_TAG_SYSTEM = """\
You generate a compact NovelAI image tag string (under 200 characters, comma-separated English tags) \
for the current appearance of a character in a raising game.
Output ONLY the tag string. No JSON, no explanation.
Include: clothing/outfit, expression/mood, pose, setting hint.
For NSFW stage {nsfw_stage}: {'explicit adult details' if nsfw_stage >= 2 else 'tasteful'} depiction."""


def build_image_tags_prompt(run: Any, language: str) -> tuple[str, str]:
    import json

    axes: dict[str, int] = json.loads(run.axes_json) if run.axes_json else {}
    growth: dict[str, int] = json.loads(run.growth_json) if run.growth_json else {}
    system = IMAGE_TAG_SYSTEM.format(nsfw_stage=run.nsfw_stage)
    user = (
        f"Character: {run.name}, Stage {run.stage}, Day {run.day}\n"
        f"Outfit: {run.equipped_outfit or 'plain_dress'}\n"
        f"Mood: {run.mood}/100, Trust: {run.trust}/100\n"
        f"Axes: {_axis_summary(axes, growth)}\n\n"
        "Generate image tags."
    )
    return system, user
