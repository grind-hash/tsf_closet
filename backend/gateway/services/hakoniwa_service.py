"""AI箱庭の操作と永続化。

住民の気分・親密度・掟を基に1日3件の出来事を生成する。
世界ごとの状態変更、住民の一言、変身、登録キャラクターの複製を管理する。
記憶・適応と名残・物語の弧・世界の違和感(書き換えの加算と対面)もここで進める。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..consts.hakoniwa import (
    DEFAULT_AREA_ID,
    DEFAULT_BASE_TAGS,
    HAKONIWA_AREAS,
    HAKONIWA_FURNITURE,
    HAKONIWA_IMAGE_MODEL_DEFAULT,
    HAKONIWA_LOCATIONS,
    HAKONIWA_PRESET_MAP,
    HAKONIWA_PRESET_RESIDENTS,
    HAKONIWA_ROOM_BACKGROUND_URL,
    HAKONIWA_RULE_CARDS,
    HAKONIWA_WORLD_NAME_MAX,
    area_background_url,
    event_location,
    furniture_url,
    location_background_url,
    preset_bundled_avatar_url,
)
from ..consts.hakoniwa_play import (
    CHAT_ALTERATION_FAILED,
    CHAT_ALTERATION_RESULT,
    CHAT_TRANSFORM_FALLBACK,
    INTERVENTION_ADAPTATION_BONUS,
    INTERVENTION_DISSONANCE_PUSH_GAIN,
    INTERVENTION_REWRITE_DISSONANCE,
)
from ..consts.hakoniwa_story import (
    DISSONANCE_CONTINUED_EVENT_GAIN,
    DISSONANCE_CUSTOM_RULE_GAIN,
    DISSONANCE_DIRECTED_EVENT_GAIN,
    DISSONANCE_REALITY_GAIN,
    DISSONANCE_RULE_GAIN,
    DISSONANCE_TRANSFORM_GAIN,
)
from ..consts.language import normalize_language
from ..consts.novelai_models import resolve_user_image_model
from ..databases.base import async_session_factory
from ..databases.models import HakoniwaWorld
from . import hakoniwa_logic as logic
from . import hakoniwa_play as play
from . import hakoniwa_story as story
from . import hakoniwa_story_text as story_text
from . import hakoniwa_web_search as web_search
from .achievement_service import achievement_service
from .achievements import (
    ACHIEVEMENTS,
    check_achievement,
    get_global_stats,
    get_user_achievements,
)
from .cost_tracker import begin_cost_tracking
from .hakoniwa_digest import build_day_digest
from .hakoniwa_generation import (
    classify_chat_alteration,
    clean_look_tags,
    clean_manual_look_tags,
    clean_manual_tags,
    clean_profile,
    clean_tags,
    convert_change_to_tags,
    convert_scene_to_tags,
    expand_appearance_tags,
    generate_chat_reply,
    generate_confrontation_event,
    generate_directed_event,
    generate_event,
    generate_greeting,
    generate_random_resident_profiles,
    generate_rule_look_tags,
    generate_touch_reaction,
    generate_transform_reaction,
    needs_tag_expansion,
    plan_event_looks,
    plan_memo_look,
    recent_titles,
    template_event,
)
from .hakoniwa_images import (
    copy_portrait,
    delete_world_images,
    generate_avatar_bytes,
    generate_scene_bytes,
    image_model_options,
    image_path,
    image_url,
    resident_image_urls,
    resolve_image_model,
    save_image,
    transparency_mode,
)
from .hakoniwa_logic import HakoniwaError
from .hakoniwa_prompts import rule_look_instruction
from .hakoniwa_random import template_residents
from .hakoniwa_random import validate_count as random_resident_count
from .hakoniwa_reactions import rule_reactions
from .hakoniwa_scene import look_tags, scene_request, scene_suggestion
from .preset_sessions import PresetSessionError, load_preset_play_source
from .real_world_lookup import web_search_configured
from .session import DEFAULT_USER_ID, session_store

logger = logging.getLogger(__name__)

# 衣装の指定が無い住民のドレス姿を作るときの変身の指示
DEFAULT_DRESS_INSTRUCTION = (
    "Change the outfit into an elegant formal dress that suits this person. "
    "Keep the face, hair and body as they are."
)

# 住民の改変で姿も変えるときに、タグの変換へ渡す指示(改変の文は事実なので、姿への言い換えを頼む)
_REALITY_LOOK_INSTRUCTION = (
    "Change the look and outfit to what fits this new fact about the character, "
    "keeping everything the fact does not affect: {text}"
)

_TRANSFORM_EVENT_TEXT = {
    "ja": {
        "title": "{name}の変身",
        "narration": (
            "{name}の姿が、その場で変わった。変身の指定は「{change}」。"
            "新しい装いが、その姿にすっかり馴染んでいる。"
        ),
    },
    "en": {
        "title": "{name}'s Transformation",
        "narration": (
            '{name}\'s look changed on the spot. The instruction: "{change}". '
            "The new look already seems to fit."
        ),
    },
}


def _load_state(world: HakoniwaWorld) -> dict[str, Any]:
    try:
        state = json.loads(world.state_json or "{}")
    except (TypeError, ValueError):
        state = {}
    return logic.normalize_state(state if isinstance(state, dict) else {})


def _store_state(world: HakoniwaWorld, state: dict[str, Any]) -> None:
    # 観察記録のための観測の事実(有効にした掟・見たドレス姿など)は保存のたびに積む
    state = play.observe(state)
    world.state_json = json.dumps(state, ensure_ascii=False)
    world.day = int(state["day"])
    world.updated_at = datetime.now()


def _transformation_view(world_id: str, entry: dict[str, Any] | None) -> dict | None:
    if not entry:
        return None
    return {
        "description": entry.get("description", ""),
        "tags": entry.get("tags", ""),
        "image": entry.get("image", ""),
        "image_url": image_url(world_id, str(entry["image"]))
        if entry.get("image")
        else None,
        "day": int(entry.get("day") or 1),
        "kind": entry.get("kind"),
    }


def _resident_view(
    world_id: str, state: dict[str, Any], resident: dict[str, Any], language: str
) -> dict[str, Any]:
    text = logic.resident_text(resident, language)
    return {
        "id": resident["id"],
        "source": resident["source"],
        "preset_id": resident.get("preset_id"),
        "character_preset_id": resident.get("character_preset_id"),
        "name": text["name"],
        "gender": logic.resident_gender(resident),
        "body_gender": logic.body_gender(state, resident),
        "age": text["age"],
        "job": text["job"],
        "personality": text["personality"],
        "pronoun": resident.get("pronoun") or "",
        "address_style": logic.resident_address_style(resident),
        "addresses": {
            other["id"]: logic.address_name(resident, other, language)
            for other in state["residents"]
            if other["id"] != resident["id"]
        },
        "appearance_text": resident.get("appearance_text") or "",
        "base_tags": resident.get("base_tags") or "",
        "dress_text": resident.get("dress_text") or "",
        "dress_tags": resident.get("dress_tags") or "",
        "mood": int(resident["mood"]),
        "affinities": dict(resident["affinities"]),
        # 変身は体に付くので、いま入っている体の変身と履歴を出す(入れ替わり中は相手の体)
        "transformation": _transformation_view(
            world_id, logic.current_transformation(state, resident)
        ),
        "transformation_history": [
            _transformation_view(world_id, item)
            for item in logic.body_of(state, resident).get("transformation_history")
            or []
        ],
        "realities": [dict(item) for item in logic.realities(resident)],
        "swapped_with": logic.swap_partner_id(state, resident["id"]),
        "current_area": resident.get("current_area") or DEFAULT_AREA_ID,
        "adaptation": _adaptation_view(story.resident_adaptation(state, resident)),
        "world_adaptation": _adaptation_view(
            story.world_adaptation_entry(state, resident)
        ),
        "remnant": story_text.remnant_view(state, resident, language),
        "memories": story_text.memories_view(state, resident["id"], language),
        **resident_image_urls(world_id, state, resident),
    }


# 住民の編集の入力のうち、文の項目以外(画像のタグ)
_RESIDENT_TAG_FIELDS = ("base_tags", "dress_tags")


def _resident_tags_input(fields: dict[str, Any], gender: str) -> tuple[str, str]:
    """住民の保存で送られた (いつもの姿, ドレス姿) のタグを整える。

    いつもの姿は必須。ドレス姿は空なら、ドレス姿を生成するときにいつもの姿から考える。
    """
    base = str(fields.get("base_tags") or "").strip()
    if not base:
        raise HakoniwaError("tags_required", "いつもの姿のタグを入力してください")
    dress = str(fields.get("dress_tags") or "").strip()
    return (
        clean_manual_tags(base, gender),
        clean_manual_tags(dress, gender) if dress else "",
    )


def _rule_tags_input(raw: str | None) -> str:
    """掟の保存で送られた見た目のタグを整える。空なら空(見た目を変えない掟)。"""
    text = str(raw or "").strip()
    return clean_manual_look_tags(text) if text else ""


def _resident_text_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """住民の編集の入力から、validate_resident_fields に渡す文の項目だけを取り出す。"""
    return {
        key: value for key, value in fields.items() if key not in _RESIDENT_TAG_FIELDS
    }


def _random_resident_entry(raw: dict[str, Any], language: str) -> dict[str, Any]:
    """作成画面で組んだおまかせの住民を、自作の住民のエントリにする。

    タグはおまかせの住民を組んだときに作ってある。無いときは性別の既定のタグにする
    (作成では生成を呼ばない)。
    """
    profile = clean_profile(raw, language)
    return logic.custom_resident(
        name=profile["name"],
        personality=profile["personality"],
        gender=profile["gender"],
        appearance_text=profile["appearance_text"],
        base_tags=profile["base_tags"] or DEFAULT_BASE_TAGS[profile["gender"]],
        age=profile["age"],
        job=profile["job"],
        pronoun=profile["pronoun"],
        address_style=profile["address_style"],
    )


def _adaptation_view(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not entry:
        return None
    return {"kind": str(entry.get("kind") or ""), "stage": int(entry.get("stage") or 0)}


def _dissonance_view(state: dict[str, Any]) -> dict[str, Any]:
    value = story.dissonance_value(state)
    upcoming = story.next_dissonance_stage(value)
    return {
        "enabled": story.dissonance_enabled(state),
        "value": value,
        "stage": story.dissonance_stage(value),
        "acknowledged": bool(state.get("dissonance_acknowledged")),
        "next_stage": upcoming["stage"] if upcoming else None,
        "remaining": upcoming["remaining"] if upcoming else None,
    }


def _arcs_view(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(arc.get("id") or ""),
            "kind": str(arc.get("kind") or ""),
            "resident_ids": list(arc.get("resident_ids") or []),
            "progress": int(arc.get("progress") or 0),
            "beats_to_climax": int(arc.get("beats_to_climax") or 0),
            "status": str(arc.get("status") or "closed"),
            "started_day": int(arc.get("started_day") or 1),
            "closed_day": arc.get("closed_day"),
            "close_reason": arc.get("close_reason"),
        }
        for arc in state.get("story_arcs") or []
    ]


def _rule_cards_view(state: dict[str, Any], language: str) -> list[dict[str, Any]]:
    lang = "ja" if language == "ja" else "en"
    active = state.get("active_rules", [])
    cards = [
        {
            "id": card["id"],
            "name": card["text"][lang]["name"],
            "description": card["text"][lang]["description"],
            "custom": False,
            "active": card["id"] in active,
            "synergies": play.card_synergies(state, card["id"], language),
        }
        for card in HAKONIWA_RULE_CARDS
    ]
    cards.extend(
        {
            "id": rule["id"],
            "name": rule["name"],
            "description": rule["text"],
            "custom": True,
            "active": rule["id"] in active,
            "appearance_text": rule.get("appearance_text") or "",
            "appearance_tags": rule.get("appearance_tags") or "",
            "body_gender": logic.rule_body_gender(rule),
            "look": logic.rule_look_status(state, rule["id"]),
        }
        for rule in state.get("custom_rules", [])
    )
    return cards


def _combo_look_view(state: dict[str, Any]) -> dict[str, Any] | None:
    """いま重なっている見た目の掟(複合の姿の対象)と、その生成状況。"""
    combo = logic.active_combo(state)
    if combo is None:
        return None
    rules = [logic.custom_rule(state, rule_id) or {} for rule_id in combo["rule_ids"]]
    return {
        "rule_ids": combo["rule_ids"],
        "names": [str(rule.get("name") or "") for rule in rules],
        "includes_dress": combo["includes_dress"],
        **logic.combo_look_status(state, combo),
    }


def _memo_look_view(state: dict[str, Any]) -> dict[str, Any] | None:
    """世界のメモが住民全員に与える姿と、その生成状況(メモが姿を変えていなければ None)。"""
    look = logic.active_memo_look(state)
    status = logic.memo_look_status(state)
    if look is None or status is None:
        return None
    return {"tags": look["tags"], "body_gender": look["body_gender"], **status}


def _unlock_hakoniwa_achievements() -> list[dict[str, Any]]:
    """条件を満たした AI箱庭の観察記録を保存し、通知用に返す(新しく達成した分だけ)。

    判定に失敗しても世界の表示は止めない(次に世界を返すときに改めて判定される)。
    """
    try:
        already = {
            status.achievement_id
            for status in get_user_achievements()
            if status.unlocked
        }
        stats = get_global_stats()
        unlocked = []
        for achievement in ACHIEVEMENTS.values():
            if achievement.category != "hakoniwa" or achievement.id in already:
                continue
            if not check_achievement(achievement, stats):
                continue
            achievement_service.save_user_achievement(achievement.id)
            unlocked.append(
                {
                    "achievement_id": achievement.id,
                    "name": achievement.name,
                    "description": achievement.description,
                    "icon": achievement.icon,
                    "category": achievement.category,
                }
            )
        return unlocked
    except Exception as error:
        logger.warning(
            "Hakoniwa achievement check failed: %s: %s", type(error).__name__, error
        )
        return []


def _world_view(
    world: HakoniwaWorld,
    state: dict[str, Any],
    language: str,
    user_settings: dict[str, Any],
) -> dict[str, Any]:
    """世界の表示。

    世界を返すのはいつも保存(commit)のあとなので、ここで観察記録を判定し、
    新しく達成した分を new_achievements で返す(すべての書き換えと、世界を開いたときに拾う)。
    """
    nsfw_mode = bool(user_settings.get("nsfw_mode"))
    effective_model = resolve_image_model(state, user_settings)
    return {
        "new_achievements": _unlock_hakoniwa_achievements(),
        "id": world.id,
        "name": world.name,
        "day": int(state["day"]),
        "created_at": world.created_at.isoformat() if world.created_at else None,
        "updated_at": world.updated_at.isoformat() if world.updated_at else None,
        "background_url": HAKONIWA_ROOM_BACKGROUND_URL,
        "image_model": state.get("image_model") or HAKONIWA_IMAGE_MODEL_DEFAULT,
        "web_search_enabled": state.get("web_search_enabled") is True,
        "web_search_configured": web_search_configured(),
        "image_model_effective": effective_model,
        "image_model_default": resolve_user_image_model(user_settings, nsfw_mode),
        "image_model_options": list(image_model_options(nsfw_mode)),
        "transparency": transparency_mode(effective_model),
        "active_rules": list(state.get("active_rules", [])),
        "swap_pair": state.get("swap_pair"),
        "rule_cards": _rule_cards_view(state, language),
        "residents": [
            _resident_view(world.id, state, resident, language)
            for resident in state["residents"]
        ],
        "events": [_event_view(world.id, event, language) for event in state["events"]],
        "areas": _areas_view(state, language),
        "locations": [
            {
                "id": location["id"],
                "name": location["name"]["ja" if language == "ja" else "en"],
                "background_url": location_background_url(location["id"]),
            }
            for location in HAKONIWA_LOCATIONS
        ],
        "last_digest": state.get("last_digest"),
        "dissonance": _dissonance_view(state),
        "story_arcs": _arcs_view(state),
        "combo_look": _combo_look_view(state),
        "memo_look": _memo_look_view(state),
        "memo_look_planned": logic.memo_look_planned(state),
        "world_memo": play.world_memo(state),
        "player_name": play.player_name(state),
        "experiment_theme": play.experiment_theme(state),
        "intervention": {
            "selected": state.get("intervention") or "watch",
            "choices": play.available_interventions(state),
        },
        "furniture_catalog": [
            {
                "id": item["id"],
                "name": item["name"]["ja" if language == "ja" else "en"],
                "url": furniture_url(item["id"]),
            }
            for item in HAKONIWA_FURNITURE
        ],
    }


def _areas_view(state: dict[str, Any], language: str) -> list[dict[str, Any]]:
    layout = state.get("furniture_layout") or {}
    key = "ja" if language == "ja" else "en"
    return [
        {
            "id": area["id"],
            "name": area["name"][key],
            "background_url": area_background_url(area["id"]),
            "slots": [
                {
                    "x": x,
                    "y": y,
                    "furniture_id": (layout.get(area["id"]) or [None] * 4)[index],
                }
                for index, (x, y) in enumerate(area["slots"])
            ],
        }
        for area in HAKONIWA_AREAS
    ]


def _event_view(world_id: str, event: dict[str, Any], language: str) -> dict[str, Any]:
    """年代記の出来事に、場面絵の URL と場面絵の提案を足す。"""
    view = dict(event)
    view.setdefault("area", DEFAULT_AREA_ID)
    scene = event.get("scene_image")
    view["scene_image_url"] = image_url(world_id, str(scene)) if scene else None
    view["scene_suggestion"] = scene_suggestion(event, language)
    return view


def _world_summary(world: HakoniwaWorld, language: str) -> dict[str, Any]:
    state = _load_state(world)
    previews = []
    for resident in state["residents"][:6]:
        urls = resident_image_urls(world.id, state, resident)
        previews.append(
            {
                "id": resident["id"],
                "name": logic.resident_name(resident, language),
                "avatar_url": urls["display_avatar_url"],
            }
        )
    return {
        "id": world.id,
        "name": world.name,
        "day": int(state["day"]),
        "resident_count": len(state["residents"]),
        "event_count": len(state["events"]),
        "created_at": world.created_at.isoformat() if world.created_at else None,
        "updated_at": world.updated_at.isoformat() if world.updated_at else None,
        "residents": previews,
    }


def _source_base_tags(resident: dict[str, Any]) -> str:
    """外見の説明が空のときに使う画像タグ(プリセット・キャラクターの元のタグ)。"""
    preset = HAKONIWA_PRESET_MAP.get(str(resident.get("preset_id") or ""))
    if preset is not None:
        return str(preset["base_tags"])
    if resident.get("source_base_tags"):
        return str(resident["source_base_tags"])
    return DEFAULT_BASE_TAGS[logic.resident_gender(resident)]


def _resident_line(events: list[dict[str, Any]], resident_id: str) -> str:
    """変身の反応の出来事から、本人の台詞を1つ取り出す(会話の返事に使う)。"""
    for event in events:
        if event.get("kind") == "transform":
            continue
        for line in event.get("lines") or []:
            if line.get("speaker") == resident_id and line.get("text"):
                return str(line["text"])
    return ""


class HakoniwaService:
    def __init__(self) -> None:
        self._world_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ------------------------------------------------------------------
    # 共通
    # ------------------------------------------------------------------

    @staticmethod
    async def _context(language: str | None) -> tuple[str, dict[str, Any]]:
        user_settings = await session_store.get_user_settings()
        lang = normalize_language(language or user_settings.get("language"))
        return lang, user_settings

    @staticmethod
    async def _load(db: Any, world_id: str) -> HakoniwaWorld:
        world = await db.get(HakoniwaWorld, world_id)
        if world is None or world.user_id != DEFAULT_USER_ID:
            raise HakoniwaError("world_not_found", "世界が見つかりません")
        return world

    async def _mutate(
        self,
        world_id: str,
        language: str | None,
        change: Any,
    ) -> dict[str, Any]:
        """状態を読み、change(state) -> state で書き換えて保存し、世界の表示を返す。"""
        lang, user_settings = await self._context(language)
        async with self._world_locks[world_id], async_session_factory() as db:
            world = await self._load(db, world_id)
            state = change(_load_state(world))
            _store_state(world, state)
            await db.commit()
            return _world_view(world, state, lang, user_settings)

    # ------------------------------------------------------------------
    # カタログ・一覧
    # ------------------------------------------------------------------

    async def catalog(self, language: str | None = None) -> dict[str, Any]:
        lang, user_settings = await self._context(language)
        key = "ja" if lang == "ja" else "en"
        return {
            "presets": [
                {
                    "id": preset["id"],
                    "gender": preset["gender"],
                    **{
                        field: preset["text"][key][field]
                        for field in ("name", "age", "job", "personality")
                    },
                    "avatar_url": preset_bundled_avatar_url(preset["id"]),
                    "dress_avatar_url": preset_bundled_avatar_url(
                        preset["id"], dress=True
                    ),
                }
                for preset in HAKONIWA_PRESET_RESIDENTS
            ],
            "rule_cards": [
                {
                    "id": card["id"],
                    "name": card["text"][key]["name"],
                    "description": card["text"][key]["description"],
                }
                for card in HAKONIWA_RULE_CARDS
            ],
            "background_url": HAKONIWA_ROOM_BACKGROUND_URL,
            "image_model_options": list(
                image_model_options(bool(user_settings.get("nsfw_mode")))
            ),
        }

    async def list_worlds(self, language: str | None = None) -> list[dict[str, Any]]:
        lang, _ = await self._context(language)
        async with async_session_factory() as db:
            worlds = (
                await db.execute(
                    select(HakoniwaWorld)
                    .where(HakoniwaWorld.user_id == DEFAULT_USER_ID)
                    .order_by(HakoniwaWorld.updated_at.desc())
                )
            ).scalars()
            return [_world_summary(world, lang) for world in worlds]

    async def get_world(self, world_id: str, language: str | None = None) -> dict:
        lang, user_settings = await self._context(language)
        async with async_session_factory() as db:
            world = await self._load(db, world_id)
            return _world_view(world, _load_state(world), lang, user_settings)

    # ------------------------------------------------------------------
    # 世界の作成・削除・設定
    # ------------------------------------------------------------------

    async def _character_resident(
        self, world_id: str, character_preset_id: str, gender: str | None
    ) -> dict[str, Any]:
        try:
            source = await load_preset_play_source(character_preset_id)
        except PresetSessionError as error:
            raise HakoniwaError(error.code, str(error)) from error
        profile = source.profile
        resolved_gender = gender or {"man": "male", "woman": "female"}.get(
            str(profile.get("gender") or "")
        )
        if resolved_gender not in ("male", "female"):
            raise HakoniwaError(
                "gender_required", "このキャラクターの性別を選んでください"
            )
        resident = logic.character_resident(
            character_preset_id, profile, gender=resolved_gender, avatar_image=None
        )
        resident["source_base_tags"] = resident["base_tags"]
        resident["avatar_image"] = copy_portrait(
            world_id, resident["id"], Path(source.image_path)
        )
        return resident

    async def create_world(
        self,
        name: str,
        preset_ids: list[str],
        characters: list[dict[str, Any]],
        language: str | None = None,
        *,
        dissonance_enabled: bool = True,
        custom_residents: list[dict[str, Any]] | None = None,
        experiment_theme: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """プリセットの住民・登録キャラクター・おまかせの住民で新しい世界を作る。

        おまかせの住民(custom_residents)は作成画面で組んだ定義。英語のタグが無ければ
        外見の説明から順に作る(並列にしない)。experiment_theme は {preset_id, text}。
        """
        clean_name = " ".join(str(name or "").split())[:HAKONIWA_WORLD_NAME_MAX]
        if not clean_name:
            raise HakoniwaError("empty_name", "世界の名前を入力してください")
        theme = (
            play.validate_theme(
                experiment_theme.get("preset_id"), experiment_theme.get("text")
            )
            if experiment_theme
            else None
        )
        lang, user_settings = await self._context(language)
        world_id = str(uuid.uuid4())
        try:
            residents = [logic.preset_resident(preset_id) for preset_id in preset_ids]
            seen: set[str] = set()
            for item in characters:
                character_id = str(item.get("character_preset_id") or "")
                if not character_id or character_id in seen:
                    continue
                seen.add(character_id)
                residents.append(
                    await self._character_resident(
                        world_id, character_id, item.get("gender")
                    )
                )
            residents.extend(
                _random_resident_entry(item, lang) for item in custom_residents or []
            )
            state = logic.new_world_state(
                residents, dissonance_enabled=dissonance_enabled
            )
            state["experiment_theme"] = theme
        except HakoniwaError:
            delete_world_images(world_id)
            raise
        now = datetime.now()
        world = HakoniwaWorld(
            id=world_id,
            user_id=DEFAULT_USER_ID,
            name=clean_name,
            day=1,
            state_json="{}",
            created_at=now,
            updated_at=now,
        )
        _store_state(world, state)
        async with async_session_factory() as db:
            db.add(world)
            await db.commit()
            await db.refresh(world)
            return _world_view(world, state, lang, user_settings)

    async def random_residents(
        self,
        count: int,
        exclude_names: list[str],
        language: str | None = None,
    ) -> dict[str, Any]:
        """おまかせの住民の構成を作る(状態は変えない)。

        テキストモデルで作り、作れなければ語彙の組み合わせで組み立てる。どの住民にも
        英語のタグを付けて返す(作成では生成を呼ばない)。
        """
        count = random_resident_count(count)
        exclude = [str(name) for name in exclude_names if str(name or "").strip()]
        lang, user_settings = await self._context(language)
        novelai_model = user_settings.get("novelai_text_model")
        tracker = begin_cost_tracking()
        profiles = await generate_random_resident_profiles(
            count, lang, exclude_names=exclude, novelai_model=novelai_model
        )
        source = "llm"
        if profiles is None:
            profiles = template_residents(count, lang, random.Random(), exclude)
            source = "template"
        for profile in profiles:
            if profile["base_tags"]:
                continue
            # タグが使えなかった住民だけ、外見の説明から順に作る(並列にしない)
            tags, _failed = await self._derive_tags(
                profile["appearance_text"] if lang == "ja" else "",
                profile["gender"],
                dress=False,
                fallback=DEFAULT_BASE_TAGS[profile["gender"]],
                novelai_model=novelai_model,
            )
            profile["base_tags"] = tags
        return {
            "residents": profiles,
            "source": source,
            "cost_usd": tracker.total_usd or None,
        }

    async def delete_world(self, world_id: str) -> None:
        async with self._world_locks[world_id], async_session_factory() as db:
            world = await self._load(db, world_id)
            await db.delete(world)
            await db.commit()
        delete_world_images(world_id)
        self._world_locks.pop(world_id, None)

    async def update_settings(
        self,
        world_id: str,
        *,
        image_model: str | None = None,
        dissonance_enabled: bool | None = None,
        web_search_enabled: bool | None = None,
        world_memo: str | None = None,
        experiment_theme: dict[str, Any] | None = None,
        player_name: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """世界の設定(画像モデル・Web検索・世界の違和感・メモ・実験テーマ・プレイヤーの名前)。

        None の項目は変えない。実験テーマは {preset_id, text}。どちらも空ならテーマ無しにする。
        """
        memo = play.validate_world_memo(world_memo) if world_memo is not None else None
        name = (
            play.validate_player_name(player_name) if player_name is not None else None
        )
        theme = (
            play.validate_theme(
                experiment_theme.get("preset_id"), experiment_theme.get("text")
            )
            if experiment_theme is not None
            else None
        )
        _, user_settings = await self._context(language)
        options = image_model_options(bool(user_settings.get("nsfw_mode")))
        if (
            image_model is not None
            and image_model != HAKONIWA_IMAGE_MODEL_DEFAULT
            and image_model not in options
        ):
            raise HakoniwaError("invalid_image_model", "選べない画像モデルです")

        def change(state: dict[str, Any]) -> dict[str, Any]:
            updated = dict(state)
            if image_model is not None:
                updated["image_model"] = image_model
            if dissonance_enabled is not None:
                updated["dissonance_enabled"] = bool(dissonance_enabled)
            if web_search_enabled is not None:
                updated["web_search_enabled"] = web_search_enabled
            if memo is not None:
                updated["world_memo"] = memo
            if experiment_theme is not None:
                updated["experiment_theme"] = theme
            if name is not None:
                updated["player_name"] = name
            return updated

        return await self._mutate(world_id, language, change)

    async def _apply_dissonance_gain(
        self,
        state: dict[str, Any],
        amount: int,
        language: str,
        user_settings: dict[str, Any],
        rng: random.Random,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """書き換えで違和感を溜め、到達点に達したら対面の出来事を一度だけ積む。"""
        state = story.add_dissonance(state, amount)
        if not story.confrontation_pending(state):
            return state, []
        event = await generate_confrontation_event(
            state,
            language,
            novelai_model=user_settings.get("novelai_text_model"),
            nsfw=bool(user_settings.get("nsfw_mode")),
        )
        if event is None:
            return state, []
        state = logic.apply_event(state, event, rng)
        record = state["events"][-1]
        return story.resolve_confrontation(state), [record]

    # ------------------------------------------------------------------
    # 1日進める
    # ------------------------------------------------------------------

    async def advance_day(
        self, world_id: str, language: str | None = None
    ) -> dict[str, Any]:
        """その日の出来事を3件作って適用し、日を1つ進める。

        3件は開始時点の状態から並列に生成し(NovelAI は実行ゲートで直列になる)、順に適用する。
        """
        lang, user_settings = await self._context(language)
        novelai_model = user_settings.get("novelai_text_model")
        nsfw = bool(user_settings.get("nsfw_mode"))
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                world = await self._load(db, world_id)
                state = _load_state(world)
            tracker = begin_cost_tracking()
            rng = random.Random()
            before = state
            # 物語の弧: 前提の消えた弧を閉じ、条件を満たす新しい弧を立てる
            state = story.refresh_story_arcs(state)
            # プレイヤーの介入: 選んでおいた介入をこの日に効かせ、見守るに戻す
            intervention = play.pending_intervention(state)
            state = {**state, "intervention": "watch"}
            new_events: list[dict[str, Any]] = []
            if intervention in ("rewrite", "dissonance_push"):
                gain = (
                    INTERVENTION_REWRITE_DISSONANCE
                    if intervention == "rewrite"
                    else INTERVENTION_DISSONANCE_PUSH_GAIN
                )
                state, new_events = await self._apply_dissonance_gain(
                    state, gain, lang, user_settings, rng
                )
            elif intervention == "arc_boost":
                state = play.boost_arc_relationships(state)
            groups = logic.choose_groups(state, rng)
            areas = [logic.pick_event_area(state, group, rng) for group in groups]
            focus = logic.custom_rule_focus_assignments(state, groups)
            arc_focus = story.arc_focus_assignments(state, groups)
            titles = recent_titles(state)
            names = [
                [logic.resident_name(resident, lang) for resident in group]
                for group in groups
            ]
            # 自由文の実験テーマは、その日の出来事のうち1件だけに渡す(全部が染まらないように)
            theme_index = (
                rng.randrange(len(groups))
                if play.theme_text(state) and groups
                else None
            )
            news_index = web_search.choose_news_index(
                state, groups, focus, arc_focus, theme_index, rng
            )
            events = await asyncio.gather(
                *(
                    generate_event(
                        state,
                        group,
                        lang,
                        random.Random(rng.random()),
                        novelai_model=novelai_model,
                        nsfw=nsfw,
                        rule_focus_rule_id=focus.get(index),
                        others_today=[
                            item for other, item in enumerate(names) if other != index
                        ],
                        recent_titles=titles,
                        area_id=areas[index],
                        arc_focus_id=(arc_focus.get(index) or {}).get("arc_id"),
                        arc_climax=bool((arc_focus.get(index) or {}).get("climax")),
                        intervention=intervention,
                        include_theme=index == theme_index,
                        use_web_search=index == news_index,
                    )
                    for index, group in enumerate(groups)
                )
            )
            used_titles = set(titles)
            for index, (group, area_id, event) in enumerate(
                zip(groups, areas, events, strict=True)
            ):
                if event.get("source") == "template" and event["title"] in used_titles:
                    # 並列に選んだ定型が同じ日に重ならないよう選び直す
                    search_metadata = event.get("web_search")
                    event = template_event(
                        state, group, lang, rng, recent_titles=used_titles
                    )
                    event["area"] = area_id
                    if search_metadata:
                        event["web_search"] = search_metadata
                used_titles.add(event["title"])
                assignment = arc_focus.get(index)
                if assignment:
                    event["arc_id"] = assignment["arc_id"]
                    event["arc_climax"] = bool(assignment["climax"]) or None
                state = logic.apply_event(state, event, rng)
                record = state["events"][-1]
                if assignment:
                    state = story.record_arc_event(
                        state, assignment["arc_id"], record, assignment["climax"]
                    )
                new_events.append(record)
            # 日の終わり: 適応が進み、名残は薄れ、書き換えの無い日は違和感が静まる
            state, adaptations = story.advance_adaptations(
                state,
                bonus=INTERVENTION_ADAPTATION_BONUS
                if intervention in ("nudge", "adaptation_care")
                else 0.0,
            )
            state, world_adaptations = story.advance_world_adaptations(state)
            state = story.decay_remnants(state)
            state = story.decay_dissonance(state)
            state = play.record_theme_day(state)
            closing = state
            state = logic.finish_day(state, rng)
            digest = build_day_digest(
                before,
                closing,
                new_events,
                adaptations=adaptations,
                world_adaptations=world_adaptations,
                intervention=intervention,
                theme=play.theme_progress(closing),
            )
            state["last_digest"] = digest
            async with async_session_factory() as db:
                world = await self._load(db, world_id)
                _store_state(world, state)
                await db.commit()
                view = _world_view(world, state, lang, user_settings)
        return {
            "world": view,
            "new_events": [_event_view(world_id, event, lang) for event in new_events],
            "digest": digest,
            "cost_usd": tracker.total_usd or None,
        }

    # ------------------------------------------------------------------
    # 掟
    # ------------------------------------------------------------------

    async def set_rule(
        self,
        world_id: str,
        card_id: str,
        active: bool,
        language: str | None = None,
        *,
        area_id: str | None = None,
    ) -> dict[str, Any]:
        """掟を切り替える。書き換えで違和感が溜まり、到達点なら対面の出来事が起きる。

        切り替え直後の住民の反応(定型文)も返す。話し手は見ている場所(area_id)を優先する。
        """
        lang, user_settings = await self._context(language)
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                world = await self._load(db, world_id)
                before = _load_state(world)
            tracker = begin_cost_tracking()
            rng = random.Random()
            state = logic.set_rule(before, card_id, active, rng)
            reaction = rule_reactions(
                before, state, card_id, active, lang, area_id, rng
            )
            new_events: list[dict[str, Any]] = []
            if state["active_rules"] != before["active_rules"]:
                state = story.record_rule_toggle_memories(
                    state, card_id, active, before.get("swap_pair")
                )
                custom = card_id in logic.custom_rule_ids(state)
                gain = (
                    DISSONANCE_CUSTOM_RULE_GAIN
                    if active and custom
                    else DISSONANCE_RULE_GAIN
                )
                state, new_events = await self._apply_dissonance_gain(
                    state, gain, lang, user_settings, rng
                )
            async with async_session_factory() as db:
                world = await self._load(db, world_id)
                _store_state(world, state)
                await db.commit()
                view = _world_view(world, state, lang, user_settings)
        return {
            "world": view,
            "new_events": [_event_view(world_id, event, lang) for event in new_events],
            "reaction": (
                {"card_id": card_id, "active": active, **reaction} if reaction else None
            ),
            "cost_usd": tracker.total_usd or None,
        }

    async def make_rule_look_tags(
        self,
        name: str,
        text: str,
        appearance_text: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """掟の名前・本文・見た目の説明から、見た目のタグを作って返す(保存はしない)。

        見た目の説明が英語のタグならそのまま整え、日本語の文章か空なら LLM に考えさせる。
        """
        _, user_settings = await self._context(language)
        name, text, description = (
            str(value or "").strip() for value in (name, text, appearance_text)
        )
        if not text and not description:
            raise HakoniwaError(
                "look_source_empty", "先に掟の本文か見た目の説明を書いてください"
            )
        tracker = begin_cost_tracking()
        if description and not needs_tag_expansion(description):
            tags = clean_look_tags(description)
        else:
            tags = await generate_rule_look_tags(
                name,
                text,
                description,
                novelai_model=user_settings.get("novelai_text_model"),
            )
        if not tags:
            raise HakoniwaError("tags_failed", "見た目のタグを作れませんでした")
        return {"tags": tags, "cost_usd": tracker.total_usd or None}

    async def make_resident_tags(
        self,
        appearance_text: str,
        gender: str,
        *,
        dress: bool = False,
        language: str | None = None,
    ) -> dict[str, Any]:
        """住民の外見(dress ならドレス姿)の説明から画像タグを作って返す(保存はしない)。"""
        _, user_settings = await self._context(language)
        description = str(appearance_text or "").strip()
        if not description:
            raise HakoniwaError("look_source_empty", "先に説明を書いてください")
        tracker = begin_cost_tracking()
        if needs_tag_expansion(description):
            tags = await expand_appearance_tags(
                description,
                gender,
                dress=dress,
                novelai_model=user_settings.get("novelai_text_model"),
            )
        else:
            tags = clean_tags(description)
        if not tags:
            raise HakoniwaError("tags_failed", "見た目のタグを作れませんでした")
        # 性別は住民の性別で決める(変換が逆の性別を書いても直す)
        return {
            "tags": logic.set_gender_token(tags, gender),
            "cost_usd": tracker.total_usd or None,
        }

    async def add_custom_rule(
        self,
        world_id: str,
        name: str,
        text: str,
        appearance_text: str = "",
        language: str | None = None,
        appearance_tags: str = "",
        body_gender: str | None = None,
    ) -> dict[str, Any]:
        """掟を書く。見た目のタグは書かれたものを整えて使う(空なら見た目を変えない)。"""
        tags = _rule_tags_input(appearance_tags)
        return await self._mutate(
            world_id,
            language,
            lambda state: logic.add_custom_rule(
                state,
                name,
                text,
                appearance_text,
                appearance_tags=tags,
                body_gender=body_gender,
            ),
        )

    async def update_custom_rule(
        self,
        world_id: str,
        rule_id: str,
        name: str,
        text: str,
        appearance_text: str = "",
        language: str | None = None,
        appearance_tags: str = "",
        body_gender: str | None = None,
    ) -> dict[str, Any]:
        """掟を編集する。見た目のタグは書かれたものを整えて使う(空なら見た目を変えない)。"""
        tags = _rule_tags_input(appearance_tags)
        return await self._mutate(
            world_id,
            language,
            lambda state: logic.update_custom_rule(
                state,
                rule_id,
                name,
                text,
                appearance_text,
                appearance_tags=tags,
                body_gender=body_gender,
            ),
        )

    async def _generate_look_images(
        self,
        world_id: str,
        state: dict[str, Any],
        user_settings: dict[str, Any],
        *,
        kind: str,
        key: str,
        source_tags: str,
        body_gender: str | None,
        dress: bool,
        regenerate: bool,
        resident_id: str | None = None,
    ) -> tuple[dict[str, Any], int, int]:
        """住民ごとに掟の姿・複合の姿を作る。NovelAI の 429 を避けるため1人ずつ順に呼ぶ。

        regenerate でなければ、今の見た目(タグと体の性別)でまだ生成していない住民だけ。
        resident_id を渡すとその住民だけ(画面は1人ずつ呼び、そのたびに保存して進み具合を出す)。
        body_gender は掟が定める体の性別で、None なら住民それぞれの性別のまま。
        戻り値は (状態, 生成した人数, 失敗した人数)。
        """
        field = logic.look_image_field(kind)
        instruction = rule_look_instruction(
            source_tags, dress=dress, body_gender=body_gender
        )
        novelai_model = user_settings.get("novelai_text_model")
        generated = failed = 0
        residents = list(state["residents"])
        if resident_id is not None:
            residents = [item for item in residents if item["id"] == resident_id]
            if not residents:
                raise HakoniwaError("resident_not_found", "住民が見つかりません")
        for resident in residents:
            entry = (resident.get(field) or {}).get(key) or {}
            if (
                not regenerate
                and entry.get("image")
                and logic.look_entry_is_current(entry, source_tags, body_gender)
            ):
                continue
            gender = logic.resident_gender(resident)
            # 掟の姿は、世界のメモの姿(いまのメモで生成済み)があればその上に重ねる
            memo_tags = (
                logic.current_memo_look_tags(state, resident)
                if kind != "memo" and not dress
                else ""
            )
            base = (
                memo_tags
                or (str(resident.get("dress_tags") or "") if dress else "")
                or str(resident.get("base_tags") or _source_base_tags(resident))
            )
            tags = await convert_change_to_tags(
                instruction, base, novelai_model=novelai_model
            )
            if not tags:
                failed += 1
                continue
            # 体の性別は LLM の変換に任せず、掟の指定で決める
            tags = (
                logic.set_gender_token(tags, body_gender)
                if body_gender
                else logic.ensure_gender_token(tags, gender)
            )
            try:
                data = await self._generate_image(state, user_settings, tags)
            except HakoniwaError:
                failed += 1
                continue
            filename = save_image(world_id, f"{kind}_{resident['id']}", data)
            state = logic.set_look_image(
                state,
                resident["id"],
                kind=kind,
                key=key,
                entry={
                    "image": filename,
                    "tags": tags,
                    "source_tags": source_tags,
                    "source_body": body_gender,
                },
            )
            generated += 1
            if entry.get("image") and entry["image"] != filename:
                with contextlib.suppress(OSError, HakoniwaError):
                    image_path(world_id, str(entry["image"])).unlink(missing_ok=True)
        return state, generated, failed

    async def _finish_look(
        self,
        world_id: str,
        state: dict[str, Any],
        lang: str,
        user_settings: dict[str, Any],
        tracker: Any,
        generated: int,
        failed: int,
    ) -> dict[str, Any]:
        async with async_session_factory() as db:
            world = await self._load(db, world_id)
            _store_state(world, state)
            await db.commit()
            view = _world_view(world, state, lang, user_settings)
        if failed and not generated:
            raise HakoniwaError("image_generation_failed", "姿の生成に失敗しました")
        return {
            "world": view,
            "generated": generated,
            "failed": failed,
            "cost_usd": tracker.total_usd or None,
        }

    async def generate_rule_look(
        self,
        world_id: str,
        rule_id: str,
        *,
        regenerate: bool = False,
        resident_id: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """自作の掟の姿を住民の人数分(resident_id があればその1人)つくる。

        見た目を変えない掟では作れない。
        """
        lang, user_settings = await self._context(language)
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            rule = logic.custom_rule(state, rule_id)
            if rule is None:
                raise HakoniwaError("rule_not_found", "掟が見つかりません")
            if not logic.is_look_rule(rule):
                raise HakoniwaError(
                    "rule_has_no_look", "この掟は見た目を変えないため、姿を作れません"
                )
            tracker = begin_cost_tracking()
            state, generated, failed = await self._generate_look_images(
                world_id,
                state,
                user_settings,
                kind="rule",
                key=rule_id,
                source_tags=str(rule.get("appearance_tags") or ""),
                body_gender=logic.rule_body_gender(rule),
                dress=False,
                regenerate=regenerate,
                resident_id=resident_id,
            )
            return await self._finish_look(
                world_id, state, lang, user_settings, tracker, generated, failed
            )

    async def generate_combo_look(
        self,
        world_id: str,
        *,
        regenerate: bool = False,
        resident_id: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """いま重なっている見た目の掟(ドレスの掟を含む)を合わせた複合の姿をつくる。"""
        lang, user_settings = await self._context(language)
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            combo = logic.active_combo(state)
            if combo is None:
                raise HakoniwaError(
                    "no_combo", "見た目に関わる掟を2つ以上有効にしてください"
                )
            tracker = begin_cost_tracking()
            state, generated, failed = await self._generate_look_images(
                world_id,
                state,
                user_settings,
                kind="combo",
                key=combo["digest"],
                source_tags=logic.combo_tags(state, combo["rule_ids"]),
                body_gender=logic.look_body_gender(state, combo["rule_ids"]),
                dress=combo["includes_dress"],
                regenerate=regenerate,
                resident_id=resident_id,
            )
            return await self._finish_look(
                world_id, state, lang, user_settings, tracker, generated, failed
            )

    async def plan_memo_look(
        self, world_id: str, language: str | None = None
    ) -> dict[str, Any]:
        """いまの世界のメモが住民全員の姿を変えるかを LLM に確かめ、メモの姿の指定を保存する。

        同じメモでもう確かめていれば LLM を呼ばない。メモが空なら指定を消す。
        """
        lang, user_settings = await self._context(language)
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            tracker = begin_cost_tracking()
            memo = play.world_memo(state)
            if not logic.memo_look_planned(state):
                tags, body_gender = (
                    await plan_memo_look(
                        memo, novelai_model=user_settings.get("novelai_text_model")
                    )
                    if memo
                    else ("", None)
                )
                state = logic.set_memo_look(state, tags, body_gender)
            view = await self._store_view(world_id, state, lang, user_settings)
        return {
            "world": view,
            "changes_look": logic.active_memo_look(state) is not None,
            "cost_usd": tracker.total_usd or None,
        }

    async def generate_memo_look(
        self,
        world_id: str,
        *,
        regenerate: bool = False,
        resident_id: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """世界のメモの姿を住民の人数分(resident_id があればその1人)つくる。"""
        lang, user_settings = await self._context(language)
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            look = logic.active_memo_look(state)
            if look is None:
                raise HakoniwaError("no_memo_look", "世界のメモは姿を変えていません")
            tracker = begin_cost_tracking()
            state, generated, failed = await self._generate_look_images(
                world_id,
                state,
                user_settings,
                kind="memo",
                key=logic.MEMO_LOOK_KEY,
                source_tags=look["tags"],
                body_gender=look["body_gender"],
                dress=False,
                regenerate=regenerate,
                resident_id=resident_id,
            )
            return await self._finish_look(
                world_id, state, lang, user_settings, tracker, generated, failed
            )

    async def delete_custom_rule(
        self, world_id: str, rule_id: str, language: str | None = None
    ) -> dict[str, Any]:
        return await self._mutate(
            world_id, language, lambda state: logic.delete_custom_rule(state, rule_id)
        )

    # ------------------------------------------------------------------
    # 住民
    # ------------------------------------------------------------------

    async def _derive_tags(
        self,
        text: str,
        gender: str,
        *,
        dress: bool,
        fallback: str,
        novelai_model: str | None,
    ) -> tuple[str, bool]:
        """外見の説明を画像タグにする。(タグ, 変換に失敗したか) を返す。

        空なら fallback、英語のタグならそのまま、日本語の文章なら LLM で変換する。
        """
        cleaned = str(text or "").strip()
        if not cleaned:
            return fallback, False
        if not needs_tag_expansion(cleaned):
            return logic.ensure_gender_token(cleaned, gender), False
        expanded = await expand_appearance_tags(
            cleaned, gender, dress=dress, novelai_model=novelai_model
        )
        if not expanded:
            return fallback, True
        return logic.ensure_gender_token(expanded, gender), False

    async def add_custom_resident(
        self,
        world_id: str,
        fields: dict[str, Any],
        language: str | None = None,
    ) -> dict[str, Any]:
        """自作の住民を迎える。画像のタグは書かれたものを整えて使う(いつもの姿は必須)。"""
        lang, _ = await self._context(language)
        clean = logic.validate_resident_fields(**_resident_text_fields(fields))
        base_tags, dress_tags = _resident_tags_input(fields, clean["gender"])
        resident = logic.custom_resident(
            name=clean["name"],
            personality=clean["personality"],
            gender=clean["gender"],
            appearance_text=clean["appearance_text"],
            base_tags=base_tags,
            dress_text=clean["dress_text"],
            dress_tags=dress_tags,
            address_style=clean["address_style"],
        )
        view = await self._mutate(
            world_id, lang, lambda state: logic.add_resident(state, resident)
        )
        return {"world": view, "resident_id": resident["id"]}

    async def add_character_resident(
        self,
        world_id: str,
        character_preset_id: str,
        gender: str | None,
        language: str | None = None,
    ) -> dict[str, Any]:
        lang, _ = await self._context(language)
        async with async_session_factory() as db:
            world = await self._load(db, world_id)
            state = _load_state(world)
        if any(
            item.get("character_preset_id") == character_preset_id
            for item in state["residents"]
        ):
            raise HakoniwaError(
                "duplicate_resident", "このキャラクターはすでに住民です"
            )
        resident = await self._character_resident(world_id, character_preset_id, gender)
        try:
            view = await self._mutate(
                world_id, lang, lambda current: logic.add_resident(current, resident)
            )
        except HakoniwaError:
            image = resident.get("avatar_image")
            if image:
                with contextlib.suppress(HakoniwaError):
                    image_path(world_id, image).unlink(missing_ok=True)
            raise
        return {"world": view, "resident_id": resident["id"]}

    async def update_resident(
        self,
        world_id: str,
        resident_id: str,
        fields: dict[str, Any],
        language: str | None = None,
    ) -> dict[str, Any]:
        """住民の名前・性格・性別・外見の説明・呼び方・画像のタグを書き換える。

        画像のタグは書かれたものを整えて使う(いつもの姿は必須)。タグを書き換えたら
        プレイヤーの手直しとして印を付ける(プリセットの描き直しで上書きしないため)。
        """
        lang, _ = await self._context(language)
        clean = logic.validate_resident_fields(**_resident_text_fields(fields))
        async with async_session_factory() as db:
            world = await self._load(db, world_id)
            current = logic.find_resident(_load_state(world), resident_id)
        base_tags, dress_tags = _resident_tags_input(fields, clean["gender"])
        updates: dict[str, Any] = {
            **clean,
            "base_tags": base_tags,
            "dress_tags": dress_tags,
        }
        if fields.get("address_style") is None:
            # 呼び方の指定が無ければ今のまま
            updates.pop("address_style")
        if base_tags != (current.get("base_tags") or ""):
            updates["base_tags_manual"] = True
        if dress_tags != (current.get("dress_tags") or ""):
            updates["dress_tags_manual"] = True
        view = await self._mutate(
            world_id,
            lang,
            lambda state: logic.update_resident(state, resident_id, updates),
        )
        return {"world": view, "resident_id": resident_id}

    async def remove_resident(
        self, world_id: str, resident_id: str, language: str | None = None
    ) -> dict[str, Any]:
        return await self._mutate(
            world_id, language, lambda state: logic.remove_resident(state, resident_id)
        )

    async def greet(
        self, world_id: str, resident_id: str, language: str | None = None
    ) -> dict[str, Any]:
        """住民の一言(状態は変えない)。"""
        lang, user_settings = await self._context(language)
        async with async_session_factory() as db:
            world = await self._load(db, world_id)
            state = _load_state(world)
        resident = logic.find_resident(state, resident_id)
        tracker = begin_cost_tracking()
        greeting = await generate_greeting(
            state,
            resident,
            lang,
            random.Random(),
            novelai_model=user_settings.get("novelai_text_model"),
            nsfw=bool(user_settings.get("nsfw_mode")),
        )
        return {
            "resident_id": resident_id,
            "text": greeting["text"],
            "source": greeting["source"],
            "cost_usd": tracker.total_usd or None,
        }

    async def set_favorite(
        self,
        world_id: str,
        event_id: str,
        favorite: bool,
        language: str | None = None,
    ) -> dict[str, Any]:
        return await self._mutate(
            world_id,
            language,
            lambda state: logic.toggle_favorite(state, event_id, favorite),
        )

    # ------------------------------------------------------------------
    # 画像の生成(アバター・変身)
    # ------------------------------------------------------------------

    @staticmethod
    async def _generate_image(
        state: dict[str, Any],
        user_settings: dict[str, Any],
        tags: str,
    ) -> bytes:
        image_model = resolve_image_model(state, user_settings)
        try:
            return await generate_avatar_bytes(
                tags,
                image_model=image_model,
                nsfw_mode=bool(user_settings.get("nsfw_mode")),
            )
        except Exception as error:
            logger.warning(
                "Hakoniwa image generation failed: %s: %s", type(error).__name__, error
            )
            raise HakoniwaError(
                "image_generation_failed", "画像の生成に失敗しました"
            ) from error

    async def generate_avatar(
        self,
        world_id: str,
        resident_id: str,
        variant: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """住民の通常の姿(base)かドレス姿(dress)を生成し直す。"""
        if variant not in ("base", "dress"):
            raise HakoniwaError("invalid_variant", "姿の種類が正しくありません")
        lang, user_settings = await self._context(language)
        novelai_model = user_settings.get("novelai_text_model")
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                world = await self._load(db, world_id)
                state = _load_state(world)
            resident = logic.find_resident(state, resident_id)
            gender = logic.resident_gender(resident)
            tracker = begin_cost_tracking()
            updates: dict[str, Any] = {}
            if variant == "base":
                tags = logic.ensure_gender_token(
                    resident.get("base_tags") or _source_base_tags(resident), gender
                )
            else:
                tags = str(resident.get("dress_tags") or "")
                if not tags:
                    # 衣装の指定が無ければ、今の姿からドレス姿のタグを作って保存する
                    derived = await convert_change_to_tags(
                        DEFAULT_DRESS_INSTRUCTION,
                        resident.get("base_tags") or _source_base_tags(resident),
                        novelai_model=novelai_model,
                    )
                    if not derived:
                        raise HakoniwaError(
                            "tag_conversion_failed", "ドレス姿のタグを作れませんでした"
                        )
                    tags = logic.ensure_gender_token(derived, gender)
                    updates["dress_tags"] = tags
            data = await self._generate_image(state, user_settings, tags)
            filename = save_image(world_id, f"{variant}_{resident_id}", data)
            updates["avatar_image" if variant == "base" else "dress_image"] = filename
            async with async_session_factory() as db:
                world = await self._load(db, world_id)
                state = logic.update_resident(_load_state(world), resident_id, updates)
                _store_state(world, state)
                await db.commit()
                view = _world_view(world, state, lang, user_settings)
        return {"world": view, "cost_usd": tracker.total_usd or None}

    async def _apply_transform(
        self,
        world_id: str,
        state: dict[str, Any],
        resident_id: str,
        change_text: str,
        lang: str,
        user_settings: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """変身の本体(タグ変換・画像・変身と反応の出来事・違和感)。世界のロックの中で呼ぶ。"""
        novelai_model = user_settings.get("novelai_text_model")
        nsfw = bool(user_settings.get("nsfw_mode"))
        state = await self._change_look(
            world_id,
            state,
            resident_id,
            change_text,
            user_settings,
            transformation={"description": change_text},
        )
        rng = random.Random()
        target = logic.find_resident(state, resident_id)
        others = logic.bystanders(state, resident_id, rng)
        texts = _TRANSFORM_EVENT_TEXT["ja" if lang == "ja" else "en"]
        name = logic.resident_name(target, lang)
        state = logic.apply_event(
            state,
            {
                "title": texts["title"].format(name=name),
                "narration": texts["narration"].format(name=name, change=change_text),
                "lines": [],
                "participants": [resident_id, *(item["id"] for item in others)],
                "mood_delta": {resident_id: 4},
                "affinity_delta": 0,
                "source": "player",
                "kind": "transform",
                "change_text": change_text,
                "area": target.get("current_area"),
            },
            rng,
        )
        new_events = [state["events"][-1]]
        target = logic.find_resident(state, resident_id)
        others = [logic.find_resident(state, item["id"]) for item in others]
        reaction = await generate_transform_reaction(
            state,
            target,
            change_text,
            others,
            lang,
            novelai_model=novelai_model,
            nsfw=nsfw,
        )
        reaction["area"] = target.get("current_area")
        state = logic.apply_event(state, reaction, rng)
        new_events.append(state["events"][-1])
        # 変身は世界の書き換えとして違和感を溜める(対面に届くこともある)
        state, confrontation = await self._apply_dissonance_gain(
            state, DISSONANCE_TRANSFORM_GAIN, lang, user_settings, rng
        )
        new_events.extend(confrontation)
        return state, new_events

    async def _change_look(
        self,
        world_id: str,
        state: dict[str, Any],
        resident_id: str,
        change_text: str,
        user_settings: dict[str, Any],
        *,
        transformation: dict[str, Any],
    ) -> dict[str, Any]:
        """指定の文から姿のタグと画像を作り、変身(いまの姿)として付けた状態を返す。

        変身は体に付く。入れ替わり中なら、本人がいま入っている相手の体を書き換える。
        元にするのはその体の今見えている姿(変身・複合・掟・メモの姿)。
        transformation は変身の記録に足す項目(description・kind・reality_id)。
        """
        novelai_model = user_settings.get("novelai_text_model")
        resident = logic.find_resident(state, resident_id)
        body = logic.body_of(state, resident)
        base_tags = (
            logic.own_look(state, body).get("tags")
            or (
                body.get("dress_tags")
                if "dress" in state.get("active_rules", [])
                else None
            )
            or body.get("base_tags")
            or _source_base_tags(body)
        )
        tags = await convert_change_to_tags(
            change_text, base_tags, novelai_model=novelai_model
        )
        if not tags:
            raise HakoniwaError(
                "tag_conversion_failed",
                "変身の指定を画像のタグにできませんでした。文を変えてお試しください",
            )
        return await self._apply_look_tags(
            world_id,
            state,
            resident_id,
            tags,
            user_settings,
            transformation=transformation,
        )

    async def _apply_look_tags(
        self,
        world_id: str,
        state: dict[str, Any],
        resident_id: str,
        tags: str,
        user_settings: dict[str, Any],
        *,
        transformation: dict[str, Any],
    ) -> dict[str, Any]:
        """姿のタグから画像を作り、変身(いまの姿)として付けた状態を返す。

        変身は体に付く(入れ替わり中は、本人がいま入っている相手の体)。性別のタグは体に合わせる。
        """
        resident = logic.find_resident(state, resident_id)
        body = logic.body_of(state, resident)
        tags = logic.ensure_gender_token(tags, logic.resident_gender(body))
        data = await self._generate_image(state, user_settings, tags)
        filename = save_image(world_id, f"tf_{body['id']}", data)
        return logic.set_transformation(
            state,
            resident_id,
            {
                **transformation,
                "tags": tags,
                "image": filename,
                "day": state["day"],
            },
        )

    async def _store_view(
        self,
        world_id: str,
        state: dict[str, Any],
        lang: str,
        user_settings: dict[str, Any],
    ) -> dict[str, Any]:
        async with async_session_factory() as db:
            world = await self._load(db, world_id)
            _store_state(world, state)
            await db.commit()
            return _world_view(world, state, lang, user_settings)

    async def transform(
        self,
        world_id: str,
        resident_id: str,
        instruction: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """住民をその場で変身させ、変身と周りの反応の出来事を年代記に積む。"""
        change_text = logic.validate_transform_text(instruction)
        lang, user_settings = await self._context(language)
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            logic.find_resident(state, resident_id)
            tracker = begin_cost_tracking()
            state, new_events = await self._apply_transform(
                world_id, state, resident_id, change_text, lang, user_settings
            )
            view = await self._store_view(world_id, state, lang, user_settings)
        return {
            "world": view,
            "new_events": [_event_view(world_id, event, lang) for event in new_events],
            "cost_usd": tracker.total_usd or None,
        }

    async def alter_reality(
        self,
        world_id: str,
        resident_id: str,
        instruction: str,
        *,
        change_look: bool,
        language: str | None = None,
    ) -> dict[str, Any]:
        """住民についての世界の常識を書き換える(住民の改変)。

        本人も周りも昔からそうだと受け止める。change_look なら変身と同じ仕組みで姿も変える
        (慣れの段階は始めない)。そのあと、新しい日常の一場面を年代記に積み、違和感を溜める。
        """
        text = logic.validate_reality_text(instruction)
        lang, user_settings = await self._context(language)
        novelai_model = user_settings.get("novelai_text_model")
        nsfw = bool(user_settings.get("nsfw_mode"))
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            tracker = begin_cost_tracking()
            state, reality = logic.add_reality(state, resident_id, text)
            if change_look:
                state = await self._change_look(
                    world_id,
                    state,
                    resident_id,
                    _REALITY_LOOK_INSTRUCTION.format(text=text),
                    user_settings,
                    transformation={
                        "description": text,
                        "kind": "reality",
                        "reality_id": reality["id"],
                    },
                )
            rng = random.Random()
            target = logic.find_resident(state, resident_id)
            others = [
                logic.find_resident(state, item["id"])
                for item in logic.bystanders(state, resident_id, rng)
            ]
            event = await generate_transform_reaction(
                state,
                target,
                text,
                others,
                lang,
                novelai_model=novelai_model,
                nsfw=nsfw,
                reality=True,
            )
            event.update(
                {
                    "area": target.get("current_area"),
                    "kind": "reality",
                    "change_text": text,
                }
            )
            state = logic.apply_event(state, event, rng)
            new_events = [state["events"][-1]]
            # 改変も世界の書き換えとして違和感を溜める(対面に届くこともある)
            state, confrontation = await self._apply_dissonance_gain(
                state, DISSONANCE_REALITY_GAIN, lang, user_settings, rng
            )
            new_events.extend(confrontation)
            view = await self._store_view(world_id, state, lang, user_settings)
        return {
            "world": view,
            "new_events": [_event_view(world_id, event, lang) for event in new_events],
            "cost_usd": tracker.total_usd or None,
        }

    async def remove_reality(
        self,
        world_id: str,
        resident_id: str,
        reality_id: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """住民の改変を消す(その改変で変えた姿がいまの姿なら、元の姿に戻る)。"""
        return await self._mutate(
            world_id,
            language,
            lambda state: logic.remove_reality(state, resident_id, reality_id),
        )

    async def directed_event(
        self,
        world_id: str,
        resident_id: str,
        instruction: str,
        scope: str,
        partner_ids: list[str] | None = None,
        language: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        """書き手の指示で、住民のいまの姿のまま出来事を1件起こして年代記に積む。

        場所は location(空なら内容に合う場所を生成が選ぶ)。エリアなら参加者はそこへ、
        エリアの外の場所なら本人のいる部屋へ集まる扱いにする。書き手が直接手を下すので、
        世界の違和感も溜める(到達点に達したら対面の出来事が続く)。
        """
        text = logic.validate_event_instruction(instruction)
        location_id = logic.validate_event_location(location)
        lang, user_settings = await self._context(language)
        rng = random.Random()
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            group = logic.directed_event_cast(
                state, resident_id, scope, partner_ids, rng
            )
            area_id = group[0].get("current_area")
            tracker = begin_cost_tracking()
            event = await generate_directed_event(
                state,
                group,
                text,
                lang,
                novelai_model=user_settings.get("novelai_text_model"),
                nsfw=bool(user_settings.get("nsfw_mode")),
                area_id=area_id,
                location_id=location_id,
            )
            event.update({"source": "player", "kind": "directed", "instruction": text})
            state = logic.apply_event(state, event, rng)
            new_events = [state["events"][-1]]
            state, confrontation = await self._apply_dissonance_gain(
                state, DISSONANCE_DIRECTED_EVENT_GAIN, lang, user_settings, rng
            )
            new_events.extend(confrontation)
            view = await self._store_view(world_id, state, lang, user_settings)
        return {
            "world": view,
            "new_events": [_event_view(world_id, event, lang) for event in new_events],
            "cost_usd": tracker.total_usd or None,
        }

    async def continue_event(
        self,
        world_id: str,
        event_id: str,
        instruction: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """今日の出来事の続きを、書き手の指示で1件起こして年代記に積む。

        参加者は元の出来事と同じ(いまも住んでいる住民)。場所は元の場面の場所が既定で、
        指示が別の場所を示せば移る。同じ介入の延長なので、違和感は小さく溜める。
        """
        text = logic.validate_event_instruction(instruction)
        lang, user_settings = await self._context(language)
        rng = random.Random()
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            previous = logic.continuation_source(state, event_id)
            group = logic.continuation_cast(state, previous)
            tracker = begin_cost_tracking()
            event = await generate_directed_event(
                state,
                group,
                text,
                lang,
                novelai_model=user_settings.get("novelai_text_model"),
                nsfw=bool(user_settings.get("nsfw_mode")),
                area_id=previous.get("area"),
                previous_event=previous,
            )
            event.update(
                {
                    "source": "player",
                    "kind": "directed",
                    "instruction": text,
                    "continues": previous["id"],
                }
            )
            state = logic.apply_event(state, event, rng)
            new_events = [state["events"][-1]]
            state, confrontation = await self._apply_dissonance_gain(
                state, DISSONANCE_CONTINUED_EVENT_GAIN, lang, user_settings, rng
            )
            new_events.extend(confrontation)
            view = await self._store_view(world_id, state, lang, user_settings)
        return {
            "world": view,
            "new_events": [_event_view(world_id, event, lang) for event in new_events],
            "cost_usd": tracker.total_usd or None,
        }

    async def plan_event_looks(
        self, world_id: str, event_id: str, language: str | None = None
    ) -> dict[str, Any]:
        """出来事の結果として姿が変わった参加者と、変化後の姿を決めて出来事に保存する。

        服の交換のように相手の出来事の前の姿が要る変化があるので、画像を作る前に、
        いまの姿から参加者全員ぶんを1回で決める。画像は apply_event_look で1人ずつ作る。
        """
        lang, user_settings = await self._context(language)
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            event = next(
                (item for item in state["events"] if item["id"] == event_id), None
            )
            if event is None:
                raise HakoniwaError("event_not_found", "出来事が見つかりません")
            by_id = {resident["id"]: resident for resident in state["residents"]}
            cast = [pid for pid in event.get("participants") or [] if pid in by_id]
            if not cast:
                raise HakoniwaError("no_participants", "この出来事の住民がもういません")
            tracker = begin_cost_tracking()
            plan = await plan_event_looks(
                {**event, "participants": cast},
                {pid: logic.resident_name(by_id[pid], lang) for pid in cast},
                {pid: look_tags(state, by_id[pid]) for pid in cast},
                lang,
                novelai_model=user_settings.get("novelai_text_model"),
            )
            state = logic.set_event_look_plan(state, event_id, plan)
            view = await self._store_view(world_id, state, lang, user_settings)
        return {
            "world": view,
            "changes": [
                {"resident_id": item["resident_id"], "description": item["description"]}
                for item in plan
            ],
            "cost_usd": tracker.total_usd or None,
        }

    async def apply_event_look(
        self,
        world_id: str,
        event_id: str,
        resident_id: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """出来事で決めた変化後の姿を、その住民の1人ぶん生成して変身として付ける。

        変身と同じ扱い(履歴に残り、元に戻せて、慣れの段階が始まる)。出来事そのものが
        場面なので、反応の出来事は足さず、違和感も出来事ぶんより増やさない。
        """
        lang, user_settings = await self._context(language)
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            logic.find_resident(state, resident_id)
            entry = logic.event_look_entry(state, event_id, resident_id)
            tracker = begin_cost_tracking()
            state = await self._apply_look_tags(
                world_id,
                state,
                resident_id,
                entry["tags"],
                user_settings,
                transformation={"description": entry["description"]},
            )
            view = await self._store_view(world_id, state, lang, user_settings)
        return {"world": view, "cost_usd": tracker.total_usd or None}

    # ------------------------------------------------------------------
    # 箱庭の中での会話・タッチ・介入
    # ------------------------------------------------------------------

    async def chat_history(self, world_id: str, resident_id: str) -> dict[str, Any]:
        async with async_session_factory() as db:
            state = _load_state(await self._load(db, world_id))
        logic.find_resident(state, resident_id)
        return {
            "resident_id": resident_id,
            "history": play.chat_history(state, resident_id),
        }

    async def chat(
        self,
        world_id: str,
        resident_id: str,
        message: str,
        *,
        allow_image: bool = True,
        confirmed_instruction: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """住民と会話する。変身・元に戻す指示なら実行し、結果を会話に残す。

        変身は画像を生成するので、allow_image が偽(V5 の利用上限を使い切っていて
        確認が要る)なら実行せず needs_confirmation を返す。確認のあとは
        confirmed_instruction を付けて送り直してもらい、分類せずに変身する。
        """
        text = play.validate_chat_message(message)
        lang, user_settings = await self._context(language)
        novelai_model = user_settings.get("novelai_text_model")
        nsfw = bool(user_settings.get("nsfw_mode"))
        rng = random.Random()
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            resident = logic.find_resident(state, resident_id)
            tracker = begin_cost_tracking()
            if confirmed_instruction:
                detection = {
                    "action": "transform",
                    "instruction": logic.validate_transform_text(confirmed_instruction),
                }
            else:
                detection = await classify_chat_alteration(
                    state, resident, text, lang, novelai_model=novelai_model
                )
            action = detection["action"]
            alteration = {
                "action": action,
                "instruction": detection.get("instruction") or "",
                "executed": False,
                "needs_confirmation": False,
            }
            if action == "transform" and not allow_image:
                alteration["needs_confirmation"] = True
                return {
                    "world": None,
                    "reply": None,
                    "history": play.chat_history(state, resident_id),
                    "alteration": alteration,
                    "new_events": [],
                    "cost_usd": tracker.total_usd or None,
                }
            key = "ja" if lang == "ja" else "en"
            new_events: list[dict[str, Any]] = []
            entries: list[dict[str, Any]] = [{"role": "player", "text": text}]
            reply: dict[str, Any]
            if action == "clear":
                if logic.current_transformation(state, resident):
                    state = logic.clear_transformation(state, resident_id)
                    result = CHAT_ALTERATION_RESULT["clear"][key]
                    alteration["executed"] = True
                else:
                    result = CHAT_ALTERATION_RESULT["not_transformed"][key]
                reply = {"role": "system", "text": result, "kind": "alteration"}
                entries.append(reply)
            elif action == "transform":
                instruction = alteration["instruction"] or text
                try:
                    state, new_events = await self._apply_transform(
                        world_id, state, resident_id, instruction, lang, user_settings
                    )
                except HakoniwaError as error:
                    reply = {
                        "role": "system",
                        "text": CHAT_ALTERATION_FAILED[key].format(reason=str(error)),
                        "kind": "alteration",
                    }
                    entries.append(reply)
                else:
                    alteration["executed"] = True
                    entries.append(
                        {
                            "role": "system",
                            "text": CHAT_ALTERATION_RESULT["transform"][key].format(
                                instruction=instruction
                            ),
                            "kind": "alteration",
                        }
                    )
                    reply = {
                        "role": "resident",
                        "text": _resident_line(new_events, resident_id)
                        or CHAT_TRANSFORM_FALLBACK[key],
                        "kind": "alteration_reaction",
                    }
                    entries.append(reply)
            else:
                generated = await generate_chat_reply(
                    state,
                    resident,
                    play.chat_history(state, resident_id),
                    text,
                    lang,
                    rng,
                    novelai_model=novelai_model,
                    nsfw=nsfw,
                )
                reply = {
                    "role": "resident",
                    "text": generated["text"],
                    "source": generated["source"],
                    "web_search": generated.get("web_search"),
                }
                entries.append(reply)
            state = play.append_chat(state, resident_id, entries)
            view = await self._store_view(world_id, state, lang, user_settings)
        return {
            "world": view,
            "reply": reply,
            "history": play.chat_history(state, resident_id),
            "alteration": alteration,
            "new_events": [_event_view(world_id, event, lang) for event in new_events],
            "cost_usd": tracker.total_usd or None,
        }

    async def touch(
        self,
        world_id: str,
        resident_id: str,
        part: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """立ち絵に触れたときの住民の反応。気分が少し動く。年代記には残さない。"""
        part = play.validate_touch_part(part)
        lang, user_settings = await self._context(language)
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            resident = logic.find_resident(state, resident_id)
            tracker = begin_cost_tracking()
            reaction = await generate_touch_reaction(
                state,
                resident,
                part,
                lang,
                random.Random(),
                novelai_model=user_settings.get("novelai_text_model"),
                nsfw=bool(user_settings.get("nsfw_mode")),
            )
            delta = play.touch_mood_delta(resident, part)
            if delta:
                state = play.adjust_mood(state, resident_id, delta)
            view = await self._store_view(world_id, state, lang, user_settings)
        return {
            "world": view,
            "resident_id": resident_id,
            "part": part,
            "text": reaction["text"],
            "source": reaction["source"],
            "mood_delta": delta,
            "cost_usd": tracker.total_usd or None,
        }

    async def set_intervention(
        self, world_id: str, choice: str, language: str | None = None
    ) -> dict[str, Any]:
        return await self._mutate(
            world_id, language, lambda state: play.set_intervention(state, choice)
        )

    # ------------------------------------------------------------------
    # 家具と場面絵
    # ------------------------------------------------------------------

    async def place_furniture(
        self,
        world_id: str,
        area_id: str,
        slot: int,
        furniture_id: str | None,
        language: str | None = None,
    ) -> dict[str, Any]:
        return await self._mutate(
            world_id,
            language,
            lambda state: logic.place_furniture(state, area_id, slot, furniture_id),
        )

    async def generate_scene_image(
        self, world_id: str, event_id: str, language: str | None = None
    ) -> dict[str, Any]:
        """年代記の出来事の山場を、参加者のいまの姿で1枚の横長の絵にする。"""
        lang, user_settings = await self._context(language)
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                world = await self._load(db, world_id)
                state = _load_state(world)
            event = next(
                (item for item in state["events"] if item["id"] == event_id), None
            )
            if event is None:
                raise HakoniwaError("event_not_found", "出来事が見つかりません")
            ids = {resident["id"] for resident in state["residents"]}
            if not any(pid in ids for pid in event.get("participants") or []):
                raise HakoniwaError("no_participants", "この出来事の住民がもういません")
            event = {
                **event,
                "participants": [
                    pid for pid in event.get("participants") or [] if pid in ids
                ],
            }
            tracker = begin_cost_tracking()
            names = {
                resident["id"]: logic.resident_name(resident, lang)
                for resident in state["residents"]
            }
            nsfw = bool(user_settings.get("nsfw_mode"))
            scene = await convert_scene_to_tags(
                event,
                names,
                event_location(event)["scene"],
                novelai_model=user_settings.get("novelai_text_model"),
                nsfw=nsfw,
            )
            # 服装は場面の絵だけで変える(浴室なら裸・タオルなど)。住民の姿は変えない
            request = scene_request(
                state,
                event,
                scene.tags if scene else "",
                scene.attire if scene else None,
                nsfw=nsfw,
            )
            try:
                data = await generate_scene_bytes(
                    request,
                    image_model=resolve_image_model(state, user_settings),
                    nsfw_mode=bool(user_settings.get("nsfw_mode")),
                )
            except HakoniwaError:
                raise
            except Exception as error:
                logger.warning(
                    "Hakoniwa scene image failed: %s: %s", type(error).__name__, error
                )
                raise HakoniwaError(
                    "image_generation_failed", "画像の生成に失敗しました"
                ) from error
            filename = save_image(world_id, f"scene_{event_id[:8]}", data)
            async with async_session_factory() as db:
                world = await self._load(db, world_id)
                state = logic.set_event_scene_image(
                    _load_state(world), event_id, filename
                )
                _store_state(world, state)
                await db.commit()
                view = _world_view(world, state, lang, user_settings)
        return {"world": view, "cost_usd": tracker.total_usd or None}

    async def clear_transform(
        self, world_id: str, resident_id: str, language: str | None = None
    ) -> dict[str, Any]:
        return await self._mutate(
            world_id,
            language,
            lambda state: logic.clear_transformation(state, resident_id),
        )

    async def reapply_transform(
        self, world_id: str, resident_id: str, image: str, language: str | None = None
    ) -> dict[str, Any]:
        return await self._mutate(
            world_id,
            language,
            lambda state: logic.reapply_transformation(state, resident_id, image),
        )

    @staticmethod
    def image_file(world_id: str, filename: str) -> Path:
        return image_path(world_id, filename)


hakoniwa_service = HakoniwaService()

__all__ = ["HakoniwaError", "HakoniwaService", "hakoniwa_service"]
