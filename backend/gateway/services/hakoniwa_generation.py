"""AI箱庭モードのテキスト生成(出来事・一言・変身のタグ変換と反応)。

本文生成と同じプロバイダ・テキストモデルを使い、別のプロバイダへは切り替えない。
生成に失敗したら定型の出来事・一言に落とす(変身のタグ変換と、書き手が指示した
出来事だけは失敗を返す)。
"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from ..consts.adventure_bgm import coerce_bgm_key, get_hakoniwa_event_bgm_keys
from ..consts.hakoniwa import (
    GENERIC_GREETINGS,
    HAKONIWA_ADDRESS_STYLE_DEFAULT,
    HAKONIWA_APPEARANCE_TEXT_MAX,
    HAKONIWA_CONVERT_TAGS_MAX_ATTEMPTS,
    HAKONIWA_EVENT_LINE_TEXT_MAX,
    HAKONIWA_EVENT_LINES_MAX,
    HAKONIWA_EVENT_NARRATION_MAX,
    HAKONIWA_EVENT_TITLE_MAX,
    HAKONIWA_GREETING_MAX,
    HAKONIWA_PERSONALITY_MAX,
    HAKONIWA_RECENT_EVENTS_CONTEXT,
    HAKONIWA_RESIDENT_NAME_MAX,
    HAKONIWA_SCENE_ATTIRES,
    HAKONIWA_TAGS_MAX_LENGTH,
    HAKONIWA_TEMPLATES,
    event_location,
)
from ..consts.hakoniwa_play import (
    CHAT_FALLBACKS,
    HAKONIWA_CHAT_MESSAGE_MAX,
    HAKONIWA_CHAT_REPLY_MAX,
    TOUCH_REACTION_TEMPLATES,
    TOUCH_TOLERANT_MOOD,
)
from ..consts.hakoniwa_random import (
    HAKONIWA_RANDOM_AGE_MAX,
    HAKONIWA_RANDOM_JOB_MAX,
    HAKONIWA_RANDOM_PRONOUN_MAX,
)
from . import hakoniwa_play as play
from . import hakoniwa_story as story
from .cost_tracker import record_cost
from .hakoniwa_errors import HakoniwaError
from .hakoniwa_logic import (
    clean_address_style,
    ensure_gender_token,
    is_male_in_feminine_form,
    resident_name,
    resident_text,
    settle_event_location,
    tags_gender,
)
from .hakoniwa_prompts import (
    DIRECTED_EVENT_RETRY_NOTE,
    RULE_FOCUS_RETRY_NOTE,
    alteration_prompts,
    appearance_is_risque,
    appearance_tags_prompts,
    chat_reply_prompts,
    confrontation_prompts,
    current_appearance_summary,
    event_system_prompt,
    event_user_prompt,
    greeting_prompts,
    memo_look_prompts,
    random_residents_prompts,
    rule_look_tags_prompts,
    scene_tags_prompts,
    touch_prompts,
    transform_reaction_prompts,
    transform_tags_prompts,
)
from .hakoniwa_random import name_key
from .hakoniwa_text import SIMPLIFIED_ONLY_CHARS, normalize_output
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
    # 出来事の場所の id。一覧に無ければ Python が無視して起きたエリアにする
    location: Any = None
    mood_delta: dict[str, Any] = Field(default_factory=dict)
    affinity_delta: Any = 0
    # 出来事を見せる間の BGM のキー。候補に無ければ None(ふだんの曲のまま)にし、修復を起こさない
    bgm: str | None = None

    @field_validator("bgm", mode="before")
    @classmethod
    def _bgm_key(cls, value: Any) -> str | None:
        return coerce_bgm_key(value, get_hakoniwa_event_bgm_keys())

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
        "title": normalize_output(output.title.strip(), language)[
            :HAKONIWA_EVENT_TITLE_MAX
        ],
        "narration": normalize_output(output.narration.strip(), language)[
            :HAKONIWA_EVENT_NARRATION_MAX
        ],
        "lines": [
            {
                "speaker": id_by_name[_norm_name(line.speaker)],
                "text": normalize_output(line.text.strip(), language)[
                    :HAKONIWA_EVENT_LINE_TEXT_MAX
                ],
            }
            for line in output.lines
        ],
        "participants": [resident["id"] for resident in group],
        "mood_delta": mood_delta,
        "affinity_delta": _int_delta(output.affinity_delta, -15, 15)
        if len(group) >= 2
        else 0,
        "source": "llm",
        **({"bgm": output.bgm} if output.bgm else {}),
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
        if story.is_investigation_group(state, group):
            candidates = list(templates["investigation"]) + candidates
            weights = [3.0] * len(templates["investigation"]) + weights
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
    if template in templates.get("investigation", []):
        # 調査の定型は調べ役を {a} にする
        lead = story.investigator(state)
        group = tuple(
            sorted(group, key=lambda item: item["id"] != (lead or {}).get("id"))
        )
    keys = dict(zip(("a", "b", "c"), group, strict=False))
    return _instantiate(template, keys, language)


def transform_reaction_template(
    target: dict[str, Any],
    bystanders: list[dict[str, Any]],
    language: str,
    *,
    reality: bool = False,
) -> dict[str, Any]:
    templates = HAKONIWA_TEMPLATES[_lang(language)]
    key = "reality" if reality else "reaction"
    if bystanders:
        return _instantiate(
            templates[key][0],
            {"target": target, "other": bystanders[0]},
            language,
        )
    return _instantiate(templates[f"{key}_solo"][0], {"target": target}, language)


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
    arc_focus_id: str | None = None,
    arc_climax: bool = False,
    intervention: str | None = None,
    include_theme: bool = True,
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
        arc_focus_id=arc_focus_id,
        arc_climax=arc_climax,
        intervention=intervention,
        include_theme=include_theme,
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
            return settle_event_location(event, area_id, output.location)
        except Exception as error:
            logger.warning(
                "Hakoniwa event generation failed: %s: %s", type(error).__name__, error
            )
    event = template_event(state, group, language, rng, recent_titles=recent_titles)
    event["area"] = area_id
    return event


async def generate_directed_event(
    state: dict[str, Any],
    group: tuple[dict[str, Any], ...],
    instruction: str,
    language: str,
    *,
    novelai_model: str | None,
    nsfw: bool,
    area_id: str | None,
    location_id: str | None = None,
    previous_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """書き手が指示した出来事を1件生成する。

    location_id はプレイヤーが決めた場所(無ければ内容に合う場所を生成が選ぶ)。
    previous_event は続きを指示した元の出来事。直前の場面として渡し、生成が場所を
    示さなければ同じ場所で続ける。

    指示を無視した場面を積まないよう、定型の出来事には落とさない。検証に落ちたら指示を
    再掲してもう一度だけ生成し、それも落ちたら event_generation_failed を投げる。
    """
    names = [resident_name(resident, language) for resident in group]
    system_prompt = event_system_prompt(
        group, state, language, nsfw=nsfw, directed=True
    )
    user_prompt = event_user_prompt(
        state,
        group,
        language,
        nsfw=nsfw,
        area_id=area_id,
        include_theme=False,
        directed_instruction=instruction,
        location_id=location_id,
        continues_event=previous_event,
    )
    stay = event_location(previous_event)["id"] if previous_event else None

    async def generate(system: str, user: str) -> str:
        return await _generate_text(system, user, novelai_model=novelai_model)

    for attempt in range(2):
        prompt = (
            user_prompt if attempt == 0 else user_prompt + DIRECTED_EVENT_RETRY_NOTE
        )
        try:
            output = await generate_validated(
                EventOutput,
                generate=generate,
                system_prompt=system_prompt,
                user_prompt=prompt,
                context={"names": names},
            )
        except Exception as error:
            logger.warning(
                "Hakoniwa directed event generation failed: %s: %s",
                type(error).__name__,
                error,
            )
            continue
        event = _event_from_output(output, group, language)
        return settle_event_location(
            event, area_id, location_id or output.location, fallback=stay
        )
    raise HakoniwaError(
        "event_generation_failed",
        "出来事を生成できませんでした。指示の文を変えてお試しください",
    )


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
            return {"text": normalize_output(cleaned, language), "source": "llm"}
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
    return _join_within_limit(tags)


def _join_within_limit(tags: list[str]) -> str:
    """タグをつなげる。長さの上限を超える分は、タグの途中で切らずに後ろから落とす。"""
    kept: list[str] = []
    length = 0
    for tag in tags:
        added = len(tag) + (2 if kept else 0)
        if length + added > HAKONIWA_TAGS_MAX_LENGTH:
            break
        kept.append(tag)
        length += added
    return ", ".join(kept)


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


# 掟の見た目のタグから外す、人物そのものの性別・人数のタグ
_PERSON_TAG = re.compile(
    r"^(?:\d*\+?(?:girl|boy)s?|solo|multiple (?:girls|boys)|woman|man|female|male)$",
    re.IGNORECASE,
)


def clean_look_tags(raw: str) -> str | None:
    """掟の見た目のタグを整える(英語のタグだけ・人物の性別と人数のタグは外す)。"""
    tags = clean_tags(raw)
    if not tags:
        return None
    kept = [
        tag.strip() for tag in tags.split(",") if not _PERSON_TAG.match(tag.strip())
    ]
    return ", ".join(kept) or None


def _manual_tag_list(raw: str) -> list[str]:
    """プレイヤーが手で書いたタグを分ける。改行もカンマと同じに扱い、切り詰めずに断る。"""
    text = ", ".join(line.strip() for line in str(raw or "").splitlines())
    tags = [tag.strip() for tag in text.split(",") if tag.strip()]
    if not tags or not all(_TAG_CHARS.match(tag) for tag in tags):
        raise HakoniwaError(
            "invalid_tags",
            "タグは英語(半角の英数字と記号)のカンマ区切りで書いてください",
        )
    if len(", ".join(tags)) > HAKONIWA_TAGS_MAX_LENGTH:
        raise HakoniwaError(
            "too_many_tags",
            f"タグが長すぎます({HAKONIWA_TAGS_MAX_LENGTH}文字まで)",
        )
    return tags


def clean_manual_tags(raw: str, gender: str) -> str:
    """プレイヤーが手で書いた住民のタグ(いつもの姿・ドレス姿)を整える。

    性別トークンが無ければ補う(無いと女性寄りに描かれる)。住民の性別と逆の性別トークンは断る。
    """
    tags = ", ".join(_manual_tag_list(raw))
    found = tags_gender(tags)
    if found is not None and found != gender:
        raise HakoniwaError(
            "tags_gender_mismatch",
            "タグの性別(1girl / 1boy)が住民の性別と合っていません",
        )
    return ensure_gender_token(tags, gender)


def clean_manual_look_tags(raw: str) -> str:
    """プレイヤーが手で書いた掟の見た目のタグを整える(人物の性別と人数のタグは外す)。"""
    tags = _manual_tag_list(raw)
    kept = [tag for tag in tags if not _PERSON_TAG.match(tag)]
    if not kept:
        raise HakoniwaError(
            "invalid_tags",
            "掟の見た目のタグには、服装や髪型などの見た目を書いてください",
        )
    return ", ".join(kept)


class MemoLookOutput(BaseModel):
    """世界のメモが住民全員の見た目を変えるかの判断。"""

    changes_look: bool = False
    appearance_tags: str = ""
    body_gender: str | None = None

    @field_validator("appearance_tags", mode="before")
    @classmethod
    def _tags(cls, value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        return value if isinstance(value, str) else ""

    @field_validator("body_gender", mode="before")
    @classmethod
    def _body(cls, value: Any) -> str | None:
        return value if value in ("female", "male") else None


async def plan_memo_look(
    memo: str, *, novelai_model: str | None
) -> tuple[str, str | None]:
    """世界のメモが住民全員の見た目を変えるかを判断し、(見た目のタグ, 体の性別) を返す。

    姿に関わらなければ ("", None)。生成に失敗したら HakoniwaError。
    """
    system_prompt, user_prompt = memo_look_prompts(memo)

    async def generate(system: str, user: str) -> str:
        return await _generate_text(
            system, user, novelai_model=novelai_model, max_tokens=300
        )

    try:
        output = await generate_validated(
            MemoLookOutput,
            generate=generate,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    except Exception as error:
        logger.warning(
            "Hakoniwa memo look plan failed: %s: %s", type(error).__name__, error
        )
        raise HakoniwaError(
            "memo_look_failed",
            "世界のメモが姿に関わるかを確かめられませんでした。もう一度お試しください",
        ) from error
    if not output.changes_look:
        return "", None
    tags = clean_look_tags(output.appearance_tags) or ""
    return tags, output.body_gender


async def generate_rule_look_tags(
    name: str, text: str, description: str, *, novelai_model: str | None
) -> str | None:
    """自作の掟(と見た目の説明)から、見た目のタグを作る。失敗したら None。"""
    system_prompt, user_prompt = rule_look_tags_prompts(name, text, description)
    for _ in range(HAKONIWA_CONVERT_TAGS_MAX_ATTEMPTS):
        try:
            raw = await _generate_text(
                system_prompt, user_prompt, novelai_model=novelai_model, max_tokens=200
            )
        except Exception as error:
            logger.warning(
                "Hakoniwa rule look tags failed: %s: %s", type(error).__name__, error
            )
            continue
        tags = clean_look_tags(raw)
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
    reality: bool = False,
) -> dict[str, Any]:
    """変身の直後の反応の出来事。失敗したら定型の反応にする。

    reality=True は住民の改変の直後で、昔からそうだったように過ごす一場面にする。
    """
    group = (target, *bystanders)
    names = [resident_name(resident, language) for resident in group]
    system_prompt, user_prompt = transform_reaction_prompts(
        state, target, change_text, bystanders, language, nsfw=nsfw, reality=reality
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
    return transform_reaction_template(target, bystanders, language, reality=reality)


async def generate_confrontation_event(
    state: dict[str, Any],
    language: str,
    *,
    novelai_model: str | None,
    nsfw: bool,
) -> dict[str, Any] | None:
    """住民が書き手へ呼びかける対面の出来事。失敗したら定型。住民が2人未満なら None。"""
    pair = story.confrontation_pair(state)
    if pair is None:
        return None
    names = [resident_name(resident, language) for resident in pair]
    system_prompt, user_prompt = confrontation_prompts(state, pair, language, nsfw=nsfw)

    async def generate(system: str, user: str) -> str:
        return await _generate_text(system, user, novelai_model=novelai_model)

    try:
        output = await generate_validated(
            EventOutput,
            generate=generate,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context={"names": names},
        )
        event = _event_from_output(output, pair, language)
    except Exception as error:
        logger.warning(
            "Hakoniwa confrontation generation failed: %s: %s",
            type(error).__name__,
            error,
        )
        template = HAKONIWA_TEMPLATES[_lang(language)]["confrontation"][0]
        event = _instantiate(template, {"a": pair[0], "b": pair[1]}, language)
    event["kind"] = "confrontation"
    event["area"] = pair[0].get("current_area")
    return event


# 場面のタグの個数の上限
SCENE_TAGS_MAX_COUNT = 12


class _SceneTagsOutput(BaseModel):
    tags: str = Field(min_length=1)
    attire: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class SceneTags:
    """場面の絵の動作・構図のタグと、住民 id ごとのその場面での服装。"""

    tags: str
    attire: dict[str, str]


async def convert_scene_to_tags(
    event: dict[str, Any],
    names: dict[str, str],
    area_label: str,
    *,
    novelai_model: str | None,
    nsfw: bool = False,
) -> SceneTags | None:
    """出来事の山場の動作・表情・構図のタグと、参加者ごとの場面の服装を作る。

    失敗したら None(呼び出し側が定型のタグ・いまの服にする)。服装は一覧にある id だけを残す。
    """
    system_prompt, user_prompt = scene_tags_prompts(event, names, area_label, nsfw=nsfw)

    async def generate(system: str, user: str) -> str:
        return await _generate_text(
            system, user, novelai_model=novelai_model, max_tokens=400
        )

    try:
        output = await generate_validated(
            _SceneTagsOutput,
            generate=generate,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    except Exception as error:
        logger.warning(
            "Hakoniwa scene tags failed: %s: %s", type(error).__name__, error
        )
        return None
    tags = clean_tags(output.tags)
    if not tags:
        return None
    id_by_name = {
        _norm_name(names.get(str(resident_id), "")): str(resident_id)
        for resident_id in event.get("participants") or []
    }
    attire = {
        id_by_name[_norm_name(name)]: str(value).strip()
        for name, value in output.attire.items()
        if _norm_name(name) in id_by_name
        and str(value).strip() in HAKONIWA_SCENE_ATTIRES
    }
    return SceneTags(", ".join(tags.split(", ")[:SCENE_TAGS_MAX_COUNT]), attire)


# --- タッチ ---


def touch_tone(state: dict[str, Any], resident: dict[str, Any], part: str) -> str:
    """定型の反応の調子。胸・腰は 男性の戸惑い → 際どい姿 → 機嫌が良い → 通常 の順。"""
    if part != "head":
        if is_male_in_feminine_form(state, resident):
            return "confused"
        if appearance_is_risque(state, resident):
            return "risque"
        if int(resident.get("mood") or 50) >= TOUCH_TOLERANT_MOOD:
            return "tolerant"
        return "standard"
    return "confused" if is_male_in_feminine_form(state, resident) else "standard"


def touch_reaction_template(
    state: dict[str, Any],
    resident: dict[str, Any],
    part: str,
    language: str,
    rng: random.Random,
) -> str:
    pools = TOUCH_REACTION_TEMPLATES[_lang(language)]
    pool = (
        pools.get((part, touch_tone(state, resident, part)))
        or pools[(part, "standard")]
    )
    return rng.choice(pool)


async def generate_touch_reaction(
    state: dict[str, Any],
    resident: dict[str, Any],
    part: str,
    language: str,
    rng: random.Random,
    *,
    novelai_model: str | None,
    nsfw: bool,
) -> dict[str, str]:
    """触られた住民のその場の一言。失敗したら定型。"""
    system_prompt, user_prompt = touch_prompts(
        state, resident, part, language, nsfw=nsfw
    )
    try:
        raw = await _generate_text(
            system_prompt, user_prompt, novelai_model=novelai_model, max_tokens=300
        )
        cleaned = _clean_greeting(raw)
        if cleaned:
            return {"text": normalize_output(cleaned, language), "source": "llm"}
    except Exception as error:
        logger.warning(
            "Hakoniwa touch reaction failed: %s: %s", type(error).__name__, error
        )
    return {
        "text": touch_reaction_template(state, resident, part, language, rng),
        "source": "template",
    }


# --- 会話 ---


def _clean_chat_reply(raw: str) -> str | None:
    text = re.sub(r"^```\w*\s*|\s*```$", "", str(raw or "").strip()).strip()
    if not text or text.startswith(("{", "[")):
        return None
    if text[0] in '「“"' and text[-1] in '」”"':
        text = text[1:-1].strip()
    if not text or len(text) > HAKONIWA_CHAT_REPLY_MAX:
        return None
    return text


def chat_fallback(resident: dict[str, Any], language: str, rng: random.Random) -> str:
    if rng.random() < 0.5:
        return greeting_fallback(resident, language, rng)
    return rng.choice(CHAT_FALLBACKS[_lang(language)])


async def generate_chat_reply(
    state: dict[str, Any],
    resident: dict[str, Any],
    history: list[dict[str, Any]],
    message: str,
    language: str,
    rng: random.Random,
    *,
    novelai_model: str | None,
    nsfw: bool,
) -> dict[str, str]:
    """住民本人としての会話の返事。失敗したら定型の相槌。"""
    system_prompt, user_prompt = chat_reply_prompts(
        state, resident, history, message, language, nsfw=nsfw
    )
    try:
        raw = await _generate_text(
            system_prompt, user_prompt, novelai_model=novelai_model, max_tokens=600
        )
        cleaned = _clean_chat_reply(raw)
        if cleaned:
            return {"text": normalize_output(cleaned, language), "source": "llm"}
    except Exception as error:
        logger.warning(
            "Hakoniwa chat reply failed: %s: %s", type(error).__name__, error
        )
    return {"text": chat_fallback(resident, language, rng), "source": "template"}


def _parse_alteration(raw: str, message: str) -> dict[str, str] | None:
    match = re.search(r"\{.*\}", str(raw or ""), flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("action") not in (
        "transform",
        "clear",
        "none",
    ):
        return None
    instruction = str(data.get("instruction") or "").strip() or message
    if data["action"] == "none":
        return {"action": "none", "instruction": ""}
    return {
        "action": str(data["action"]),
        "instruction": instruction[:HAKONIWA_CHAT_MESSAGE_MAX],
    }


async def classify_chat_alteration(
    state: dict[str, Any],
    resident: dict[str, Any],
    message: str,
    language: str,
    *,
    novelai_model: str | None,
) -> dict[str, str]:
    """会話文が変身・元に戻す指示かを判定する。

    はっきりした言い回しは規則で決め、姿や服に触れているのに決まらない文だけを、
    同じプロバイダで分類させる。分類できなければ通常の会話として扱う(誤って画像を
    生成しないため)。
    """
    detected = play.detect_chat_alteration(message)
    if detected["action"] != "none" or not play.alteration_candidate(message):
        return detected
    look = current_appearance_summary(state, resident) or "the usual look"
    system_prompt, user_prompt = alteration_prompts(
        message, resident_name(resident, language), look
    )
    try:
        raw = await _generate_text(
            system_prompt, user_prompt, novelai_model=novelai_model, max_tokens=200
        )
    except Exception as error:
        logger.warning(
            "Hakoniwa alteration classification failed: %s: %s",
            type(error).__name__,
            error,
        )
        return {"action": "none", "instruction": ""}
    return _parse_alteration(raw, message) or {"action": "none", "instruction": ""}


# --- おまかせの住民(ランダムな住民構成) ---


class _RandomResident(BaseModel):
    name: str = Field(min_length=1)
    gender: str
    age: str = ""
    job: str = ""
    personality: str = Field(min_length=1)
    pronoun: str = ""
    address_style: str = ""
    appearance: str = Field(min_length=1)
    appearance_tags: str = ""

    @field_validator("gender")
    @classmethod
    def _gender(cls, gender: str) -> str:
        if gender not in ("female", "male"):
            raise ValueError("gender must be 'female' or 'male'")
        return gender


class RandomResidentsOutput(BaseModel):
    """生成された住民の構成。人数は context の count、名前は重複と exclude_names を禁じる。"""

    residents: list[_RandomResident] = Field(min_length=1)

    @field_validator("residents")
    @classmethod
    def _count_and_names(
        cls, residents: list[_RandomResident], info: ValidationInfo
    ) -> list[_RandomResident]:
        context = info.context or {}
        count = context.get("count")
        if count and len(residents) != count:
            raise ValueError(f"exactly {count} residents are required")
        used = {name_key(name) for name in context.get("exclude_names") or []}
        for resident in residents:
            key = name_key(resident.name)
            if key in used:
                raise ValueError(f"the name '{resident.name}' is already used")
            used.add(key)
            if context.get("language") == "ja":
                fields = (
                    resident.name,
                    resident.age,
                    resident.job,
                    resident.personality,
                    resident.appearance,
                )
                found = sorted(
                    {char for text in fields for char in text} & SIMPLIFIED_ONLY_CHARS
                )
                if found:
                    raise ValueError(
                        "write natural Japanese, not simplified Chinese "
                        f"(found {''.join(found)} in {resident.name})"
                    )
        return residents


def clean_profile(raw: dict[str, Any], language: str) -> dict[str, str]:
    """住民の定義を整える(長さ・日本語の字形・タグ)。タグが使えなければ空にする。"""
    gender = "male" if raw.get("gender") == "male" else "female"

    def text(key: str, limit: int) -> str:
        value = " ".join(str(raw.get(key) or "").split())
        return normalize_output(value, language)[:limit]

    tags = clean_tags(str(raw.get("base_tags") or raw.get("appearance_tags") or ""))
    return {
        "name": text("name", HAKONIWA_RESIDENT_NAME_MAX),
        "gender": gender,
        "age": text("age", HAKONIWA_RANDOM_AGE_MAX),
        "job": text("job", HAKONIWA_RANDOM_JOB_MAX),
        "personality": text("personality", HAKONIWA_PERSONALITY_MAX),
        "pronoun": text("pronoun", HAKONIWA_RANDOM_PRONOUN_MAX)
        or ("私" if language == "ja" else "I"),
        # 知らない値は既定のくせにする(生成のやり直しはしない)
        "address_style": clean_address_style(raw.get("address_style"))
        or HAKONIWA_ADDRESS_STYLE_DEFAULT,
        "appearance_text": text(
            "appearance_text" if raw.get("appearance_text") else "appearance",
            HAKONIWA_APPEARANCE_TEXT_MAX,
        ),
        "base_tags": ensure_gender_token(tags, gender) if tags else "",
    }


async def generate_random_resident_profiles(
    count: int,
    language: str,
    *,
    exclude_names: list[str],
    novelai_model: str | None,
) -> list[dict[str, str]] | None:
    """住民の構成をテキストモデルで作る。作れなかったら None(定型の組み立てに切り替える)。"""
    system_prompt, user_prompt = random_residents_prompts(
        count, language, exclude_names
    )

    async def generate(system: str, user: str) -> str:
        return await _generate_text(
            system, user, novelai_model=novelai_model, max_tokens=1800
        )

    try:
        output = await generate_validated(
            RandomResidentsOutput,
            generate=generate,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            context={
                "count": count,
                "exclude_names": exclude_names,
                "language": language,
            },
        )
    except Exception as error:
        logger.warning(
            "Hakoniwa random residents failed: %s: %s", type(error).__name__, error
        )
        return None
    return [clean_profile(item.model_dump(), language) for item in output.residents]
