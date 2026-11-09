"""AI箱庭モードのテキスト生成(出来事・一言・変身のタグ変換と反応)。

本文生成と同じプロバイダ・テキストモデルを使い、別のプロバイダへは切り替えない。
生成に失敗したら定型の出来事・一言に落とす(変身のタグ変換だけは失敗を返す)。
"""

from __future__ import annotations

import logging
import random
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from ..consts.hakoniwa import (
    GENERIC_GREETINGS,
    HAKONIWA_CONVERT_TAGS_MAX_ATTEMPTS,
    HAKONIWA_EVENT_LINE_TEXT_MAX,
    HAKONIWA_EVENT_LINES_MAX,
    HAKONIWA_EVENT_NARRATION_MAX,
    HAKONIWA_EVENT_TITLE_MAX,
    HAKONIWA_GREETING_MAX,
    HAKONIWA_RECENT_EVENTS_CONTEXT,
    HAKONIWA_TAGS_MAX_COUNT,
    HAKONIWA_TAGS_MAX_LENGTH,
    HAKONIWA_TEMPLATES,
)
from .cost_tracker import record_cost
from .hakoniwa_logic import resident_name, resident_text
from .hakoniwa_prompts import (
    RULE_FOCUS_RETRY_NOTE,
    appearance_tags_prompts,
    event_system_prompt,
    event_user_prompt,
    greeting_prompts,
    scene_tags_prompts,
    transform_reaction_prompts,
    transform_tags_prompts,
)
from .llm_json import generate_validated
from .llm_service import llm_service

logger = logging.getLogger(__name__)


async def _generate_text(
    system_prompt: str,
    user_prompt: str,
    *,
    novelai_model: str | None,
    max_tokens: int = 1400,
) -> str:
    # 本文生成と同じプロバイダ・テキストモデルに従わせる(料金は記録する)
    result = await llm_service.generate_feeling(
        system_prompt,
        user_prompt,
        novelai_model_override=novelai_model,
        max_tokens=max_tokens,
    )
    record_cost(result.cost_usd)
    return result.content


# --- 出来事の検証 ---


def _norm_name(name: str) -> str:
    """名前の照合用に空白(全角を含む)を取り除く。"""
    return "".join(str(name or "").split())


class _Line(BaseModel):
    speaker: str
    text: str = Field(min_length=1)


class EventOutput(BaseModel):
    """生成された出来事。話者と参加者は context の names と一致しなければならない。"""

    title: str = Field(min_length=1)
    narration: str = Field(min_length=10)
    lines: list[_Line] = Field(min_length=1, max_length=HAKONIWA_EVENT_LINES_MAX)
    participants: list[str] | None = None
    mood_delta: dict[str, Any] = Field(default_factory=dict)
    affinity_delta: Any = 0

    @field_validator("lines")
    @classmethod
    def _speakers_in_cast(cls, lines: list[_Line], info: ValidationInfo) -> list[_Line]:
        names = {_norm_name(name) for name in (info.context or {}).get("names") or []}
        for line in lines:
            if names and _norm_name(line.speaker) not in names:
                raise ValueError(
                    f"speaker '{line.speaker}' is not one of {sorted(names)}"
                )
        return lines

    @field_validator("participants")
    @classmethod
    def _participants_match(
        cls, participants: list[str] | None, info: ValidationInfo
    ) -> list[str] | None:
        names = {_norm_name(name) for name in (info.context or {}).get("names") or []}
        if (
            participants is not None
            and names
            and {_norm_name(item) for item in participants} != names
        ):
            raise ValueError(f"participants must be exactly {sorted(names)}")
        return participants


