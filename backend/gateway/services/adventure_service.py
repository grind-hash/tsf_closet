"""独立アドベンチャーモードの生成と永続化。"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import shutil
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypeVar

from annotated_types import MaxLen
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

from ..consts.adventure_narration import (
    NARRATION_PRONOUN_DEFAULT,
    NARRATION_PRONOUN_MAX_LENGTH,
    NARRATION_VOICE_DEFAULT,
    NARRATION_VOICES,
)
from ..consts.adventure_romance import (
    ROMANCE_MILESTONES,
    ROMANCE_PLAYER_DEFAULT_CHARACTER_ID,
    ROMANCE_SLOTS_PER_DAY,
)
from ..consts.adventure_turns import (
    ADVENTURE_TURNS_DEFAULT,
    ADVENTURE_TURNS_MAX,
    ADVENTURE_TURNS_MIN,
)
from ..databases.base import async_session_factory
from ..databases.models import AdventureRun, AdventureTurn
from ..settings.config import BASE_DIR, settings
from .character_service import extract_protagonist_tags_from_history
from .characters import character_manager
from .clothing_layers import (
    CLOTHING_LAYER_COVERED_NEGATIVE,
    merge_negative_prompt,
    normalize_tag_for_match,
    peel_undergarment_tags,
    split_tag_tokens,
)
from .image_generation import image_service
from .adventure_romance import (
    ROMANCE_NARRATIVE_GUIDANCE,
    ROMANCE_RESOLUTION_GUIDANCE,
    ROMANCE_VISUAL_GUIDANCE,
    RomanceActionError,
    RomanceSetupOutput,
    apply_romance_outcome,
    clamp_romance_max_turns,
    init_romance_state,
    opening_sim_view,
    public_sim_view,
    resolve_romance_action,
    romance_setup_system_prompt,
)
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


def _choice_as_dict(item: Any) -> dict[str, Any] | None:
    """選択肢要素を id/label の dict に正規化する。"""
    if isinstance(item, dict):
        return item
    if isinstance(item, BaseModel):
        return item.model_dump()
    if hasattr(item, "id") and hasattr(item, "label"):
        return {"id": getattr(item, "id"), "label": getattr(item, "label")}
    return None


def _choices_preview(choices: Any, *, limit: int = 3) -> str:
    """ログ用に選択肢入力の要約を返す。"""
    try:
        if not isinstance(choices, list):
            return repr(choices)[:300]
        preview: list[Any] = []
        for item in choices[:limit]:
            normalized = _choice_as_dict(item)
            if normalized is None:
                preview.append(
                    {
                        "type": type(item).__name__,
                        "repr": repr(item)[:120],
                    }
                )
                continue
            preview.append(
                {
                    "id": str(normalized.get("id") or "")[:40],
                    "label": str(normalized.get("label") or "")[:80],
                }
            )
        return json.dumps(preview, ensure_ascii=False)
    except Exception:
        return f"<unprintable:{type(choices).__name__}>"


def _sanitize_choices(
    choices: Any,
    *,
    language: str,
    fallback: list[dict[str, str]] | None = None,
    source: str = "unknown",
) -> list[dict[str, str]]:
    """有効な選択肢がちょうど3件そろうときだけ採用し、それ以外はフォールバックする。"""
    defaults = fallback if fallback is not None else _default_director_choices(language)
    # fallback=[] は「採用できなければ空のまま」という中間検証用。既定3択ではない。
    should_log_fallback = fallback is None or len(defaults) > 0

    if not isinstance(choices, list):
        if should_log_fallback:
            logger.warning(
                "Adventure choices fallback applied: source=%s language=%s "
                "reason=not_a_list raw_type=%s raw_preview=%s fallback_count=%s",
                source,
                language,
                type(choices).__name__,
                _choices_preview(choices),
                len(defaults),
            )
        return [dict(item) for item in defaults]

    cleaned: list[dict[str, str]] = []
    drop_reasons: list[str] = []
    for index, item in enumerate(choices):
        normalized = _choice_as_dict(item)
        if normalized is None:
            drop_reasons.append(f"[{index}] unnormalized_type={type(item).__name__}")
            continue
        choice_id = str(normalized.get("id") or "").strip()
        label = str(normalized.get("label") or "").strip()
        if not choice_id and not label:
            drop_reasons.append(f"[{index}] empty_id_and_label")
            continue
        if not choice_id:
            drop_reasons.append(f"[{index}] empty_id label={label[:40]!r}")
            continue
        if not label:
            drop_reasons.append(f"[{index}] empty_label id={choice_id[:40]!r}")
            continue
        cleaned.append({"id": choice_id[:40], "label": label[:160]})

    if len(cleaned) != 3:
        if should_log_fallback:
            if len(choices) != 3:
                reason = f"count_mismatch raw_count={len(choices)} valid_count={len(cleaned)}"
            else:
                reason = f"invalid_items valid_count={len(cleaned)}"
            logger.warning(
                "Adventure choices fallback applied: source=%s language=%s "
                "reason=%s raw_count=%s valid_count=%s drop_reasons=%s "
                "raw_preview=%s fallback_count=%s",
                source,
                language,
                reason,
                len(choices),
                len(cleaned),
                drop_reasons[:8],
                _choices_preview(choices),
                len(defaults),
            )
        return [dict(item) for item in defaults]
    return cleaned


class AdventureError(RuntimeError):
    """アドベンチャー処理の利用者向けエラー。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _truncate_overlong_text(value: str, limit: int) -> str:
    """上限超過の文字列を区切りを保って上限以内へ切り詰める。"""
    truncated = value[:limit]
    boundary = max(truncated.rfind(","), truncated.rfind("、"))
    if boundary >= limit // 2:
        truncated = truncated[:boundary]
    result = truncated.rstrip(" ,、。")
    return result or value[:limit]


def _clamp_to_declared_max(
    model: type[BaseModel], value: Any, field_name: str | None
) -> Any:
    """フィールド宣言の max_length を超える文字列を検証エラーにせず切り詰める。

    LLM 出力が長すぎるだけでターン全体の画像生成を失わないための保険。
    """
    if not isinstance(value, str) or not field_name:
        return value
    field = model.model_fields.get(field_name)
    if field is None:
        return value
    limit = next(
        (item.max_length for item in field.metadata if isinstance(item, MaxLen)),
        None,
    )
    if limit is None or len(value) <= limit:
        return value
    return _truncate_overlong_text(value, limit)


