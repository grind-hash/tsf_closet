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
    DISSONANCE_CUSTOM_RULE_GAIN,
    DISSONANCE_DIRECTED_EVENT_GAIN,
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
from .hakoniwa_scene import scene_request, scene_suggestion
from .preset_sessions import PresetSessionError, load_preset_play_source
from .session import DEFAULT_USER_ID, session_store

logger = logging.getLogger(__name__)

# 衣装の指定が無い住民のドレス姿を作るときの変身の指示
DEFAULT_DRESS_INSTRUCTION = (
    "Change the outfit into an elegant formal dress that suits this person. "
    "Keep the face, hair and body as they are."
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
        "base_tags_manual": bool(resident.get("base_tags_manual")),
        "dress_text": resident.get("dress_text") or "",
        "dress_tags": resident.get("dress_tags") or "",
        "dress_tags_manual": bool(resident.get("dress_tags_manual")),
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


# 住民の編集の入力のうち、文の項目以外(タグの手直しと作り直しの指示)
_RESIDENT_TAG_FIELDS = (
    "base_tags",
    "dress_tags",
    "regenerate_base_tags",
    "regenerate_dress_tags",
)


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
            "appearance_tags_manual": bool(rule.get("appearance_tags_manual")),
            "look": logic.rule_look_status(state, rule["id"]),
        }
        for rule in state.get("custom_rules", [])
    )
    return cards


