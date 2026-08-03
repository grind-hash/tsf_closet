"""独立アドベンチャーモードの生成と永続化。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from ..databases.base import async_session_factory
from ..databases.models import AdventureRun, AdventureTurn
from ..settings.config import settings
from .character_service import extract_protagonist_tags_from_history
from .image_generation import image_service
from .adventure_template_loader import SCENARIO_TEMPLATES, template_localized
from .llm_service import llm_service
from .session import DEFAULT_USER_ID, session_store

logger = logging.getLogger(__name__)


def _default_director_choices(language: str) -> list[dict[str, str]]:
    if language == "ja":
        return [
            {"id": "observe", "label": "周囲を詳しく観察する"},
            {"id": "talk", "label": "近くの人物に話しかける"},
            {"id": "advance", "label": "目的に向かって移動する"},
        ]
    return [
        {"id": "observe", "label": "Observe the surroundings closely"},
        {"id": "talk", "label": "Speak to someone nearby"},
        {"id": "advance", "label": "Move toward the objective"},
    ]


class AdventureError(RuntimeError):
    """アドベンチャー処理の利用者向けエラー。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AdventureChoice(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=160)


class AdventureVisualCharacter(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=800)
    clothing: str = Field(default="", max_length=600)
    action: str = Field(default="", max_length=400)