class AdventureChoice(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=160)

    @field_validator("id", "label", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class AdventureVisualCharacter(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=1200)
    clothing: str = Field(default="", max_length=1200)
    action: str = Field(default="", max_length=800)

    @field_validator("name", "description", "clothing", "action", mode="before")
    @classmethod
    def clamp_overlong_text(cls, value: Any, info: ValidationInfo) -> Any:
        return _clamp_to_declared_max(cls, value, info.field_name)


class AdventureVisualState(BaseModel):
    location: str = Field(min_length=1, max_length=200)
    appearance: str = Field(min_length=1, max_length=1200)
    clothing: str = Field(default="", max_length=1200)
    surroundings: str = Field(default="", max_length=1600)
    main_characters: list[AdventureVisualCharacter] = Field(
        default_factory=list, max_length=5
    )

    @field_validator(
        "location", "appearance", "clothing", "surroundings", mode="before"
    )
    @classmethod
    def clamp_overlong_text(cls, value: Any, info: ValidationInfo) -> Any:
        return _clamp_to_declared_max(cls, value, info.field_name)

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
        fallback = (info.context or {}).get("fallback_choices")
        if not isinstance(fallback, list) or len(fallback) != 3:
            fallback = None
        language = (info.context or {}).get("language") or "ja"
        sanitized = _sanitize_choices(
            value.get("choices"),
            language=str(language),
            fallback=fallback if isinstance(fallback, list) else None,
            source="AdventureDirectorOutput",
        )
        return {**value, "choices": sanitized}

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

    @field_validator("scene_tags", "player_tags", mode="before")
    @classmethod
    def clamp_overlong_text(cls, value: Any, info: ValidationInfo) -> Any:
        return _clamp_to_declared_max(cls, value, info.field_name)


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
        fallback = (info.context or {}).get("fallback_choices")
        if not isinstance(fallback, list) or len(fallback) != 3:
            fallback = None
        language = (info.context or {}).get("language") or "ja"
        sanitized = _sanitize_choices(
            value.get("choices"),
            language=str(language),
            fallback=fallback if isinstance(fallback, list) else None,
            source="AdventureResolutionOutput",
        )
        return {**value, "choices": sanitized}

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


class AdventureRomanceResolutionOutput(AdventureResolutionOutput):
    """romance ターン用。好感度と好み書換の機械可読フィールドを追加する。

    affection_set と updated_*_gift_ids は reality_alter ターンでのみ
    Python 側が採用する。適用規則は adventure_romance.apply_romance_outcome。
    """

    affection_delta: int = Field(default=0, ge=-20, le=20)
    affection_set: int | None = Field(default=None, ge=0, le=100)
    # 宣言が「交際を始める」を明示した場合のみ true。reality_alter ターン限定で
    # 告白成功と同じ扱い(全 milestone 達成 + success エンディング)になる
    start_dating: bool = False
    updated_liked_gift_ids: list[str] = Field(default_factory=list, max_length=12)
    updated_disliked_gift_ids: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("affection_delta", mode="before")
    @classmethod
    def clamp_affection_delta(cls, value: Any) -> Any:
        # LLM の過大値で検証エラー→修復リトライへ落ちないよう先にクランプする
        try:
            return max(-20, min(20, int(value)))
        except (TypeError, ValueError):
            return 0

    @field_validator("affection_set", mode="before")
    @classmethod
    def clamp_affection_set(cls, value: Any) -> Any:
        if value is None:
            return None
        try:
            return max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return None

    @field_validator("start_dating", mode="before")
    @classmethod
    def coerce_start_dating(cls, value: Any) -> Any:
        # null や文字列表現でも検証エラー→修復リトライへ落とさない
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes"}
        return bool(value)


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


def _template_visual_style(template: dict[str, Any] | None) -> dict[str, Any] | None:
    if not template:
        return None
    visual_style = template.get("visual_style")
    return visual_style if isinstance(visual_style, dict) else None


def _localized_visual_style_text(
    visual_style: dict[str, Any] | None, key: str, language: str
) -> str:
    if not visual_style:
        return ""
    value = visual_style.get(key)
    if not isinstance(value, dict):
        return str(value or "").strip()
    return str(value.get(language) or value.get("en") or "").strip()


def _authored_scene_tags(
    template: dict[str, Any] | None = None, state: dict[str, Any] | None = None
) -> str:
    if state:
        stored = str(state.get("authored_scene_tags") or "").strip()
        if stored:
            return stored
    visual_style = _template_visual_style(template)
    if not visual_style:
        return ""
    return str(visual_style.get("scene_tags") or "").strip()


def _merge_scene_tags(authored: str, generated: str) -> str:
    authored_clean = authored.strip().strip(",")
    generated_clean = generated.strip().strip(",")
    if not authored_clean:
        return generated_clean
    if not generated_clean:
        return authored_clean
    if authored_clean.lower() in generated_clean.lower():
        return generated_clean[:1800]
    return f"{authored_clean}, {generated_clean}"[:1800]


def _apply_visual_style_to_state(
    visual_state: AdventureVisualState,
    visual_style: dict[str, Any] | None,
    language: str,
    *,
    force: bool = True,
) -> None:
    location = _localized_visual_style_text(visual_style, "location", language)
    surroundings = _localized_visual_style_text(visual_style, "surroundings", language)
    if location and (force or _looks_like_drab_room(visual_state.location)):
        visual_state.location = location
    if surroundings and (force or _looks_like_drab_room(visual_state.surroundings)):
        visual_state.surroundings = surroundings


_DRAB_ROOM_PATTERN = re.compile(
    r"basement|locker|warehouse|fluorescent|concrete|dungeon|cellar|"
    r"地下室|ロッカー|倉庫|蛍光灯|コンクリート|地下|更衣室|石造り|寒い密室|密室",
    re.IGNORECASE,
)


def _looks_like_drab_room(text: str) -> bool:
    return bool(text and _DRAB_ROOM_PATTERN.search(text))


def _lean_state_for_llm(state: dict[str, Any]) -> dict[str, Any]:
    """物語・選択肢生成向けに、画像用の巨大フィールドを除いた state を返す。"""
    omit = {
        "last_image_prompt",
        "authored_scene_tags",
        "opening_image_path",
        # romance の相手立ち絵まわりのファイルパスは LLM に不要
        "partner_image_path",
        "partner_portrait_path",
        "opening_partner_portrait_path",
        # 人称指示はシステムプロンプト側に載るため、user prompt へは流さない
        "narration_voice",
        "narration_pronoun",
    }
    return {key: value for key, value in state.items() if key not in omit}


def _image_tags_changed(
    previous: dict[str, Any] | None, current: AdventureImagePromptOutput
) -> bool:
    if not previous:
        return True
    return (
        str(previous.get("scene_tags") or "").strip() != current.scene_tags.strip()
        or str(previous.get("player_tags") or "").strip() != current.player_tags.strip()
        or list(previous.get("npc_tags") or []) != list(current.npc_tags)
    )


# 装備IDごとの画像用英語タグ。LLM任せだとドレスが背景のラック側に逃げやすい。
_EQUIPMENT_IMAGE_TAGS: dict[str, str] = {
    "panties": "wearing panties",
    "bra": "wearing bra",
    "dress": (
        "wearing elegant princess ball gown, wearing dress, fully clothed, "
        "frilly princess dress on the body, long dress, sparkling gown"
    ),
    "tiara": "wearing tiara, crown on head",
    "sanitary_pad": "sanitary pad worn under clothing",
}


# Adventure の構造化JSON出力向けの衣装レイヤールール。
# clothing_layers.CLOTHING_LAYER_IMAGE_RULE は WORN_UNDER_LAYERS 行の出力を要求し、
# JSONスキーマと衝突するため、ここではタグ配置の指示だけを与える。
_CLOTHING_LAYER_TAG_RULE = """
Clothing layers are persistent state, not visibility. An outer garment covers the underwear beneath it without removing it, so keep worn underwear in visual_state.clothing even when it cannot be seen. In NovelAI tags, bra, panties, underwear, and lingerie mean the undergarment is VISIBLE: when the player wears an outer garment such as a dress or gown over them, omit those words from player_tags entirely and describe only the outer garment. Put them into player_tags only when the narrative explicitly lifts, opens, removes, or sees through the outer garment, and then only for the exposed area. When the intent is ambiguous, prefer the covered wording."""

# 下着を覆う外衣の装備ID。着用済みなら下着タグを positive から外す。
_EQUIPMENT_OUTER_ITEMS: frozenset[str] = frozenset({"dress"})

# 外衣に覆われる内側の装備ID。
_EQUIPMENT_UNDER_ITEMS: frozenset[str] = frozenset({"panties", "bra", "sanitary_pad"})

# 露出状態タグ（bottomless / topless）の判定用に上下を分ける。
_EQUIPMENT_UPPER_UNDER_ITEMS: frozenset[str] = frozenset({"bra"})
_EQUIPMENT_LOWER_UNDER_ITEMS: frozenset[str] = frozenset({"panties", "sanitary_pad"})


def _equipment_layers_covered(
    worn_items: set[str] | list[str], respect_clothing_layers: bool
) -> bool:
    """外衣を着ていて下着が覆われている状態かを返す。"""
    if not respect_clothing_layers:
        return False
    worn = {str(item) for item in worn_items}
    return bool(worn & _EQUIPMENT_OUTER_ITEMS) and bool(worn & _EQUIPMENT_UNDER_ITEMS)


def _equipment_image_tags(
    template: dict[str, Any] | None,
    worn_items: set[str] | list[str],
    *,
    respect_clothing_layers: bool = False,
) -> str:
    """装備済みアイテムの画像用タグを返す。

    respect_clothing_layers が有効で外衣を着ている場合、下着アイテムのタグは
    positive から除外する。NovelAI では bra / panties 等のタグが
    「下着が見えている」意味になり、ドレスの上から下着が描かれてしまうため。
    """
    if not template or not worn_items:
        return ""
    worn = {str(item) for item in worn_items}
    covered = _equipment_layers_covered(worn, respect_clothing_layers)
    tags: list[str] = []
    for item in template.get("rule", {}).get("items", []):
        item_id = str(item.get("id") or "")
        if item_id not in worn:
            continue
        if covered and item_id in _EQUIPMENT_UNDER_ITEMS:
            continue
        tag = _EQUIPMENT_IMAGE_TAGS.get(item_id)
        if tag:
            tags.append(tag)
        labels = item.get("labels") or {}
        en_label = str(labels.get("en") or "").strip()
        if en_label and en_label.lower() not in ",".join(tags).lower():
            tags.append(f"wearing {en_label}")
    return ", ".join(dict.fromkeys(tags))


# 未装備アイテムを打ち消す negative。装備済みアイテムのタグと語が重ならないよう、
# underwear / lingerie のような総称語は使わない（clothing_layers._UNDERGARMENT_HINTS）。
_EQUIPMENT_NEGATIVE_TAGS: dict[str, str] = {
    # 下着はモデルが強く補完してくるため重みを上げる。
    # underwear / lingerie のような総称語は着用中の相方まで消すので使わない。
    "panties": "1.5::panties::, panty, thong, briefs, boyshorts",
    "bra": "1.5::bra::, sports bra, bikini top",
    "dress": "dress, gown, ball gown, evening gown",
    "tiara": "tiara, crown, diadem, headdress",
    # 服の下で見えないため negative を出す意味がない
    "sanitary_pad": "",
}


def _unworn_equipment_items(
    template: dict[str, Any] | None, worn_items: set[str] | list[str]
) -> list[dict[str, Any]]:
    """equipment_score テンプレートで、まだ装備していないアイテムを返す。

    外衣を着ている場合、覆われる下着は「見えない」だけで矛盾しないため対象外にする。
    CLOTHING_LAYER_COVERED_NEGATIVE が `no panties` を negative に含めるので、
    ここで `panties` を negative に足すと自己矛盾になる。
    """
    rule = template.get("rule", {}) if template else {}
    if rule.get("type") != "equipment_score":
        return []
    worn = {str(item) for item in worn_items}
    outer_worn = bool(worn & _EQUIPMENT_OUTER_ITEMS)
    unworn: list[dict[str, Any]] = []
    for item in rule.get("items", []):
        item_id = str(item.get("id") or "")
        if not item_id or item_id in worn:
            continue
        if outer_worn and item_id in _EQUIPMENT_UNDER_ITEMS:
            continue
        unworn.append(item)
    return unworn


def _equipment_negative_tags(
    template: dict[str, Any] | None, worn_items: set[str] | list[str]
) -> str:
    """未装備アイテムを描かせないための negative タグを返す。"""
    tags: list[str] = []
    for item in _unworn_equipment_items(template, worn_items):
        item_id = str(item.get("id") or "")
        tag = _EQUIPMENT_NEGATIVE_TAGS.get(item_id)
        if tag is None:
            labels = item.get("labels") or {}
            tag = str(labels.get("en") or "").strip()
        if tag:
            tags.extend(part.strip() for part in tag.split(",") if part.strip())
    return ", ".join(dict.fromkeys(tags))


# _equipment_clothing_state_tags が出力する露出状態語と、LLM がその同義で書く語。
# 前ターンの last_image_prompt 経由で LLM が引き継いでくるため、装備採点シナリオでは
# 服装タグと同様に毎ターン全て落とし、worn_items から権威ある状態タグを付け直す。
_EXPOSURE_STATE_TAG_PATTERN = re.compile(
    r"\b(?:bottomless|topless|braless|pantiless|pantyless|nude|naked|"
    r"undressed|unclothed|"
    r"bare (?:chest|breasts?|hips?|butt|bottom|body|torso)|"
    r"exposed (?:chest|breasts?|nipples?|crotch|hips?))\b",
    re.IGNORECASE,
)


def _strip_clothing_tags_for_equipment_scenario(
    template: dict[str, Any] | None, player_tags: str
) -> str:
    """equipment_score シナリオの player_tags から服装・露出状態タグを一括で外す。

    このルールでは着ている物が worn_items だけで決まるのに、player_tags は
    visual_state が補正される前に LLM が書くため、元セッションの私服などが
    そのまま残りうる。前ターンの露出状態タグ（topless 等）も previous_image_tags
    経由で引き継がれ、新しい装備タグを打ち消してしまう。
    服装と露出状態は決定論のタグで置き直す。
    """
    rule = template.get("rule", {}) if template else {}
    if rule.get("type") != "equipment_score" or not player_tags.strip():
        return player_tags
    kept = [
        token
        for token in split_tag_tokens(player_tags)
        if not _CLOTHING_TAG_PATTERN.search(normalize_tag_for_match(token))
        and not _EXPOSURE_STATE_TAG_PATTERN.search(normalize_tag_for_match(token))
    ]
    # player_tags は min_length=1。全部消える入力では元をそのまま返す。
    return ", ".join(kept) if kept else player_tags


def _equipment_clothing_state_tags(
    template: dict[str, Any] | None, worn_items: set[str] | list[str]
) -> str:
    """今の露出状態を表すタグを返す。

    「ブラだけ」のような状態は学習分布から外れており、negative で下衣を消すだけ
    では下着を描き足されてしまう。Danbooru 語彙の bottomless / topless で
    「上だけ着ている」状態そのものを指示する方が確実に効く。
    服装タグを外したままにもできないので、裸の場合も明示する。
    """
    rule = template.get("rule", {}) if template else {}
    if rule.get("type") != "equipment_score":
        return ""
    worn = {str(item) for item in worn_items}
    if worn & _EQUIPMENT_OUTER_ITEMS:
        # 外衣で覆われていれば露出状態を指示する必要はない
        return ""
    upper_worn = bool(worn & _EQUIPMENT_UPPER_UNDER_ITEMS)
    lower_worn = bool(worn & _EQUIPMENT_LOWER_UNDER_ITEMS)
    if upper_worn and not lower_worn:
        return "1.4::bottomless::, no panties, bare hips"
    if lower_worn and not upper_worn:
        return "1.4::topless::, no bra, bare chest"
    if not upper_worn and not lower_worn and rule.get("empty_clothing"):
        return "1.4::completely nude::, no clothes"
    return ""


def _apply_clothing_layers_to_player_tags(
    player_tags: str, *, covered: bool
) -> tuple[str, str | None]:
    """覆い状態なら player_tags から下着タグを剥がし、(タグ, extra negative) を返す。"""
    if not covered:
        return player_tags, None
    kept, peeled = peel_undergarment_tags(player_tags)
    if not peeled:
        return player_tags, CLOTHING_LAYER_COVERED_NEGATIVE
    return kept, CLOTHING_LAYER_COVERED_NEGATIVE


# equipment_score の決定論選択肢用。露出済み衣類の「調べる」を避け、着用動詞で進行させる。
_EQUIPMENT_WEAR_VERB_JA: dict[str, str] = {
    "panties": "を履く",
    "bra": "をつける",
    "dress": "を着る",
    "tiara": "をつける",
    "sanitary_pad": "をつける",
}


def _equipment_wear_choice_label(item_id: str, label: str, language: str) -> str:
    """装備アイテムの着用選択肢ラベルを生成する。"""
    clean = label.strip()
    if not clean:
        clean = item_id
    if language == "ja":
        verb = _EQUIPMENT_WEAR_VERB_JA.get(item_id, "を身につける")
        return f"{clean}{verb}"
    return f"Put on {clean}"


def _equipment_score_choices(
    template: dict[str, Any] | None,
    state: dict[str, Any],
    language: str,
) -> list[dict[str, str]] | None:
    """equipment_score 用の次手3択を未装備から決定論生成する。非対象なら None。"""
    rule = template.get("rule", {}) if template else {}
    if rule.get("type") != "equipment_score":
        return None

    items = rule.get("items") or []
    if not isinstance(items, list) or not items:
        return None

    required = {str(item_id) for item_id in rule.get("required_items", [])}
    base_outfit = {str(item_id) for item_id in rule.get("base_outfit", [])}
    template_state = state.get("template_state") or {}
    worn = {str(item_id) for item_id in template_state.get("worn_items", [])}
    flags = template_state.get("flags") or {}
    rule_read = bool(template_state.get("rule_read") or flags.get("rule_read"))

    item_by_id: dict[str, dict[str, Any]] = {}
    missing_ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            continue
        item_by_id[item_id] = item
        if item_id in required and item_id not in worn:
            missing_ids.append(item_id)

    choices: list[dict[str, str]] = []
    for item_id in missing_ids[:2]:
        item = item_by_id[item_id]
        labels = item.get("labels") or {}
        label = str(labels.get(language) or labels.get("en") or item_id)
        choices.append(
            {
                "id": f"wear_{item_id}"[:40],
                "label": _equipment_wear_choice_label(item_id, label, language)[:160],
            }
        )

    if language == "ja":
        explore_pool = [
            (
                "read_rule",
                "扉の文章を読む",
                not rule_read,
            ),
            (
                "check_door",
                "扉の前に立って採点を確認する",
                base_outfit.issubset(worn) or not missing_ids,
            ),
            (
                "look_around",
                "部屋を見回す",
                True,
            ),
            (
                "review_outfit",
                "身につけた品を確認する",
                bool(worn),
            ),
        ]
    else:
        explore_pool = [
            ("read_rule", "Read the door text", not rule_read),
            (
                "check_door",
                "Stand before the door and check the score",
                base_outfit.issubset(worn) or not missing_ids,
            ),
            ("look_around", "Look around the room", True),
            ("review_outfit", "Review the equipped items", bool(worn)),
        ]

    # 優先度順: 条件を満たす explore を先に、look_around は常に候補
    ordered_explore: list[dict[str, str]] = []
    for choice_id, label, enabled in explore_pool:
        if not enabled:
            continue
        ordered_explore.append({"id": choice_id, "label": label})

    seen_labels = {item["label"] for item in choices}
    for filler in ordered_explore:
        if len(choices) >= 3:
            break
        if filler["label"] in seen_labels:
            continue
        choices.append(filler)
        seen_labels.add(filler["label"])

    if len(choices) < 3:
        defaults = _default_director_choices(language)
        for item in defaults:
            if len(choices) >= 3:
                break
            if item["label"] in seen_labels:
                continue
            choices.append(dict(item))
            seen_labels.add(item["label"])

    if len(choices) != 3:
        return None
    return choices


def _character_reference_strength(
    *, outfit_changed: bool, has_fresh_portrait: bool
) -> tuple[float, float]:
    """character reference の (strength, fidelity) を返す。

    参照画像が旧衣装の初期画像である場合のみ、衣装変更時に弱参照へ落とす。
    このターンの新衣装で描いた直後の立ち絵を参照する場合は弱めない。
    """
    if has_fresh_portrait or not outfit_changed:
        return 0.85, 1.0
    return 0.35, 0.55


def _compose_scene_base_tags(image_prompt: AdventureImagePromptOutput) -> str:
    """合成シーンの base プロンプト用タグを組み立てる。

    solo シーンでは NPC への衣装ブリードが起きないため、立ち絵と同様に
    base プロンプトでも主人公の衣装タグを先頭で明示し、character
    サブプロンプトのみの場合より衣装の一致率を上げる。
    """
    if image_prompt.npc_tags:
        return image_prompt.scene_tags
    return _merge_player_tags(image_prompt.player_tags, image_prompt.scene_tags)


def _merge_player_tags(base: str, extra: str) -> str:
    base_clean = base.strip().strip(",")
    extra_clean = extra.strip().strip(",")
    if not extra_clean:
        return base_clean
    if not base_clean:
        return extra_clean
    if extra_clean.lower() in base_clean.lower():
        return base_clean
    return f"{base_clean}, {extra_clean}"[:1200]


def _enhance_adventure_prompt(prompt: str, *, nsfw_mode: bool) -> str:
    from .prompts import enhance_prompt_for_novelai

    result = enhance_prompt_for_novelai(prompt)
    if nsfw_mode and "nsfw" not in result.lower():
        result = f"{result}, nsfw"
    return result


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


def _sanitize_visual_state(value: Any) -> dict[str, Any] | None:
    """state_json の visual_state を API レスポンス用の形へ整える。"""
    if not isinstance(value, dict):
        return None
    characters: list[dict[str, str]] = []
    for item in value.get("main_characters") or []:
        if isinstance(item, str):
            item = {"description": item}
        if not isinstance(item, dict):
            continue
        character = {
            key: str(item.get(key) or "")
            for key in ("name", "description", "clothing", "action")
        }
        if any(character.values()):
            characters.append(character)
    return {
        "location": str(value.get("location") or ""),
        "appearance": str(value.get("appearance") or ""),
        "clothing": str(value.get("clothing") or ""),
        "surroundings": str(value.get("surroundings") or ""),
        "main_characters": characters[:5],
    }


def clamp_generated_max_turns(value: int) -> int:
    """Keep an auto-generated run's turn budget inside the supported range."""
    return max(ADVENTURE_TURNS_MIN, min(ADVENTURE_TURNS_MAX, int(value)))


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
    "romance": {
        "title": "恋愛シミュレーション",
        "objective": "期限の日までに想いを通わせ、交際を始める",
        "guidance": (
            "特定の相手との好感度育成シミュレーション。1日は昼と夜の2枠で進み、"
            "romance_resolution が示す日付・時間帯・金銭・バイト・プレゼント・"
            "告白の結果を確定事実として描写する。相手の言動は関係段階に応じて"
            "温度を変え、プレイヤー自身の感情や同意は決めつけない。恋愛的な"
            "進展は相手の主体的な反応として描き、金額や数値は本文へ書かない。"
        ),
        "milestones": ROMANCE_MILESTONES,
    },
}


# 既定エンディング文言。ending_title 未設定時のフォールバックに使う
_MISSION_ENDING_TITLES: dict[str, str] = {
    "success": "目的達成",
    "partial": "部分達成",
    "failure": "ミッション失敗",
}
_ROMANCE_ENDING_TITLES: dict[str, str] = {
    "success": "交際成立",
    "partial": "想いは届きかけた",
    "failure": "恋は実らなかった",
}


def _default_ending_title(preset: str, status: str) -> str | None:
    titles = _ROMANCE_ENDING_TITLES if preset == "romance" else _MISSION_ENDING_TITLES
    return titles.get(status)


def _romance_prompt_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """romance の攻略対象素材として LLM へ渡す snapshot。

    character_name はそのセッションの変身前の主人公名であり、変身後の姿である
    攻略対象の名前ではないため除外する(相手の名前は LLM が新しく考える)。
    """
    return {key: value for key, value in snapshot.items() if key != "character_name"}


