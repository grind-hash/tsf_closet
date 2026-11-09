"""AI箱庭の操作と永続化。

住民の気分・親密度・掟を基に1日3件の出来事を生成する。
世界ごとの状態変更、住民の一言、変身、登録キャラクターの複製を管理する。
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
    HAKONIWA_AREA_MAP,
    HAKONIWA_AREAS,
    HAKONIWA_FURNITURE,
    HAKONIWA_IMAGE_MODEL_DEFAULT,
    HAKONIWA_PRESET_MAP,
    HAKONIWA_PRESET_RESIDENTS,
    HAKONIWA_ROOM_BACKGROUND_URL,
    HAKONIWA_RULE_CARDS,
    HAKONIWA_WORLD_NAME_MAX,
    area_background_url,
    furniture_url,
    preset_bundled_avatar_url,
)
from ..consts.language import normalize_language
from ..consts.novelai_models import resolve_user_image_model
from ..databases.base import async_session_factory
from ..databases.models import HakoniwaWorld
from . import hakoniwa_logic as logic
from .cost_tracker import begin_cost_tracking
from .hakoniwa_digest import build_day_digest
from .hakoniwa_generation import (
    convert_change_to_tags,
    convert_scene_to_tags,
    expand_appearance_tags,
    generate_event,
    generate_greeting,
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
        "appearance_text": resident.get("appearance_text") or "",
        "base_tags": resident.get("base_tags") or "",
        "dress_text": resident.get("dress_text") or "",
        "dress_tags": resident.get("dress_tags") or "",
        "mood": int(resident["mood"]),
        "affinities": dict(resident["affinities"]),
        "transformation": _transformation_view(
            world_id, resident.get("transformation")
        ),
        "transformation_history": [
            _transformation_view(world_id, item)
            for item in resident.get("transformation_history") or []
        ],
        "swapped_with": logic.swap_partner_id(state, resident["id"]),
        "current_area": resident.get("current_area") or DEFAULT_AREA_ID,
        **resident_image_urls(world_id, state, resident),
    }


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
        }
        for rule in state.get("custom_rules", [])
    )
    return cards


def _world_view(
    world: HakoniwaWorld,
    state: dict[str, Any],
    language: str,
    user_settings: dict[str, Any],
) -> dict[str, Any]:
    nsfw_mode = bool(user_settings.get("nsfw_mode"))
    effective_model = resolve_image_model(state, user_settings)
    return {
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
        "last_digest": state.get("last_digest"),
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
    ) -> dict[str, Any]:
        """プリセットの住民と登録キャラクターで新しい世界を作る。"""
        clean_name = " ".join(str(name or "").split())[:HAKONIWA_WORLD_NAME_MAX]
        if not clean_name:
            raise HakoniwaError("empty_name", "世界の名前を入力してください")
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
            state = logic.new_world_state(residents)
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

    async def delete_world(self, world_id: str) -> None:
        async with self._world_locks[world_id], async_session_factory() as db:
            world = await self._load(db, world_id)
            await db.delete(world)
            await db.commit()
        delete_world_images(world_id)
        self._world_locks.pop(world_id, None)

    async def update_settings(
        self, world_id: str, *, image_model: str, language: str | None = None
    ) -> dict[str, Any]:
        _, user_settings = await self._context(language)
        options = image_model_options(bool(user_settings.get("nsfw_mode")))
        if image_model != HAKONIWA_IMAGE_MODEL_DEFAULT and image_model not in options:
            raise HakoniwaError("invalid_image_model", "選べない画像モデルです")

        def change(state: dict[str, Any]) -> dict[str, Any]:
            return {**state, "image_model": image_model}

        return await self._mutate(world_id, language, change)

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
            groups = logic.choose_groups(state, rng)
            areas = [logic.pick_event_area(state, group, rng) for group in groups]
            focus = logic.custom_rule_focus_assignments(state, groups)
            titles = recent_titles(state)
            names = [
                [logic.resident_name(resident, lang) for resident in group]
                for group in groups
            ]
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
                    )
                    for index, group in enumerate(groups)
                )
            )
            used_titles = set(titles)
            new_events: list[dict[str, Any]] = []
            for group, area_id, event in zip(groups, areas, events, strict=True):
                if event.get("source") == "template" and event["title"] in used_titles:
                    # 並列に選んだ定型が同じ日に重ならないよう選び直す
                    event = template_event(
                        state, group, lang, rng, recent_titles=used_titles
                    )
                    event["area"] = area_id
                used_titles.add(event["title"])
                state = logic.apply_event(state, event, rng)
                new_events.append(state["events"][-1])
            state = logic.finish_day(state, rng)
            digest = build_day_digest(before, state, new_events)
            state["last_digest"] = digest
            async with async_session_factory() as db:
                world = await self._load(db, world_id)
                _store_state(world, state)
                await db.commit()
                view = _world_view(world, state, lang, user_settings)
        return {
            "world": view,
            "new_events": new_events,
            "digest": digest,
            "cost_usd": tracker.total_usd or None,
        }

    # ------------------------------------------------------------------
    # 掟
    # ------------------------------------------------------------------

    async def set_rule(
        self, world_id: str, card_id: str, active: bool, language: str | None = None
    ) -> dict[str, Any]:
        rng = random.Random()
        return await self._mutate(
            world_id,
            language,
            lambda state: logic.set_rule(state, card_id, active, rng),
        )

    async def add_custom_rule(
        self, world_id: str, name: str, text: str, language: str | None = None
    ) -> dict[str, Any]:
        return await self._mutate(
            world_id, language, lambda state: logic.add_custom_rule(state, name, text)
        )

    async def update_custom_rule(
        self,
        world_id: str,
        rule_id: str,
        name: str,
        text: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        return await self._mutate(
            world_id,
            language,
            lambda state: logic.update_custom_rule(state, rule_id, name, text),
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
        clean = logic.validate_resident_fields(**fields)
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
        """住民の名前・性格・性別・外見の説明を書き換える。外見の説明はタグに変換する。"""
        lang, user_settings = await self._context(language)
        clean = logic.validate_resident_fields(**fields)
        async with async_session_factory() as db:
            world = await self._load(db, world_id)
            current = logic.find_resident(_load_state(world), resident_id)
        tracker = begin_cost_tracking()
        novelai_model = user_settings.get("novelai_text_model")
        failed = False
        updates: dict[str, Any] = dict(clean)
        if clean["appearance_text"] != (current.get("appearance_text") or "") or clean[
            "gender"
        ] != logic.resident_gender(current):
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
            failed = failed or failed_base
        if clean["dress_text"] != (current.get("dress_text") or ""):
            preset = HAKONIWA_PRESET_MAP.get(str(current.get("preset_id") or ""))
            updates["dress_tags"], failed_dress = await self._derive_tags(
                clean["dress_text"],
                clean["gender"],
                dress=True,
                fallback=str(preset["dress_tags"]) if preset else "",
                novelai_model=novelai_model,
            )
            failed = failed or failed_dress
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
        novelai_model = user_settings.get("novelai_text_model")
        nsfw = bool(user_settings.get("nsfw_mode"))
        async with self._world_locks[world_id]:
            async with async_session_factory() as db:
                world = await self._load(db, world_id)
                state = _load_state(world)
            resident = logic.find_resident(state, resident_id)
            tracker = begin_cost_tracking()
            transformation = resident.get("transformation") or {}
            base_tags = (
                transformation.get("tags")
                or (
                    resident.get("dress_tags")
                    if "dress" in state.get("active_rules", [])
                    else None
                )
                or resident.get("base_tags")
                or _source_base_tags(resident)
            )
            tags = await convert_change_to_tags(
                change_text, base_tags, novelai_model=novelai_model
            )
            if not tags:
                raise HakoniwaError(
                    "tag_conversion_failed",
                    "変身の指定を画像のタグにできませんでした。文を変えてお試しください",
                )
            tags = logic.ensure_gender_token(tags, logic.resident_gender(resident))
            data = await self._generate_image(state, user_settings, tags)
            filename = save_image(world_id, f"tf_{resident_id}", data)
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
                    "narration": texts["narration"].format(
                        name=name, change=change_text
                    ),
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
            async with async_session_factory() as db:
                world = await self._load(db, world_id)
                _store_state(world, state)
                await db.commit()
                view = _world_view(world, state, lang, user_settings)
        return {
            "world": view,
            "new_events": new_events,
            "cost_usd": tracker.total_usd or None,
        }

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
            area = (
                HAKONIWA_AREA_MAP.get(str(event.get("area") or ""))
                or (HAKONIWA_AREA_MAP[DEFAULT_AREA_ID])
            )
            scene_tags = await convert_scene_to_tags(
                event,
                names,
                area["scene"],
                novelai_model=user_settings.get("novelai_text_model"),
            )
            request = scene_request(state, event, scene_tags or "")
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