class AdventureVisualState(BaseModel):
    location: str = Field(min_length=1, max_length=200)
    appearance: str = Field(min_length=1, max_length=600)
    clothing: str = Field(default="", max_length=600)
    surroundings: str = Field(default="", max_length=800)
    main_characters: list[AdventureVisualCharacter] = Field(
        default_factory=list, max_length=5
    )

    @model_validator(mode="before")
    @classmethod
    def fill_missing_appearance(cls, value: Any, info: ValidationInfo) -> Any:
        if not isinstance(value, dict):
            return value
        appearance = value.get("appearance")
        if isinstance(appearance, str) and appearance.strip():
            return value
        fallback = (info.context or {}).get("fallback_appearance")
        if not isinstance(fallback, str) or not fallback.strip():
            return value
        return {**value, "appearance": fallback.strip()}

    @field_validator("main_characters", mode="before")
    @classmethod
    def normalize_main_characters(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [
            {"description": item} if isinstance(item, str) else item for item in value
        ]


class AdventureDirectorOutput(BaseModel):
    narrative: str = Field(min_length=1, max_length=3000)
    choices: list[AdventureChoice] = Field(min_length=3, max_length=3)
    discovered_clues: list[str] = Field(default_factory=list, max_length=10)
    completed_milestones: list[str] = Field(default_factory=list, max_length=3)
    visual_state: AdventureVisualState
    ending_status: Literal["continue", "success", "partial", "failure"] = "continue"
    ending_title: str | None = Field(default=None, max_length=160)
    ending_summary: str | None = Field(default=None, max_length=1200)

    @model_validator(mode="before")
    @classmethod
    def fill_missing_choices(cls, value: Any, info: ValidationInfo) -> Any:
        if not isinstance(value, dict):
            return value
        choices = value.get("choices")
        if isinstance(choices, list) and len(choices) == 3:
            return value
        fallback = (info.context or {}).get("fallback_choices")
        if not isinstance(fallback, list) or len(fallback) != 3:
            return value
        return {**value, "choices": fallback}

    @field_validator("completed_milestones", mode="before")
    @classmethod
    def normalize_completed_milestones(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [
            item.get("id")
            if isinstance(item, dict) and isinstance(item.get("id"), str)
            else item
            for item in value
        ]


class AdventureSetupOutput(BaseModel):
    setting: str = Field(min_length=1, max_length=600)
    objective: str = Field(min_length=1, max_length=600)
    constraints: list[str] = Field(min_length=1, max_length=4)


class AdventureImagePromptOutput(BaseModel):
    scene_tags: str = Field(min_length=1, max_length=1800)
    player_tags: str = Field(min_length=1, max_length=1200)
    npc_tags: list[str] = Field(default_factory=list, max_length=3)


class AdventureResolutionOutput(BaseModel):
    """確定済みナラティブから機械的な結果だけを抽出した出力。"""

    choices: list[AdventureChoice] = Field(min_length=3, max_length=3)
    discovered_clues: list[str] = Field(default_factory=list, max_length=10)
    completed_milestones: list[str] = Field(default_factory=list, max_length=3)
    ending_status: Literal["continue", "success", "partial", "failure"] = "continue"
    ending_title: str | None = Field(default=None, max_length=160)
    ending_summary: str | None = Field(default=None, max_length=1200)

    @model_validator(mode="before")
    @classmethod
    def fill_missing_choices(cls, value: Any, info: ValidationInfo) -> Any:
        if not isinstance(value, dict):
            return value
        choices = value.get("choices")
        if isinstance(choices, list) and len(choices) == 3:
            return value
        fallback = (info.context or {}).get("fallback_choices")
        if not isinstance(fallback, list) or len(fallback) != 3:
            return value
        return {**value, "choices": fallback}

    @field_validator("completed_milestones", mode="before")
    @classmethod
    def normalize_completed_milestones(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [
            item.get("id")
            if isinstance(item, dict) and isinstance(item.get("id"), str)
            else item
            for item in value
        ]


class AdventureVisualOutput(AdventureImagePromptOutput):
    """visual_state の更新と画像タグ変換を1回の生成でまとめた出力。"""

    visual_state: AdventureVisualState


_StructuredOutputT = TypeVar("_StructuredOutputT", bound=BaseModel)


def _image_prompt_payload(prompt: AdventureImagePromptOutput) -> dict[str, Any]:
    return {
        "scene_tags": prompt.scene_tags,
        "player_tags": prompt.player_tags,
        "npc_tags": list(prompt.npc_tags),
    }


def _visual_state_changed(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    return any(
        previous.get(key) != current.get(key)
        for key in (
            "location",
            "appearance",
            "clothing",
            "surroundings",
            "main_characters",
        )
    )


PRESETS: dict[str, dict[str, Any]] = {
    "infiltration": {
        "title": "潜入ミッション",
        "objective": "目的地へ潜入し、対象を確保して安全に離脱する",
        "guidance": (
            "変身後の外見や身体的特徴が開始スナップショットで明示されている場合、"
            "現地の制服や社員服へ着替えて役割になりすます選択肢を提示してよい。"
            "着替えはプレイヤーが選んだ場合だけ成立させる。"
        ),
        "milestones": [
            {"id": "gain_access", "label": "侵入経路を確保"},
            {"id": "secure_target", "label": "目的物または情報を確保"},
            {"id": "leave_safely", "label": "安全に離脱"},
        ],
    },
    "escape": {
        "title": "脱出・帰還ミッション",
        "objective": "障害を越えて安全な場所へ到達する",
        "guidance": "衣服や持ち物を環境へ適応する手段として利用できるが、着替えはプレイヤーが選んだ場合だけ成立させる。",
        "milestones": [
            {"id": "find_route", "label": "進路を発見"},
            {"id": "clear_obstacle", "label": "主要な障害を突破"},
            {"id": "reach_safety", "label": "目的地へ到達"},
        ],
    },
    "negotiation": {
        "title": "交渉ミッション",
        "objective": "相手から必要な協力、許可、または情報を得る",
        "guidance": "服装や役割が交渉へ影響する状況を作ってよいが、プレイヤーの感情や同意を決めつけない。",
        "milestones": [
            {"id": "find_leverage", "label": "交渉材料を発見"},
            {"id": "offer_terms", "label": "条件を提示"},
            {"id": "reach_agreement", "label": "合意を成立"},
        ],
    },
    "disguise": {
        "title": "なりすまし・着替えミッション",
        "objective": "変身後の人物として服装と振る舞いを整え、正体を怪しまれず目的を達成する",
        "guidance": (
            "プレイヤーは開始時点ですでに特定人物の姿へ変身している。"
            "開始場面で変身前の名前と変身後の人物名を具体的に示す。"
            "変身後の人物の観測可能な外見は開始スナップショットと完全に同一であり、"
            "髪色、髪型、目の色、体格などの特徴を新しく設定または変更しない。"
            "変身後の人物名や外見は物語上の事実として扱うが、その人物の記憶、知識、"
            "人間関係、口癖、技能、暗証番号、認証情報はプレイヤーへ与えない。"
            "プレイヤーは観察、会話、持ち物や服装の確認、即興の演技によって"
            "対象人物らしく振る舞い、NPCの疑念を避ける必要がある。"
            "NPCは外見から対象人物として認識してよいが、行動の矛盾には事実に基づいて疑念を示す。"
            "現地で入手可能な制服、社員服、ドレス、作業着などを具体的に登場させ、"
            "服を着る行為はプレイヤーが選んだ場合だけ描写する。"
        ),
        "milestones": [
            {"id": "learn_identity", "label": "対象人物の立場と振る舞いを把握する"},
            {"id": "complete_outfit", "label": "対象人物らしい服装と小物を整える"},
            {"id": "pass_as_identity", "label": "疑念を招かず目的を達成する"},
        ],
    },
}


def _last_equipment_action(value: str, aliases: tuple[str, ...]) -> str | None:
    lowered = value.lower()
    wear_pattern = re.compile(
        r"(?:着る|着用|身につけ|身に着け|履く|履い|つける|つけ|付ける|付け|貼る|貼り|装着|"
        r"かぶる|被る|使用|put on|wear|attach|apply)",
        re.IGNORECASE,
    )
    remove_pattern = re.compile(
        r"(?:脱ぐ|脱い|外す|外し|下げる|remove|take off)", re.IGNORECASE
    )
    actions: list[tuple[int, str]] = []
    for alias in aliases:
        for item_match in re.finditer(re.escape(alias.lower()), lowered):
            window = lowered[item_match.start() : item_match.start() + 60]
            actions.extend(
                (item_match.start() + match.start(), "wear")
                for match in wear_pattern.finditer(window)
            )
            actions.extend(
                (item_match.start() + match.start(), "remove")
                for match in remove_pattern.finditer(window)
            )
    return max(actions)[1] if actions else None


def _transform_appearance(appearance: str, config: dict[str, Any]) -> str:
    tags = [tag.strip() for tag in appearance.split(",") if tag.strip()]
    removed = {str(tag).lower() for tag in config.get("remove_tags", [])}
    transformed: list[str] = []
    for tag in tags:
        if tag.lower() in removed:
            continue
        for replacement in config.get("replace_patterns", []):
            tag = re.sub(
                str(replacement.get("pattern") or ""),
                str(replacement.get("replacement") or ""),
                tag,
                count=int(replacement.get("count") or 0),
                flags=re.IGNORECASE,
            )
        transformed.append(tag)
    for tag in config.get("ensure_tags", []):
        if str(tag).lower() not in {item.lower() for item in transformed}:
            transformed.append(str(tag))
    return ", ".join(dict.fromkeys(transformed))


def _json_load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _strip_json_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text


_CLOTHING_TAG_PATTERN = re.compile(
    r"\b(?:dress|skirt|shirt|top|pants|shorts|uniform|jacket|coat|suit|"
    r"leotard|lingerie|underwear|bra|panties|swimsuit|kimono|clothes|"
    r"outfit|shoes|boots|socks|stockings|gloves|hat)\b",
    re.IGNORECASE,
)
_SCENE_OR_ACTION_TAG_PATTERN = re.compile(
    r"\b(?:looking|applying|standing|sitting|walking|mirror|closet|room|"
    r"background|shelf)\b",
    re.IGNORECASE,
)


def _history_visual_description(history: Any) -> tuple[str, str]:
    description = history.after_description or history.before_description or ""
    extracted = extract_protagonist_tags_from_history(description)
    if not extracted:
        return description.strip(), ""

    tags = [tag.strip() for tag in extracted.split(",") if tag.strip()]
    clothing = [tag for tag in tags if _CLOTHING_TAG_PATTERN.search(tag)]
    appearance = [
        tag
        for tag in tags
        if not _CLOTHING_TAG_PATTERN.search(tag)
        and not _SCENE_OR_ACTION_TAG_PATTERN.search(tag)
    ]
    return ", ".join(appearance) or extracted, ", ".join(clothing)


class AdventureService:
    """アドベンチャーRunを元セッションから分離して管理する。"""

    def __init__(self) -> None:
        self._run_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._images_dir = settings.history_images_dir.parent / "adventure_images"
        self._images_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_image(self, raw_path: str) -> Path | None:
        raw = Path(raw_path)
        candidates = [
            raw,
            settings.history_images_dir.parent / raw,
            settings.history_images_dir / raw.name,
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    async def _build_snapshot(
        self, source_session_id: str, source_history_id: str | None
    ) -> tuple[dict[str, Any], Path, str, bool]:
        source_session = await session_store.get_session_by_id(source_session_id)
        if source_session is None or source_session.user_id != DEFAULT_USER_ID:
            raise AdventureError("source_not_found", "開始元セッションが見つかりません")

        source_history = None
        until_created_at = None
        appearance = ""
        starting_clothing = ""
        if source_history_id:
            source_history = await session_store.get_history_by_id(source_history_id)
            if source_history is None or source_history.session_id != source_session_id:
                raise AdventureError("source_not_found", "開始元の履歴が見つかりません")
            image_path = session_store.resolve_history_image_file(source_history)
            until_created_at = source_history.created_at
            appearance, starting_clothing = _history_visual_description(source_history)
        else:
            image_path = self._resolve_image(source_session.current_image_path)
            current_image_name = Path(source_session.current_image_path or "").name
            histories = await session_store.get_history(source_session_id)
            current_history = next(
                (
                    item
                    for item in reversed(histories)
                    if Path(item.image_path).name == current_image_name
                ),
                None,
            )
            if current_history is not None:
                appearance, starting_clothing = _history_visual_description(
                    current_history
                )

        if image_path is None:
            raise AdventureError("image_not_found", "開始画像が見つかりません")

        timeline = await session_store.get_session_timeline_until(
            source_session_id, until_created_at=until_created_at, limit=30
        )
        attributes_raw = await session_store.get_session_attributes(source_session_id)
        attributes: list[str] = []
        for attribute in attributes_raw:
            created_raw = attribute.get("created_at")
            if until_created_at is not None and created_raw:
                try:
                    if datetime.fromisoformat(str(created_raw)) > until_created_at:
                        continue
                except (TypeError, ValueError):
                    pass
            attributes.append(str(attribute.get("attribute_text", "")))

        stats = await session_store.get_session_stats(source_session_id)
        if source_history_id and stats is not None:
            stats = await session_store.reconstruct_stats_at_history(
                source_session_id,
                source_history_id,
                difficulty=stats.difficulty,
                nsfw_mode=stats.nsfw_mode,
            )
        nsfw_mode = bool(stats.nsfw_mode) if stats else False
        snapshot = {
            "source_session_id": source_session_id,
            "source_history_id": source_history_id,
            "appearance": appearance,
            "clothing": starting_clothing,
            "attributes": attributes,
            "timeline": [
                {"type": event_type, "text": text} for event_type, text in timeline
            ],
            "stats": {
                "bloom": stats.bloom,
                "shame": stats.shame,
                "adaptation": stats.adaptation,
            }
            if stats
            else None,
        }
        return snapshot, image_path, appearance, nsfw_mode

    def _director_system_prompt(self, language: str) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        return f"""You are the director of a short objective-based adventure game.
Return one JSON object only, in {response_language}, matching this schema:
{{"narrative":"...","choices":[{{"id":"...","label":"..."}},{{"id":"...","label":"..."}},{{"id":"...","label":"..."}}],"discovered_clues":[],"completed_milestones":[],"visual_state":{{"location":"...","appearance":"...","clothing":"...","surroundings":"...","main_characters":[{{"name":"...","description":"...","clothing":"...","action":"..."}}]}},"ending_status":"continue|success|partial|failure","ending_title":null,"ending_summary":null}}
Keep narrative under 800 characters and the entire JSON response compact. Never decide the player's feelings, consent, past wishes, bodily sensations, or voluntary actions unless the player's input explicitly states them. If the player's action objectively makes the mission impossible to continue, return a concise failure ending instead of refusing, truncating, or leaving the JSON incomplete. Describe observable events and NPC actions. Do not introduce an unrequested body transformation. Never grant the player another person's memories, personal knowledge, relationships, habits, skills, credentials, passwords, or authentication information unless the supplied source facts explicitly state them. A copied appearance or name does not imply copied memory or competence. Treat source_snapshot.appearance and required_visual_appearance as an immutable identity signature. Copy its hair color, hair length, hairstyle, eye color, and body features exactly into visual_state.appearance; never replace or supplement those traits. Do not change the player's physical appearance unless scenario_capabilities or authored_template_resolution explicitly allows and triggers that change. Clothing may be offered, found, or discussed, but the player only puts on, removes, or changes clothing when their input explicitly chooses that action. When the player explicitly chooses to put on clothing, visual_state.clothing must show that garment as currently worn in the same turn. Unless the input explicitly requests layering, the new garment replaces the previous outfit instead of being worn over it. If the source snapshot explicitly establishes a transformed sex or body, it may create practical disguise or role opportunities without inventing further changes. Keep visual_state concrete enough to illustrate the main characters, their clothing, and the surrounding location. completed_milestones must contain milestone ID strings only, never objects. Complete milestones only when the narrated action actually earns them. When authored_template_resolution is provided, treat it as authoritative and never narrate a score, transformation, unlocked exit, or ending beyond its event."""

    async def _generate_director_output(
        self,
        *,
        prompt: str,
        language: str,
        text_model: str,
        fallback_appearance: str = "",
    ) -> AdventureDirectorOutput:
        system_prompt = self._director_system_prompt(language)
        raw = await llm_service.generate_text(
            system_prompt,
            prompt,
            provider_override="novelai",
            novelai_model_override=text_model,
        )
        try:
            return AdventureDirectorOutput.model_validate_json(
                _strip_json_fence(raw.content),
                context={
                    "fallback_appearance": fallback_appearance,
                    "fallback_choices": _default_director_choices(language),
                },
            )
        except ValidationError as first_error:
            response_language = "Japanese" if language == "ja" else "English"
            repair_system_prompt = f"""Repair invalid adventure output as one new compact JSON object in {response_language}.
Return JSON only and keep the entire response under 1200 characters. Do not repeat or continue the source verbatim. Preserve only facts already present. Keep narrative under 500 characters. If the source describes an action that objectively ends the mission, preserve ending_status as failure and provide a short ending_summary. Required minimum shape: {{"narrative":"...","visual_state":{{"location":"...","appearance":"...","clothing":"..."}},"ending_status":"continue|success|partial|failure","ending_title":null,"ending_summary":null}}."""
            repair_prompt = "Invalid source output:\n\n" + raw.content
            repaired = await llm_service.generate_text(
                repair_system_prompt,
                repair_prompt,
                provider_override="novelai",
                novelai_model_override=text_model,
            )
            try:
                return AdventureDirectorOutput.model_validate_json(
                    _strip_json_fence(repaired.content),
                    context={
                        "fallback_appearance": fallback_appearance,
                        "fallback_choices": _default_director_choices(language),
                    },
                )
            except ValidationError as second_error:
                logger.warning(
                    "Adventure JSON validation failed: raw_length=%d "
                    "repaired_length=%d: %s / %s",
                    len(raw.content),
                    len(repaired.content),
                    first_error,
                    second_error,
                )
                raise AdventureError(
                    "invalid_model_output",
                    "物語生成結果を解析できませんでした。もう一度お試しください",
                ) from second_error

    def _narrative_system_prompt(self, language: str) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        return f"""You are the director of a short objective-based adventure game.
Write only the narrative for the next scene, as plain prose in {response_language}. Do not output JSON, markdown, headings, choices, labels, or commentary.
Keep the narrative under 800 characters. Never decide the player's feelings, consent, past wishes, bodily sensations, or voluntary actions unless the player's input explicitly states them. If the player's action objectively makes the mission impossible to continue, narrate a concise failure ending instead of refusing or truncating. Describe observable events and NPC actions. Do not introduce an unrequested body transformation. Never grant the player another person's memories, personal knowledge, relationships, habits, skills, credentials, passwords, or authentication information unless the supplied source facts explicitly state them. A copied appearance or name does not imply copied memory or competence. Treat state.appearance_lock and required_visual_appearance as an immutable identity signature, and never change the player's hair color, hair length, hairstyle, eye color, or body features unless scenario_guidance or authored_template_resolution explicitly allows and triggers that change. Clothing may be offered, found, or discussed, but the player only puts on, removes, or changes clothing when their input explicitly chooses that action. Unless the input explicitly requests layering, a new garment replaces the previous outfit instead of being worn over it. If the source snapshot explicitly establishes a transformed sex or body, it may create practical disguise or role opportunities without inventing further changes. When authored_template_resolution is provided, treat it as authoritative and never narrate a score, transformation, unlocked exit, or ending beyond its event."""

    def _resolution_system_prompt(self, language: str) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        return f"""You resolve the mechanical outcome of one adventure turn that has already been narrated.
Return one JSON object only, in {response_language}, matching this schema:
{{"choices":[{{"id":"...","label":"..."}},{{"id":"...","label":"..."}},{{"id":"...","label":"..."}}],"discovered_clues":[],"completed_milestones":[],"ending_status":"continue|success|partial|failure","ending_title":null,"ending_summary":null}}
Base every value strictly on the supplied narrative and game state, and never invent events the narrative does not contain. choices must offer exactly three distinct actions the player could take next. discovered_clues must contain only new information the narrative actually revealed, and must not repeat state.clues. completed_milestones must contain milestone ID strings only, never objects, and only when the narrated action actually earns them. Keep ending_status as continue unless the narrative itself concludes the mission, and fill ending_title and ending_summary only in that case. Never decide the player's feelings, consent, or voluntary actions. When authored_template_resolution is provided, treat it as authoritative and never report a score, transformation, or ending beyond its event. Keep the entire response compact."""

    def _visual_system_prompt(self, language: str) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        return f"""You update the visual state of an adventure scene and convert it into NovelAI image tags.
Return one JSON object only, matching this schema:
{{"visual_state":{{"location":"...","appearance":"...","clothing":"...","surroundings":"...","main_characters":[{{"name":"...","description":"...","clothing":"...","action":"..."}}]}},"scene_tags":"...","player_tags":"...","npc_tags":["..."]}}
Write visual_state values in {response_language}. Write scene_tags, player_tags, and npc_tags as concise English comma-separated tags.
Derive visual_state from previous_visual_state, changing only what the narrative states. Treat required_visual_appearance as an immutable identity signature: copy its hair color, hair length, hairstyle, eye color, and body features exactly into visual_state.appearance, and never replace or supplement those traits unless authored_template_resolution explicitly triggers that change. The player only puts on, removes, or changes clothing when player_input explicitly chose that action; otherwise keep previous_visual_state.clothing unchanged. Unless layering was explicitly requested, a new garment replaces the previous outfit. Keep visual_state concrete enough to illustrate the main characters, their clothing, and the surrounding location. main_characters contains NPCs, never the player.
When previous_image_tags is provided, treat it as the wording a human editor deliberately chose: reuse its scene_tags, player_tags, and npc_tags as the starting point and edit them only where visual_state or the narrative now requires a change, preserving the rest of the original wording and phrasing style. When previous_image_tags is absent, write the tags from scratch.
scene_tags contains only environment, camera, composition, lighting, and the observable interaction; it must not contain any character's gender, body, face, hair, or clothing. player_tags describes only the player from visual_state.appearance and visual_state.clothing. The player is always the primary subject in the center foreground. visual_state.clothing is authoritative and must never be replaced with an NPC outfit. npc_tags must contain one entry per NPC in main_characters, in the same order, describing only that NPC; every NPC is a secondary subject placed to the side or behind the player. Never merge player and NPC attributes. Do not add text, UI, split panels, or unstated changes."""

    async def _generate_structured_output(
        self,
        model: type[_StructuredOutputT],
        *,
        system_prompt: str,
        user_prompt: str,
        text_model: str,
        error_code: str,
        error_message: str,
        context: dict[str, Any] | None = None,
    ) -> _StructuredOutputT:
        raw = await llm_service.generate_text(
            system_prompt,
            user_prompt,
            provider_override="novelai",
            novelai_model_override=text_model,
        )
        try:
            return model.model_validate_json(
                _strip_json_fence(raw.content), context=context
            )
        except ValidationError as first_error:
            repaired = await llm_service.generate_text(
                system_prompt,
                "Repair the following output into one valid compact JSON object for "
                "the required schema. Return JSON only and do not add new facts.\n\n"
                + raw.content,
                provider_override="novelai",
                novelai_model_override=text_model,
            )
            try:
                return model.model_validate_json(
                    _strip_json_fence(repaired.content), context=context
                )
            except ValidationError as second_error:
                logger.warning(
                    "Adventure %s validation failed: %s / %s",
                    model.__name__,
                    first_error,
                    second_error,
                )
                raise AdventureError(error_code, error_message) from second_error

    async def _generate_resolution_output(
        self,
        *,
        narrative: str,
        turn_context: dict[str, Any],
        language: str,
        text_model: str,
    ) -> AdventureResolutionOutput:
        return await self._generate_structured_output(
            AdventureResolutionOutput,
            system_prompt=self._resolution_system_prompt(language),
            user_prompt=json.dumps(
                {**turn_context, "narrative": narrative}, ensure_ascii=False
            ),
            text_model=text_model,
            error_code="invalid_model_output",
            error_message="物語生成結果を解析できませんでした。もう一度お試しください",
            context={"fallback_choices": _default_director_choices(language)},
        )

    async def _generate_visual_output(
        self,
        *,
        narrative: str,
        turn_context: dict[str, Any],
        previous_visual: dict[str, Any],
        appearance_lock: str,
        language: str,
        text_model: str,
        previous_image_tags: dict[str, Any] | None = None,
    ) -> AdventureVisualOutput:
        return await self._generate_structured_output(
            AdventureVisualOutput,
            system_prompt=self._visual_system_prompt(language),
            user_prompt=json.dumps(
                {
                    "narrative": narrative,
                    "player_input": turn_context.get("player_input", ""),
                    "authored_template_resolution": turn_context.get(
                        "authored_template_resolution", {}
                    ),
                    "previous_visual_state": previous_visual,
                    "previous_image_tags": previous_image_tags,
                    "required_visual_appearance": appearance_lock,
                },
                ensure_ascii=False,
            ),
            text_model=text_model,
            error_code="invalid_image_prompt",
            error_message="場面の見た目を解析できませんでした",
            context={"fallback_appearance": appearance_lock},
        )

    def _setup_system_prompt(self, language: str) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        return f"""You design a concise setup for an eight-turn objective-based adventure game.
Return one JSON object only, in {response_language}, matching this schema:
{{"setting":"...","objective":"...","constraints":["...","..."]}}
The objective must name a concrete target and an observable end condition that can be judged as achieved or failed within eight turns. Do not use vague goals such as succeed, investigate the situation, or reach the objective. The setting, objective, and constraints must fit the selected mission preset and supplied character snapshot. Constraints must create actionable complications without dictating the player's feelings, consent, memories, bodily sensations, or voluntary actions. Do not introduce another body transformation or assign physical traits that conflict with source_snapshot.appearance. For a disguise mission, generate the transformed person's name and role while keeping the supplied appearance exactly; the player does not have that person's memories, relationships, habits, skills, credentials, passwords, or authentication information."""

    async def _generate_setup_output(
        self, *, prompt: str, language: str, text_model: str
    ) -> AdventureSetupOutput:
        system_prompt = self._setup_system_prompt(language)
        raw = await llm_service.generate_text(
            system_prompt,
            prompt,
            provider_override="novelai",
            novelai_model_override=text_model,
        )
        try:
            return AdventureSetupOutput.model_validate_json(
                _strip_json_fence(raw.content)
            )
        except ValidationError as first_error:
            repair_prompt = (
                "Repair the following output into valid JSON for the required schema. "
                "Do not add new scenario facts.\n\n" + raw.content
            )
            repaired = await llm_service.generate_text(
                system_prompt,
                repair_prompt,
                provider_override="novelai",
                novelai_model_override=text_model,
            )
            try:
                return AdventureSetupOutput.model_validate_json(
                    _strip_json_fence(repaired.content)
                )
            except ValidationError as second_error:
                logger.warning(
                    "Adventure setup JSON validation failed: %s / %s",
                    first_error,
                    second_error,
                )
                raise AdventureError(
                    "invalid_model_output",
                    "ミッション案を解析できませんでした。もう一度お試しください",
                ) from second_error

    async def generate_setup(
        self,
        *,
        source_session_id: str,
        source_history_id: str | None,
        preset: str,
    ) -> dict[str, Any]:
        preset_config = PRESETS.get(preset)
        if preset_config is None:
            raise AdventureError("invalid_preset", "シナリオ種別が不正です")

        snapshot, _, appearance, _ = await self._build_snapshot(
            source_session_id, source_history_id
        )
        user_settings = await session_store.get_user_settings()
        language = str(user_settings.get("language") or "ja")
        text_model = str(
            user_settings.get("novelai_text_model") or settings.novelai_text_model
        )
        prompt = json.dumps(
            {
                "task": "Generate one mission setup for the selected preset.",
                "preset": preset,
                "mission_definition": {
                    "title": preset_config["title"],
                    "default_objective": preset_config["objective"],
                    "milestones": preset_config["milestones"],
                    "guidance": preset_config["guidance"],
                },
                "source_snapshot": snapshot,
                "required_visual_appearance": appearance
                or "Preserve the source image appearance",
            },
            ensure_ascii=False,
        )
        generated = await self._generate_setup_output(
            prompt=prompt, language=language, text_model=text_model
        )
        return generated.model_dump()

    async def list_templates(self) -> list[dict[str, Any]]:
        user_settings = await session_store.get_user_settings()
        language = str(user_settings.get("language") or "ja")
        return [
            {
                "id": template_id,
                "preset": template["preset"],
                "title": template_localized(template, "title", language),
                "synopsis": template_localized(template, "synopsis", language),
                "setting": template_localized(template, "setting", language),
                "objective": template_localized(template, "objective", language),
                "constraints": template_localized(template, "constraints", language),
                "max_turns": template["max_turns"],
                "content_rating": template["content_rating"],
            }
            for template_id, template in SCENARIO_TEMPLATES.items()
        ]

    async def create_run(
        self,
        *,
        source_session_id: str,
        source_history_id: str | None,
        preset: str,
        custom_setup: str = "",
        scenario_setting: str = "",
        scenario_objective: str = "",
        scenario_constraints: list[str] | None = None,
        scenario_template_id: str | None = None,
        replay_run_id: str | None = None,
    ) -> dict[str, Any]:
        replay_run = None
        replay_state: dict[str, Any] = {}
        if replay_run_id:
            replay_run = await self.get_run_orm(replay_run_id)
            replay_state = _json_load(replay_run.state_json, {})
            replay_template_id = replay_state.get("scenario_template_id")
            scenario_template_id = (
                str(replay_template_id) if replay_template_id else None
            )
            preset = replay_run.preset
        template = (
            SCENARIO_TEMPLATES.get(scenario_template_id)
            if scenario_template_id
            else None
        )
        if scenario_template_id and template is None:
            raise AdventureError(
                "invalid_scenario_template", "作品シナリオが見つかりません"
            )
        effective_preset = str(template["preset"]) if template else preset
        preset_config = PRESETS.get(effective_preset)
        if preset_config is None:
            raise AdventureError("invalid_preset", "シナリオ種別が不正です")

        snapshot, source_image, appearance, nsfw_mode = await self._build_snapshot(
            source_session_id, source_history_id
        )
        user_settings = await session_store.get_user_settings()
        language = str(user_settings.get("language") or "ja")
        text_model = str(
            user_settings.get("novelai_text_model") or settings.novelai_text_model
        )
        if template:
            setting = str(template_localized(template, "setting", language))
            objective = str(template_localized(template, "objective", language))
            constraints = list(template_localized(template, "constraints", language))
            milestones = list(template_localized(template, "milestones", language))
            title = str(template_localized(template, "title", language))
            max_turns = int(template["max_turns"])
            scenario_guidance = (
                str(preset_config["guidance"]) + " " + str(template["guidance"])
            )
            opening_premise = str(
                template_localized(template, "opening_premise", language)
            )
        elif replay_run:
            setting = str(replay_state.get("setting") or "")
            objective = replay_run.objective
            constraints = list(_json_load(replay_run.constraints_json, []))
            milestones = list(
                replay_state.get("milestones") or preset_config["milestones"]
            )
            title = replay_run.title
            max_turns = replay_run.max_turns
            scenario_guidance = str(preset_config["guidance"])
            opening_premise = ""
        else:
            setting = scenario_setting.strip()
            objective = (
                scenario_objective.strip()
                or custom_setup.strip()
                or str(preset_config["objective"])
            )
            constraints = [
                item.strip() for item in (scenario_constraints or []) if item.strip()
            ]
            milestones = list(preset_config["milestones"])
            title = str(preset_config["title"])
            max_turns = 8
            scenario_guidance = str(preset_config["guidance"])
            opening_premise = ""

        start_state = template.get("start_state", {}) if template else {}
        prompt = json.dumps(
            {
                "task": "Create the opening scene for this adventure.",
                "preset": effective_preset,
                "setting": setting,
                "objective": objective,
                "constraints": constraints,
                "milestones": milestones,
                "scenario_guidance": scenario_guidance,
                "authored_opening_premise": opening_premise,
                "scenario_capabilities": start_state,
                "source_snapshot": snapshot,
                "required_visual_appearance": appearance
                or "Preserve the source image appearance",
            },
            ensure_ascii=False,
        )
        opening = await self._generate_director_output(
            prompt=prompt,
            language=language,
            text_model=text_model,
            fallback_appearance=appearance
            or str(snapshot.get("appearance") or "")
            or "Preserve the source image appearance",
        )
        if appearance:
            opening.visual_state.appearance = appearance
        clothing_policy = start_state.get("clothing", "source")
        if clothing_policy == "none":
            empty_clothing = template.get("rule", {}).get("empty_clothing", {})
            opening.visual_state.clothing = str(
                empty_clothing.get(language)
                or empty_clothing.get("en")
                or "not wearing any clothing"
            )
        elif clothing_policy == "fixed":
            fixed_clothing = start_state.get("fixed_clothing", {})
            opening.visual_state.clothing = str(
                fixed_clothing.get(language) or fixed_clothing.get("en") or ""
            )
        else:
            starting_clothing = str(snapshot.get("clothing") or "")
            if starting_clothing:
                opening.visual_state.clothing = starting_clothing

        run_id = str(uuid.uuid4())
        run_dir = self._images_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        source_suffix = source_image.suffix.lower()
        if source_suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            source_suffix = ".png"
        initial_path = run_dir / f"initial{source_suffix}"
        shutil.copyfile(source_image, initial_path)
        state = {
            "milestones": milestones,
            "completed_milestones": [],
            "clues": [],
            "setting": setting,
            "constraints": constraints,
            "appearance_lock": appearance,
            "scenario_template_id": scenario_template_id,
            "replayed_from_run_id": replay_run_id,
            "scenario_capabilities": start_state,
            "visual_state": opening.visual_state.model_dump(),
            "opening_narrative": opening.narrative,
            "opening_image_path": str(initial_path),
            "choices": [choice.model_dump() for choice in opening.choices],
        }
        if template:
            state["template_state"] = {
                "worn_items": [],
                "flags": {},
                "score": 0,
                "transformed": False,
            }
        run = AdventureRun(
            id=run_id,
            user_id=DEFAULT_USER_ID,
            source_session_id=source_session_id,
            source_history_id=source_history_id,
            preset=effective_preset,
            title=title,
            objective=objective,
            constraints_json=json.dumps(constraints, ensure_ascii=False),
            snapshot_json=json.dumps(snapshot, ensure_ascii=False),
            state_json=json.dumps(state, ensure_ascii=False),
            current_image_path=str(initial_path),
            initial_image_path=str(initial_path),
            status="active",
            max_turns=max_turns,
            language=language,
            nsfw_mode=nsfw_mode,
            text_model=text_model,
            image_provider="novelai",
            image_model=settings.novelai_model,
        )
        async with async_session_factory() as db:
            db.add(run)
            await db.commit()
            await db.refresh(run)
        try:
            await self.generate_image(run_id, redraw_from_reference=True)
        except Exception:
            logger.exception(
                "Adventure opening image generation failed: run_id=%s", run_id
            )
        return await self.get_run(run_id)

    async def list_runs(self) -> list[dict[str, Any]]:
        async with async_session_factory() as db:
            rows = (
                (
                    await db.execute(
                        select(AdventureRun)
                        .where(AdventureRun.user_id == DEFAULT_USER_ID)
                        .order_by(AdventureRun.updated_at.desc())
                    )
                )
                .scalars()
                .all()
            )
        return [self._serialize_run(row, [], include_snapshot=False) for row in rows]

    async def get_run_orm(
        self, run_id: str, *, with_turns: bool = False
    ) -> AdventureRun:
        async with async_session_factory() as db:
            stmt = select(AdventureRun).where(
                AdventureRun.id == run_id, AdventureRun.user_id == DEFAULT_USER_ID
            )
            if with_turns:
                stmt = stmt.options(selectinload(AdventureRun.turns))
            run = (await db.execute(stmt)).scalar_one_or_none()
        if run is None:
            raise AdventureError("run_not_found", "アドベンチャーが見つかりません")
        return run

    async def get_run(self, run_id: str) -> dict[str, Any]:
        run = await self.get_run_orm(run_id, with_turns=True)
        turns = sorted(run.turns, key=lambda item: item.turn_number)
        return self._serialize_run(run, turns)

    async def delete_run(self, run_id: str) -> None:
        await self.get_run_orm(run_id)
        async with async_session_factory() as db:
            await db.execute(delete(AdventureRun).where(AdventureRun.id == run_id))
            await db.commit()
        shutil.rmtree(self._images_dir / run_id, ignore_errors=True)

    def _merge_output(
        self,
        run: AdventureRun,
        output: AdventureDirectorOutput,
        turn_number: int,
        state_override: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str, bool, bool]:
        state = (
            state_override
            if state_override is not None
            else _json_load(run.state_json, {})
        )
        valid_ids = {item["id"] for item in state.get("milestones", [])}
        completed = set(state.get("completed_milestones", []))
        completed.update(
            item for item in output.completed_milestones if item in valid_ids
        )
        clues = list(
            dict.fromkeys([*state.get("clues", []), *output.discovered_clues])
        )[:20]
        previous_visual = state.get("visual_state", {})
        appearance_lock = state.get("appearance_lock")
        template_state = state.get("template_state", {})
        transformed = bool(
            isinstance(template_state, dict) and template_state.get("transformed")
        )
        if (
            not transformed
            and isinstance(appearance_lock, str)
            and appearance_lock.strip()
        ):
            output.visual_state.appearance = appearance_lock
        next_visual = output.visual_state.model_dump()
        clothing_changed = previous_visual.get("clothing", "") != next_visual.get(
            "clothing", ""
        )
        visual_changed = any(
            previous_visual.get(key) != next_visual.get(key)
            for key in (
                "location",
                "appearance",
                "clothing",
                "surroundings",
                "main_characters",
            )
        )
        state.update(
            {
                "completed_milestones": sorted(completed),
                "clues": clues,
                "visual_state": next_visual,
                "choices": [choice.model_dump() for choice in output.choices],
            }
        )

        status = output.ending_status
        if completed == valid_ids and valid_ids:
            status = "success"
        elif turn_number >= run.max_turns and status == "continue":
            status = "partial" if completed else "failure"
        ending_title = output.ending_title
        ending_summary = output.ending_summary
        if status != "continue" and not ending_title:
            ending_title = {
                "success": "目的達成",
                "partial": "部分達成",
                "failure": "ミッション失敗",
            }[status]
        if status != "continue" and not ending_summary:
            ending_summary = output.narrative
        state["ending_summary"] = ending_summary
        return state, status, visual_changed, clothing_changed

    def _explicit_clothing_from_input(
        self, user_input: str, language: str
    ) -> str | None:
        patterns = (
            r"(?P<item>[^。！？\n]{1,100}?)を(?:着る|着用する|身につける|身に着ける)",
            r"(?P<item>[^。！？\n]{1,100}?)に(?:着替える|着替えます)",
        )
        clothing = None
        for pattern in patterns:
            match = re.search(pattern, user_input.strip())
            if match:
                clothing = match.group("item").strip(" 、。！？")
                break
        if clothing is None and language != "ja":
            match = re.search(
                r"\b(?:put on|wear|change into)\s+(?:the\s+|an?\s+)?"
                r"(?P<item>[^.!?\n]{1,100})",
                user_input.strip(),
                flags=re.IGNORECASE,
            )
            if match:
                clothing = re.split(
                    r",|\s+(?:and|then)\s+", match.group("item"), maxsplit=1
                )[0].strip()
        if not clothing:
            return None

        clothing = re.sub(
            r"^(?:私は|僕は|俺は|自分は|君は|主人公は|すぐに|今すぐ|その場で)\s*",
            "",
            clothing,
        ).strip()
        return clothing or None

    def _clothing_narrative_suffix(
        self, clothing: str | None, narrative: str, language: str
    ) -> str:
        if not clothing:
            return ""
        if language == "ja":
            if re.search(r"(?:着た|着ている|着用した|着替えた)", narrative):
                return ""
            return f"君は{clothing}を着用した。"
        if re.search(
            r"\b(?:put on|wearing|wore|changed into)\b",
            narrative,
            flags=re.IGNORECASE,
        ):
            return ""
        return f"You put on {clothing}."

    def _enforce_explicit_clothing_action(
        self,
        output: AdventureDirectorOutput,
        user_input: str,
        language: str,
        *,
        apply_narrative_suffix: bool = True,
    ) -> bool:
        clothing = self._explicit_clothing_from_input(user_input, language)
        if not clothing:
            return False

        output.visual_state.clothing = clothing
        if apply_narrative_suffix:
            suffix = self._clothing_narrative_suffix(
                clothing, output.narrative, language
            )
            if suffix:
                output.narrative = f"{output.narrative.rstrip()}\n\n{suffix}"
        return True

    def _resolve_template_action(
        self,
        template: dict[str, Any] | None,
        state: dict[str, Any],
        user_input: str,
    ) -> dict[str, Any]:
        rule = template.get("rule", {}) if template else {}
        if rule.get("type") != "equipment_score":
            return {}

        template_state = state.setdefault(
            "template_state",
            {
                "worn_items": [],
                "flags": {},
                "score": 0,
                "transformed": False,
            },
        )
        worn_items = set(template_state.get("worn_items", []))
        item_actions: dict[str, str] = {}
        for item in rule.get("items", []):
            item_id = str(item.get("id") or "")
            aliases = tuple(str(alias) for alias in item.get("aliases", []))
            if not item_id or not aliases:
                continue
            action = _last_equipment_action(user_input, aliases)
            if action == "wear":
                worn_items.add(item_id)
                worn_items.update(str(value) for value in item.get("implies", []))
                item_actions[item_id] = action
            elif action == "remove":
                worn_items.discard(item_id)
                item_actions[item_id] = action

        flags = dict(template_state.get("flags", {}))
        rule_read = bool(template_state.get("rule_read") or flags.get("rule_read"))
        if any(
            re.search(str(pattern), user_input, re.IGNORECASE)
            for pattern in rule.get("read_rule_patterns", [])
        ):
            rule_read = True
        flags["rule_read"] = rule_read

        goal_checked = bool(
            any(
                re.search(str(pattern), user_input, re.IGNORECASE)
                for pattern in rule.get("goal_subject_patterns", [])
            )
            and any(
                re.search(str(pattern), user_input, re.IGNORECASE)
                for pattern in rule.get("goal_action_patterns", [])
            )
        )
        base_outfit = {str(value) for value in rule.get("base_outfit", [])}
        required_items = {str(value) for value in rule.get("required_items", [])}
        scores = rule.get("scores", {})
        event = "continue"
        score = int(template_state.get("score", template_state.get("door_score", 0)))
        if goal_checked and required_items.issubset(worn_items):
            score = int(scores.get("success", 100))
            template_state["transformed"] = True
            event = "perfect_score"
        elif goal_checked and base_outfit.issubset(worn_items):
            score = int(scores.get("almost", 90))
            event = "almost_complete"
        elif goal_checked:
            score = int(scores.get("incomplete", 0))
            event = "incomplete"

        milestone_ids = rule.get("milestone_ids", {})
        completed: list[str] = []
        if rule_read and milestone_ids.get("rule_read"):
            completed.append(str(milestone_ids["rule_read"]))
        if base_outfit.issubset(worn_items) and milestone_ids.get("base_outfit"):
            completed.append(str(milestone_ids["base_outfit"]))
        if score == int(scores.get("success", 100)) and milestone_ids.get("success"):
            completed.append(str(milestone_ids["success"]))

        template_state.update(
            {
                "worn_items": sorted(worn_items),
                "flags": flags,
                "score": score,
                "rule_read": rule_read,
                "door_score": score,
            }
        )
        state["completed_milestones"] = completed
        return {
            "event": event,
            "goal_checked": goal_checked,
            "score": score,
            "door_score": score,
            "worn_items": sorted(worn_items),
            "item_actions": item_actions,
            "transformation_triggered": event == "perfect_score",
        }

    def _template_event_config(
        self, template: dict[str, Any] | None, resolution: dict[str, Any]
    ) -> dict[str, Any]:
        rule = template.get("rule", {}) if template else {}
        if rule.get("type") != "equipment_score":
            return {}
        return rule.get("events", {}).get(resolution.get("event"), {}) or {}

    def _template_narrative_suffix(
        self,
        template: dict[str, Any] | None,
        resolution: dict[str, Any],
        language: str,
    ) -> str:
        narrative_suffix = self._template_event_config(template, resolution).get(
            "narrative_suffix", {}
        )
        return str(narrative_suffix.get(language) or narrative_suffix.get("en") or "")

    def _enforce_template_visual(
        self,
        template: dict[str, Any] | None,
        state: dict[str, Any],
        visual_state: AdventureVisualState,
        resolution: dict[str, Any],
        language: str,
    ) -> None:
        rule = template.get("rule", {}) if template else {}
        if rule.get("type") != "equipment_score":
            return

        worn_items = set(resolution.get("worn_items", []))
        visible_clothing: list[str] = []
        for item in rule.get("items", []):
            item_id = str(item.get("id") or "")
            if item_id not in worn_items:
                continue
            labels = item.get("labels", {})
            visible_clothing.append(
                str(labels.get(language) or labels.get("en") or item_id)
            )
        visual_state.clothing = (
            "、".join(visible_clothing)
            if language == "ja"
            else ", ".join(visible_clothing)
        )
        if not visible_clothing:
            empty_clothing = rule.get("empty_clothing", {})
            visual_state.clothing = str(
                empty_clothing.get(language)
                or empty_clothing.get("en")
                or "not wearing any clothing"
            )

        appearance_transform = self._template_event_config(template, resolution).get(
            "appearance_transform"
        )
        if isinstance(appearance_transform, dict):
            visual_state.appearance = _transform_appearance(
                str(state.get("appearance_lock") or visual_state.appearance),
                appearance_transform,
            )

    def _enforce_template_output(
        self,
        template: dict[str, Any] | None,
        state: dict[str, Any],
        output: AdventureDirectorOutput,
        resolution: dict[str, Any],
        language: str,
        *,
        apply_visual: bool = True,
        apply_narrative_suffix: bool = True,
    ) -> None:
        rule = template.get("rule", {}) if template else {}
        if rule.get("type") != "equipment_score":
            return

        output.completed_milestones = []
        output.ending_status = "continue"
        output.ending_title = None
        output.ending_summary = None
        if apply_visual:
            self._enforce_template_visual(
                template, state, output.visual_state, resolution, language
            )

        event_config = self._template_event_config(template, resolution)
        if not event_config:
            return
        clues = event_config.get("clues", {})
        localized_clues = clues.get(language) or clues.get("en") or []
        output.discovered_clues = list(
            dict.fromkeys([*output.discovered_clues, *localized_clues])
        )[:10]
        if apply_narrative_suffix:
            suffix = self._template_narrative_suffix(template, resolution, language)
            if suffix:
                output.narrative = f"{output.narrative.rstrip()}\n\n{suffix}"
        choices = event_config.get("choices", {})
        localized_choices = choices.get(language) or choices.get("en") or []
        if localized_choices:
            output.choices = [
                AdventureChoice.model_validate(item) for item in localized_choices
            ]
        ending_status = event_config.get("ending_status")
        if ending_status:
            output.ending_status = str(ending_status)
            ending_title = event_config.get("ending_title", {})
            ending_summary = event_config.get("ending_summary", {})
            output.ending_title = (
                str(ending_title.get(language) or ending_title.get("en") or "") or None
            )
            output.ending_summary = (
                str(ending_summary.get(language) or ending_summary.get("en") or "")
                or None
            )

    async def process_turn(
        self,
        *,
        run_id: str,
        client_turn_id: str,
        user_input: str,
        input_kind: str,
    ) -> tuple[dict[str, Any], bool, bool]:
        async with self._run_locks[run_id]:
            run = await self.get_run_orm(run_id, with_turns=True)
            for existing in run.turns:
                if existing.client_turn_id == client_turn_id:
                    return self._serialize_turn(existing), False, False
            if run.status != "active":
                raise AdventureError("run_completed", "このシナリオは終了しています")

            state = _json_load(run.state_json, {})
            template_id = state.get("scenario_template_id")
            template = SCENARIO_TEMPLATES.get(str(template_id))
            template_resolution = self._resolve_template_action(
                template, state, user_input
            )
            scenario_guidance = PRESETS.get(run.preset, {}).get("guidance", "")
            if template:
                scenario_guidance = f"{scenario_guidance} {template['guidance']}"
            previous_turns = [
                {"user_input": item.user_input, "narrative": item.narrative}
                for item in sorted(run.turns, key=lambda item: item.turn_number)
            ]
            prompt = json.dumps(
                {
                    "task": "Resolve the player's next action.",
                    "preset": run.preset,
                    "scenario_guidance": scenario_guidance,
                    "authored_template_resolution": template_resolution,
                    "objective": run.objective,
                    "max_turns": run.max_turns,
                    "next_turn": run.turn_count + 1,
                    "state": state,
                    "recent_turns": previous_turns[-7:],
                    "player_input": user_input,
                },
                ensure_ascii=False,
            )
            output = await self._generate_director_output(
                prompt=prompt,
                language=run.language,
                text_model=run.text_model,
                fallback_appearance=str(
                    state.get("appearance_lock")
                    or state.get("visual_state", {}).get("appearance")
                    or "Preserve the source image appearance"
                ),
            )
            if template:
                self._enforce_template_output(
                    template, state, output, template_resolution, run.language
                )
            else:
                self._enforce_explicit_clothing_action(output, user_input, run.language)
            turn_number = run.turn_count + 1
            next_state, next_status, visual_changed, clothing_changed = (
                self._merge_output(run, output, turn_number, state_override=state)
            )
            turn = AdventureTurn(
                id=str(uuid.uuid4()),
                run_id=run.id,
                client_turn_id=client_turn_id,
                turn_number=turn_number,
                user_input=user_input,
                input_kind=input_kind,
                narrative=output.narrative,
                choices_json=json.dumps(
                    [choice.model_dump() for choice in output.choices],
                    ensure_ascii=False,
                ),
                state_delta_json=json.dumps(next_state, ensure_ascii=False),
                image_path=run.current_image_path,
                image_status="pending" if visual_changed else "not_requested",
            )
            async with async_session_factory() as db:
                persisted = await db.get(AdventureRun, run.id)
                if persisted is None:
                    raise AdventureError(
                        "run_not_found", "アドベンチャーが見つかりません"
                    )
                persisted.state_json = json.dumps(next_state, ensure_ascii=False)
                persisted.turn_count = turn_number
                persisted.status = (
                    "active" if next_status == "continue" else next_status
                )
                persisted.ending_title = output.ending_title or (
                    next_state.get("ending_summary")
                    and {
                        "success": "目的達成",
                        "partial": "部分達成",
                        "failure": "ミッション失敗",
                    }.get(next_status)
                )
                persisted.ending_summary = next_state.get("ending_summary")
                persisted.updated_at = datetime.now()
                db.add(turn)
                await db.commit()
                await db.refresh(turn)

            result = self._serialize_turn(turn)
            result["run_status"] = (
                "active" if next_status == "continue" else next_status
            )
            result["remaining_turns"] = max(0, run.max_turns - turn_number)
            result["clues"] = next_state.get("clues", [])
            result["ending_title"] = output.ending_title or (
                {
                    "success": "目的達成",
                    "partial": "部分達成",
                    "failure": "ミッション失敗",
                }.get(next_status)
            )
            result["ending_summary"] = next_state.get("ending_summary")
            return result, visual_changed, clothing_changed

    async def stream_turn(
        self,
        *,
        run_id: str,
        client_turn_id: str,
        user_input: str,
        input_kind: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """ナラティブを逐次配信し、手がかり抽出と画像生成を並列実行する。"""
        async with self._run_locks[run_id]:
            run = await self.get_run_orm(run_id, with_turns=True)
            for existing in run.turns:
                if existing.client_turn_id == client_turn_id:
                    yield {"event": "turn", "data": self._serialize_turn(existing)}
                    yield {"event": "complete", "data": {"status": run.status}}
                    return
            if run.status != "active":
                raise AdventureError("run_completed", "このシナリオは終了しています")

            state = _json_load(run.state_json, {})
            template = SCENARIO_TEMPLATES.get(str(state.get("scenario_template_id")))
            template_resolution = self._resolve_template_action(
                template, state, user_input
            )
            scenario_guidance = PRESETS.get(run.preset, {}).get("guidance", "")
            if template:
                scenario_guidance = f"{scenario_guidance} {template['guidance']}"
            previous_turns = [
                {"user_input": item.user_input, "narrative": item.narrative}
                for item in sorted(run.turns, key=lambda item: item.turn_number)
            ]
            appearance_lock = str(
                state.get("appearance_lock")
                or state.get("visual_state", {}).get("appearance")
                or "Preserve the source image appearance"
            )
            turn_context = {
                "task": "Resolve the player's next action.",
                "preset": run.preset,
                "scenario_guidance": scenario_guidance,
                "authored_template_resolution": template_resolution,
                "objective": run.objective,
                "max_turns": run.max_turns,
                "next_turn": run.turn_count + 1,
                "state": state,
                "recent_turns": previous_turns[-7:],
                "player_input": user_input,
                "required_visual_appearance": appearance_lock,
            }

            yield {"event": "status", "data": {"phase": "narrative"}}
            narrative = ""
            async for chunk in llm_service.generate_feeling_stream(
                self._narrative_system_prompt(run.language),
                json.dumps(turn_context, ensure_ascii=False),
                provider_override="novelai",
                novelai_model_override=run.text_model,
            ):
                if not chunk:
                    continue
                narrative += chunk
                yield {"event": "narrative_chunk", "data": {"chunk": chunk}}
            narrative = _strip_json_fence(narrative.strip())[:3000].strip()
            if not narrative:
                raise AdventureError(
                    "invalid_model_output",
                    "物語生成結果を解析できませんでした。もう一度お試しください",
                )

            explicit_clothing = (
                None
                if template
                else self._explicit_clothing_from_input(user_input, run.language)
            )
            suffix = (
                self._template_narrative_suffix(
                    template, template_resolution, run.language
                )
                if template
                else self._clothing_narrative_suffix(
                    explicit_clothing, narrative, run.language
                )
            )
            if suffix:
                narrative = f"{narrative.rstrip()}\n\n{suffix}"
                yield {"event": "narrative_chunk", "data": {"chunk": f"\n\n{suffix}"}}
            yield {"event": "narrative_done", "data": {"narrative": narrative}}

            previous_visual = state.get("visual_state", {})
            queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

            async def resolution_producer() -> None:
                try:
                    resolution = await self._generate_resolution_output(
                        narrative=narrative,
                        turn_context=turn_context,
                        language=run.language,
                        text_model=run.text_model,
                    )
                    await queue.put(("resolution", resolution))
                except Exception as error:
                    logger.warning("Adventure resolution generation failed: %s", error)
                    await queue.put(("resolution_error", error))

            async def visual_producer() -> None:
                try:
                    visual = await self._generate_visual_output(
                        narrative=narrative,
                        turn_context=turn_context,
                        previous_visual=previous_visual,
                        appearance_lock=appearance_lock,
                        language=run.language,
                        text_model=run.text_model,
                        previous_image_tags=state.get("last_image_prompt"),
                    )
                except Exception as error:
                    logger.warning("Adventure visual generation failed: %s", error)
                    await queue.put(("visual_error", error))
                    return
                if template:
                    self._enforce_template_visual(
                        template,
                        state,
                        visual.visual_state,
                        template_resolution,
                        run.language,
                    )
                elif explicit_clothing:
                    visual.visual_state.clothing = explicit_clothing
                self._apply_appearance_lock(state, visual.visual_state)
                await queue.put(("visual", visual))

                next_visual = visual.visual_state.model_dump()
                if not _visual_state_changed(previous_visual, next_visual):
                    await queue.put(("image_skipped", None))
                    return
                clothing_changed = previous_visual.get(
                    "clothing", ""
                ) != next_visual.get("clothing", "")
                await queue.put(("status", {"phase": "image_generation"}))
                try:
                    image_path, _ = await self._generate_image_unlocked(
                        run.id,
                        None,
                        redraw_from_reference=clothing_changed,
                        prompt_override=visual,
                        turn_number=run.turn_count + 1,
                    )
                    await queue.put(("image", image_path))
                except Exception as error:
                    logger.warning("Adventure turn image generation failed: %s", error)
                    await queue.put(("image_error", error))

            resolution_task = asyncio.create_task(resolution_producer())
            visual_task = asyncio.create_task(visual_producer())
            yield {"event": "status", "data": {"phase": "clue_check"}}

            resolution: AdventureResolutionOutput | None = None
            visual_output: AdventureVisualOutput | None = None
            image_path: Path | None = None
            failures: list[tuple[str, Exception]] = []
            resolution_done = False
            visual_done = False
            image_done = False
            try:
                while not (resolution_done and visual_done and image_done):
                    kind, payload = await queue.get()
                    if kind == "status":
                        yield {"event": "status", "data": payload}
                    elif kind == "resolution":
                        resolution = payload
                        resolution_done = True
                    elif kind == "resolution_error":
                        failures.append(("clue_check", payload))
                        resolution_done = True
                    elif kind == "visual":
                        visual_output = payload
                        visual_done = True
                    elif kind == "visual_error":
                        failures.append(("image_generation", payload))
                        visual_done = True
                        image_done = True
                    elif kind == "image":
                        image_path = payload
                        image_done = True
                    elif kind == "image_error":
                        failures.append(("image_generation", payload))
                        image_done = True
                    elif kind == "image_skipped":
                        image_done = True
            finally:
                await asyncio.gather(
                    resolution_task, visual_task, return_exceptions=True
                )

            for phase, error in failures:
                yield {
                    "event": "error",
                    "data": {
                        "code": error.code
                        if isinstance(error, AdventureError)
                        else "generation_failed",
                        "message": str(error),
                        "phase": phase,
                        "retryable": True,
                    },
                }

            if resolution is None:
                resolution = AdventureResolutionOutput.model_validate(
                    {"choices": _default_director_choices(run.language)}
                )
            visual_state = (
                visual_output.visual_state
                if visual_output is not None
                else self._fallback_visual_state(previous_visual, appearance_lock)
            )

            output = AdventureDirectorOutput(
                narrative=narrative,
                choices=resolution.choices,
                discovered_clues=resolution.discovered_clues,
                completed_milestones=resolution.completed_milestones,
                visual_state=visual_state,
                ending_status=resolution.ending_status,
                ending_title=resolution.ending_title,
                ending_summary=resolution.ending_summary,
            )
            if template:
                self._enforce_template_output(
                    template,
                    state,
                    output,
                    template_resolution,
                    run.language,
                    apply_visual=False,
                    apply_narrative_suffix=False,
                )
            turn_number = run.turn_count + 1
            next_state, next_status, _, _ = self._merge_output(
                run, output, turn_number, state_override=state
            )
            if visual_output is not None and image_path is not None:
                next_state["last_image_prompt"] = _image_prompt_payload(visual_output)

            if image_path is not None:
                turn_image_path = str(image_path)
                image_status = "completed"
            else:
                turn_image_path = run.current_image_path
                image_status = "failed" if failures else "not_requested"

            turn = AdventureTurn(
                id=str(uuid.uuid4()),
                run_id=run.id,
                client_turn_id=client_turn_id,
                turn_number=turn_number,
                user_input=user_input,
                input_kind=input_kind,
                narrative=output.narrative,
                choices_json=json.dumps(
                    [choice.model_dump() for choice in output.choices],
                    ensure_ascii=False,
                ),
                state_delta_json=json.dumps(next_state, ensure_ascii=False),
                image_path=turn_image_path,
                image_status=image_status,
            )
            async with async_session_factory() as db:
                persisted = await db.get(AdventureRun, run.id)
                if persisted is None:
                    raise AdventureError(
                        "run_not_found", "アドベンチャーが見つかりません"
                    )
                persisted.state_json = json.dumps(next_state, ensure_ascii=False)
                persisted.turn_count = turn_number
                persisted.status = (
                    "active" if next_status == "continue" else next_status
                )
                persisted.ending_title = output.ending_title or (
                    next_state.get("ending_summary")
                    and {
                        "success": "目的達成",
                        "partial": "部分達成",
                        "failure": "ミッション失敗",
                    }.get(next_status)
                )
                persisted.ending_summary = next_state.get("ending_summary")
                persisted.updated_at = datetime.now()
                db.add(turn)
                await db.commit()
                await db.refresh(turn)

            result = self._serialize_turn(turn)
            result["run_status"] = (
                "active" if next_status == "continue" else next_status
            )
            result["remaining_turns"] = max(0, run.max_turns - turn_number)
            result["clues"] = next_state.get("clues", [])
            result["ending_title"] = output.ending_title or (
                {
                    "success": "目的達成",
                    "partial": "部分達成",
                    "failure": "ミッション失敗",
                }.get(next_status)
            )
            result["ending_summary"] = next_state.get("ending_summary")

            yield {"event": "turn", "data": result}
            if image_path is not None:
                yield {
                    "event": "image",
                    "data": {
                        "image_url": self.image_url(run.id, image_path),
                        "turn_id": turn.id,
                    },
                }
            yield {
                "event": "complete",
                "data": {
                    "status": result["run_status"],
                    "ending_title": result["ending_title"],
                    "ending_summary": result["ending_summary"],
                },
            }

    def _apply_appearance_lock(
        self, state: dict[str, Any], visual_state: AdventureVisualState
    ) -> None:
        template_state = state.get("template_state", {})
        transformed = bool(
            isinstance(template_state, dict) and template_state.get("transformed")
        )
        appearance_lock = state.get("appearance_lock")
        if (
            not transformed
            and isinstance(appearance_lock, str)
            and appearance_lock.strip()
        ):
            visual_state.appearance = appearance_lock

    def _fallback_visual_state(
        self, previous_visual: dict[str, Any], appearance_lock: str
    ) -> AdventureVisualState:
        try:
            return AdventureVisualState.model_validate(
                previous_visual, context={"fallback_appearance": appearance_lock}
            )
        except ValidationError as error:
            raise AdventureError(
                "invalid_image_prompt", "場面の見た目を解析できませんでした"
            ) from error

    async def _generate_image_prompt_output(
        self, visual_state: dict[str, Any], text_model: str
    ) -> AdventureImagePromptOutput:
        system_prompt = """Convert a visual_state into NovelAI image tags.
Return one JSON object only: {"scene_tags":"...","player_tags":"...","npc_tags":["..."]}.
All values must be concise English comma-separated tags. scene_tags contains only environment, camera, composition, lighting, and the observable interaction; it must not contain any character's gender, body, face, hair, or clothing. player_tags describes only the player from visual_state.appearance and visual_state.clothing. The player is always the primary subject in the center foreground. visual_state.clothing is authoritative and must never be replaced with an NPC outfit. main_characters contains NPCs, not the player. npc_tags must contain one entry per important NPC in the same order, describing only that NPC; every NPC is a secondary subject placed to the side or behind the player. Never merge player and NPC attributes. Do not add text, UI, split panels, or unstated changes."""
        raw = await llm_service.generate_text(
            system_prompt,
            json.dumps(visual_state, ensure_ascii=False),
            provider_override="novelai",
            novelai_model_override=text_model,
        )
        try:
            return AdventureImagePromptOutput.model_validate_json(
                _strip_json_fence(raw.content)
            )
        except ValidationError as first_error:
            logger.warning(
                "Adventure image prompt JSON validation failed: %s", first_error
            )
            repaired = await llm_service.generate_text(
                system_prompt,
                "Repair this into valid JSON without adding facts:\n\n" + raw.content,
                provider_override="novelai",
                novelai_model_override=text_model,
            )
            try:
                return AdventureImagePromptOutput.model_validate_json(
                    _strip_json_fence(repaired.content)
                )
            except ValidationError as second_error:
                raise AdventureError(
                    "invalid_image_prompt",
                    "画像プロンプトの生成結果を解釈できませんでした",
                ) from second_error

    async def generate_image(
        self,
        run_id: str,
        turn_id: str | None = None,
        *,
        redraw_from_reference: bool = False,
        prompt_override: AdventureImagePromptOutput | None = None,
    ) -> dict[str, Any]:
        async with self._run_locks[run_id]:
            image_path, effective_turn_id = await self._generate_image_unlocked(
                run_id,
                turn_id,
                redraw_from_reference=redraw_from_reference,
                prompt_override=prompt_override,
            )
        return {
            "image_url": self.image_url(run_id, image_path),
            "turn_id": effective_turn_id,
        }

    async def _generate_image_unlocked(
        self,
        run_id: str,
        turn_id: str | None = None,
        *,
        redraw_from_reference: bool = False,
        prompt_override: AdventureImagePromptOutput | None = None,
        turn_number: int | None = None,
    ) -> tuple[Path, str | None]:
        """呼び出し側が既に run ロックを保持している前提で画像を生成する。"""
        run = await self.get_run_orm(run_id)
        effective_turn_number = run.turn_count if turn_number is None else turn_number
        effective_turn_id = turn_id
        if effective_turn_id is None and turn_number is None and run.turn_count > 0:
            async with async_session_factory() as db:
                latest_turn = await db.scalar(
                    select(AdventureTurn)
                    .where(AdventureTurn.run_id == run.id)
                    .order_by(AdventureTurn.turn_number.desc())
                    .limit(1)
                )
                effective_turn_id = latest_turn.id if latest_turn else None
        state = _json_load(run.state_json, {})
        visual_state = state.get("visual_state", {})
        current_path = Path(run.current_image_path)
        initial_path = Path(run.initial_image_path)
        if not current_path.is_file() or not initial_path.is_file():
            raise AdventureError(
                "image_not_found", "アドベンチャー画像が見つかりません"
            )
        try:
            image_prompt = prompt_override or await self._generate_image_prompt_output(
                visual_state, run.text_model
            )
            characters = [
                {
                    "prompt": image_prompt.player_tags
                    + ", main protagonist, primary focus, center foreground",
                    "position": (0.55, 0.5),
                }
            ]
            npc_positions = ((0.18, 0.5), (0.82, 0.5), (0.12, 0.5))
            characters.extend(
                {
                    "prompt": npc_prompt
                    + ", supporting character, secondary focus, behind protagonist",
                    "position": npc_positions[index],
                }
                for index, npc_prompt in enumerate(image_prompt.npc_tags[:3])
            )
            source_image = None if redraw_from_reference else current_path.read_bytes()
            result = await image_service.generate_image(
                image_prompt.scene_tags
                + ", visual novel scene, protagonist in foreground, supporting NPCs secondary",
                image_bytes=source_image,
                provider_override="novelai",
                nsfw_mode=run.nsfw_mode,
                character_references=[
                    {
                        "image": initial_path.read_bytes(),
                        "type": "character",
                        "strength": 0.45 if redraw_from_reference else 0.85,
                        "fidelity": 0.65 if redraw_from_reference else 1.0,
                    }
                ],
                characters=characters,
                size_override="landscape",
                novelai_model_override=run.image_model,
            )
            if not result.images:
                raise AdventureError(
                    "image_generation_failed", "画像が生成されませんでした"
                )
        except AdventureError:
            await self._mark_image_failed(run.id, effective_turn_id)
            raise
        except Exception as error:
            await self._mark_image_failed(run.id, effective_turn_id)
            logger.exception(
                "Adventure image generation failed: run_id=%s turn_id=%s",
                run.id,
                turn_id,
            )
            raise AdventureError(
                "image_generation_failed",
                "場面画像の生成に失敗しました。画像を再生成してください",
            ) from error
        filename = f"turn-{effective_turn_number}-{uuid.uuid4().hex[:8]}.png"
        image_path = self._images_dir / run.id / filename
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(result.images[0])
        async with async_session_factory() as db:
            persisted_run = await db.get(AdventureRun, run.id)
            if persisted_run is None:
                raise AdventureError("run_not_found", "アドベンチャーが見つかりません")
            persisted_run.current_image_path = str(image_path)
            persisted_run.updated_at = datetime.now()
            persisted_state = _json_load(persisted_run.state_json, {})
            persisted_state["last_image_prompt"] = _image_prompt_payload(image_prompt)
            if effective_turn_number == 0:
                persisted_state["opening_image_path"] = str(image_path)
            persisted_run.state_json = json.dumps(persisted_state, ensure_ascii=False)
            if effective_turn_id:
                persisted_turn = await db.get(AdventureTurn, effective_turn_id)
                if persisted_turn and persisted_turn.run_id == run.id:
                    persisted_turn.image_path = str(image_path)
                    persisted_turn.image_status = "completed"
            await db.commit()
        return image_path, effective_turn_id

    async def _mark_image_failed(self, run_id: str, turn_id: str | None) -> None:
        if not turn_id:
            return
        try:
            async with async_session_factory() as db:
                turn = await db.get(AdventureTurn, turn_id)
                if turn and turn.run_id == run_id:
                    turn.image_status = "failed"
                    await db.commit()
        except Exception:
            logger.exception(
                "Adventure image failure status could not be saved: run_id=%s turn_id=%s",
                run_id,
                turn_id,
            )

    def image_url(self, run_id: str, image_path: Path) -> str:
        return f"/adventure/images/{run_id}/{image_path.name}"

    def image_file(self, run_id: str, filename: str) -> Path:
        safe_name = Path(filename).name
        path = self._images_dir / run_id / safe_name
        if not path.is_file():
            raise AdventureError("image_not_found", "画像が見つかりません")
        return path

    def _opening_image_path(self, run: AdventureRun, state: dict[str, Any]) -> Path:
        stored_path = Path(str(state.get("opening_image_path") or ""))
        if stored_path.is_file():
            return stored_path
        generated_images = list((self._images_dir / run.id).glob("turn-0-*.png"))
        if generated_images:
            return max(generated_images, key=lambda path: path.stat().st_mtime)
        return Path(run.initial_image_path)

    def _serialize_turn(
        self, turn: AdventureTurn, fallback_image_path: Path | None = None
    ) -> dict[str, Any]:
        image_path = Path(turn.image_path) if turn.image_path else fallback_image_path
        return {
            "id": turn.id,
            "turn_number": turn.turn_number,
            "client_turn_id": turn.client_turn_id,
            "user_input": turn.user_input,
            "input_kind": turn.input_kind,
            "narrative": turn.narrative,
            "choices": _json_load(turn.choices_json, []),
            "image_url": self.image_url(turn.run_id, image_path)
            if image_path
            else None,
            "image_status": turn.image_status,
            "created_at": turn.created_at.isoformat() if turn.created_at else None,
        }

    def _serialize_run(
        self,
        run: AdventureRun,
        turns: list[AdventureTurn],
        *,
        include_snapshot: bool = True,
    ) -> dict[str, Any]:
        state = _json_load(run.state_json, {})
        opening_image_path = self._opening_image_path(run, state)
        serialized_turns = []
        effective_image_path = opening_image_path
        for turn in turns:
            serialized_turn = self._serialize_turn(turn, effective_image_path)
            serialized_turns.append(serialized_turn)
            if turn.image_path:
                effective_image_path = Path(turn.image_path)
        response = {
            "id": run.id,
            "source_session_id": run.source_session_id,
            "source_history_id": run.source_history_id,
            "preset": run.preset,
            "scenario_template_id": state.get("scenario_template_id"),
            "title": run.title,
            "objective": run.objective,
            "setting": state.get("setting", ""),
            "constraints": _json_load(run.constraints_json, []),
            "status": run.status,
            "turn_count": run.turn_count,
            "max_turns": run.max_turns,
            "remaining_turns": max(0, run.max_turns - run.turn_count),
            "ending_title": run.ending_title,
            "ending_summary": run.ending_summary,
            "clues": state.get("clues", []),
            "milestones": state.get("milestones", []),
            "completed_milestones": state.get("completed_milestones", []),
            "opening_narrative": state.get("opening_narrative", ""),
            "opening_image_url": self.image_url(run.id, opening_image_path),
            "choices": state.get("choices", []),
            "current_image_url": self.image_url(run.id, Path(run.current_image_path)),
            "current_image_prompt": state.get("last_image_prompt"),
            "turns": serialized_turns,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        }
        if include_snapshot:
            response["snapshot"] = _json_load(run.snapshot_json, {})
        return response


adventure_service = AdventureService()