def _romance_partner_visual_entry(
    main_characters: list[Any], npc_tags: list[str], partner_name: str
) -> tuple[dict[str, str] | None, str]:
    """main_characters から攻略対象のエントリと対応する npc_tags を探す。

    エントリは dict / Pydantic モデルの両方を受け付ける(state 保存値と
    LLM 出力の両方から呼ばれるため)。
    """
    name_key = str(partner_name or "").strip()
    if not name_key:
        return None, ""
    for index, member in enumerate(main_characters):
        if isinstance(member, dict):
            member_name = str(member.get("name") or "").strip()
            description = str(member.get("description") or "")
            clothing = str(member.get("clothing") or "")
        else:
            member_name = str(getattr(member, "name", "") or "").strip()
            description = str(getattr(member, "description", "") or "")
            clothing = str(getattr(member, "clothing", "") or "")
        if not member_name:
            continue
        if name_key in member_name or member_name in name_key:
            entry = {
                "name": member_name,
                "description": description,
                "clothing": clothing,
            }
            tags = npc_tags[index] if index < len(npc_tags) else ""
            return entry, tags
    return None, ""


_GENDER_TAG_PATTERN = re.compile(
    r"\b(1boy|1girl|male|female|boy|girl|man|woman|androgynous)\b", re.IGNORECASE
)


def _romance_template_player_appearance(character: Any) -> str:
    """テンプレ主人公の外見タグを組み立てる。

    base_tags に性別トークンが無いと画像モデルが女性寄りに描画するため、
    キャラ定義の gender から明示タグを先頭に足す。既に含まれていれば足さない。
    """
    base = str(
        getattr(character, "base_tags", "") or getattr(character, "description", "")
    ).strip()
    if _GENDER_TAG_PATTERN.search(base):
        return base
    gender = str(getattr(character, "gender", "") or "").strip().lower()
    if gender in {"man", "male", "boy"}:
        prefix = "male, 1boy"
    elif gender in {"woman", "female", "girl"}:
        prefix = "female, 1girl"
    else:
        return base
    return f"{prefix}, {base}" if base else prefix


_EQUIPMENT_WEAR_PATTERN = re.compile(
    r"(?:着る|着用|身につけ|身に着け|履く|履い|つける|つけ|付ける|付け|貼る|貼り|装着|"
    r"かぶる|被る|使用|put on|wear|attach|apply)",
    re.IGNORECASE,
)
_EQUIPMENT_REMOVE_PATTERN = re.compile(
    r"(?:脱ぐ|脱い|外す|外し|下げる|remove|take off)", re.IGNORECASE
)
# エイリアス前後の走査幅。日本語は名詞の後ろ、英語は名詞の前に動詞が来る。
_EQUIPMENT_ACTION_WINDOW = 60

# 「AとBを身につける」のように動詞を共有する並列表現。境界として扱わない。
_EQUIPMENT_LIST_JOINER = re.compile(
    r"[\s、,，・/&]*(?:と|や|および|and)?[\s、,，・/&]*"
)

# 「ナプキンをショーツの内側に貼る」の「ショーツの」のように、直後が修飾・場所を
# 示す助詞なら、その語は着脱動詞の対象ではないので境界にしない。
_EQUIPMENT_MODIFIER_PARTICLE = re.compile(r"^(?:の|に|へ|で|から|より|まで)")


def _alias_spans(lowered: str, aliases: tuple[str, ...]) -> list[tuple[int, int]]:
    """小文字化済み文字列から、いずれかのエイリアスに一致する範囲を返す。"""
    spans: list[tuple[int, int]] = []
    for alias in aliases:
        cleaned = alias.lower().strip()
        if not cleaned:
            continue
        spans.extend(
            (match.start(), match.end())
            for match in re.finditer(re.escape(cleaned), lowered)
        )
    return spans


def _last_equipment_action(
    value: str,
    aliases: tuple[str, ...],
    *,
    other_aliases: tuple[str, ...] = (),
) -> str | None:
    """入力からこのアイテムに対する着脱操作を判定する。

    エイリアス出現位置の前後を見て、最も近い着脱動詞をそのエイリアスへ帰属させる。
    走査範囲は other_aliases（他アイテムの語）で打ち切り、隣の衣類に付いた動詞を
    取り違えないようにする。
    """
    lowered = value.lower()
    own_spans = _alias_spans(lowered, aliases)
    if not own_spans:
        return None
    other_spans = [
        span for span in _alias_spans(lowered, other_aliases) if span not in own_spans
    ]
    # 「ヘッドドレス」の中の「ドレス」のように、他アイテムのより長い語に
    # 内包されているだけの一致は自分の出現として数えない。
    own_spans = [
        (start, end)
        for start, end in own_spans
        if not any(
            other_start <= start
            and end <= other_end
            and (other_end - other_start) > (end - start)
            for other_start, other_end in other_spans
        )
    ]
    if not own_spans:
        return None
    # 「ドレスの上からティアラをつける」の「ドレスの」のように、直後が修飾・場所の
    # 助詞なら着脱の対象ではない。全出現が修飾なら、このアイテムは操作されていない。
    direct_spans = [
        (start, end)
        for start, end in own_spans
        if not _EQUIPMENT_MODIFIER_PARTICLE.match(lowered[end:])
    ]
    if not direct_spans:
        return None
    own_spans = direct_spans

    def _is_joined(gap_start: int, gap_end: int) -> bool:
        """並列助詞だけで隔てられているなら境界として扱わない。"""
        if gap_start >= gap_end:
            return True
        return _EQUIPMENT_LIST_JOINER.fullmatch(lowered[gap_start:gap_end]) is not None

    def _is_boundary(other_start: int, other_end: int) -> bool:
        """他アイテムの語を走査の打ち切り位置として扱うか。"""
        return not _EQUIPMENT_MODIFIER_PARTICLE.match(lowered[other_end:])

    # (エイリアスからの距離, 出現位置, 種別) の最小をアイテム全体の判定とする
    best: tuple[int, int, str] | None = None
    for start, end in own_spans:
        # 他アイテムの語を越えない範囲へ窓を狭める
        left_bound = max(
            [0, start - _EQUIPMENT_ACTION_WINDOW]
            + [
                other_end
                for other_start, other_end in other_spans
                if other_end <= start
                and not _is_joined(other_end, start)
                and _is_boundary(other_start, other_end)
            ]
        )
        right_bound = min(
            [len(lowered), end + _EQUIPMENT_ACTION_WINDOW]
            + [
                other_start
                for other_start, other_end in other_spans
                if other_start >= end
                and not _is_joined(end, other_start)
                and _is_boundary(other_start, other_end)
            ]
        )
        window = lowered[left_bound:right_bound]
        for pattern, action in (
            (_EQUIPMENT_WEAR_PATTERN, "wear"),
            (_EQUIPMENT_REMOVE_PATTERN, "remove"),
        ):
            for match in pattern.finditer(window):
                position = left_bound + match.start()
                distance = start - position if position < start else position - end
                candidate = (max(distance, 0), position, action)
                if best is None or candidate < best:
                    best = candidate
    return best[2] if best else None


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


# プレイヤーが手番中に宣言する現実改変。通常ゲームのセッション属性とは独立に、
# Run の state へ蓄積して以降の全ターン判定へ渡す。
# 括弧形式（通常ゲームの属性表記）はコロン省略可。素の語形はコロン必須にして、
# 「現実改変について尋ねる」のような通常の行動を誤検出しない。
_REALITY_DECLARATION_PATTERN = re.compile(
    r"^\s*(?:"
    r"\[\s*(?:現実改変|reality(?:[ _-]?alteration)?)\s*\]\s*[:：]?"
    r"|(?:現実改変|reality(?:[ _-]?alteration)?)\s*[:：]"
    r")\s*(?P<rule>.+)",
    re.IGNORECASE | re.DOTALL,
)
_MAX_REALITY_RULES = 12
_MAX_REALITY_RULE_LENGTH = 300

# 全ターン判定へ共通で載せる現実改変の扱い。宣言済みルールが空でも無害。
_REALITY_RULES_INSTRUCTION = (
    "reality_rules is a list of world-alteration rules the player has declared. "
    "Treat every entry as an absolute, already-established fact of this world that "
    "applies to the entire scene and to every character in it, not as an intention, "
    "a request, or something that might fail. They override ordinary social "
    "expectations, NPC suspicion, and scenario constraints wherever they conflict. "
    "No NPC questions, doubts, objects to, is alarmed by, reports, restrains, or "
    "escalates any behaviour that a rule covers, however extreme or sexual that "
    "behaviour is; they react as if it were entirely unremarkable. Behaviour covered "
    "by a rule must never by itself set ending_status to failure, block the "
    "objective, or make the mission impossible to continue, and must never be "
    "narrated as being noticed as strange. The player may deliberately exploit these "
    "rules to advance: an action that a rule makes possible can legitimately reveal "
    "clues, complete milestones, and satisfy the objective. The mission may still end "
    "in failure for reasons no rule covers, such as running out of turns or acting "
    "against the objective itself. When reality_rule_declared_this_turn is set, the "
    "player's input declared that rule this turn: narrate the world already conforming "
    "to it, keep ending_status as continue, and never treat the declaration itself as "
    "a suspicious act."
)


# 人称を切り替えても、同意・主体性のガードは弱めない。どの人称でも同じ文を添える。
_NARRATION_VOICE_GUARD = (
    "Choosing this grammatical person changes only the grammatical subject and "
    "viewpoint of the prose. It grants no additional authority over the player "
    "character and overrides no other rule: you must still never state or imply the "
    "player character's feelings, emotions, opinions, preferences, comfort, consent, "
    "refusal, wishes, memories, intentions, plans, or any voluntary action that the "
    "player's input did not explicitly state. Earlier entries in recent_turns may use "
    "a different narration voice; ignore their voice and follow this rule."
)

_NARRATION_VOICE_RULES: dict[str, str] = {
    "second_person": (
        "Write the player character in the second person, addressing them directly as "
        '"you" (in Japanese, 「あなた」 or 「君」). '
    ),
    "third_person": (
        "Write the player character in the third person, as a character observed from "
        "outside rather than an addressee. Refer to them with third-person pronouns "
        "and, where a noun phrase reads better, a short descriptive phrase built only "
        "from traits already present in required_visual_appearance — for example "
        '「黒髪ボブの彼女」. Never address the player as "you"/「あなた」/「君」 and '
        "never use a first-person pronoun for them. Narrate only what an outside "
        "observer could see or hear. "
    ),
}


def normalize_narration_pronoun(value: str | None) -> str:
    """一人称語を1語に正規化する。システムプロンプトへ入るため改行等を落とす。"""
    cleaned = re.sub(r"\s+", "", str(value or ""))[:NARRATION_PRONOUN_MAX_LENGTH]
    return cleaned or NARRATION_PRONOUN_DEFAULT


def normalize_narration_voice(value: str | None) -> str:
    """未知の値や旧 run の欠落は既定の二人称へ倒す。"""
    voice = str(value or "")
    return voice if voice in NARRATION_VOICES else NARRATION_VOICE_DEFAULT


def _narration_voice_instruction(voice: str, pronoun: str) -> str:
    """語りの人称指示を返す。プロンプト末尾に置いて直近性を効かせる。"""
    voice = normalize_narration_voice(voice)
    if voice == "first_person":
        rule = (
            "Write the player character in the first person, as their own account of "
            f"the scene, using the pronoun 「{normalize_narration_pronoun(pronoun)}」 "
            "for every self-reference and never substituting a different first-person "
            "pronoun. First person permits exactly two additions and nothing more: "
            "(1) the character's physical actions that follow directly from the "
            "player's input, and (2) what the character can perceive with their senses "
            "at this instant. Do not write interior monologue, deliberation, "
            "self-commentary, reaction, or judgement. If a sentence would require the "
            "character to want, decide, feel, agree to, refuse, or remember something, "
            "drop the sentence and narrate the external event instead. "
        )
    else:
        rule = _NARRATION_VOICE_RULES[voice]
    return "NARRATION VOICE: " + rule + _NARRATION_VOICE_GUARD


def _narration_from_state(state: dict[str, Any]) -> tuple[str, str]:
    """run の state から (人称, 一人称語) を取り出す。旧 run は既定へ倒す。"""
    return (
        normalize_narration_voice(state.get("narration_voice")),
        normalize_narration_pronoun(state.get("narration_pronoun")),
    )


def _detect_reality_declaration(user_input: str) -> str | None:
    """「現実改変：〜」形式の宣言ならルール本文を返す。宣言でなければ None。"""
    match = _REALITY_DECLARATION_PATTERN.match(user_input or "")
    if match is None:
        return None
    rule = " ".join(match.group("rule").split()).strip()
    if not rule:
        return None
    return rule[:_MAX_REALITY_RULE_LENGTH]