def _combo_look_view(state: dict[str, Any]) -> dict[str, Any] | None:
    """いま重なっている見た目の掟(複合の姿の対象)と、その生成状況。

    見た目のタグがまだ無い掟も数える(生成するときにタグを考える)。
    """
    combo = logic.active_combo(state, require_tags=False)
    if combo is None:
        return None
    rules = [logic.custom_rule(state, rule_id) or {} for rule_id in combo["rule_ids"]]
    untagged = [
        str(rule.get("name") or "")
        for rule in rules
        if not str(rule.get("appearance_tags") or "").strip()
    ]
    tagged = logic.active_combo(state)
    status = (
        logic.combo_look_status(state, tagged)
        if tagged is not None and not untagged
        else {"ready": 0, "stale": 0, "total": len(state["residents"])}
    )
    return {
        "rule_ids": combo["rule_ids"],
        "names": [str(rule.get("name") or "") for rule in rules],
        "includes_dress": combo["includes_dress"],
        "untagged_names": untagged,
        **status,
    }


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
            }
            for location in HAKONIWA_LOCATIONS
        ],
        "last_digest": state.get("last_digest"),
        "dissonance": _dissonance_view(state),
        "story_arcs": _arcs_view(state),
        "combo_look": _combo_look_view(state),
        "world_memo": play.world_memo(state),
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
        world_memo: str | None = None,
        experiment_theme: dict[str, Any] | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """世界の設定(画像モデル・世界の違和感・世界のメモ・実験テーマ)。None の項目は変えない。

        実験テーマは {preset_id, text}。どちらも空ならテーマ無しにする。
        """
        memo = play.validate_world_memo(world_memo) if world_memo is not None else None
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
            if memo is not None:
                updated["world_memo"] = memo
            if experiment_theme is not None:
                updated["experiment_theme"] = theme
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
                    event = template_event(
                        state, group, lang, rng, recent_titles=used_titles
                    )
                    event["area"] = area_id
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

    async def _rule_look_tags(
        self, clean: dict[str, str], user_settings: dict[str, Any]
    ) -> str:
        """掟の見た目の説明からタグを作る。英語のタグはそのまま、空なら空のまま
        (姿を生成するときに掟の本文から考える)。変換に失敗しても保存は止めない。"""
        description = clean["appearance_text"]
        if not description:
            return ""
        if not needs_tag_expansion(description):
            return clean_look_tags(description) or ""
        tags = await generate_rule_look_tags(
            clean["name"],
            clean["text"],
            description,
            novelai_model=user_settings.get("novelai_text_model"),
        )
        return tags or ""

    async def add_custom_rule(
        self,
        world_id: str,
        name: str,
        text: str,
        appearance_text: str = "",
        language: str | None = None,
        appearance_tags: str | None = None,
    ) -> dict[str, Any]:
        """掟を書く。見た目のタグを手で書いたらそれを使い、無ければ説明から作る。"""
        _, user_settings = await self._context(language)
        clean = logic.validate_custom_rule(name, text, appearance_text)
        manual = bool(str(appearance_tags or "").strip())
        tags = (
            clean_manual_look_tags(str(appearance_tags))
            if manual
            else await self._rule_look_tags(clean, user_settings)
        )
        return await self._mutate(
            world_id,
            language,
            lambda state: logic.add_custom_rule(
                state,
                name,
                text,
                appearance_text,
                appearance_tags=tags,
                appearance_tags_manual=manual,
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
        appearance_tags: str | None = None,
        regenerate_appearance_tags: bool = False,
    ) -> dict[str, Any]:
        """掟を編集する。見た目の説明を変えたときだけ見た目のタグを作り直す。

        手で直したタグは、説明を変えても作り直さない(作り直しの指示か、タグを空にした
        ときだけ説明から作る)。appearance_tags が None ならタグは手直ししていない。
        """
        _, user_settings = await self._context(language)
        clean = logic.validate_custom_rule(name, text, appearance_text)
        async with async_session_factory() as db:
            current = logic.custom_rule(
                _load_state(await self._load(db, world_id)), rule_id
            )
        if current is None:
            raise HakoniwaError("rule_not_found", "掟が見つかりません")
        action = logic.tag_action(
            edited=appearance_tags,
            regenerate=regenerate_appearance_tags,
            manual=bool(current.get("appearance_tags_manual")),
            source_changed=clean["appearance_text"]
            != (current.get("appearance_text") or ""),
        )
        tags: str | None = None
        manual = False
        if action == "manual":
            tags = clean_manual_look_tags(str(appearance_tags))
            manual = True
        elif action == "derive":
            tags = await self._rule_look_tags(clean, user_settings)
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
                appearance_tags_manual=manual,
            ),
        )

    async def _ensure_rule_look_tags(
        self,
        state: dict[str, Any],
        rule_ids: list[str],
        user_settings: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        """見た目のタグが無い掟に、掟の本文からタグを考えて入れる。考えられなかった掟名を返す。"""
        failed: list[str] = []
        for rule_id in rule_ids:
            rule = logic.custom_rule(state, rule_id)
            if rule is None or str(rule.get("appearance_tags") or "").strip():
                continue
            tags = await generate_rule_look_tags(
                rule["name"],
                rule["text"],
                str(rule.get("appearance_text") or ""),
                novelai_model=user_settings.get("novelai_text_model"),
            )
            if tags:
                state = logic.set_rule_appearance_tags(state, rule_id, tags)
            else:
                failed.append(str(rule["name"]))
        return state, failed

    async def _generate_look_images(
        self,
        world_id: str,
        state: dict[str, Any],
        user_settings: dict[str, Any],
        *,
        kind: str,
        key: str,
        source_tags: str,
        dress: bool,
        regenerate: bool,
    ) -> tuple[dict[str, Any], int, int]:
        """住民ごとに掟の姿・複合の姿を作る。NovelAI の 429 を避けるため1人ずつ順に呼ぶ。

        regenerate でなければ、今の見た目でまだ生成していない住民だけ。
        戻り値は (状態, 生成した人数, 失敗した人数)。
        """
        field = "rule_images" if kind == "rule" else "combo_images"
        instruction = rule_look_instruction(source_tags, dress=dress)
        novelai_model = user_settings.get("novelai_text_model")
        generated = failed = 0
        for resident in list(state["residents"]):
            entry = (resident.get(field) or {}).get(key) or {}
            if (
                not regenerate
                and entry.get("image")
                and entry.get("source_tags") == source_tags
            ):
                continue
            gender = logic.resident_gender(resident)
            base = (str(resident.get("dress_tags") or "") if dress else "") or str(
                resident.get("base_tags") or _source_base_tags(resident)
            )
            tags = await convert_change_to_tags(
                instruction, base, novelai_model=novelai_model
            )
            if not tags:
                failed += 1
                continue
            tags = logic.ensure_gender_token(tags, gender)
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
                entry={"image": filename, "tags": tags, "source_tags": source_tags},
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
        language: str | None = None,
    ) -> dict[str, Any]:
        """自作の掟の姿を住民の人数分つくる(見た目のタグが無ければ掟の本文から考える)。"""
        lang, user_settings = await self._context(language)
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            if logic.custom_rule(state, rule_id) is None:
                raise HakoniwaError("rule_not_found", "掟が見つかりません")
            tracker = begin_cost_tracking()
            state, failed_names = await self._ensure_rule_look_tags(
                state, [rule_id], user_settings
            )
            if failed_names:
                raise HakoniwaError(
                    "look_tags_failed", "掟の見た目のタグを作れませんでした"
                )
            source_tags = str(logic.custom_rule(state, rule_id)["appearance_tags"])
            state, generated, failed = await self._generate_look_images(
                world_id,
                state,
                user_settings,
                kind="rule",
                key=rule_id,
                source_tags=source_tags,
                dress=False,
                regenerate=regenerate,
            )
            return await self._finish_look(
                world_id, state, lang, user_settings, tracker, generated, failed
            )

    async def generate_combo_look(
        self,
        world_id: str,
        *,
        regenerate: bool = False,
        language: str | None = None,
    ) -> dict[str, Any]:
        """いま重なっている見た目の掟(ドレスの掟を含む)を合わせた複合の姿をつくる。"""
        lang, user_settings = await self._context(language)
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                state = _load_state(await self._load(db, world_id))
            combo = logic.active_combo(state, require_tags=False)
            if combo is None:
                raise HakoniwaError(
                    "no_combo", "見た目に関わる掟を2つ以上有効にしてください"
                )
            tracker = begin_cost_tracking()
            state, failed_names = await self._ensure_rule_look_tags(
                state, combo["rule_ids"], user_settings
            )
            combo = logic.active_combo(state)
            if failed_names or combo is None:
                async with async_session_factory() as db:
                    world = await self._load(db, world_id)
                    _store_state(world, state)
                    await db.commit()
                raise HakoniwaError(
                    "look_tags_failed", "掟の見た目のタグを作れませんでした"
                )
            state, generated, failed = await self._generate_look_images(
                world_id,
                state,
                user_settings,
                kind="combo",
                key=combo["digest"],
                source_tags=logic.combo_tags(state, combo["rule_ids"]),
                dress=combo["includes_dress"],
                regenerate=regenerate,
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
        lang, user_settings = await self._context(language)
        clean = logic.validate_resident_fields(**_resident_text_fields(fields))
        tracker = begin_cost_tracking()
        novelai_model = user_settings.get("novelai_text_model")
        base_tags, base_failed = await self._derive_tags(
            clean["appearance_text"],
            clean["gender"],
            dress=False,
            fallback=DEFAULT_BASE_TAGS[clean["gender"]],
            novelai_model=novelai_model,
        )
        dress_tags, dress_failed = await self._derive_tags(
            clean["dress_text"],
            clean["gender"],
            dress=True,
            fallback="",
            novelai_model=novelai_model,
        )
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
        return {
            "world": view,
            "resident_id": resident["id"],
            "tag_expansion_failed": base_failed or dress_failed,
            "cost_usd": tracker.total_usd or None,
        }

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

        外見の説明はタグに変換する。ただしプレイヤーが手で直したタグは、説明を変えても
        作り直さない(作り直しの指示か、タグを空にしたときだけ説明から作る)。
        """
        lang, user_settings = await self._context(language)
        clean = logic.validate_resident_fields(**_resident_text_fields(fields))
        async with async_session_factory() as db:
            world = await self._load(db, world_id)
            current = logic.find_resident(_load_state(world), resident_id)
        tracker = begin_cost_tracking()
        novelai_model = user_settings.get("novelai_text_model")
        failed = False
        updates: dict[str, Any] = dict(clean)
        if fields.get("address_style") is None:
            # 呼び方の指定が無ければ今のまま
            updates.pop("address_style")
        gender_changed = clean["gender"] != logic.resident_gender(current)
        base_action = logic.tag_action(
            edited=fields.get("base_tags"),
            regenerate=bool(fields.get("regenerate_base_tags")),
            manual=bool(current.get("base_tags_manual")),
            source_changed=gender_changed
            or clean["appearance_text"] != (current.get("appearance_text") or ""),
        )
        if base_action == "manual":
            updates["base_tags"] = clean_manual_tags(
                str(fields["base_tags"]), clean["gender"]
            )
            updates["base_tags_manual"] = True
        elif base_action == "derive":
            fallback_resident = {**current, "gender": clean["gender"]}
            updates["base_tags"], failed_base = await self._derive_tags(
                clean["appearance_text"],
                clean["gender"],
                dress=False,
                fallback=logic.ensure_gender_token(
                    _source_base_tags(fallback_resident), clean["gender"]
                ),
                novelai_model=novelai_model,
            )
            updates["base_tags_manual"] = False
            failed = failed or failed_base
        elif gender_changed and current.get("base_tags_manual"):
            # 手で直したタグを残すときも、性別を変えたらタグの性別と合っているか確かめる
            updates["base_tags"] = clean_manual_tags(
                str(current.get("base_tags") or ""), clean["gender"]
            )
        dress_action = logic.tag_action(
            edited=fields.get("dress_tags"),
            regenerate=bool(fields.get("regenerate_dress_tags")),
            manual=bool(current.get("dress_tags_manual")),
            source_changed=clean["dress_text"] != (current.get("dress_text") or ""),
        )
        if dress_action == "manual":
            updates["dress_tags"] = clean_manual_tags(
                str(fields["dress_tags"]), clean["gender"]
            )
            updates["dress_tags_manual"] = True
        elif dress_action == "derive":
            preset = HAKONIWA_PRESET_MAP.get(str(current.get("preset_id") or ""))
            updates["dress_tags"], failed_dress = await self._derive_tags(
                clean["dress_text"],
                clean["gender"],
                dress=True,
                fallback=str(preset["dress_tags"]) if preset else "",
                novelai_model=novelai_model,
            )
            updates["dress_tags_manual"] = False
            failed = failed or failed_dress
        elif (
            gender_changed
            and current.get("dress_tags_manual")
            and current.get("dress_tags")
        ):
            updates["dress_tags"] = clean_manual_tags(
                str(current.get("dress_tags") or ""), clean["gender"]
            )
        view = await self._mutate(
            world_id,
            lang,
            lambda state: logic.update_resident(state, resident_id, updates),
        )
        return {
            "world": view,
            "resident_id": resident_id,
            "tag_expansion_failed": failed,
            "cost_usd": tracker.total_usd or None,
        }

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
        resident = logic.find_resident(state, resident_id)
        # 変身は体に付く。入れ替わり中なら、本人がいま入っている相手の体を書き換える。
        # 元にするのはその体の今見えている姿(変身・複合・掟の姿)
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
        tags = logic.ensure_gender_token(tags, logic.resident_gender(body))
        data = await self._generate_image(state, user_settings, tags)
        filename = save_image(world_id, f"tf_{body['id']}", data)
        rng = random.Random()
        state = logic.set_transformation(
            state,
            resident_id,
            {
                "description": change_text,
                "tags": tags,
                "image": filename,
                "day": state["day"],
            },
        )
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