def _int_delta(value: Any, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return 0


def _event_from_output(
    output: EventOutput,
    group: tuple[dict[str, Any], ...],
    language: str,
    *,
    mood_range: int = 20,
) -> dict[str, Any]:
    id_by_name = {
        _norm_name(resident_name(resident, language)): resident["id"]
        for resident in group
    }
    mood_delta = {
        id_by_name[_norm_name(name)]: _int_delta(value, -mood_range, mood_range)
        for name, value in output.mood_delta.items()
        if _norm_name(name) in id_by_name
    }
    return {
        "title": output.title.strip()[:HAKONIWA_EVENT_TITLE_MAX],
        "narration": output.narration.strip()[:HAKONIWA_EVENT_NARRATION_MAX],
        "lines": [
            {
                "speaker": id_by_name[_norm_name(line.speaker)],
                "text": line.text.strip()[:HAKONIWA_EVENT_LINE_TEXT_MAX],
            }
            for line in output.lines
        ],
        "participants": [resident["id"] for resident in group],
        "mood_delta": mood_delta,
        "affinity_delta": _int_delta(output.affinity_delta, -15, 15)
        if len(group) >= 2
        else 0,
        "source": "llm",
    }


# --- 定型の出来事 ---


def _lang(language: str) -> str:
    return "ja" if language == "ja" else "en"


def _instantiate(
    template: dict[str, Any], keys: dict[str, dict[str, Any]], language: str
) -> dict[str, Any]:
    names = {key: resident_name(resident, language) for key, resident in keys.items()}
    return {
        "title": template["title"],
        "narration": template["narration"].format(**names),
        "lines": [
            {"speaker": keys[speaker]["id"], "text": text.format(**names)}
            for speaker, text in template["lines"]
            if speaker in keys
        ],
        "participants": [resident["id"] for resident in keys.values()],
        "mood_delta": {
            keys[key]["id"]: int(value)
            for key, value in template.get("mood_delta", {}).items()
            if key in keys
        },
        "affinity_delta": int(template.get("affinity_delta", 0))
        if len(keys) >= 2
        else 0,
        "source": "template",
    }


def is_swap_group(state: dict[str, Any], group: tuple[dict[str, Any], ...]) -> bool:
    pair = state.get("swap_pair")
    return (
        "swap" in state.get("active_rules", [])
        and bool(pair)
        and len(group) == 2
        and {group[0]["id"], group[1]["id"]} == set(pair)
    )


def template_event(
    state: dict[str, Any],
    group: tuple[dict[str, Any], ...],
    language: str,
    rng: random.Random,
    *,
    recent_titles: set[str] | None = None,
) -> dict[str, Any]:
    """定型の出来事。人数で候補を変え、入れ替わりの当事者なら専用の定型を優先する。"""
    templates = HAKONIWA_TEMPLATES[_lang(language)]
    if len(group) == 1:
        candidates = list(templates["solo"])
        weights = [1.0] * len(candidates)
    elif len(group) >= 3:
        candidates = list(templates["trio"])
        weights = [1.0] * len(candidates)
    else:
        candidates = list(templates["pair"])
        weights = [1.0] * len(candidates)
        if is_swap_group(state, group):
            candidates = list(templates["swap"]) + candidates
            weights = [3.0] * len(templates["swap"]) + weights
    if recent_titles:
        filtered = [
            (item, weight)
            for item, weight in zip(candidates, weights, strict=True)
            if item["title"] not in recent_titles
        ]
        if filtered:
            candidates = [item for item, _ in filtered]
            weights = [weight for _, weight in filtered]
    template = rng.choices(candidates, weights=weights, k=1)[0]
    keys = dict(zip(("a", "b", "c"), group, strict=False))
    return _instantiate(template, keys, language)


def transform_reaction_template(
    target: dict[str, Any], bystanders: list[dict[str, Any]], language: str
) -> dict[str, Any]:
    templates = HAKONIWA_TEMPLATES[_lang(language)]
    if bystanders:
        return _instantiate(
            templates["reaction"][0],
            {"target": target, "other": bystanders[0]},
            language,
        )
    return _instantiate(templates["reaction_solo"][0], {"target": target}, language)


# --- 生成 ---


async def generate_event(
    state: dict[str, Any],
    group: tuple[dict[str, Any], ...],
    language: str,
    rng: random.Random,
    *,
    novelai_model: str | None,
    nsfw: bool,
    rule_focus_rule_id: str | None = None,
    others_today: list[list[str]] | None = None,
    recent_titles: set[str] | None = None,
    area_id: str | None = None,
) -> dict[str, Any]:
    """出来事を1件生成する。失敗したら定型の出来事にする(例外は投げない)。

    自作の掟を中心にする出来事だけ、検証に落ちたら指示を再掲してもう一度だけ生成する。
    """
    names = [resident_name(resident, language) for resident in group]
    system_prompt = event_system_prompt(group, state, language, nsfw=nsfw)
    user_prompt = event_user_prompt(
        state,
        group,
        language,
        nsfw=nsfw,
        rule_focus_rule_id=rule_focus_rule_id,
        others_today=others_today,
        area_id=area_id,
    )

    async def generate(system: str, user: str) -> str:
        return await _generate_text(system, user, novelai_model=novelai_model)

    attempts = 2 if rule_focus_rule_id else 1
    for attempt in range(attempts):
        prompt = user_prompt if attempt == 0 else user_prompt + RULE_FOCUS_RETRY_NOTE
        try:
            output = await generate_validated(
                EventOutput,
                generate=generate,
                system_prompt=system_prompt,
                user_prompt=prompt,
                context={"names": names},
            )
            event = _event_from_output(output, group, language)
            event["area"] = area_id
            return event
        except Exception as error:
            logger.warning(
                "Hakoniwa event generation failed: %s: %s", type(error).__name__, error
            )
    event = template_event(state, group, language, rng, recent_titles=recent_titles)
    event["area"] = area_id
    return event


def recent_titles(state: dict[str, Any]) -> set[str]:
    return {
        str(event.get("title") or "")
        for event in state["events"][-HAKONIWA_RECENT_EVENTS_CONTEXT:]
    }


_GREETING_QUOTES = "「」『』\"'“”"


def _clean_greeting(raw: str) -> str | None:
    text = " ".join(str(raw or "").split()).strip(_GREETING_QUOTES + " ")
    if not text:
        return None
    return text[:HAKONIWA_GREETING_MAX]


def greeting_fallback(
    resident: dict[str, Any], language: str, rng: random.Random
) -> str:
    greetings = (
        resident_text(resident, language)["greetings"]
        or GENERIC_GREETINGS[_lang(language)]
    )
    return rng.choice(greetings)


async def generate_greeting(
    state: dict[str, Any],
    resident: dict[str, Any],
    language: str,
    rng: random.Random,
    *,
    novelai_model: str | None,
    nsfw: bool,
) -> dict[str, str]:
    """住民の一言。失敗したら定型の一言にする。"""
    system_prompt, user_prompt = greeting_prompts(state, resident, language, nsfw=nsfw)
    try:
        raw = await _generate_text(
            system_prompt, user_prompt, novelai_model=novelai_model, max_tokens=300
        )
        cleaned = _clean_greeting(raw)
        if cleaned:
            return {"text": cleaned, "source": "llm"}
    except Exception as error:
        logger.warning(
            "Hakoniwa greeting generation failed: %s: %s", type(error).__name__, error
        )
    return {"text": greeting_fallback(resident, language, rng), "source": "template"}


_TAG_CHARS = re.compile(r"^[A-Za-z0-9 ,.\-'()/:_]+$")
_JAPANESE_CHARS = re.compile(r"[぀-ヿ㐀-鿿ｦ-ﾟ]")


def clean_tags(raw: str) -> str | None:
    """LLM の応答を英語のタグ列に整える。英語のタグでなければ None。"""
    text = str(raw or "").strip()
    if not text:
        return None
    line = text.splitlines()[0].strip().strip("`\"' ")
    if line.lower().startswith("tags:"):
        line = line[5:].strip()
    if not line or not _TAG_CHARS.match(line):
        return None
    tags = [tag.strip() for tag in line.split(",") if tag.strip()]
    if not tags:
        return None
    joined = ", ".join(tags[:HAKONIWA_TAGS_MAX_COUNT])
    return joined[:HAKONIWA_TAGS_MAX_LENGTH].rstrip(", ")


def needs_tag_expansion(text: str) -> bool:
    """日本語の文章ならタグへの変換が要る(英語のタグはそのまま使う)。"""
    return bool(_JAPANESE_CHARS.search(str(text or "")))


async def convert_change_to_tags(
    instruction: str, base_tags: str, *, novelai_model: str | None
) -> str | None:
    """変身の指定文と今のタグから、変身後の姿の全タグを作る。失敗したら None。"""
    system_prompt, user_prompt = transform_tags_prompts(instruction, base_tags)
    for _ in range(HAKONIWA_CONVERT_TAGS_MAX_ATTEMPTS):
        try:
            raw = await _generate_text(
                system_prompt, user_prompt, novelai_model=novelai_model, max_tokens=400
            )
        except Exception as error:
            logger.warning(
                "Hakoniwa tag conversion failed: %s: %s", type(error).__name__, error
            )
            continue
        tags = clean_tags(raw)
        if tags:
            return tags
    return None


async def expand_appearance_tags(
    description: str, gender: str, *, dress: bool, novelai_model: str | None
) -> str | None:
    """住民の外見の説明(日本語の文章)を英語のタグにする。失敗したら None。"""
    system_prompt, user_prompt = appearance_tags_prompts(
        description, gender, dress=dress
    )
    try:
        raw = await _generate_text(
            system_prompt, user_prompt, novelai_model=novelai_model, max_tokens=400
        )
    except Exception as error:
        logger.warning(
            "Hakoniwa appearance expansion failed: %s: %s", type(error).__name__, error
        )
        return None
    return clean_tags(raw)


async def generate_transform_reaction(
    state: dict[str, Any],
    target: dict[str, Any],
    change_text: str,
    bystanders: list[dict[str, Any]],
    language: str,
    *,
    novelai_model: str | None,
    nsfw: bool,
) -> dict[str, Any]:
    """変身の直後の反応の出来事。失敗したら定型の反応にする。"""
    group = (target, *bystanders)
    names = [resident_name(resident, language) for resident in group]
    system_prompt, user_prompt = transform_reaction_prompts(
        state, target, change_text, bystanders, language, nsfw=nsfw
    )

    async def generate(system: str, user: str) -> str:
        return await _generate_text(
            system, user, novelai_model=novelai_model, max_tokens=900
        )

    try:
        output = await generate_validated(
            EventOutput,
            generate=generate,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context={"names": names},
        )
        event = _event_from_output(output, group, language, mood_range=10)
        event["affinity_delta"] = 0
        return event
    except Exception as error:
        logger.warning(
            "Hakoniwa transform reaction failed: %s: %s", type(error).__name__, error
        )
    return transform_reaction_template(target, bystanders, language)


# 場面のタグの個数の上限
SCENE_TAGS_MAX_COUNT = 12


async def convert_scene_to_tags(
    event: dict[str, Any],
    names: dict[str, str],
    area_label: str,
    *,
    novelai_model: str | None,
) -> str | None:
    """出来事の山場の動作・表情・構図のタグを作る。失敗したら None(呼び出し側が定型にする)。"""
    system_prompt, user_prompt = scene_tags_prompts(event, names, area_label)
    try:
        raw = await _generate_text(
            system_prompt, user_prompt, novelai_model=novelai_model, max_tokens=400
        )
    except Exception as error:
        logger.warning(
            "Hakoniwa scene tags failed: %s: %s", type(error).__name__, error
        )
        return None
    tags = clean_tags(raw)
    if not tags:
        return None
    return ", ".join(tags.split(", ")[:SCENE_TAGS_MAX_COUNT])