def _append_reality_rule(state: dict[str, Any], rule: str) -> list[str]:
    """宣言されたルールを state へ追記し、更新後の一覧を返す。"""
    rules = [str(item) for item in state.get("reality_rules", []) if str(item).strip()]
    if rule not in rules:
        rules.append(rule)
    rules = rules[-_MAX_REALITY_RULES:]
    state["reality_rules"] = rules
    return rules


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
        # 旧テスト用モック等で character_id が無くても snapshot 構築は続行する
        source_character = character_manager.get_by_id(
            str(getattr(source_session, "character_id", "") or "")
        )
        snapshot = {
            "source_session_id": source_session_id,
            "source_history_id": source_history_id,
            "character_name": source_character.name if source_character else None,
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

    def _director_system_prompt(
        self,
        language: str,
        *,
        narration_voice: str = NARRATION_VOICE_DEFAULT,
        narration_pronoun: str = NARRATION_PRONOUN_DEFAULT,
        romance: bool = False,
    ) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        voice_rule = _narration_voice_instruction(narration_voice, narration_pronoun)
        if romance:
            voice_rule = f"{ROMANCE_NARRATIVE_GUIDANCE}\n{voice_rule}"
        return f"""You are the director of a short objective-based adventure game.
Return one JSON object only, in {response_language}, matching this schema:
{{"narrative":"...","choices":[{{"id":"...","label":"..."}},{{"id":"...","label":"..."}},{{"id":"...","label":"..."}}],"discovered_clues":[],"completed_milestones":[],"visual_state":{{"location":"...","appearance":"...","clothing":"...","surroundings":"...","main_characters":[{{"name":"...","description":"...","clothing":"...","action":"..."}}]}},"ending_status":"continue|success|partial|failure","ending_title":null,"ending_summary":null}}
Keep narrative under 800 characters and the entire JSON response compact. Never decide the player's feelings, consent, past wishes, bodily sensations, or voluntary actions unless the player's input explicitly states them. If the player's action objectively makes the mission impossible to continue, return a concise failure ending instead of refusing, truncating, or leaving the JSON incomplete. Describe observable events and NPC actions. Do not introduce an unrequested body transformation. Never grant the player another person's memories, personal knowledge, relationships, habits, skills, credentials, passwords, or authentication information unless the supplied source facts explicitly state them. A copied appearance or name does not imply copied memory or competence. Treat source_snapshot.appearance and required_visual_appearance as an immutable identity signature. Copy its sex, hair color, hair length, hairstyle, eye color, and body features exactly into visual_state.appearance; never replace or supplement those traits. Do not change the player's physical appearance unless scenario_capabilities or authored_template_resolution explicitly allows and triggers that change. Clothing may be offered, found, or discussed, but the player only puts on, removes, or changes clothing when their input explicitly chooses that action. When the player explicitly chooses to put on clothing, visual_state.clothing must show that garment as currently worn in the same turn. Unless the input explicitly requests layering, the new garment replaces the previous outfit instead of being worn over it. If the source snapshot explicitly establishes a transformed sex or body, it may create practical disguise or role opportunities without inventing further changes. Keep visual_state concrete enough to illustrate the main characters, their clothing, and the surrounding location. When authored_visual_style is provided, set visual_state.location and visual_state.surroundings from it and never describe the room as a basement, locker room, warehouse, or cold industrial cell. completed_milestones must contain milestone ID strings only, never objects. Complete milestones only when the narrated action actually earns them. When authored_template_resolution is provided, treat it as authoritative and never narrate a score, transformation, unlocked exit, or ending beyond its event.
{_REALITY_RULES_INSTRUCTION}
{voice_rule}"""

    async def _generate_director_output(
        self,
        *,
        prompt: str,
        language: str,
        text_model: str,
        fallback_appearance: str = "",
        narration_voice: str = NARRATION_VOICE_DEFAULT,
        narration_pronoun: str = NARRATION_PRONOUN_DEFAULT,
        romance: bool = False,
    ) -> AdventureDirectorOutput:
        system_prompt = self._director_system_prompt(
            language,
            narration_voice=narration_voice,
            narration_pronoun=narration_pronoun,
            romance=romance,
        )
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
                    "language": language,
                },
            )
        except ValidationError as first_error:
            response_language = "Japanese" if language == "ja" else "English"
            repair_system_prompt = f"""Repair invalid adventure output as one new compact JSON object in {response_language}.
Return JSON only and keep the entire response under 1200 characters. Do not repeat or continue the source verbatim. Preserve only facts already present. Keep narrative under 500 characters. If the source describes an action that objectively ends the mission, preserve ending_status as failure and provide a short ending_summary. Required minimum shape: {{"narrative":"...","visual_state":{{"location":"...","appearance":"...","clothing":"..."}},"ending_status":"continue|success|partial|failure","ending_title":null,"ending_summary":null}}.
{_narration_voice_instruction(narration_voice, narration_pronoun)}"""
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
                        "language": language,
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

    def _narrative_system_prompt(
        self,
        language: str,
        *,
        narration_voice: str = NARRATION_VOICE_DEFAULT,
        narration_pronoun: str = NARRATION_PRONOUN_DEFAULT,
        romance: bool = False,
    ) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        voice_rule = _narration_voice_instruction(narration_voice, narration_pronoun)
        if romance:
            voice_rule = f"{ROMANCE_NARRATIVE_GUIDANCE}\n{voice_rule}"
        return f"""You are the director of a short objective-based adventure game.
Write only the narrative for the next scene, as plain prose in {response_language}. Do not output JSON, markdown, headings, choices, labels, or commentary.
Keep the narrative under 800 characters. Never decide the player's feelings, consent, past wishes, bodily sensations, or voluntary actions unless the player's input explicitly states them. If the player's action objectively makes the mission impossible to continue, narrate a concise failure ending instead of refusing or truncating. Describe observable events and NPC actions. Do not introduce an unrequested body transformation. Never grant the player another person's memories, personal knowledge, relationships, habits, skills, credentials, passwords, or authentication information unless the supplied source facts explicitly state them. A copied appearance or name does not imply copied memory or competence. Treat state.appearance_lock and required_visual_appearance as an immutable identity signature, and never change the player's sex, hair color, hair length, hairstyle, eye color, or body features unless scenario_guidance or authored_template_resolution explicitly allows and triggers that change. Clothing may be offered, found, or discussed, but the player only puts on, removes, or changes clothing when their input explicitly chooses that action. Unless the input explicitly requests layering, a new garment replaces the previous outfit instead of being worn over it. If the source snapshot explicitly establishes a transformed sex or body, it may create practical disguise or role opportunities without inventing further changes. When authored_template_resolution is provided, treat it as authoritative and never narrate a score, transformation, unlocked exit, or ending beyond its event.
{_REALITY_RULES_INSTRUCTION}
{voice_rule}"""

    def _resolution_system_prompt(
        self,
        language: str,
        *,
        narration_voice: str = NARRATION_VOICE_DEFAULT,
        narration_pronoun: str = NARRATION_PRONOUN_DEFAULT,
        romance: bool = False,
    ) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        # 選択肢ラベルは行動フレーズなので、人称を載せない旨を併記する
        voice_rule = (
            _narration_voice_instruction(narration_voice, narration_pronoun)
            + " choices[].label must remain a short neutral action phrase with no "
            "narration voice, no pronoun, and no first-person or second-person subject."
        )
        if romance:
            voice_rule = f"{ROMANCE_RESOLUTION_GUIDANCE}\n{voice_rule}"
        return f"""You resolve the mechanical outcome of one adventure turn that has already been narrated.
Return one JSON object only, in {response_language}, matching this schema:
{{"choices":[{{"id":"...","label":"..."}},{{"id":"...","label":"..."}},{{"id":"...","label":"..."}}],"discovered_clues":[],"completed_milestones":[],"ending_status":"continue|success|partial|failure","ending_title":null,"ending_summary":null}}
Base every value strictly on the supplied narrative and game state, and never invent events the narrative does not contain. choices must offer exactly three distinct actions the player could take next. discovered_clues must contain only new information the narrative actually revealed, and must not repeat state.clues. completed_milestones must contain milestone ID strings only, never objects, and only when the narrated action actually earns them. Keep ending_status as continue unless the narrative itself concludes the mission, and fill ending_title and ending_summary only in that case. Never decide the player's feelings, consent, or voluntary actions. When authored_template_resolution is provided, treat it as authoritative and never report a score, transformation, or ending beyond its event. Keep the entire response compact.
{_REALITY_RULES_INSTRUCTION}
{voice_rule}"""

    def _visual_system_prompt(
        self,
        language: str,
        *,
        respect_clothing_layers: bool = False,
        romance: bool = False,
    ) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        layer_rule = _CLOTHING_LAYER_TAG_RULE if respect_clothing_layers else ""
        romance_rule = f"\n{ROMANCE_VISUAL_GUIDANCE}" if romance else ""
        return f"""You update the visual state of an adventure scene and convert it into NovelAI image tags.
Return one JSON object only, matching this schema:
{{"visual_state":{{"location":"...","appearance":"...","clothing":"...","surroundings":"...","main_characters":[{{"name":"...","description":"...","clothing":"...","action":"..."}}]}},"scene_tags":"...","player_tags":"...","npc_tags":["..."]}}
Write visual_state values in {response_language}. Write scene_tags, player_tags, and npc_tags as concise English comma-separated tags.
Derive visual_state from previous_visual_state, changing only what the narrative states. Treat required_visual_appearance as an immutable identity signature: copy its sex, hair color, hair length, hairstyle, eye color, and body features exactly into visual_state.appearance, and never replace or supplement those traits unless authored_template_resolution explicitly triggers that change. The player only puts on, removes, or changes clothing when player_input explicitly chose that action; otherwise keep previous_visual_state.clothing unchanged. Unless layering was explicitly requested, a new garment replaces the previous outfit. Keep visual_state concrete enough to illustrate the main characters, their clothing, and the surrounding location. main_characters contains NPCs, never the player.
When previous_image_tags is provided, treat it as the wording a human editor deliberately chose: reuse its scene_tags, player_tags, and npc_tags as the starting point and edit them only where visual_state or the narrative now requires a change, preserving the rest of the original wording and phrasing style. When previous_image_tags is absent, write the tags from scratch.
scene_tags contains only environment, camera, composition, lighting, and the observable interaction; it must not contain any character's gender, body, face, hair, or clothing. player_tags describes only the player from visual_state.appearance and visual_state.clothing. The player is always the primary subject in the center foreground. visual_state.clothing is authoritative and must never be replaced with an NPC outfit. npc_tags must contain one entry per NPC in main_characters, in the same order, describing only that NPC; every NPC is a secondary subject placed to the side or behind the player. Never merge player and NPC attributes. Do not add text, UI, split panels, or unstated changes. When authored_scene_tags is provided, reuse those environment tags as the base of scene_tags and only append concrete changes required by the narrative. When authored_visual_style is provided, keep visual_state.location and visual_state.surroundings aligned with it unless the narrative explicitly moves the scene to a new place after a successful exit.{layer_rule}{romance_rule}"""

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
                "the required schema. Return JSON only and do not add new facts. "
                "Respect every string length limit in the schema; when a value is "
                "too long, shorten it by dropping trailing details.\n\n" + raw.content,
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
        narration_voice: str = NARRATION_VOICE_DEFAULT,
        narration_pronoun: str = NARRATION_PRONOUN_DEFAULT,
        romance: bool = False,
    ) -> AdventureResolutionOutput:
        return await self._generate_structured_output(
            AdventureRomanceResolutionOutput if romance else AdventureResolutionOutput,
            system_prompt=self._resolution_system_prompt(
                language,
                narration_voice=narration_voice,
                narration_pronoun=narration_pronoun,
                romance=romance,
            ),
            user_prompt=json.dumps(
                {**turn_context, "narrative": narrative}, ensure_ascii=False
            ),
            text_model=text_model,
            error_code="invalid_model_output",
            error_message="物語生成結果を解析できませんでした。もう一度お試しください",
            context={
                "fallback_choices": _default_director_choices(language),
                "language": language,
            },
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
        respect_clothing_layers: bool = False,
        romance: bool = False,
    ) -> AdventureVisualOutput:
        authored_scene_tags = str(turn_context.get("authored_scene_tags") or "").strip()
        authored_visual_style = turn_context.get("authored_visual_style")
        visual_output = await self._generate_structured_output(
            AdventureVisualOutput,
            system_prompt=self._visual_system_prompt(
                language,
                respect_clothing_layers=respect_clothing_layers,
                romance=romance,
            ),
            user_prompt=json.dumps(
                {
                    "narrative": narrative,
                    "player_input": turn_context.get("player_input", ""),
                    "authored_template_resolution": turn_context.get(
                        "authored_template_resolution", {}
                    ),
                    "authored_visual_style": authored_visual_style,
                    "authored_scene_tags": authored_scene_tags or None,
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
        if authored_scene_tags:
            visual_output.scene_tags = _merge_scene_tags(
                authored_scene_tags, visual_output.scene_tags
            )
        return visual_output

    def _setup_system_prompt(
        self,
        language: str,
        max_turns: int = ADVENTURE_TURNS_DEFAULT,
        preset: str = "",
    ) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        if preset == "romance":
            days = clamp_romance_max_turns(max_turns) // ROMANCE_SLOTS_PER_DAY
            return f"""You design a concise setup for a {days}-day romance simulation in which the player aims to start dating one partner character.
Return one JSON object only, in {response_language}, matching this schema:
{{"setting":"...","objective":"...","constraints":["...","..."]}}
The partner is the character shown in source_snapshot; keep their appearance and situation consistent with it. source_snapshot deliberately contains no name for the partner: invent a fitting new name from their appearance and situation, and use that name in the objective. Never name the partner after the player. The player is a separate person courting that partner; never treat the snapshot character as the player. The setting describes where the player and the partner cross paths in daily life. The objective must name the partner and state that the player starts dating them within {days} days. Constraints must create romantic complications such as rivals, schedules, shyness, or circumstances, without dictating the player's feelings, consent, memories, bodily sensations, or voluntary actions. Do not introduce another body transformation or assign physical traits that conflict with source_snapshot.appearance."""
        turns = clamp_generated_max_turns(max_turns)
        return f"""You design a concise setup for a {turns}-turn objective-based adventure game.
Return one JSON object only, in {response_language}, matching this schema:
{{"setting":"...","objective":"...","constraints":["...","..."]}}
The objective must name a concrete target and an observable end condition that can be judged as achieved or failed within {turns} turns. Scale the scope of the objective to that turn budget: a longer budget should leave room for searching for clues and scouting the surroundings, not add unrelated sub-goals. Do not use vague goals such as succeed, investigate the situation, or reach the objective. The setting, objective, and constraints must fit the selected mission preset and supplied character snapshot. Constraints must create actionable complications without dictating the player's feelings, consent, memories, bodily sensations, or voluntary actions. Do not introduce another body transformation or assign physical traits that conflict with source_snapshot.appearance. For a disguise mission, generate the transformed person's name and role while keeping the supplied appearance exactly; the player does not have that person's memories, relationships, habits, skills, credentials, passwords, or authentication information."""

    async def _generate_setup_output(
        self,
        *,
        prompt: str,
        language: str,
        text_model: str,
        max_turns: int = ADVENTURE_TURNS_DEFAULT,
        preset: str = "",
    ) -> AdventureSetupOutput:
        system_prompt = self._setup_system_prompt(language, max_turns, preset)
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
        max_turns: int = ADVENTURE_TURNS_DEFAULT,
    ) -> dict[str, Any]:
        preset_config = PRESETS.get(preset)
        if preset_config is None:
            raise AdventureError("invalid_preset", "シナリオ種別が不正です")
        turn_budget = (
            clamp_romance_max_turns(max_turns)
            if preset == "romance"
            else clamp_generated_max_turns(max_turns)
        )

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
                "max_turns": turn_budget,
                "mission_definition": {
                    "title": preset_config["title"],
                    "default_objective": preset_config["objective"],
                    "milestones": preset_config["milestones"],
                    "guidance": preset_config["guidance"],
                },
                "source_snapshot": _romance_prompt_snapshot(snapshot)
                if preset == "romance"
                else snapshot,
                "required_visual_appearance": appearance
                or "Preserve the source image appearance",
            },
            ensure_ascii=False,
        )
        generated = await self._generate_setup_output(
            prompt=prompt,
            language=language,
            text_model=text_model,
            max_turns=turn_budget,
            preset=preset,
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
        scenario_max_turns: int = ADVENTURE_TURNS_DEFAULT,
        narration_voice: str = NARRATION_VOICE_DEFAULT,
        narration_pronoun: str = NARRATION_PRONOUN_DEFAULT,
        use_precise_reference: bool = False,
        enable_composite_scene: bool = False,
        respect_clothing_layers: bool = False,
        romance_player_character_id: str | None = None,
        romance_player_session_id: str | None = None,
        romance_player_history_id: str | None = None,
    ) -> dict[str, Any]:
        narration_voice = normalize_narration_voice(narration_voice)
        narration_pronoun = normalize_narration_pronoun(narration_pronoun)
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
            # リプレイ分岐は state を引き継がず sim を再構築できないため対象外
            if preset == "romance":
                raise AdventureError(
                    "romance_replay_unsupported",
                    "恋愛シミュレーションはもう一度遊ぶに対応していません",
                )
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

        (
            snapshot,
            source_image,
            appearance,
            session_nsfw_mode,
        ) = await self._build_snapshot(source_session_id, source_history_id)
        user_settings = await session_store.get_user_settings()
        language = str(user_settings.get("language") or "ja")
        text_model = str(
            user_settings.get("novelai_text_model") or settings.novelai_text_model
        )
        # ユーザー設定の NSFW を優先し、未設定時のみセッション統計を使う
        if "nsfw_mode" in user_settings:
            nsfw_mode = bool(user_settings.get("nsfw_mode"))
        else:
            nsfw_mode = bool(session_nsfw_mode)
        image_model = (
            settings.novelai_model if nsfw_mode else settings.novelai_curated_model
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
            max_turns = (
                clamp_romance_max_turns(scenario_max_turns)
                if effective_preset == "romance"
                else clamp_generated_max_turns(scenario_max_turns)
            )
            scenario_guidance = str(preset_config["guidance"])
            opening_premise = ""

        # 恋愛シミュレーションの相手・バイト・カタログ・隠し好みはサーバ側で
        # 1回だけ生成する。/setup/generate のレスポンスには載せない
        romance_setup: RomanceSetupOutput | None = None
        romance_partner_appearance = ""
        romance_partner_image: Path | None = None
        romance_player_name = ""
        romance_player_ref = ""
        if effective_preset == "romance":
            # 主人公(自分)を解決する。セッション指定があればその時点の変身状態、
            # なければテンプレートキャラクター(既定 char1)を使う
            if romance_player_session_id:
                (
                    player_snapshot,
                    player_image,
                    player_appearance,
                    _,
                ) = await self._build_snapshot(
                    romance_player_session_id, romance_player_history_id
                )
                romance_player_name = str(player_snapshot.get("character_name") or "")
                romance_player_ref = f"session:{romance_player_session_id}"
            else:
                player_id = (
                    str(romance_player_character_id or "").strip()
                    or ROMANCE_PLAYER_DEFAULT_CHARACTER_ID
                )
                template_player = character_manager.get_by_id(player_id)
                if template_player is None:
                    raise AdventureError(
                        "invalid_player_character",
                        "主人公キャラクターが見つかりません",
                    )
                player_image = BASE_DIR / template_player.image_path
                player_appearance = _romance_template_player_appearance(template_player)
                romance_player_name = template_player.name
                romance_player_ref = template_player.id
            romance_days = max_turns // ROMANCE_SLOTS_PER_DAY
            romance_setup = await self._generate_structured_output(
                RomanceSetupOutput,
                system_prompt=romance_setup_system_prompt(language, romance_days),
                user_prompt=json.dumps(
                    {
                        "task": "Design the romance simulation setup.",
                        "days": romance_days,
                        "setting": setting,
                        "objective": objective,
                        "constraints": constraints,
                        "source_snapshot": _romance_prompt_snapshot(snapshot),
                        "player_name": romance_player_name,
                    },
                    ensure_ascii=False,
                ),
                text_model=text_model,
                error_code="invalid_model_output",
                error_message=(
                    "恋愛シナリオの生成結果を解析できませんでした。"
                    "もう一度お試しください"
                ),
            )
            # 開始セッションの人物は攻略対象。主人公の開始画像と外見ロックは
            # 選択した主人公(テンプレキャラまたはセッション時点)へ差し替え、
            # 相手の元画像は立ち絵生成の参照用に控える
            romance_partner_appearance = appearance
            romance_partner_image = source_image
            appearance = player_appearance
            source_image = player_image

        start_state = template.get("start_state", {}) if template else {}
        visual_style = _template_visual_style(template)
        authored_scene_tags = _authored_scene_tags(template=template)
        prompt = json.dumps(
            {
                "task": "Create the opening scene for this adventure.",
                "preset": effective_preset,
                "setting": setting,
                "objective": objective,
                # 導入部の尺をターン予算に合わせるため、開始時点でも予算を渡す
                "max_turns": max_turns,
                "constraints": constraints,
                "milestones": milestones,
                "scenario_guidance": scenario_guidance,
                "authored_opening_premise": opening_premise,
                "authored_visual_style": visual_style,
                "scenario_capabilities": start_state,
                "source_snapshot": _romance_prompt_snapshot(snapshot)
                if romance_setup is not None
                else snapshot,
                "required_visual_appearance": appearance
                or "Preserve the source image appearance",
                # 開幕描写に相手と関係性を織り込む(隠し好みは渡さない)
                "romance_setup": {
                    "partner_name": romance_setup.partner_name,
                    "partner_profile": romance_setup.partner_profile,
                    "partner_appearance": romance_partner_appearance,
                    "relationship_origin": romance_setup.relationship_origin,
                    "job_name": romance_setup.job_name,
                    "player_name": romance_player_name,
                }
                if romance_setup is not None
                else None,
            },
            ensure_ascii=False,
        )
        opening = await self._generate_director_output(
            prompt=prompt,
            language=language,
            text_model=text_model,
            narration_voice=narration_voice,
            narration_pronoun=narration_pronoun,
            romance=romance_setup is not None,
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
            # romance のスナップショット服装は攻略対象のものなので主人公へは適用しない
            if starting_clothing and romance_setup is None:
                opening.visual_state.clothing = starting_clothing
        if visual_style:
            _apply_visual_style_to_state(opening.visual_state, visual_style, language)

        run_id = str(uuid.uuid4())
        run_dir = self._images_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        source_suffix = source_image.suffix.lower()
        if source_suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            source_suffix = ".png"
        initial_path = run_dir / f"initial{source_suffix}"
        shutil.copyfile(source_image, initial_path)
        # romance では攻略対象の元画像も保存し、相手立ち絵の精密参照に使う
        partner_reference_path: Path | None = None
        if romance_partner_image is not None and romance_partner_image.is_file():
            partner_suffix = romance_partner_image.suffix.lower()
            if partner_suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                partner_suffix = ".png"
            partner_reference_path = run_dir / f"partner_initial{partner_suffix}"
            shutil.copyfile(romance_partner_image, partner_reference_path)
        opening_choices = [choice.model_dump() for choice in opening.choices]
        state = {
            "milestones": milestones,
            "completed_milestones": [],
            "clues": [],
            "setting": setting,
            "constraints": constraints,
            # プレイ中に「現実改変：〜」で宣言された世界ルール
            "reality_rules": [],
            "appearance_lock": appearance,
            "scenario_template_id": scenario_template_id,
            "replayed_from_run_id": replay_run_id,
            "scenario_capabilities": start_state,
            "visual_state": opening.visual_state.model_dump(),
            "opening_narrative": opening.narrative,
            "opening_image_path": str(initial_path),
            "choices": opening_choices,
            # 精密参照はユーザー明示ONのみ。未設定・旧runはOFF扱い。
            "use_precise_reference": bool(use_precise_reference),
            # 合成シーン生成はユーザー明示ONのみ。OFF時は中央の立ち絵のみ更新
            "enable_composite_scene": bool(enable_composite_scene),
            # 衣装レイヤー考慮。ONなら外衣に覆われた下着を画像タグから外す
            "respect_clothing_layers": bool(respect_clothing_layers),
            # 語りの人称。旧runは既定の二人称として扱う
            "narration_voice": narration_voice,
            "narration_pronoun": narration_pronoun,
        }
        if romance_setup is not None:
            state["sim"] = init_romance_state(
                romance_setup,
                max_turns,
                partner_appearance=romance_partner_appearance,
                player_name=romance_player_name,
                player_character_id=romance_player_ref,
            )
            if partner_reference_path is not None:
                state["partner_image_path"] = str(partner_reference_path)
        if authored_scene_tags:
            state["authored_scene_tags"] = authored_scene_tags
        if template:
            state["template_state"] = {
                "worn_items": [],
                "flags": {},
                "score": 0,
                "transformed": False,
            }
            equipment_choices = self._apply_equipment_score_choices(
                template, state, language, prefer_authored=False
            )
            if equipment_choices:
                state["choices"] = equipment_choices
                opening.choices = [
                    AdventureChoice.model_validate(item) for item in equipment_choices
                ]
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
            image_model=image_model,
        )
        async with async_session_factory() as db:
            db.add(run)
            await db.commit()
            await db.refresh(run)
        try:
            await self._generate_opening_visuals(run_id)
        except Exception:
            logger.exception(
                "Adventure opening visual generation failed: run_id=%s", run_id
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

    async def regenerate_choices(self, run_id: str) -> dict[str, Any]:
        """現在場面の選択肢だけを再生成する。手番・物語・手掛かりは変更しない。"""
        async with self._run_locks[run_id]:
            run = await self.get_run_orm(run_id, with_turns=True)
            if run.status != "active":
                raise AdventureError("run_completed", "このシナリオは終了しています")

            state = _json_load(run.state_json, {})
            narration_voice, narration_pronoun = _narration_from_state(state)
            turns = sorted(run.turns, key=lambda item: item.turn_number)
            latest_turn = turns[-1] if turns else None
            narrative = (
                latest_turn.narrative
                if latest_turn is not None
                else str(state.get("opening_narrative") or "")
            ).strip()
            if not narrative:
                raise AdventureError(
                    "invalid_model_output",
                    "選択肢を再生成する物語がありません",
                )

            template = SCENARIO_TEMPLATES.get(str(state.get("scenario_template_id")))
            last_input = latest_turn.user_input if latest_turn is not None else ""
            # 装備状態を二重適用しないよう解決用に state のコピーを使う
            resolve_state = json.loads(json.dumps(state, ensure_ascii=False))
            template_resolution = self._resolve_template_action(
                template, resolve_state, last_input
            )
            equipment_choices = self._apply_equipment_score_choices(
                template,
                state,
                run.language,
                resolution=template_resolution,
                prefer_authored=True,
            )
            if equipment_choices:
                choices = equipment_choices
            else:
                scenario_guidance = PRESETS.get(run.preset, {}).get("guidance", "")
                if template:
                    scenario_guidance = f"{scenario_guidance} {template['guidance']}"
                previous_turns = [
                    {"user_input": item.user_input, "narrative": item.narrative}
                    for item in turns
                ]
                appearance_lock = str(
                    state.get("appearance_lock")
                    or state.get("visual_state", {}).get("appearance")
                    or "Preserve the source image appearance"
                )
                turn_context = {
                    "task": "Regenerate next player choices only.",
                    "preset": run.preset,
                    "scenario_guidance": scenario_guidance,
                    "authored_template_resolution": template_resolution,
                    "objective": run.objective,
                    "max_turns": run.max_turns,
                    "next_turn": run.turn_count + 1,
                    "state": state,
                    "recent_turns": previous_turns[-7:],
                    "player_input": last_input,
                    "reality_rules": list(state.get("reality_rules", [])),
                    "required_visual_appearance": appearance_lock,
                }
                try:
                    resolution = await self._generate_resolution_output(
                        narrative=narrative,
                        turn_context=turn_context,
                        language=run.language,
                        text_model=run.text_model,
                        narration_voice=narration_voice,
                        narration_pronoun=narration_pronoun,
                    )
                    choices = _sanitize_choices(
                        [choice.model_dump() for choice in resolution.choices],
                        language=run.language,
                        source="regenerate_choices.resolution",
                    )
                except Exception as error:
                    logger.warning(
                        "Adventure choice regeneration failed: run_id=%s error=%s "
                        "fallback=default_director_choices",
                        run_id,
                        error,
                    )
                    choices = _default_director_choices(run.language)

            state["choices"] = choices
            async with async_session_factory() as db:
                persisted = await db.get(AdventureRun, run.id)
                if persisted is None:
                    raise AdventureError(
                        "run_not_found", "アドベンチャーが見つかりません"
                    )
                persisted.state_json = json.dumps(state, ensure_ascii=False)
                persisted.updated_at = datetime.now()
                if latest_turn is not None:
                    persisted_turn = await db.get(AdventureTurn, latest_turn.id)
                    if persisted_turn is not None:
                        persisted_turn.choices_json = json.dumps(
                            choices, ensure_ascii=False
                        )
                await db.commit()

            return {"choices": choices}

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
            ending_title = _default_ending_title(run.preset, status)
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
        self,
        clothing: str | None,
        narrative: str,
        language: str,
        *,
        narration_voice: str = NARRATION_VOICE_DEFAULT,
        narration_pronoun: str = NARRATION_PRONOUN_DEFAULT,
    ) -> str:
        if not clothing:
            return ""
        voice = normalize_narration_voice(narration_voice)
        if language == "ja":
            if re.search(r"(?:着た|着ている|着用した|着替えた)", narrative):
                return ""
            if voice == "first_person":
                subject = f"{normalize_narration_pronoun(narration_pronoun)}は"
            elif voice == "third_person":
                # 変身で性別が変わりうるため主語は補わず省略する
                subject = ""
            else:
                subject = "君は"
            return f"{subject}{clothing}を着用した。"
        if re.search(
            r"\b(?:put on|wearing|wore|changed into)\b",
            narrative,
            flags=re.IGNORECASE,
        ):
            return ""
        if voice == "first_person":
            return f"I put on {clothing}."
        if voice == "third_person":
            return f"They put on {clothing}."
        return f"You put on {clothing}."

    def _enforce_explicit_clothing_action(
        self,
        output: AdventureDirectorOutput,
        user_input: str,
        language: str,
        *,
        apply_narrative_suffix: bool = True,
        narration_voice: str = NARRATION_VOICE_DEFAULT,
        narration_pronoun: str = NARRATION_PRONOUN_DEFAULT,
    ) -> bool:
        clothing = self._explicit_clothing_from_input(user_input, language)
        if not clothing:
            return False

        output.visual_state.clothing = clothing
        if apply_narrative_suffix:
            suffix = self._clothing_narrative_suffix(
                clothing,
                output.narrative,
                language,
                narration_voice=narration_voice,
                narration_pronoun=narration_pronoun,
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
        alias_by_item: dict[str, tuple[str, ...]] = {}
        for item in rule.get("items", []):
            item_id = str(item.get("id") or "")
            aliases = tuple(str(alias) for alias in item.get("aliases", []))
            if item_id and aliases:
                alias_by_item[item_id] = aliases
        for item in rule.get("items", []):
            item_id = str(item.get("id") or "")
            aliases = alias_by_item.get(item_id)
            if not item_id or not aliases:
                continue
            # 他アイテムの語で走査を打ち切り、隣の衣類の動詞を拾わないようにする。
            # 共有エイリアス（例: 「下着」）は境界にせず、両方の判定に残す。
            own = set(aliases)
            other_aliases = tuple(
                alias
                for other_id, other in alias_by_item.items()
                if other_id != item_id
                for alias in other
                if alias not in own
            )
            action = _last_equipment_action(
                user_input, aliases, other_aliases=other_aliases
            )
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

        # 毎ターン強制上書きすると visual_state が不変になり画像生成が常にスキップされる。
        # 地下室・ロッカー室などへ逸脱したときだけ authored visual_style で矯正する。
        if resolution.get("event") != "perfect_score":
            _apply_visual_style_to_state(
                visual_state,
                _template_visual_style(template),
                language,
                force=False,
            )

    def _missing_equipment_labels(
        self,
        template: dict[str, Any] | None,
        worn_items: set[str] | list[str],
        language: str,
    ) -> list[str]:
        rule = template.get("rule", {}) if template else {}
        required = {str(item) for item in rule.get("required_items", [])}
        worn = {str(item) for item in worn_items}
        missing = required - worn
        labels: list[str] = []
        for item in rule.get("items", []):
            item_id = str(item.get("id") or "")
            if item_id not in missing:
                continue
            item_labels = item.get("labels", {})
            labels.append(
                str(item_labels.get(language) or item_labels.get("en") or item_id)
            )
        return labels

    def _authored_event_choices(
        self,
        template: dict[str, Any] | None,
        resolution: dict[str, Any],
        language: str,
    ) -> list[dict[str, str]]:
        """テンプレート event に定義された作者 choices を正規化して返す。"""
        event_config = self._template_event_config(template, resolution)
        if not event_config:
            return []
        choices = event_config.get("choices", {}) or {}
        localized = choices.get(language) or choices.get("en") or []
        if not isinstance(localized, list):
            return []
        return _sanitize_choices(
            localized,
            language=language,
            fallback=[],
            source="authored_event_choices",
        )

    def _apply_equipment_score_choices(
        self,
        template: dict[str, Any] | None,
        state: dict[str, Any],
        language: str,
        *,
        resolution: dict[str, Any] | None = None,
        prefer_authored: bool = True,
    ) -> list[dict[str, str]] | None:
        """equipment_score の次手3択を返す。作者 choices 優先。非対象は None。"""
        if prefer_authored and resolution is not None:
            authored = self._authored_event_choices(template, resolution, language)
            if len(authored) == 3:
                return authored
            event_config = self._template_event_config(template, resolution)
            if event_config and event_config.get("ending_status"):
                # 成功/失敗エンディング時は着用導線を押し付けない
                return None
        return _equipment_score_choices(template, state, language)

    def _override_output_equipment_choices(
        self,
        template: dict[str, Any] | None,
        state: dict[str, Any],
        output: AdventureDirectorOutput,
        resolution: dict[str, Any],
        language: str,
    ) -> None:
        """LLM choices を equipment_score 決定論3択で上書きする（作者 choices は維持）。"""
        choices = self._apply_equipment_score_choices(
            template,
            state,
            language,
            resolution=resolution,
            prefer_authored=True,
        )
        if not choices:
            return
        # 作者 choices は _enforce_template_output 側で既に入っている場合がある
        authored = self._authored_event_choices(template, resolution, language)
        if len(authored) == 3:
            return
        output.choices = [AdventureChoice.model_validate(item) for item in choices]

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
        if not event_config and not resolution.get("goal_checked"):
            self._override_output_equipment_choices(
                template, state, output, resolution, language
            )
            return
        clues = event_config.get("clues", {}) if event_config else {}
        localized_clues = list(clues.get(language) or clues.get("en") or [])
        missing_labels = self._missing_equipment_labels(
            template, resolution.get("worn_items", []), language
        )
        if resolution.get("goal_checked") and missing_labels:
            if language == "ja":
                localized_clues.append(
                    "まだ不足している品: " + "、".join(missing_labels)
                )
            else:
                localized_clues.append("Still missing: " + ", ".join(missing_labels))
        if localized_clues:
            output.discovered_clues = list(
                dict.fromkeys([*output.discovered_clues, *localized_clues])
            )[:10]
        if apply_narrative_suffix:
            suffix = self._template_narrative_suffix(template, resolution, language)
            if suffix:
                output.narrative = f"{output.narrative.rstrip()}\n\n{suffix}"
        if (
            resolution.get("goal_checked")
            and missing_labels
            and resolution.get("event") in {"incomplete", "almost_complete"}
        ):
            if language == "ja":
                missing_line = "不足しているのは " + "、".join(missing_labels) + "。"
            else:
                missing_line = "Still missing: " + ", ".join(missing_labels) + "."
            if missing_line not in output.narrative:
                output.narrative = f"{output.narrative.rstrip()}\n\n{missing_line}"
        choices = event_config.get("choices", {}) if event_config else {}
        localized_choices = choices.get(language) or choices.get("en") or []
        if localized_choices:
            output.choices = [
                AdventureChoice.model_validate(item) for item in localized_choices
            ]
        else:
            self._override_output_equipment_choices(
                template, state, output, resolution, language
            )
        ending_status = event_config.get("ending_status") if event_config else None
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
                    return (
                        self._serialize_turn(existing, language=run.language),
                        False,
                        False,
                    )
            if run.status != "active":
                raise AdventureError("run_completed", "このシナリオは終了しています")

            state = _json_load(run.state_json, {})
            narration_voice, narration_pronoun = _narration_from_state(state)
            # 宣言はこの手番から有効にする
            declared_rule = _detect_reality_declaration(user_input)
            if declared_rule:
                _append_reality_rule(state, declared_rule)
                input_kind = "reality_alter"
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
                    "reality_rules": list(state.get("reality_rules", [])),
                    "reality_rule_declared_this_turn": declared_rule,
                },
                ensure_ascii=False,
            )
            output = await self._generate_director_output(
                prompt=prompt,
                language=run.language,
                text_model=run.text_model,
                narration_voice=narration_voice,
                narration_pronoun=narration_pronoun,
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
                self._enforce_explicit_clothing_action(
                    output,
                    user_input,
                    run.language,
                    narration_voice=narration_voice,
                    narration_pronoun=narration_pronoun,
                )
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
                    and _default_ending_title(run.preset, next_status)
                )
                persisted.ending_summary = next_state.get("ending_summary")
                persisted.updated_at = datetime.now()
                db.add(turn)
                await db.commit()
                await db.refresh(turn)

            result = self._serialize_turn(turn, language=run.language)
            result["run_status"] = (
                "active" if next_status == "continue" else next_status
            )
            result["remaining_turns"] = max(0, run.max_turns - turn_number)
            result["clues"] = next_state.get("clues", [])
            result["completed_milestones"] = next_state.get("completed_milestones", [])
            result["visual_state"] = _sanitize_visual_state(
                next_state.get("visual_state")
            )
            result["ending_title"] = output.ending_title or _default_ending_title(
                run.preset, next_status
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
        gift_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """ナラティブを逐次配信し、手がかり抽出と画像生成を並列実行する。"""
        async with self._run_locks[run_id]:
            run = await self.get_run_orm(run_id, with_turns=True)
            for existing in run.turns:
                if existing.client_turn_id == client_turn_id:
                    yield {
                        "event": "turn",
                        "data": self._serialize_turn(existing, language=run.language),
                    }
                    yield {"event": "complete", "data": {"status": run.status}}
                    return
            if run.status != "active":
                raise AdventureError("run_completed", "このシナリオは終了しています")

            state = _json_load(run.state_json, {})
            narration_voice, narration_pronoun = _narration_from_state(state)
            # 宣言はこの手番から有効にする
            declared_rule = _detect_reality_declaration(user_input)
            if declared_rule:
                _append_reality_rule(state, declared_rule)
                input_kind = "reality_alter"
            reality_rules = list(state.get("reality_rules", []))
            template = SCENARIO_TEMPLATES.get(str(state.get("scenario_template_id")))
            template_resolution = self._resolve_template_action(
                template, state, user_input
            )
            scenario_guidance = PRESETS.get(run.preset, {}).get("guidance", "")
            if template:
                scenario_guidance = f"{scenario_guidance} {template['guidance']}"
            # romance はターンの機械的結果(金銭・採点・告白成否)を先に確定する。
            # 資金不足などはターン未消費のままエラーで弾く
            romance_sim = (
                state.get("sim")
                if run.preset == "romance" and isinstance(state.get("sim"), dict)
                else None
            )
            romance_resolution: dict[str, Any] | None = None
            if romance_sim is not None:
                try:
                    romance_resolution = resolve_romance_action(
                        romance_sim,
                        user_input=user_input,
                        input_kind=input_kind,
                        gift_id=gift_id,
                        turn_number=run.turn_count + 1,
                        total_turns=run.max_turns,
                    )
                except RomanceActionError as error:
                    raise AdventureError(error.code, str(error)) from error
            previous_turns = [
                {"user_input": item.user_input, "narrative": item.narrative}
                for item in sorted(run.turns, key=lambda item: item.turn_number)
            ]
            appearance_lock = str(
                state.get("appearance_lock")
                or state.get("visual_state", {}).get("appearance")
                or "Preserve the source image appearance"
            )
            lean_state = _lean_state_for_llm(state)
            turn_context = {
                "task": "Resolve the player's next action.",
                "preset": run.preset,
                "scenario_guidance": scenario_guidance,
                "authored_template_resolution": template_resolution,
                "objective": run.objective,
                "max_turns": run.max_turns,
                "next_turn": run.turn_count + 1,
                "state": lean_state,
                "recent_turns": previous_turns[-7:],
                "player_input": user_input,
                "reality_rules": reality_rules,
                "reality_rule_declared_this_turn": declared_rule,
                "required_visual_appearance": appearance_lock,
            }
            if romance_resolution is not None:
                turn_context["romance_resolution"] = romance_resolution
            visual_turn_context = {
                **turn_context,
                "authored_visual_style": _template_visual_style(template),
                "authored_scene_tags": _authored_scene_tags(
                    template=template, state=state
                ),
            }

            yield {"event": "status", "data": {"phase": "narrative"}}
            narrative = ""
            async for chunk in llm_service.generate_feeling_stream(
                self._narrative_system_prompt(
                    run.language,
                    narration_voice=narration_voice,
                    narration_pronoun=narration_pronoun,
                    romance=romance_sim is not None,
                ),
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
                    explicit_clothing,
                    narrative,
                    run.language,
                    narration_voice=narration_voice,
                    narration_pronoun=narration_pronoun,
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
                        narration_voice=narration_voice,
                        narration_pronoun=narration_pronoun,
                        romance=romance_sim is not None,
                    )
                    await queue.put(("resolution", resolution))
                except Exception as error:
                    logger.warning("Adventure resolution generation failed: %s", error)
                    await queue.put(("resolution_error", error))

            async def visual_producer() -> None:
                try:
                    visual = await self._generate_visual_output(
                        narrative=narrative,
                        turn_context=visual_turn_context,
                        previous_visual=previous_visual,
                        appearance_lock=appearance_lock,
                        language=run.language,
                        text_model=run.text_model,
                        previous_image_tags=state.get("last_image_prompt"),
                        respect_clothing_layers=bool(
                            state.get("respect_clothing_layers")
                        ),
                        romance=romance_sim is not None,
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
                clothing_changed = previous_visual.get(
                    "clothing", ""
                ) != next_visual.get("clothing", "")
                item_actions = bool(template_resolution.get("item_actions"))
                # このターンで確定した装備。DBへの永続化はターン終了後なので、
                # 画像生成には state 経由ではなく解決結果をそのまま渡す。
                resolved_worn_items = (
                    [str(item) for item in template_resolution.get("worn_items", [])]
                    if template
                    else None
                )
                should_generate_image = (
                    clothing_changed
                    or item_actions
                    or _visual_state_changed(previous_visual, next_visual)
                    or _image_tags_changed(state.get("last_image_prompt"), visual)
                )
                if not should_generate_image:
                    await queue.put(("portrait_skipped", None))
                    await queue.put(("image_skipped", None))
                    return
                # step 情報はフロントのプログレスバー用。phase は既存契約を維持する
                enable_composite = bool(state.get("enable_composite_scene"))
                # 非合成 romance は主人公+攻略対象の2枚を直列生成する
                image_step_count = (
                    2 if (enable_composite or romance_sim is not None) else 1
                )
                await queue.put(
                    (
                        "status",
                        {
                            "phase": "image_generation",
                            "step": "portrait",
                            "step_index": 1,
                            "step_count": image_step_count,
                        },
                    )
                )
                # 立ち絵と合成シーンで同一シードを使い、衣装の描画差を抑える
                turn_seed = random.randint(0, 999_999_999)
                portrait_path: Path | None = None
                try:
                    portrait_path, _ = await self._generate_portrait_unlocked(
                        run.id,
                        None,
                        redraw_from_reference=clothing_changed or item_actions,
                        prompt_override=visual,
                        turn_number=run.turn_count + 1,
                        worn_items_override=resolved_worn_items,
                        seed_override=turn_seed,
                    )
                    await queue.put(("portrait", portrait_path))
                except Exception as error:
                    logger.warning(
                        "Adventure turn portrait generation failed: %s", error
                    )
                    await queue.put(("portrait_error", error))

                if not enable_composite:
                    # 非合成モードの romance では、攻略対象の立ち絵を並置表示する。
                    # 主人公と同様に毎ターン生成し、そのターンの表情・服装を反映する
                    if romance_sim is not None:
                        partner_name = str(romance_sim.get("partner_name") or "")
                        partner_entry, partner_tags = _romance_partner_visual_entry(
                            list(visual.visual_state.main_characters),
                            list(visual.npc_tags),
                            partner_name,
                        )
                        if not partner_tags:
                            clothing = (
                                partner_entry["clothing"] if partner_entry else ""
                            )
                            partner_tags = ", ".join(
                                part
                                for part in (
                                    str(romance_sim.get("partner_appearance") or ""),
                                    clothing,
                                )
                                if part
                            )
                        if partner_tags:
                            await queue.put(
                                (
                                    "status",
                                    {
                                        "phase": "image_generation",
                                        "step": "partner",
                                        "step_index": 2,
                                        "step_count": image_step_count,
                                    },
                                )
                            )
                            try:
                                partner_path = await (
                                    self._generate_partner_portrait_unlocked(
                                        run.id,
                                        partner_tags=partner_tags,
                                        turn_number=run.turn_count + 1,
                                        seed_override=turn_seed,
                                    )
                                )
                                await queue.put(("partner_portrait", partner_path))
                            except Exception as error:
                                # 相手立ち絵の失敗はターン進行を止めない
                                logger.warning(
                                    "Adventure partner portrait generation failed: %s",
                                    error,
                                )
                    await queue.put(("image_skipped", None))
                    return
                await queue.put(
                    (
                        "status",
                        {
                            "phase": "image_generation",
                            "step": "composite",
                            "step_index": 2,
                            "step_count": image_step_count,
                        },
                    )
                )
                try:
                    background_path_str = getattr(run, "background_image_path", None)
                    background_bytes = (
                        Path(background_path_str).read_bytes()
                        if background_path_str and Path(background_path_str).is_file()
                        else None
                    )
                    image_path, _ = await self._generate_image_unlocked(
                        run.id,
                        None,
                        redraw_from_reference=clothing_changed or item_actions,
                        prompt_override=visual,
                        turn_number=run.turn_count + 1,
                        source_image_override=background_bytes,
                        character_reference_image_override=portrait_path.read_bytes()
                        if portrait_path is not None
                        else None,
                        worn_items_override=resolved_worn_items,
                        seed_override=turn_seed,
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
            portrait_path: Path | None = None
            partner_sprite_path: Path | None = None
            image_path: Path | None = None
            failures: list[tuple[str, Exception]] = []
            resolution_done = False
            visual_done = False
            portrait_done = False
            image_done = False
            try:
                while not (
                    resolution_done and visual_done and portrait_done and image_done
                ):
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
                        portrait_done = True
                        image_done = True
                    elif kind == "portrait":
                        portrait_path = payload
                        portrait_done = True
                        yield {
                            "event": "portrait_image",
                            "data": {
                                "image_url": self.image_url(run.id, payload),
                            },
                        }
                    elif kind == "portrait_error":
                        failures.append(("image_generation", payload))
                        portrait_done = True
                    elif kind == "portrait_skipped":
                        portrait_done = True
                    elif kind == "partner_portrait":
                        # romance の攻略対象立ち絵(非合成モードのみ)。
                        # 最終の state コミットが古いパスで上書きしないよう保持する
                        partner_sprite_path = payload
                        yield {
                            "event": "partner_image",
                            "data": {
                                "image_url": self.image_url(run.id, payload),
                            },
                        }
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
                logger.warning(
                    "Adventure resolution missing after producers: run_id=%s "
                    "turn=%s failures=%s fallback=default_director_choices",
                    run.id,
                    run.turn_count + 1,
                    [
                        (
                            phase,
                            error.code
                            if isinstance(error, AdventureError)
                            else type(error).__name__,
                            str(error)[:200],
                        )
                        for phase, error in failures
                    ],
                )
                resolution = AdventureResolutionOutput.model_validate(
                    {"choices": _default_director_choices(run.language)},
                    context={
                        "fallback_choices": _default_director_choices(run.language),
                        "language": run.language,
                    },
                )
            visual_state = (
                visual_output.visual_state
                if visual_output is not None
                else self._fallback_visual_state(previous_visual, appearance_lock)
            )
            if visual_output is None:
                logger.warning(
                    "Adventure visual missing after producers: run_id=%s turn=%s "
                    "fallback=previous_visual_state failures=%s",
                    run.id,
                    run.turn_count + 1,
                    [
                        (
                            phase,
                            error.code
                            if isinstance(error, AdventureError)
                            else type(error).__name__,
                            str(error)[:200],
                        )
                        for phase, error in failures
                    ],
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
            if romance_resolution is not None:
                # sim を更新し、milestone と ending_status を Python 算出値で上書き
                apply_romance_outcome(state, output, romance_resolution, resolution)
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
            if visual_output is not None and portrait_path is not None:
                next_state["last_image_prompt"] = _image_prompt_payload(visual_output)
            # このターンで生成した攻略対象立ち絵を state と state_delta に反映する。
            # 生成ヘルパのDB保存はこの後の全stateコミットで上書きされるため必須
            if partner_sprite_path is not None:
                next_state["partner_portrait_path"] = str(partner_sprite_path)

            if image_path is not None:
                turn_image_path = str(image_path)
                image_status = "completed"
            else:
                turn_image_path = run.current_image_path
                image_status = "failed" if failures else "not_requested"

            if portrait_path is not None:
                turn_portrait_path = str(portrait_path)
                portrait_status = "completed"
            else:
                turn_portrait_path = getattr(run, "portrait_image_path", None)
                portrait_status = "failed" if failures else "not_requested"

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
                portrait_image_path=turn_portrait_path,
                portrait_status=portrait_status,
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
                    and _default_ending_title(run.preset, next_status)
                )
                persisted.ending_summary = next_state.get("ending_summary")
                persisted.updated_at = datetime.now()
                db.add(turn)
                await db.commit()
                await db.refresh(turn)

            result = self._serialize_turn(turn, language=run.language)
            result["run_status"] = (
                "active" if next_status == "continue" else next_status
            )
            result["remaining_turns"] = max(0, run.max_turns - turn_number)
            result["clues"] = next_state.get("clues", [])
            result["completed_milestones"] = next_state.get("completed_milestones", [])
            result["visual_state"] = _sanitize_visual_state(
                next_state.get("visual_state")
            )
            result["ending_title"] = output.ending_title or _default_ending_title(
                run.preset, next_status
            )
            result["ending_summary"] = next_state.get("ending_summary")
            # romance の sim / partner_note は _serialize_turn が
            # state_delta_json から復元して載せる

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
        self,
        visual_state: dict[str, Any],
        text_model: str,
        *,
        authored_scene_tags: str = "",
        respect_clothing_layers: bool = False,
    ) -> AdventureImagePromptOutput:
        system_prompt = """Convert a visual_state into NovelAI image tags.
Return one JSON object only: {"scene_tags":"...","player_tags":"...","npc_tags":["..."]}.
All values must be concise English comma-separated tags. scene_tags contains only environment, camera, composition, lighting, and the observable interaction; it must not contain any character's gender, body, face, hair, or clothing. player_tags describes only the player from visual_state.appearance and visual_state.clothing. The player is always the primary subject in the center foreground. visual_state.clothing is authoritative and must never be replaced with an NPC outfit. main_characters contains NPCs, not the player. npc_tags must contain one entry per important NPC in the same order, describing only that NPC; every NPC is a secondary subject placed to the side or behind the player. Never merge player and NPC attributes. Do not add text, UI, split panels, or unstated changes. When authored_scene_tags is provided, reuse those environment tags as the base of scene_tags and only append concrete changes required by visual_state."""
        if respect_clothing_layers:
            system_prompt += _CLOTHING_LAYER_TAG_RULE
        payload = {
            "visual_state": visual_state,
            "authored_scene_tags": authored_scene_tags or None,
        }
        raw = await llm_service.generate_text(
            system_prompt,
            json.dumps(payload, ensure_ascii=False),
            provider_override="novelai",
            novelai_model_override=text_model,
        )
        try:
            image_prompt = AdventureImagePromptOutput.model_validate_json(
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
                image_prompt = AdventureImagePromptOutput.model_validate_json(
                    _strip_json_fence(repaired.content)
                )
            except ValidationError as second_error:
                raise AdventureError(
                    "invalid_image_prompt",
                    "画像プロンプトの生成結果を解釈できませんでした",
                ) from second_error
        if authored_scene_tags:
            image_prompt.scene_tags = _merge_scene_tags(
                authored_scene_tags, image_prompt.scene_tags
            )
        return image_prompt

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
        source_image_override: bytes | None = None,
        character_reference_image_override: bytes | None = None,
        worn_items_override: list[str] | None = None,
        seed_override: int | None = None,
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
        current_path = Path(run.current_image_path)
        initial_path = Path(run.initial_image_path)
        if not current_path.is_file() or not initial_path.is_file():
            raise AdventureError(
                "image_not_found", "アドベンチャー画像が見つかりません"
            )
        try:
            (
                image_prompt,
                outfit_changed,
                nsfw_mode,
                use_precise_reference,
                extra_negative,
                raw_image_prompt,
            ) = await self._prepare_image_prompt(
                run,
                state,
                redraw_from_reference=redraw_from_reference,
                prompt_override=prompt_override,
                worn_items_override=worn_items_override,
            )
            player_prompt = _enhance_adventure_prompt(
                image_prompt.player_tags
                + ", main protagonist, primary focus, center foreground",
                nsfw_mode=nsfw_mode,
            )
            characters = [
                {
                    "prompt": player_prompt,
                    "position": (0.55, 0.5),
                }
            ]
            npc_positions = ((0.18, 0.5), (0.82, 0.5), (0.12, 0.5))
            characters.extend(
                {
                    "prompt": _enhance_adventure_prompt(
                        npc_prompt
                        + ", supporting character, secondary focus, behind protagonist",
                        nsfw_mode=nsfw_mode,
                    ),
                    "position": npc_positions[index],
                }
                for index, npc_prompt in enumerate(image_prompt.npc_tags[:3])
            )
            source_image = (
                source_image_override
                if source_image_override is not None
                else (None if outfit_changed else current_path.read_bytes())
            )
            character_references = None
            if use_precise_reference:
                char_strength, char_fidelity = _character_reference_strength(
                    outfit_changed=outfit_changed,
                    has_fresh_portrait=character_reference_image_override is not None,
                )
                reference_bytes = (
                    character_reference_image_override
                    if character_reference_image_override is not None
                    else initial_path.read_bytes()
                )
                character_references = [
                    {
                        "image": reference_bytes,
                        "type": "character",
                        "strength": char_strength,
                        "fidelity": char_fidelity,
                    }
                ]
            scene_prompt = _enhance_adventure_prompt(
                _compose_scene_base_tags(image_prompt)
                + ", visual novel scene, protagonist in foreground, supporting NPCs secondary",
                nsfw_mode=nsfw_mode,
            )
            effective_image_model = (
                settings.novelai_model if nsfw_mode else settings.novelai_curated_model
            )
            result = await image_service.generate_image(
                scene_prompt,
                image_bytes=source_image,
                provider_override="novelai",
                # 追加negativeを渡すと provider 側の既定UCが置き換わるため、
                # 品質系の基本negativeを土台にして結合する
                negative_prompt=merge_negative_prompt(
                    settings.novelai_negative_prompt, extra_negative or ""
                ),
                nsfw_mode=nsfw_mode,
                character_references=character_references,
                characters=characters,
                seed=seed_override,
                size_override="landscape",
                novelai_model_override=effective_image_model,
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
            # 決定論変換後ではなく LLM 出力を保存する（_prepare_image_prompt 参照）
            persisted_state["last_image_prompt"] = _image_prompt_payload(
                raw_image_prompt
            )
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

    async def _mark_portrait_failed(self, run_id: str, turn_id: str | None) -> None:
        if not turn_id:
            return
        try:
            async with async_session_factory() as db:
                turn = await db.get(AdventureTurn, turn_id)
                if turn and turn.run_id == run_id:
                    turn.portrait_status = "failed"
                    await db.commit()
        except Exception:
            logger.exception(
                "Adventure portrait failure status could not be saved: "
                "run_id=%s turn_id=%s",
                run_id,
                turn_id,
            )

    async def _prepare_image_prompt(
        self,
        run: AdventureRun,
        state: dict[str, Any],
        *,
        redraw_from_reference: bool,
        prompt_override: AdventureImagePromptOutput | None,
        worn_items_override: list[str] | None = None,
    ) -> tuple[
        AdventureImagePromptOutput,
        bool,
        bool,
        bool,
        str | None,
        AdventureImagePromptOutput,
    ]:
        """画像プロンプトと生成条件（服装変化・NSFW・精密参照・追加negative）を算出する。

        ポートレート生成・合成シーン生成の両方から共通で使う準備処理。
        末尾の raw_image_prompt は決定論変換前の LLM 出力。last_image_prompt には
        こちらを保存する。変換後を保存すると、次ターンの previous_image_tags 経由で
        露出状態タグや装備タグが LLM 出力へ再入し、状態変化後も残留するため。
        """
        visual_state = state.get("visual_state", {})
        template = SCENARIO_TEMPLATES.get(str(state.get("scenario_template_id") or ""))
        authored_scene_tags = _authored_scene_tags(template=template, state=state)
        respect_clothing_layers = bool(state.get("respect_clothing_layers"))
        if prompt_override is not None:
            raw_image_prompt = prompt_override
            # 呼び出し側の prompt_override を last_image_prompt として保存する経路が
            # あるため、決定論変換は複製に対して行い、元は書き換えない。
            image_prompt = prompt_override.model_copy(deep=True)
            if authored_scene_tags:
                image_prompt.scene_tags = _merge_scene_tags(
                    authored_scene_tags, image_prompt.scene_tags
                )
        else:
            raw_image_prompt = await self._generate_image_prompt_output(
                visual_state,
                run.text_model,
                authored_scene_tags=authored_scene_tags,
                respect_clothing_layers=respect_clothing_layers,
            )
            image_prompt = raw_image_prompt.model_copy(deep=True)
        # 画像生成は state を DB から読み直すため、ターン中は永続化前の古い
        # worn_items を掴む。呼び出し側が確定値を持つ場合はそちらを優先する。
        if worn_items_override is not None:
            worn_items: list[str] = [str(item) for item in worn_items_override]
        else:
            template_state = state.get("template_state") or {}
            worn_items = list(template_state.get("worn_items") or [])
        # 装備採点シナリオでは worn_items が唯一の服装情報。LLM が書いた服装タグは
        # 補正前の visual_state 由来なので落とし、装備タグで置き直す。
        image_prompt.player_tags = _strip_clothing_tags_for_equipment_scenario(
            template, image_prompt.player_tags
        )
        equipment_tags = _equipment_image_tags(
            template, worn_items, respect_clothing_layers=respect_clothing_layers
        )
        nude_tags = _equipment_clothing_state_tags(template, worn_items)
        if nude_tags:
            image_prompt.player_tags = _merge_player_tags(
                image_prompt.player_tags, nude_tags
            )
        if equipment_tags:
            image_prompt.player_tags = _merge_player_tags(
                image_prompt.player_tags, equipment_tags
            )
        covered = _equipment_layers_covered(worn_items, respect_clothing_layers)
        image_prompt.player_tags, extra_negative = (
            _apply_clothing_layers_to_player_tags(
                image_prompt.player_tags, covered=covered
            )
        )
        extra_negative = merge_negative_prompt(
            extra_negative, _equipment_negative_tags(template, worn_items)
        )
        outfit_changed = redraw_from_reference or bool(equipment_tags)
        if "dress" in {str(item) for item in worn_items}:
            outfit_changed = True
        user_settings = await session_store.get_user_settings()
        if "nsfw_mode" in user_settings:
            nsfw_mode = bool(user_settings.get("nsfw_mode"))
        else:
            nsfw_mode = bool(run.nsfw_mode)
        use_precise_reference = bool(state.get("use_precise_reference"))
        return (
            image_prompt,
            outfit_changed,
            nsfw_mode,
            use_precise_reference,
            extra_negative,
            raw_image_prompt,
        )

    async def _generate_background_image_unlocked(
        self,
        run_id: str,
        *,
        scene_tags: str,
        nsfw_mode: bool,
    ) -> Path:
        """シナリオ開始時に一度だけ背景画像を生成する。以降のターンでは再利用のみ。"""
        run = await self.get_run_orm(run_id)
        # scene_tags は「観察可能な相互作用」を含みうるため、no humans 等の
        # 除外タグを前置してNovelAIに人物非表示を強く指示する
        scenery_prompt = _enhance_adventure_prompt(
            "no humans, empty, uninhabited, scenery, background, " + scene_tags,
            nsfw_mode=nsfw_mode,
        )
        result = await image_service.generate_scenery(
            prompt=scenery_prompt,
            size="landscape",
            nsfw_mode=nsfw_mode,
            include_people=False,
            provider_override="novelai",
        )
        if not result.images:
            raise AdventureError(
                "image_generation_failed", "背景画像が生成されませんでした"
            )
        background_path = self._images_dir / run.id / "background.png"
        background_path.parent.mkdir(parents=True, exist_ok=True)
        background_path.write_bytes(result.images[0])
        async with async_session_factory() as db:
            persisted_run = await db.get(AdventureRun, run.id)
            if persisted_run is None:
                raise AdventureError("run_not_found", "アドベンチャーが見つかりません")
            persisted_run.background_image_path = str(background_path)
            persisted_run.updated_at = datetime.now()
            await db.commit()
        return background_path

    async def _generate_portrait_unlocked(
        self,
        run_id: str,
        turn_id: str | None = None,
        *,
        redraw_from_reference: bool = False,
        prompt_override: AdventureImagePromptOutput | None = None,
        turn_number: int | None = None,
        worn_items_override: list[str] | None = None,
        seed_override: int | None = None,
    ) -> tuple[Path, str | None]:
        """呼び出し側が既に run ロックを保持している前提で中央の立ち絵を生成する。"""
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
        initial_path = Path(run.initial_image_path)
        if not initial_path.is_file():
            raise AdventureError(
                "image_not_found", "アドベンチャー画像が見つかりません"
            )
        try:
            (
                image_prompt,
                outfit_changed,
                nsfw_mode,
                use_precise_reference,
                extra_negative,
                raw_image_prompt,
            ) = await self._prepare_image_prompt(
                run,
                state,
                redraw_from_reference=redraw_from_reference,
                prompt_override=prompt_override,
                worn_items_override=worn_items_override,
            )
            # 立ち絵はフロント側で背景を透過するため、必ず白背景で生成させる。
            player_prompt = _enhance_adventure_prompt(
                image_prompt.player_tags
                + ", solo, full body standing portrait, simple background,"
                " white background, no shadow",
                nsfw_mode=nsfw_mode,
            )
            character_references = None
            if use_precise_reference:
                # 参照は常に旧衣装の初期画像なので fresh portrait 扱いにしない
                char_strength, char_fidelity = _character_reference_strength(
                    outfit_changed=outfit_changed, has_fresh_portrait=False
                )
                character_references = [
                    {
                        "image": initial_path.read_bytes(),
                        "type": "character",
                        "strength": char_strength,
                        "fidelity": char_fidelity,
                    }
                ]
            effective_image_model = (
                settings.novelai_model if nsfw_mode else settings.novelai_curated_model
            )
            result = await image_service.generate_image(
                player_prompt,
                image_bytes=None,
                provider_override="novelai",
                # 追加negativeを渡すと provider 側の既定UCが置き換わるため、
                # 品質系の基本negativeを土台にして結合する
                negative_prompt=merge_negative_prompt(
                    settings.novelai_negative_prompt, extra_negative or ""
                ),
                nsfw_mode=nsfw_mode,
                character_references=character_references,
                characters=None,
                seed=seed_override,
                size_override="portrait",
                novelai_model_override=effective_image_model,
            )
            if not result.images:
                raise AdventureError(
                    "image_generation_failed", "ポートレート画像が生成されませんでした"
                )
        except AdventureError:
            await self._mark_portrait_failed(run.id, effective_turn_id)
            raise
        except Exception as error:
            await self._mark_portrait_failed(run.id, effective_turn_id)
            logger.exception(
                "Adventure portrait generation failed: run_id=%s turn_id=%s",
                run.id,
                effective_turn_id,
            )
            raise AdventureError(
                "image_generation_failed",
                "ポートレート画像の生成に失敗しました",
            ) from error
        filename = f"portrait-{effective_turn_number}-{uuid.uuid4().hex[:8]}.png"
        portrait_path = self._images_dir / run.id / filename
        portrait_path.parent.mkdir(parents=True, exist_ok=True)
        portrait_path.write_bytes(result.images[0])
        async with async_session_factory() as db:
            persisted_run = await db.get(AdventureRun, run.id)
            if persisted_run is None:
                raise AdventureError("run_not_found", "アドベンチャーが見つかりません")
            persisted_run.portrait_image_path = str(portrait_path)
            persisted_run.updated_at = datetime.now()
            persisted_state = _json_load(persisted_run.state_json, {})
            # 決定論変換後ではなく LLM 出力を保存する（_prepare_image_prompt 参照）
            persisted_state["last_image_prompt"] = _image_prompt_payload(
                raw_image_prompt
            )
            if effective_turn_number == 0:
                persisted_state["opening_portrait_path"] = str(portrait_path)
            persisted_run.state_json = json.dumps(persisted_state, ensure_ascii=False)
            if effective_turn_id:
                persisted_turn = await db.get(AdventureTurn, effective_turn_id)
                if persisted_turn and persisted_turn.run_id == run.id:
                    persisted_turn.portrait_image_path = str(portrait_path)
                    persisted_turn.portrait_status = "completed"
            await db.commit()
        return portrait_path, effective_turn_id

    async def _generate_partner_portrait_unlocked(
        self,
        run_id: str,
        *,
        partner_tags: str,
        turn_number: int,
        seed_override: int | None = None,
    ) -> Path:
        """romance の攻略対象の立ち絵を生成する(非合成モードの並置表示用)。

        主人公の立ち絵と同じく白背景で生成し、フロント側で透過する。
        最新の1枚だけを state["partner_portrait_path"] に保持する。
        """
        run = await self.get_run_orm(run_id)
        state = _json_load(run.state_json, {})
        nsfw_mode = bool(run.nsfw_mode)
        prompt = _enhance_adventure_prompt(
            partner_tags + ", solo, full body standing portrait, simple background,"
            " white background, no shadow",
            nsfw_mode=nsfw_mode,
        )
        character_references = None
        reference_path = Path(str(state.get("partner_image_path") or ""))
        if bool(state.get("use_precise_reference")) and reference_path.is_file():
            # 参照は開始セッションの元画像。服装は変化し得るため弱めに参照する
            char_strength, char_fidelity = _character_reference_strength(
                outfit_changed=True, has_fresh_portrait=False
            )
            character_references = [
                {
                    "image": reference_path.read_bytes(),
                    "type": "character",
                    "strength": char_strength,
                    "fidelity": char_fidelity,
                }
            ]
        effective_image_model = (
            settings.novelai_model if nsfw_mode else settings.novelai_curated_model
        )
        result = await image_service.generate_image(
            prompt,
            image_bytes=None,
            provider_override="novelai",
            negative_prompt=settings.novelai_negative_prompt,
            nsfw_mode=nsfw_mode,
            character_references=character_references,
            characters=None,
            seed=seed_override,
            size_override="portrait",
            novelai_model_override=effective_image_model,
        )
        if not result.images:
            raise AdventureError(
                "image_generation_failed", "相手の立ち絵が生成されませんでした"
            )
        filename = f"partner-{turn_number}-{uuid.uuid4().hex[:8]}.png"
        partner_path = self._images_dir / run.id / filename
        partner_path.parent.mkdir(parents=True, exist_ok=True)
        partner_path.write_bytes(result.images[0])
        async with async_session_factory() as db:
            persisted_run = await db.get(AdventureRun, run.id)
            if persisted_run is None:
                raise AdventureError("run_not_found", "アドベンチャーが見つかりません")
            persisted_state = _json_load(persisted_run.state_json, {})
            persisted_state["partner_portrait_path"] = str(partner_path)
            if turn_number == 0:
                # 開幕フレーム表示用に、開幕時の1枚は別キーでも保持する
                persisted_state["opening_partner_portrait_path"] = str(partner_path)
            persisted_run.state_json = json.dumps(persisted_state, ensure_ascii=False)
            persisted_run.updated_at = datetime.now()
            await db.commit()
        return partner_path

    async def _generate_opening_visuals(self, run_id: str) -> None:
        """Run作成直後に、背景1回・ポートレート・（設定時のみ）合成シーンを直列生成する。"""
        async with self._run_locks[run_id]:
            run = await self.get_run_orm(run_id)
            state = _json_load(run.state_json, {})
            # 決定論変換は各生成メソッド内で再適用されるため、後続へは変換前の
            # LLM 出力を渡す。変換後を渡すと turn 0 の last_image_prompt に
            # 露出状態タグ等が保存され、次ターンの LLM へ再入する。
            (
                _prepared_prompt,
                _outfit_changed,
                nsfw_mode,
                _use_precise_reference,
                _extra_negative,
                image_prompt,
            ) = await self._prepare_image_prompt(
                run,
                state,
                redraw_from_reference=True,
                prompt_override=None,
            )
            background_path = await self._generate_background_image_unlocked(
                run_id, scene_tags=image_prompt.scene_tags, nsfw_mode=nsfw_mode
            )
            # 立ち絵と合成シーンで同一シードを使い、衣装の描画差を抑える
            opening_seed = random.randint(0, 999_999_999)
            portrait_path, _ = await self._generate_portrait_unlocked(
                run_id,
                None,
                redraw_from_reference=True,
                prompt_override=image_prompt,
                turn_number=0,
                seed_override=opening_seed,
            )
            # romance では攻略対象の立ち絵も開幕時に用意する(非合成モードの
            # 並置表示用。合成へ切り替えた場合もそのまま無害)
            sim_state = state.get("sim")
            if isinstance(sim_state, dict):
                partner_entry, partner_tags = _romance_partner_visual_entry(
                    list(state.get("visual_state", {}).get("main_characters") or []),
                    list(image_prompt.npc_tags),
                    str(sim_state.get("partner_name") or ""),
                )
                if not partner_tags:
                    clothing = partner_entry["clothing"] if partner_entry else ""
                    partner_tags = ", ".join(
                        part
                        for part in (
                            str(sim_state.get("partner_appearance") or ""),
                            clothing,
                        )
                        if part
                    )
                if partner_tags:
                    try:
                        await self._generate_partner_portrait_unlocked(
                            run_id,
                            partner_tags=partner_tags,
                            turn_number=0,
                            seed_override=opening_seed,
                        )
                    except Exception:
                        logger.exception(
                            "Adventure opening partner portrait failed: run_id=%s",
                            run_id,
                        )
                    # 立ち絵生成が state を更新するため読み直す
                    run = await self.get_run_orm(run_id)
                    state = _json_load(run.state_json, {})
            enable_composite_scene = bool(state.get("enable_composite_scene"))
            if enable_composite_scene:
                await self._generate_image_unlocked(
                    run_id,
                    None,
                    redraw_from_reference=True,
                    prompt_override=image_prompt,
                    turn_number=0,
                    source_image_override=background_path.read_bytes(),
                    character_reference_image_override=portrait_path.read_bytes(),
                    seed_override=opening_seed,
                )
            else:
                async with async_session_factory() as db:
                    persisted_run = await db.get(AdventureRun, run_id)
                    if persisted_run is None:
                        raise AdventureError(
                            "run_not_found", "アドベンチャーが見つかりません"
                        )
                    persisted_run.current_image_path = str(background_path)
                    persisted_run.updated_at = datetime.now()
                    await db.commit()

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

    def _opening_portrait_path(
        self, run: AdventureRun, state: dict[str, Any]
    ) -> Path | None:
        stored_path = Path(str(state.get("opening_portrait_path") or ""))
        if stored_path.is_file():
            return stored_path
        generated_portraits = list((self._images_dir / run.id).glob("portrait-0-*.png"))
        if generated_portraits:
            return max(generated_portraits, key=lambda path: path.stat().st_mtime)
        portrait_path = getattr(run, "portrait_image_path", None)
        return Path(portrait_path) if portrait_path else None

    def _serialize_turn(
        self,
        turn: AdventureTurn,
        fallback_image_path: Path | None = None,
        fallback_portrait_path: Path | None = None,
        *,
        language: str = "ja",
    ) -> dict[str, Any]:
        image_path = Path(turn.image_path) if turn.image_path else fallback_image_path
        portrait_image_path = (
            Path(turn.portrait_image_path)
            if turn.portrait_image_path
            else fallback_portrait_path
        )
        state_delta = _json_load(turn.state_delta_json, {})
        turn_visual = _sanitize_visual_state(state_delta.get("visual_state"))
        result = {
            "id": turn.id,
            "turn_number": turn.turn_number,
            "client_turn_id": turn.client_turn_id,
            "user_input": turn.user_input,
            "input_kind": turn.input_kind,
            "narrative": turn.narrative,
            "location": turn_visual["location"] if turn_visual else None,
            "choices": _sanitize_choices(
                _json_load(turn.choices_json, []),
                language=language,
                source=f"serialize_turn:{turn.id}",
            ),
            "image_url": self.image_url(turn.run_id, image_path)
            if image_path
            else None,
            "image_status": turn.image_status,
            "portrait_image_url": self.image_url(turn.run_id, portrait_image_path)
            if portrait_image_path
            else None,
            "portrait_status": turn.portrait_status,
            "created_at": turn.created_at.isoformat() if turn.created_at else None,
        }
        # romance ではターン確定時点の公開シミュ状態と攻略対象の様子を返す。
        # state_delta は当該ターン適用後の全 state のため、隠し好みは
        # public_sim_view で除外する
        sim_state = state_delta.get("sim")
        if isinstance(sim_state, dict) and sim_state:
            result["sim"] = public_sim_view(sim_state, turn.turn_number)
            partner_entry, _ = _romance_partner_visual_entry(
                list((turn_visual or {}).get("main_characters") or []),
                [],
                str(sim_state.get("partner_name") or ""),
            )
            note = str((partner_entry or {}).get("description") or "").strip()
            result["partner_note"] = note or None
            # このターン確定時点の攻略対象立ち絵。過去フレーム表示に使う
            partner_sprite = Path(str(state_delta.get("partner_portrait_path") or ""))
            result["partner_portrait_url"] = (
                self.image_url(turn.run_id, partner_sprite)
                if partner_sprite.is_file()
                else None
            )
        return result

    async def update_run_settings(
        self,
        run_id: str,
        *,
        use_precise_reference: bool,
        enable_composite_scene: bool,
        respect_clothing_layers: bool | None = None,
    ) -> dict[str, Any]:
        """実行中シナリオの画像設定を更新する（次回生成から反映）。"""
        async with self._run_locks[run_id]:
            run = await self.get_run_orm(run_id, with_turns=True)
            state = _json_load(run.state_json, {})
            state["use_precise_reference"] = bool(use_precise_reference)
            state["enable_composite_scene"] = bool(enable_composite_scene)
            if respect_clothing_layers is not None:
                state["respect_clothing_layers"] = bool(respect_clothing_layers)
            async with async_session_factory() as db:
                persisted = await db.get(AdventureRun, run.id)
                if persisted is None:
                    raise AdventureError(
                        "run_not_found", "アドベンチャーが見つかりません"
                    )
                persisted.state_json = json.dumps(state, ensure_ascii=False)
                persisted.updated_at = datetime.now()
                await db.commit()
            turns = sorted(run.turns, key=lambda item: item.turn_number)
            # 最新 state を反映して返す
            run.state_json = json.dumps(state, ensure_ascii=False)
            return self._serialize_run(run, turns)

    def _serialize_run(
        self,
        run: AdventureRun,
        turns: list[AdventureTurn],
        *,
        include_snapshot: bool = True,
    ) -> dict[str, Any]:
        state = _json_load(run.state_json, {})
        opening_image_path = self._opening_image_path(run, state)
        opening_portrait_path = self._opening_portrait_path(run, state)
        serialized_turns = []
        effective_image_path = opening_image_path
        effective_portrait_path = opening_portrait_path
        for turn in turns:
            serialized_turn = self._serialize_turn(
                turn,
                effective_image_path,
                effective_portrait_path,
                language=run.language,
            )
            serialized_turns.append(serialized_turn)
            if turn.image_path:
                effective_image_path = Path(turn.image_path)
            if turn.portrait_image_path:
                effective_portrait_path = Path(turn.portrait_image_path)
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
            "reality_rules": state.get("reality_rules", []),
            "milestones": state.get("milestones", []),
            "completed_milestones": state.get("completed_milestones", []),
            "visual_state": _sanitize_visual_state(state.get("visual_state")),
            "opening_narrative": state.get("opening_narrative", ""),
            "opening_image_url": self.image_url(run.id, opening_image_path),
            "choices": _sanitize_choices(
                state.get("choices", []),
                language=run.language,
                source=f"serialize_run:{run.id}",
            ),
            "current_image_url": self.image_url(run.id, Path(run.current_image_path)),
            "current_image_prompt": state.get("last_image_prompt"),
            # 旧 run でキー未設定なら OFF（意図しない Anlas 消費を防ぐ）
            "use_precise_reference": bool(state.get("use_precise_reference")),
            # 旧 run でキー未設定なら合成モード扱い（current_image_path に既に合成画像が入っている）
            "enable_composite_scene": bool(state.get("enable_composite_scene", True)),
            "respect_clothing_layers": bool(state.get("respect_clothing_layers")),
            # 旧 run は既定の二人称・「僕」へ倒す
            "narration_voice": normalize_narration_voice(state.get("narration_voice")),
            "narration_pronoun": normalize_narration_pronoun(
                state.get("narration_pronoun")
            ),
            "background_image_url": (
                self.image_url(run.id, Path(run.background_image_path))
                if getattr(run, "background_image_path", None)
                else None
            ),
            "portrait_image_url": (
                self.image_url(run.id, Path(run.portrait_image_path))
                if getattr(run, "portrait_image_path", None)
                else None
            ),
            "opening_portrait_url": (
                self.image_url(run.id, opening_portrait_path)
                if opening_portrait_path
                else None
            ),
            "turns": serialized_turns,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        }
        # romance の sim は hidden_preferences を除いた公開ビューだけ返す
        sim_state = state.get("sim")
        if run.preset == "romance" and isinstance(sim_state, dict):
            response["sim"] = public_sim_view(sim_state, run.turn_count)
            # 開幕フレーム(手番0)の表示用。開始値は定数から再構成する
            response["opening_sim"] = opening_sim_view(sim_state)
            partner_portrait = Path(str(state.get("partner_portrait_path") or ""))
            response["partner_portrait_url"] = (
                self.image_url(run.id, partner_portrait)
                if partner_portrait.is_file()
                else None
            )
            opening_partner = Path(
                str(state.get("opening_partner_portrait_path") or "")
            )
            response["opening_partner_portrait_url"] = (
                self.image_url(run.id, opening_partner)
                if opening_partner.is_file()
                else None
            )
        if include_snapshot:
            response["snapshot"] = _json_load(run.snapshot_json, {})
        return response


adventure_service = AdventureService()
