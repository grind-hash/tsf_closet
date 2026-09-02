"""独立アドベンチャーモードの生成と永続化。"""

from __future__ import annotations

import asyncio
import contextvars
import copy
import json
import logging
import random
import re
import shutil
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator, Iterable, Sequence
from dataclasses import dataclass, field
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

from ..consts.adventure_bgm import (
    BGM_SELECTION_RULES,
    get_bgm_default,
    get_bgm_keys,
    get_bgm_prompt_guide,
)
from ..consts.adventure_narration import (
    NARRATION_PRONOUN_DEFAULT,
    NARRATION_PRONOUN_MAX_LENGTH,
    NARRATION_VOICE_DEFAULT,
    NARRATION_VOICES,
)
from ..consts.adventure_partner_portrait import (
    PARTNER_PORTRAIT_FAILED,
    PARTNER_PORTRAIT_GENERATED,
    PARTNER_PORTRAIT_NOT_REQUESTED,
    PARTNER_PORTRAIT_PARTNER_ABSENT,
    PARTNER_PORTRAIT_SCENE_UNCHANGED,
    PARTNER_PORTRAIT_VISUAL_FAILED,
    normalize_partner_portrait_status,
)
from ..consts.adventure_romance import (
    ROMANCE_ALTER_DAYS_MAX,
    ROMANCE_BACKGROUND_CACHE_MAX,
    ROMANCE_MILESTONES,
    ROMANCE_PLAYER_DEFAULT_CHARACTER_ID,
    ROMANCE_SLOTS_PER_DAY,
    ROMANCE_TALK_FALLBACK_DELTA,
    ROMANCE_TALK_SCENE_CONTEXT_MAX,
)
from ..consts.adventure_setup import SCENARIO_CONSTRAINTS_MAX_ITEMS
from ..consts.companion_avatar import (
    avatar_expression_keys,
    avatar_gesture_keys,
    avatar_resolution_instruction,
    avatar_wardrobe_narrative_instruction,
    avatar_wardrobe_resolution_instruction,
    normalize_avatar_expression,
    normalize_avatar_gesture,
    normalize_avatar_outfit_key,
    parse_talk_header,
)
from ..consts.adventure_speech import (
    PARTNER_SPEECH_STYLE_MAX_LENGTH,
    SPEECH_CUSTOM_MAX_LENGTH,
    SPEECH_STYLE_DEFAULT,
    SPEECH_STYLES,
)
from ..consts.adventure_turns import (
    ADVENTURE_ALTER_TURNS_MAX,
    ADVENTURE_TURNS_DEFAULT,
    ADVENTURE_TURNS_MAX,
    ADVENTURE_TURNS_MIN,
)
from ..consts.novelai_models import (
    NOVELAI_IMAGE_MODELS,
    is_v5_image_model,
    resolve_user_image_model,
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
    ROMANCE_COMPANION_RESOLUTION_GUIDANCE,
    ROMANCE_NARRATIVE_GUIDANCE,
    ROMANCE_RECENT_TALK_GUIDANCE,
    ROMANCE_RESOLUTION_GUIDANCE,
    ROMANCE_VISUAL_GUIDANCE,
    RomanceActionError,
    RomanceAlteredGift,
    RomanceSetupOutput,
    append_talk_entry,
    apply_romance_outcome,
    apply_romance_time_of_day,
    clamp_romance_max_turns,
    init_romance_state,
    normalize_player_name,
    normalize_talk_input,
    normalize_talk_reply,
    opening_sim_view,
    public_sim_view,
    public_talk_log,
    recent_talk_entries,
    resolve_romance_action,
    romance_companion_narrative_guidance,
    romance_day_slot,
    romance_location_key,
    romance_script_format_guidance,
    romance_script_names,
    romance_setup_system_prompt,
    romance_talk_system_prompt,
    strip_duplicate_action_choices,
    strip_romance_time_of_day,
    talk_history_messages,
    talk_relationship_context,
)
from .adventure_template_loader import SCENARIO_TEMPLATES, template_localized
from .avatar_service import (
    avatar_exists,
    avatar_file_url,
    avatar_variant_label,
    list_avatar_variants,
)
from .llm_service import llm_service
from .prompt_expander_service import (
    PromptExpanderError,
    PromptExpanderService,
    entry_nsfw,
    entry_to_dict,
    resolve_entry_image_file,
)
from .session import DEFAULT_USER_ID, session_store

logger = logging.getLogger(__name__)

# 選択肢ラベルの上限。行動パネルは幅 260〜360px の縦長カラムなので、長い
# ラベルは何行にも折り返して選択肢一覧が読めなくなる。プロンプト側で
# 20字程度を要求したうえで、この値は超過分を静かに切り詰める最後の砦として使う
_CHOICE_LABEL_MAX_LENGTH = 60

_KNOWN_PROVIDERS = ("selfhost", "openrouter", "novelai")


def _text_provider() -> str:
    """Adventureのテキスト生成プロバイダー。通常ゲームと同じ設定に従う。"""
    provider = str(settings.feeling_provider or "").lower()
    return provider if provider in _KNOWN_PROVIDERS else "selfhost"


def _image_provider() -> str:
    """Adventureの画像生成プロバイダー。通常ゲームと同じ設定に従う。"""
    provider = str(settings.image_provider or "").lower()
    return provider if provider in _KNOWN_PROVIDERS else "selfhost"


def _image_calls_parallelizable() -> bool:
    """画像生成APIを並列に呼んでよいか。

    OpenRouterは従量課金のクラウドAPIで同時リクエストを受けられる。
    selfhost(単一GPU)とNovelAI(直列ゲート対象)は従来どおり直列にする。
    """
    return _image_provider() == "openrouter"


class _CostTracker:
    """1オペレーション(ターン・Run作成など)のAPI料金(USD)を集計する。"""

    __slots__ = ("total_usd",)

    def __init__(self) -> None:
        self.total_usd = 0.0

    def add(self, cost_usd: float | None) -> None:
        if cost_usd:
            self.total_usd += float(cost_usd)


# asyncio.create_task はコンテキストを複製するが、同一トラッカーオブジェクトを
# 共有するため、producer タスク内の加算も呼び出し元の合計へ反映される
_cost_tracker: contextvars.ContextVar[_CostTracker | None] = contextvars.ContextVar(
    "adventure_cost_tracker", default=None
)


def _record_cost(cost_usd: float | None) -> None:
    tracker = _cost_tracker.get()
    if tracker is not None:
        tracker.add(cost_usd)


async def _generate_text(
    system_prompt: str, user_prompt: str, *, text_model: str
) -> str:
    """設定プロバイダーでテキストを生成し、API料金を集計へ加算する。

    text_model は NovelAI 利用時のみ意味を持つ。OpenRouter / selfhost は
    それぞれの設定値(openrouter_llm_model / litellm_llm_model)を使う。
    """
    result = await llm_service.generate_text(
        system_prompt,
        user_prompt,
        provider_override=_text_provider(),
        novelai_model_override=text_model,
    )
    _record_cost(getattr(result, "cost_usd", None))
    return result.content


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
        cleaned.append(
            {
                "id": choice_id[:40],
                "label": _truncate_overlong_text(label, _CHOICE_LABEL_MAX_LENGTH),
            }
        )

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


def _clamp_list_to_declared_max(
    model: type[BaseModel], value: Any, field_name: str | None
) -> Any:
    """フィールド宣言の max_length を超えるリストを検証エラーにせず切り詰める。

    LLM 出力の件数超過だけで生成全体を失わないための保険。
    """
    if not isinstance(value, list) or not field_name:
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
    return value[:limit]


class AdventureChoice(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=_CHOICE_LABEL_MAX_LENGTH)

    @field_validator("id", "label", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("label", mode="before")
    @classmethod
    def clamp_label(cls, value: Any) -> Any:
        """長すぎるラベルは検証エラーにせず切り詰める。

        1手番まるごと修復リトライに落とすほどの問題ではなく、
        長さを理由に3択が既定文へ差し替わるほうが体験を損なうため。
        """
        if isinstance(value, str) and len(value) > _CHOICE_LABEL_MAX_LENGTH:
            return _truncate_overlong_text(value, _CHOICE_LABEL_MAX_LENGTH)
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


def _coerce_bgm_key(value: Any) -> str | None:
    """BGMキーを検証エラー→修復リトライへ落とさず None(=据え置き)に劣化させる。"""
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in get_bgm_keys():
            return candidate
    return None


# 選曲理由の表示上限。プロンプトの "200 characters or fewer" と揃える
_BGM_REASON_MAX_LENGTH = 200


def _coerce_bgm_reason(value: Any) -> str | None:
    """選曲理由を検証エラーへ落とさず、長すぎる出力は切り詰めて受け入れる。"""
    if isinstance(value, str):
        candidate = value.strip()
        if candidate:
            return candidate[:_BGM_REASON_MAX_LENGTH]
    return None


class AdventureDirectorOutput(BaseModel):
    narrative: str = Field(min_length=1, max_length=3000)
    choices: list[AdventureChoice] = Field(min_length=3, max_length=3)
    discovered_clues: list[str] = Field(default_factory=list, max_length=10)
    completed_milestones: list[str] = Field(default_factory=list, max_length=3)
    visual_state: AdventureVisualState
    ending_status: Literal["continue", "success", "partial", "failure"] = "continue"
    ending_title: str | None = Field(default=None, max_length=160)
    ending_summary: str | None = Field(default=None, max_length=1200)
    bgm: str | None = None
    bgm_reason: str | None = None
    # 対面会話モードの 3D アバター向け。語彙外は None(FE が neutral/idle に倒す)
    partner_expression: str | None = None
    partner_gesture: str | None = None

    @field_validator("partner_expression", mode="before")
    @classmethod
    def coerce_partner_expression(cls, value: Any) -> Any:
        return normalize_avatar_expression(value)

    @field_validator("partner_gesture", mode="before")
    @classmethod
    def coerce_partner_gesture(cls, value: Any) -> Any:
        return normalize_avatar_gesture(value)

    @field_validator("bgm", mode="before")
    @classmethod
    def coerce_bgm(cls, value: Any) -> Any:
        return _coerce_bgm_key(value)

    @field_validator("bgm_reason", mode="before")
    @classmethod
    def coerce_bgm_reason(cls, value: Any) -> Any:
        return _coerce_bgm_reason(value)

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
    # ユーザーの下書きに多数の制約があっても落とさず返せるよう、入力側と同じ上限にする
    constraints: list[str] = Field(
        min_length=1, max_length=SCENARIO_CONSTRAINTS_MAX_ITEMS
    )

    @field_validator("constraints", mode="before")
    @classmethod
    def clamp_overlong_list(cls, value: Any, info: ValidationInfo) -> Any:
        # ローカルモデルは件数指示を守れないことがあるため、超過分は捨てる
        return _clamp_list_to_declared_max(cls, value, info.field_name)


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
    bgm: str | None = None
    bgm_reason: str | None = None
    # 対面会話モードの 3D アバター向け。語彙外は None(FE が neutral/idle に倒す)
    partner_expression: str | None = None
    partner_gesture: str | None = None
    # 衣装差分(同じキャラクターの VRM が 2 件以上)があるときだけ載る着替え先の
    # キー("1","2",…)。stream_turn が登録 ID へ写す。欠落・空は据え置き
    partner_outfit: str | None = None
    # 宣言がタイムリミット(総手数)を変更した場合のみ入る。
    # reality_alter ターン限定で Python 側が範囲を丸めて run.max_turns へ反映する
    updated_max_turns: int | None = None

    @field_validator("partner_expression", mode="before")
    @classmethod
    def coerce_partner_expression(cls, value: Any) -> Any:
        return normalize_avatar_expression(value)

    @field_validator("partner_gesture", mode="before")
    @classmethod
    def coerce_partner_gesture(cls, value: Any) -> Any:
        return normalize_avatar_gesture(value)

    @field_validator("partner_outfit", mode="before")
    @classmethod
    def coerce_partner_outfit(cls, value: Any) -> Any:
        return normalize_avatar_outfit_key(value)

    @field_validator("updated_max_turns", mode="before")
    @classmethod
    def coerce_updated_max_turns(cls, value: Any) -> Any:
        # 不正値で検証エラー→修復リトライへ落とさず「変更なし」へ倒す
        if value is None:
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @field_validator("bgm", mode="before")
    @classmethod
    def coerce_bgm(cls, value: Any) -> Any:
        return _coerce_bgm_key(value)

    @field_validator("bgm_reason", mode="before")
    @classmethod
    def coerce_bgm_reason(cls, value: Any) -> Any:
        return _coerce_bgm_reason(value)

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
    """romance ターン用。好感度・所持金と好み書換の機械可読フィールドを追加する。

    affection_set、money_set/money_delta、updated_*_gift_ids は reality_alter
    ターンでのみ Python 側が採用する。適用規則は
    adventure_romance.apply_romance_outcome。
    """

    affection_delta: int = Field(default=0, ge=-20, le=20)
    affection_set: int | None = Field(default=None, ge=0, le=100)
    money_delta: int = Field(default=0, ge=-999_999_999, le=999_999_999)
    money_set: int | None = Field(default=None, ge=0, le=999_999_999)
    # 宣言が「交際を始める」を明示した場合のみ true。reality_alter ターン限定で
    # 告白成功と同じ扱い(全 milestone 達成 + success エンディング)になる
    start_dating: bool = False
    updated_liked_gift_ids: list[str] = Field(default_factory=list, max_length=12)
    updated_disliked_gift_ids: list[str] = Field(default_factory=list, max_length=12)
    # 宣言が攻略対象の外見を書き換えた場合のみ、変更後の外見全体を保持する。
    # reality_alter ターン限定で sim["partner_appearance"] へ反映される
    updated_partner_appearance: str | None = Field(default=None, max_length=600)
    # 宣言がタイムリミット(日数)を変更した場合のみ入る。reality_alter ターン
    # 限定で Python 側が範囲を丸めて sim["total_days"] / run.max_turns へ反映する
    updated_total_days: int | None = None
    # 宣言がギフトカタログを書き換えた場合のみ、変更後の全品目が入る。
    # 空リストは「変更なし」。適用規則は adventure_romance.apply_gift_catalog_update
    updated_gift_catalog: list[RomanceAlteredGift] = Field(
        default_factory=list, max_length=12
    )

    @field_validator("updated_total_days", mode="before")
    @classmethod
    def coerce_updated_total_days(cls, value: Any) -> Any:
        # 不正値で検証エラー→修復リトライへ落とさず「変更なし」へ倒す
        if value is None:
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @field_validator("updated_gift_catalog", mode="before")
    @classmethod
    def coerce_updated_gift_catalog(cls, value: Any) -> Any:
        # 非リスト・不正な品目で検証エラー→修復リトライへ落とさない
        if not isinstance(value, list):
            return []
        items: list[Any] = []
        for item in value[:12]:
            if isinstance(item, dict) and str(item.get("name") or "").strip():
                items.append(item)
        return items

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

    @field_validator("money_delta", mode="before")
    @classmethod
    def clamp_money_delta(cls, value: Any) -> Any:
        # LLM の過大値で検証エラー→修復リトライへ落ちないよう先にクランプする
        try:
            return max(-999_999_999, min(999_999_999, int(value)))
        except (TypeError, ValueError):
            return 0

    @field_validator("money_set", mode="before")
    @classmethod
    def clamp_money_set(cls, value: Any) -> Any:
        if value is None:
            return None
        try:
            return max(0, min(999_999_999, int(value)))
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
        # 立ち絵を描いたか/据え置いた理由の表示用記録。LLM には不要
        "partner_portrait_status",
        # 背景キャッシュもファイルパスの索引で、LLM には不要
        "background_cache",
        "background_image_path",
        # 巻き戻し用の内部記録。LLM に見せると終了済みと誤解させる
        "final_status",
        "final_ending_title",
        # 人称指示はシステムプロンプト側に載るため、user prompt へは流さない
        "narration_voice",
        "narration_pronoun",
        # 口調指示も同様にシステムプロンプト末尾へ載せる
        "player_speech_style",
        "player_speech_custom",
        # 直前の選択肢を state ごと渡すと LLM がそのまま書き写し、
        # 選択肢が更新されない。必要な分は previous_choices として別に渡す
        "choices",
        # 選曲理由は表示用メタデータ。LLM へは current_bgm だけを渡す
        "bgm_reason",
        "opening_bgm_reason",
        # 開始時の外見。参照画像の乖離判定にだけ使う内部値で、改変後の現在値と
        # 食い違うため LLM に見せると元の姿へ戻す誘導になる
        "initial_appearance_lock",
        "initial_partner_appearance",
        # 未反映の付与ルール。内容は reality_rules と
        # reality_rule_declared_this_turn で別途渡すため重複して見せない
        "pending_reality_rules",
        # 画像モデルの run 単位上書き。物語生成には無関係な内部設定
        "image_model_override",
        # 対面会話モードは画像工程だけの設定。台本形式はシステムプロンプト側に載せる
        "companion_mode",
        # 3D アバターの登録 ID は表示設定。LLM には無関係
        "companion_avatar_id",
        # 表情・身振りは手番ごとの表示用出力。次の手番の入力にはしない
        "partner_expression",
        "partner_gesture",
        # トークログは必要な分だけ recent_talk として別途渡す
        "talk_log",
    }
    return {key: value for key, value in state.items() if key not in omit}


class _TalkHeaderBuffer:
    """トーク返答の先頭ヘッダ行を配信前に取り除く小さなバッファ。

    対面会話モードの返答は ``[expression=.. gesture=..]`` で始まる。改行か
    一定長までは溜め、先頭が ``[`` でないと分かった時点で即時に流す。
    """

    _LIMIT = 64

    def __init__(self, *, enabled: bool) -> None:
        self._pending = ""
        self._decided = not enabled

    def feed(self, chunk: str) -> list[str]:
        if self._decided:
            return [chunk]
        self._pending += chunk
        stripped = self._pending.lstrip()
        if stripped and not stripped.startswith("["):
            return self._release()
        if "\n" in self._pending or len(self._pending) >= self._LIMIT:
            return self._release()
        return []

    def flush(self) -> list[str]:
        if self._decided:
            return []
        return self._release()

    def _release(self) -> list[str]:
        self._decided = True
        _, _, rest = parse_talk_header(self._pending)
        self._pending = ""
        return [rest] if rest else []


def _turn_affection(turn: Any) -> int | None:
    """手番適用後の好感度。state_delta_json が無い旧データや欠落は None。"""
    raw = getattr(turn, "state_delta_json", None)
    delta = _json_load(raw, {}) if raw else {}
    sim = delta.get("sim") if isinstance(delta, dict) else None
    if not isinstance(sim, dict) or sim.get("affection") is None:
        return None
    try:
        return int(sim.get("affection"))
    except (TypeError, ValueError):
        return None


def _talk_recent_scenes(turns: list[Any]) -> list[dict[str, Any]]:
    """トークの文脈へ渡す直近の場面。各手番後の好感度とその増減を添える。

    state_delta_json は手番適用後の全 state のスナップショットなので、そこから
    sim.affection を読み、直前の手番との差分を affection_change にする。渡す
    範囲の一つ前の手番を増減の起点にし、比較対象が無い場合は None。
    """
    recent = turns[-ROMANCE_TALK_SCENE_CONTEXT_MAX:]
    previous: int | None = None
    if len(turns) > len(recent):
        previous = _turn_affection(turns[-len(recent) - 1])
    scenes: list[dict[str, Any]] = []
    for turn in recent:
        after = _turn_affection(turn)
        change = (
            after - previous if after is not None and previous is not None else None
        )
        day, slot = romance_day_slot(int(turn.turn_number))
        scenes.append(
            {
                "turn": int(turn.turn_number),
                "day": day,
                "slot": slot,
                "player_action": turn.user_input,
                "input_kind": getattr(turn, "input_kind", None),
                "narrative": turn.narrative,
                "affection_after": after,
                "affection_change": change,
            }
        )
        if after is not None:
            previous = after
    return scenes


def _companion_avatar_id(run: AdventureRun, state: dict[str, Any]) -> str | None:
    """romance run に割り当てた 3D アバターの登録 ID。未設定・他プリセットは None。"""
    if run.preset != "romance":
        return None
    value = str(state.get("companion_avatar_id") or "").strip()
    return value or None


async def _validate_companion_avatar(avatar_id: str | None) -> str | None:
    """登録済みアバター ID を検証して返す。空は None、未登録は avatar_not_found。"""
    value = str(avatar_id or "").strip()
    if not value:
        return None
    async with async_session_factory() as db:
        if not await avatar_exists(db, value):
            raise AdventureError("avatar_not_found", "3Dモデルが見つかりません")
    return value


def _wardrobe_context(options: list[dict[str, Any]]) -> dict[str, Any]:
    """turn_context.partner_wardrobe。現在の装いと候補(キーとラベル)だけを見せる。"""
    current = next((item for item in options if item.get("current")), None)
    return {
        "current": (
            {"key": str(current["key"]), "label": str(current["label"])}
            if current
            else None
        ),
        "options": [
            {"key": str(item["key"]), "label": str(item["label"])} for item in options
        ],
    }


def _resolve_outfit_choice(
    value: str | None, options: list[dict[str, Any]]
) -> str | None:
    """判定が返した partner_outfit を登録 ID へ写す。候補外・欠落は None。

    キー("1")で照合し、LLM がラベルや ID をそのまま返した場合も受け付ける。
    """
    if not options:
        return None
    key = normalize_avatar_outfit_key(value)
    if key is None:
        return None
    folded = key.casefold()
    for item in options:
        if str(item.get("key")) == key:
            return str(item["id"])
    for item in options:
        if (
            str(item.get("id")) == key
            or str(item.get("label", "")).casefold() == folded
        ):
            return str(item["id"])
    return None


def _previous_choice_labels(state: dict[str, Any]) -> list[str]:
    """直前ターンで提示済みの選択肢ラベルを返す(重複回避の指示用)。"""
    labels: list[str] = []
    for item in state.get("choices", []) or []:
        normalized = _choice_as_dict(item)
        if normalized is None:
            continue
        label = str(normalized.get("label") or "").strip()
        if label:
            labels.append(label[:160])
    return labels


def _choice_label_key(choices: Any) -> tuple[str, ...]:
    """選択肢の同一性判定に使う正規化ラベル列。空白と表記ゆれを吸収する。"""
    keys: list[str] = []
    for item in choices or []:
        normalized = _choice_as_dict(item)
        if normalized is None:
            continue
        label = re.sub(r"\s+", "", str(normalized.get("label") or ""))
        if label:
            keys.append(label)
    return tuple(sorted(keys))


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


def _flatten_scene_prompt(
    scene_prompt: str, player_prompt: str, npc_prompts: list[str]
) -> str:
    """NovelAI V4のキャラクター枠を持たないプロバイダー向けに1本へ畳む。

    NovelAI では scene/player/npc を分離プロンプトで送るが、OpenRouter や
    ComfyUI は単一プロンプトしか受けないため、役割を明示して連結する。
    """
    parts = [f"Scene: {scene_prompt.strip()}"]
    if player_prompt.strip():
        parts.append(
            "Main character in the center foreground: " + player_prompt.strip()
        )
    for index, npc_prompt in enumerate(npc_prompts, start=1):
        if npc_prompt.strip():
            parts.append(
                f"Secondary character {index}, beside or behind the main "
                "character: " + npc_prompt.strip()
            )
    return "\n".join(parts)


def _scene_edit_instruction(has_background: bool, has_reference: bool) -> str:
    """OpenRouter画像編集用の指示文。添付画像の役割を明示する。"""
    if has_background and has_reference:
        return (
            "Create one single-frame illustration: place the exact character "
            "from the second attached image into the scene of the first "
            "attached image. Keep the character's face, hair, body, and "
            "outfit consistent with the description below.\n"
        )
    if has_background:
        return (
            "Create one single-frame illustration based on the attached "
            "image, updated to match the description below.\n"
        )
    return ""


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
            "1回の入力は半日分の場面(昼枠=朝〜夕方、夜枠=夕方〜就寝前)として、"
            "入力をきっかけに半日を共に過ごす一連の流れへ膨らませて描く。"
            "場面の締めでは次の枠へ向かう時間の気配を軽く示す。"
            "romance_resolution が示す日付・時間帯・金銭・バイト・プレゼント・"
            "告白の結果を確定事実として描写する。相手の言動は関係段階に応じて"
            "温度を変え、プレイヤー自身の感情や同意は決めつけない。恋愛的な"
            "進展は相手の主体的な反応として描き、金額や数値は本文へ書かない。"
        ),
        "milestones": ROMANCE_MILESTONES,
    },
}


# エンディング後の継続プレイ(エピローグ)で scenario_guidance へ連結する指示
EPILOGUE_GUIDANCE = (
    "The scenario's objective has already been settled and this run is now "
    "an open-ended epilogue. There is no deadline and no remaining-turn "
    "pressure: never mention time running out, never push the story toward "
    "an ending, and never conclude the scenario on your own. Depict "
    "everyday continuation of the characters and the world exactly as they "
    "were left at the ending."
)


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


# ミッション案の自動生成でユーザーが入力済みの舞台・ゴール・制約を「著者の下書き」として
# 扱わせる指示。意味・固有名詞・条件は保ち、文言の仕上げと空欄の補完だけを許す
_SETUP_DRAFT_GUIDANCE = (
    "\nuser_draft contains the author's own draft for some fields. Treat each "
    "provided field as authoritative intent: keep its meaning and every named "
    "place, person, item, and condition; you may polish wording and make it "
    "consistent with the turn budget and source_snapshot, but do not replace it "
    "with a different idea. Generate only the missing fields so they fit the draft."
)
# romance は「新しい名前を発明せよ」と指示しているため、下書きに名前があればそれを優先させる
_SETUP_DRAFT_ROMANCE_GUIDANCE = (
    " If user_draft already names the partner, use that name instead of inventing one."
)


def _build_setup_user_draft(
    setting: str,
    objective: str,
    constraints: Sequence[str] | None,
) -> dict[str, Any]:
    """入力済み項目だけを集めた下書き。全て空なら空 dict を返す。"""
    draft: dict[str, Any] = {}
    if setting.strip():
        draft["setting"] = setting.strip()
    if objective.strip():
        draft["objective"] = objective.strip()
    cleaned_constraints = [
        item.strip() for item in (constraints or []) if item and item.strip()
    ]
    if cleaned_constraints:
        draft["constraints"] = cleaned_constraints
    return draft


def _romance_prompt_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """romance の攻略対象素材として LLM へ渡す snapshot。

    character_name はそのセッションの変身前の主人公名であり、変身後の姿である
    攻略対象の名前ではないため除外する(相手の名前は LLM が新しく考える)。
    """
    return {key: value for key, value in snapshot.items() if key != "character_name"}


def _romance_replay_player_selection(
    replay_state: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    """リプレイ元 run の sim から主人公の選択を復元する。

    返り値は (character_id, session_id, history_id)。sim の player_character_id
    は "session:{id}" 形式でセッション由来の主人公を表す。history_id を持たない
    旧 run はセッションの現在状態から始め直す。player_character_id を持たない
    さらに古い run は全て None を返し、既定キャラクターへフォールバックする。
    """
    replay_sim = (
        replay_state["sim"] if isinstance(replay_state.get("sim"), dict) else {}
    )
    stored_player = str(replay_sim.get("player_character_id") or "")
    if stored_player.startswith("session:"):
        return (
            None,
            stored_player.removeprefix("session:"),
            str(replay_sim.get("player_history_id") or "") or None,
        )
    if stored_player:
        return stored_player, None, None
    return None, None, None


def _romance_replay_player_name(replay_state: dict[str, Any]) -> str:
    """リプレイ元 run の sim から主人公の呼び名を復元する。無ければ空文字。"""
    replay_sim = (
        replay_state["sim"] if isinstance(replay_state.get("sim"), dict) else {}
    )
    return normalize_player_name(str(replay_sim.get("player_name") or ""))


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


def _normalized_appearance(value: Any) -> str:
    """外見文字列の比較用正規化。空白の揺れと大文字小文字を吸収する。"""
    return " ".join(str(value or "").split()).casefold()


def _appearance_diverged(state: dict[str, Any]) -> bool:
    """主人公の外見が開始時から変わっているか。

    どちらかの値が欠けていれば False を返し、旧 run は従来どおり開始画像を
    参照し続ける。
    """
    initial = _normalized_appearance(state.get("initial_appearance_lock"))
    current = _normalized_appearance(state.get("appearance_lock"))
    if not initial or not current:
        return False
    return initial != current


def _partner_appearance_diverged(state: dict[str, Any]) -> bool:
    """攻略対象の外見が開始時から変わっているか。旧 run と非 romance は False。"""
    sim = state.get("sim")
    if not isinstance(sim, dict):
        return False
    initial = _normalized_appearance(state.get("initial_partner_appearance"))
    current = _normalized_appearance(sim.get("partner_appearance"))
    if not initial or not current:
        return False
    return initial != current


def _romance_partner_turn_portrait_tags(
    main_characters: list[Any],
    npc_tags: list[str],
    partner_name: str,
    partner_appearance: str,
) -> str:
    """その手番の攻略対象立ち絵に使うタグ。描き直さないなら空文字を返す。

    その手番の場面に相手が居ない(main_characters に居ない)なら描き直さず、
    前の1枚を残す。居ない相手を sim の外見から描くと、服装の情報が無いぶん
    裸で描かれたり、改変前の古い外見へ戻ったりする。
    相手は居るが npc_tags を取れなかったときだけ sim の外見で補う。
    """
    entry, tags = _romance_partner_visual_entry(main_characters, npc_tags, partner_name)
    if entry is None:
        return ""
    if tags:
        return tags
    return ", ".join(part for part in (partner_appearance, entry["clothing"]) if part)


def _romance_partner_scene_reference(
    state: dict[str, Any],
    image_prompt: AdventureImagePromptOutput,
    *,
    reference_override: bytes | None = None,
) -> dict[str, Any] | None:
    """合成シーン用に攻略対象の character reference を組み立てる。

    romance で攻略対象がシーンの NPC として描かれるターンだけ返す。登場しない
    ターンに渡すと無関係な参照が絵を引っ張るため付けない。API には参照とキャラ枠を
    紐付ける手段が無く、どの人物へ効くかはモデルの照合に任せる。
    reference_override はそのターンに描き直した攻略対象の立ち絵。衣装・表情が
    現在のものなので強参照にする。override が無い場合は開始素材の画像を使い、
    服装は変化し得るため弱参照にする。
    現実改変で sim["partner_appearance"] が開始時から変わった後は、開始素材が
    元の姿のままなので使わず、直近の相手立ち絵へ切り替える。それも無ければ
    参照なしとする(古い姿を弱参照するより無参照の方が正しい)。
    """
    sim_state = state.get("sim")
    if not isinstance(sim_state, dict):
        return None
    reference_bytes = reference_override
    if reference_bytes is None:
        reference_key = (
            "partner_portrait_path"
            if _partner_appearance_diverged(state)
            else "partner_image_path"
        )
        reference_path = Path(str(state.get(reference_key) or ""))
        if not reference_path.is_file():
            return None
        reference_bytes = reference_path.read_bytes()
    # ターン中は state_json が永続化前で古いため、visual_state を持つ
    # prompt_override(AdventureVisualOutput)があればそちらを優先する
    visual_state = getattr(image_prompt, "visual_state", None)
    main_characters = (
        list(visual_state.main_characters)
        if visual_state is not None
        else list(state.get("visual_state", {}).get("main_characters") or [])
    )
    _entry, partner_tags = _romance_partner_visual_entry(
        main_characters,
        list(image_prompt.npc_tags),
        str(sim_state.get("partner_name") or ""),
    )
    if not partner_tags:
        return None
    strength, fidelity = _character_reference_strength(
        outfit_changed=True, has_fresh_portrait=reference_override is not None
    )
    return {
        "image": reference_bytes,
        "type": "character",
        "strength": strength,
        "fidelity": fidelity,
    }


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


def _validate_model_json(
    model: type[_StructuredOutputT],
    raw: str,
    *,
    context: dict[str, Any] | None = None,
) -> _StructuredOutputT:
    """LLM 出力の JSON を検証する。制御文字だけが不正な場合は救済する。

    ローカルモデルは JSON 文字列内へ生の改行を混ぜやすく、厳密パースだけでは
    復旧可能な出力まで失うため、json.loads(strict=False) で再試行する。
    それでも読めなければ元の検証エラーを送出し、呼び出し側のリペアへ委ねる。
    """
    text = _strip_json_fence(raw)
    try:
        return model.model_validate_json(text, context=context)
    except ValidationError as strict_error:
        try:
            data = json.loads(text, strict=False)
        except ValueError:
            raise strict_error
        return model.model_validate(data, context=context)


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

# 「ターン毎に徐々に女体化する」のような、毎ターン進行し続ける改変ルールの検出。
# 該当ルールが1件でも残っている間は毎ターン外見ロックの更新を許し、
# 宣言ターン以降もロックに阻まれて変化が止まらないようにする
_PROGRESSIVE_RULE_PATTERN = re.compile(
    r"毎ターン|ターン毎|ターンごと|毎手番|手番ごと|徐々に|少しずつ|だんだん|"
    r"段々|次第に|日に日に|日ごと|日毎|進行していく|進行する|進んでいく|"
    r"gradual|slowly|step by step|each turn|every turn|per turn|turn by turn|"
    r"over time|day by day|progressiv|bit by bit|little by little",
    re.IGNORECASE,
)


def _progressive_reality_rules(rules: Iterable[Any]) -> list[str]:
    """進行型(毎ターン変化し続ける)の現実改変ルールだけを返す。"""
    return [
        rule
        for rule in _normalize_reality_rules(rules)
        if _PROGRESSIVE_RULE_PATTERN.search(rule)
    ]


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
    "player established those rules as of this turn, either by declaring them in their "
    "input or by adding them directly: narrate the world already conforming to them, "
    "keep ending_status as continue, and never treat the declaration itself as "
    "a suspicious act. Every entry in reality_rules stays in force on every later turn, "
    "so a rule that states how the player looks, what they wear, or how others treat "
    "them must keep being reflected even long after the turn that established it. "
    "Re-read every entry of reality_rules on every turn before writing, and keep the "
    "world, the NPCs, and the player consistent with all of them at once; never let "
    "an old rule quietly fade out of the story. "
    "progressive_reality_rules lists the subset of reality_rules that describe a "
    "gradual, repeated, or per-turn ongoing change (for example, the player's body "
    "becoming more feminine every turn). Such a rule is never finished after the turn "
    "that declared it: on every single turn, including this one, the change it "
    "describes advances by one clearly noticeable step compared to the previous "
    "turn's state, and it never reverts to an earlier stage while the rule remains "
    "in reality_rules. The immutable-identity-signature rule does not protect traits "
    "that a progressive rule changes: describe those traits one step further "
    "advanced than the previous turn, and state the newly advanced step concretely."
)

# 非 romance の resolution へ追加する、タイムリミット変更の申告フィールド。
# romance 側の updated_total_days は ROMANCE_RESOLUTION_GUIDANCE が説明する
_TIME_LIMIT_ALTER_INSTRUCTION = (
    'Add one extra field to the JSON object: "updated_max_turns" (integer or '
    "null). Keep it null on every turn except when the player's reality "
    "declaration in this turn (reality_rule_declared_this_turn) explicitly "
    "changes the mission's time limit or total turn budget; in that case "
    "report the new total number of turns as updated_max_turns. max_turns in "
    "the input shows the current budget. Never invent a change the "
    "declaration does not state."
)


def _apply_time_limit_alteration(
    run: AdventureRun,
    state: dict[str, Any],
    resolution: AdventureResolutionOutput,
    *,
    input_kind: str,
    turn_number: int,
    epilogue: bool,
) -> bool:
    """現実改変宣言によるタイムリミット変更を run.max_turns へ反映する。

    reality_alter ターン限定。romance は updated_total_days(日数)を、その他は
    updated_max_turns(総手数)を読む。現在の手番(日)を下回らないよう丸め、
    上限は ADVENTURE_ALTER_TURNS_MAX / ROMANCE_ALTER_DAYS_MAX。エピローグ中は
    期限が意味を持たないため無視する。反映したら True(呼び出し側が永続化する)。
    """
    if epilogue or input_kind != "reality_alter":
        return False
    sim = state.get("sim")
    if run.preset == "romance" and isinstance(sim, dict):
        days = getattr(resolution, "updated_total_days", None)
        if not isinstance(days, int):
            return False
        current_day, _ = romance_day_slot(turn_number)
        days = max(current_day, min(ROMANCE_ALTER_DAYS_MAX, days))
        new_max = days * ROMANCE_SLOTS_PER_DAY
        if new_max == run.max_turns:
            return False
        run.max_turns = new_max
        sim["total_days"] = days
        return True
    turns = getattr(resolution, "updated_max_turns", None)
    if not isinstance(turns, int):
        return False
    new_max = max(turn_number, min(ADVENTURE_ALTER_TURNS_MAX, turns))
    if new_max == run.max_turns:
        return False
    run.max_turns = new_max
    return True


# 選択肢が攻略対象やNPC側の台詞・行動として生成される事故を防ぐ。
# 台詞入りの選択肢では「主人公が発する言葉」だけを引用させる
_CHOICES_PERSPECTIVE_INSTRUCTION = (
    "Every choices[].label describes an action the player character performs "
    "next, written from the player's standpoint. Never write a label that "
    "describes an NPC's action, service, or reaction toward the player. When "
    "a label contains quoted dialogue, the quoted words must be lines the "
    "player speaks to an NPC, never lines an NPC speaks to the player (for "
    "example, never a staff greeting that addresses the player by name)."
)


# 行動パネルは幅 260〜360px の縦長カラムなので、長いラベルは何行にも折り返って
# 3択が読めなくなる。内容の粒度ではなく「書き方」を短くさせる
_CHOICES_LENGTH_INSTRUCTION = (
    "Keep every choices[].label short enough to read at a glance in a narrow "
    "column: at most 20 Japanese characters, or at most 8 English words. Name "
    "the action in the fewest words that still identify it, and drop scene "
    "description, motives, adjectives, and clauses that restate the narrative "
    "(write 「新作ドリンクを出す」, not 「彼女の座っているテーブルへ、考え抜いた新しい"
    "ドリンクを提供する」). Shortening the wording never changes the required "
    "scope of the action itself."
)


# 直前の選択肢の焼き直しを禁じる。previous_choices は「避けるべき既出案」
_CHOICES_FRESHNESS_INSTRUCTION = (
    "previous_choices lists the options that were already offered to the player "
    "before this turn. Write three options for the situation the narrative has "
    "just reached: never reuse a previous_choices label, its wording, or a "
    "paraphrase of it, and never re-offer the action the player has just taken. "
    "If the scene barely moved, still propose different concrete approaches "
    "rather than repeating the earlier list."
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


# 主人公のセリフの敬体・常体。語りの人称(地の文の主語)とは独立した軸で、
# 「バイト先の相手にため口で話す」といった破綻を防ぐために明示する
_SPEECH_STYLE_RULES: dict[str, str] = {
    "polite": (
        "The player character speaks politely to everyone, using Japanese "
        "です/ます forms (or their equivalent in the response language), and "
        "never drops into plain casual speech even as the relationship warms."
    ),
    "casual": (
        "The player character speaks casually and familiarly, using Japanese "
        "plain forms (だ/だよ/〜ね) rather than です/ます, as one would with a "
        "close friend."
    ),
    "formal": (
        "The player character speaks in deferential, formal Japanese, "
        "combining です/ます with honorific and humble forms (いらっしゃる, "
        "いたします, 申し上げます) as one would toward a customer or a superior."
    ),
}

# 口調指示が同意・主体性のガードを緩める口実にならないよう、人称と同じ形で添える
_SPEECH_STYLE_GUARD = (
    "This register governs only the wording of the lines the player character "
    "actually speaks. It grants no authority to invent the player character's "
    "feelings, consent, wishes, or voluntary actions, and it never changes what "
    "they choose to say. Earlier entries in recent_turns may use a different "
    "register; ignore theirs and follow this rule."
)


def normalize_speech_style(value: str | None) -> str:
    """未知の値や旧 run の欠落は既定の丁寧語へ倒す。"""
    style = str(value or "")
    return style if style in SPEECH_STYLES else SPEECH_STYLE_DEFAULT


def normalize_speech_custom(value: str | None) -> str:
    """自由入力の口調を1行へ正規化する。システムプロンプトへ入るため改行を畳む。"""
    return " ".join(str(value or "").split()).strip()[:SPEECH_CUSTOM_MAX_LENGTH]


def normalize_partner_speech_style(value: str | None) -> str:
    """攻略対象の口調文を1行へ正規化する。空文字は「未設定」を意味する。"""
    return " ".join(str(value or "").split()).strip()[:PARTNER_SPEECH_STYLE_MAX_LENGTH]


def _speech_style_instruction(
    style: str | None,
    custom: str | None,
    *,
    partner_style: str = "",
    partner_name: str = "",
    player_name: str = "",
) -> str:
    """セリフの口調指示を返す。プロンプト末尾に置いて直近性を効かせる。

    主人公と(romance なら)攻略対象の両方を1ブロックにまとめる。相手の口調は
    user prompt の state.sim にも載るが、名前参照だけでは守られないため、
    人称指示と同じ末尾位置で実際の文言を再掲する。

    player_name があれば、セリフの中では主人公をその名前で呼ばせる。二人称の
    語り(「あなた」)がセリフへ漏れて「あなたさん」のような呼びかけになるのを防ぐ。
    """
    style = normalize_speech_style(style)
    if style == "custom":
        custom = normalize_speech_custom(custom)
        player_rule = (
            "The player character speaks in this register, and keeps it in every "
            f"line they speak: 「{custom}」"
            if custom
            else _SPEECH_STYLE_RULES[SPEECH_STYLE_DEFAULT]
        )
    else:
        player_rule = _SPEECH_STYLE_RULES[style]
    partner_rule = ""
    partner_style = normalize_partner_speech_style(partner_style)
    if partner_style:
        who = partner_name.strip() or "The romance partner"
        partner_rule = (
            f" {who} speaks in this register, and keeps it in every line they "
            f"speak regardless of how the player speaks and regardless of how "
            f"far the relationship has progressed: 「{partner_style}」 Never "
            "converge their register onto the player's."
        )
    address_rule = ""
    player_name = normalize_player_name(player_name)
    if player_name:
        address_rule = (
            f" Inside quoted dialogue, other characters call the player character "
            f"by name, 「{player_name}」, shortened or combined with an honorific or "
            "nickname as their own speech style names. The narration's "
            '"you"/「あなた」 is the narrator\'s voice only: never let a character '
            "use it as the player's name (never 「あなたさん」)."
        )
    return (
        "SPEECH REGISTER: "
        + player_rule
        + partner_rule
        + address_rule
        + " "
        + _SPEECH_STYLE_GUARD
    )


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


def _speech_rule_from_state(state: dict[str, Any]) -> str:
    """run の state からセリフの口調指示を組み立てる。旧 run は既定へ倒す。

    攻略対象(romance)の口調も同じブロックへ含めるため、sim からも読み出す。
    """
    sim = state.get("sim")
    sim = sim if isinstance(sim, dict) else {}
    return _speech_style_instruction(
        state.get("player_speech_style"),
        state.get("player_speech_custom"),
        partner_style=str(sim.get("partner_speech_style") or ""),
        partner_name=str(sim.get("partner_name") or ""),
        player_name=str(sim.get("player_name") or ""),
    )


def _normalize_reality_rule(rule: Any) -> str:
    """ルール1件の表記ゆれを吸収する。空白を畳み、上限文字数で切る。

    宣言経路(_detect_reality_declaration)と管理経路(update_reality_rules)で
    同じ文字列になるよう、正規化はこの1箇所に集約する。
    """
    return " ".join(str(rule or "").split()).strip()[:_MAX_REALITY_RULE_LENGTH]


def _normalize_reality_rules(rules: Iterable[Any]) -> list[str]:
    """一覧を正規化し、空要素を捨てて順序を保ったまま重複を除く。"""
    normalized: list[str] = []
    for item in rules:
        rule = _normalize_reality_rule(item)
        if rule and rule not in normalized:
            normalized.append(rule)
    return normalized


# 画像生成へ渡すときに付ける定型サフィックス。プレビューと送信で同じものを使う
_SCENE_PROMPT_SUFFIX = (
    ", visual novel scene, protagonist in foreground, supporting NPCs secondary"
)
_PLAYER_PROMPT_SUFFIX = ", main protagonist, primary focus, center foreground"
_NPC_PROMPT_SUFFIX = ", supporting character, secondary focus, behind protagonist"
# 立ち絵専用の追加ネガティブ。full body + 透過/白背景の組み合わせは
# キャラクターシート風の複数ビュー・複数人を誘発しやすく、特に V5 で
# 同一人物が2人並ぶ事故が起きるため、単独1ビューを強制する
_PORTRAIT_EXTRA_NEGATIVE = (
    "2girls, 2boys, 3girls, multiple girls, multiple boys, multiple views, "
    "reference sheet, character sheet, turnaround, variations, "
    "two people, multiple people, duplicate character, clone"
)

# 攻略対象の立ち絵は V5 で同一人物が2人並ぶ絵になりやすいため、さらに抑止語を足す
_PARTNER_SOLO_NEGATIVE = (
    "twins, mirror image, side by side, two figures, split view, "
    "before and after, comparison"
)

_PORTRAIT_PROMPT_SUFFIX = ", solo, full body standing portrait, simple background, white background, no shadow"
# V5系モデルは透過背景をネイティブ生成できるため、白背景ではなく透過を指示する
# （フロント側の透過処理は既に透過を持つ画像を素通しする）
_PORTRAIT_PROMPT_SUFFIX_V5 = (
    ", solo, full body standing portrait, transparent background, no shadow"
)


def _portrait_prompt_suffix(image_model: str | None) -> str:
    """立ち絵用サフィックスをモデルに応じて返す（V5のみ透過背景指示）。"""
    return (
        _PORTRAIT_PROMPT_SUFFIX_V5
        if is_v5_image_model(image_model)
        else _PORTRAIT_PROMPT_SUFFIX
    )


def _visual_user_payload(
    *,
    narrative: str,
    turn_context: dict[str, Any],
    previous_visual: dict[str, Any],
    appearance_lock: str,
    previous_image_tags: dict[str, Any] | None,
    romance_partner: dict[str, Any] | None,
) -> str:
    """ビジュアル呼び出しの user prompt。プレビューと送信で同じものを使う。"""
    authored_scene_tags = str(turn_context.get("authored_scene_tags") or "").strip()
    return json.dumps(
        {
            "narrative": narrative,
            "player_input": turn_context.get("player_input", ""),
            "authored_template_resolution": turn_context.get(
                "authored_template_resolution", {}
            ),
            "authored_visual_style": turn_context.get("authored_visual_style"),
            "authored_scene_tags": authored_scene_tags or None,
            "previous_visual_state": previous_visual,
            "previous_image_tags": previous_image_tags,
            "required_visual_appearance": appearance_lock,
            # 現実改変を外見へ反映させるための世界ルール。宣言ターンの
            # 検出は reality_rule_declared_this_turn で伝える
            "reality_rules": turn_context.get("reality_rules", []),
            "reality_rule_declared_this_turn": turn_context.get(
                "reality_rule_declared_this_turn"
            ),
            # 進行型ルール。残っている限り毎ターン外見を一段進めさせる
            "progressive_reality_rules": turn_context.get(
                "progressive_reality_rules", []
            ),
            "romance_partner": romance_partner,
        },
        ensure_ascii=False,
    )


# 対面会話モードでは半日枠が無いため、判定結果のうち時間帯のキーを LLM に見せない
_COMPANION_HIDDEN_RESOLUTION_KEYS = frozenset({"day", "slot", "next_day", "next_slot"})


@dataclass
class _TurnContexts:
    """1手番のLLM呼び出しに渡す文脈と、その組み立て過程で決まる値。

    stream_turn と、プロンプトプレビュー(preview_turn_prompts)の両方が
    _build_turn_contexts からこれを受け取る。プレビューが実際の送信内容と
    食い違わないよう、組み立てはこの1経路に集約する。
    """

    turn_context: dict[str, Any]
    visual_turn_context: dict[str, Any]
    # 「現実改変：〜」を検出すると reality_alter へ昇格するため、呼び出し側の値と
    # 食い違い得る
    input_kind: str
    narration_voice: str
    narration_pronoun: str
    # 組み立て済みのセリフ口調ブロック。主人公と攻略対象の両方を含む
    speech_rule: str
    appearance_update_allowed: bool
    template: dict[str, Any] | None
    template_resolution: dict[str, Any]
    romance_sim: dict[str, Any] | None
    romance_resolution: dict[str, Any] | None
    appearance_lock: str
    previous_choice_key: tuple[str, ...]
    # 対面会話モードのときだけ (攻略対象名, 主人公名)。台本形式の指示に使う
    script_names: tuple[str, str] | None = None
    # 対面会話モードで表示中の 3D モデルと同じキャラクターの衣装差分(2 件以上の
    # ときだけ)。各要素は {key, id, label, current}。_companion_outfit_options 参照
    outfit_options: list[dict[str, Any]] = field(default_factory=list)


def _take_established_reality_rules(
    state: dict[str, Any], declared_rule: str | None
) -> str | None:
    """この手番で確定したルールを1つの文字列にまとめて返す。

    入力による宣言と、手番を使わず付与された未反映分(pending_reality_rules)を
    同じ扱いにする。pending は一度きりの通知なので state から取り除く。
    どちらも無ければ None を返す。
    """
    pending = _normalize_reality_rules(state.pop("pending_reality_rules", []))
    established = _normalize_reality_rules(
        [*([declared_rule] if declared_rule else []), *pending]
    )
    return "; ".join(established) or None


def _detect_reality_declaration(user_input: str) -> str | None:
    """「現実改変：〜」形式の宣言ならルール本文を返す。宣言でなければ None。"""
    match = _REALITY_DECLARATION_PATTERN.match(user_input or "")
    if match is None:
        return None
    return _normalize_reality_rule(match.group("rule")) or None


def _append_reality_rule(state: dict[str, Any], rule: str) -> list[str]:
    """宣言されたルールを state へ追記し、更新後の一覧を返す。

    上限超過時は最も古いルールを落とす。物語中の宣言は必ず効く必要があるため、
    管理経路(update_reality_rules)のように拒否はしない。
    """
    rules = _normalize_reality_rules(state.get("reality_rules", []))
    normalized = _normalize_reality_rule(rule)
    if normalized and normalized not in rules:
        rules.append(normalized)
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


def _identity_tags_only(tags: str) -> str:
    """カンマ区切りタグから服装・情景タグを除き、同一性タグだけを返す。

    partner_appearance の初期値を作る _history_visual_description と同じ
    フィルタを使い、書き戻し後も初期値と同じ形式を保つ。npc_tags は服装を
    含むため、素のまま保存すると攻略対象の服装が以後固定されてしまう。
    """
    parts = [tag.strip() for tag in tags.split(",") if tag.strip()]
    identity = [
        tag
        for tag in parts
        if not _CLOTHING_TAG_PATTERN.search(tag)
        and not _SCENE_OR_ACTION_TAG_PATTERN.search(tag)
    ]
    return ", ".join(identity)


class AdventureService:
    """アドベンチャーRunを元セッションから分離して管理する。"""

    def __init__(self) -> None:
        self._run_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        # 画像生成の並列実行(OpenRouter)時に、state_json の
        # read-modify-write が交錯して更新を失わないよう永続化だけ直列化する
        self._persist_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
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

    async def _build_prompt_expander_snapshot(
        self, entry_id: str
    ) -> tuple[dict[str, Any], Path, str, bool]:
        """Prompt Expander のエントリを開始素材にしたスナップショットを組み立てる。

        ゲームセッション由来の時系列・属性・統計は無く、外見は保存済みの最終プロンプト
        （＋キャラクタープロンプト）を使う。NSFW は画像モデルの family から導出する。
        """
        try:
            async with async_session_factory() as db:
                entry = await PromptExpanderService.get_entry(
                    db, entry_id=entry_id, user_id=DEFAULT_USER_ID
                )
                view = entry_to_dict(entry)
                image_path = resolve_entry_image_file(entry)
                nsfw_mode = bool(entry_nsfw(entry))
        except PromptExpanderError as exc:
            raise AdventureError(
                "source_not_found", "開始元の Prompt Expander エントリが見つかりません"
            ) from exc
        if image_path is None:
            raise AdventureError("image_not_found", "開始画像が見つかりません")
        appearance_parts = [str(view.get("final_prompt") or "").strip()]
        appearance_parts.extend(
            str(item).strip() for item in view.get("character_prompts") or []
        )
        appearance = ", ".join(part for part in appearance_parts if part)
        snapshot = {
            "source_session_id": None,
            "source_history_id": None,
            "source_prompt_expander_entry_id": entry_id,
            "character_name": None,
            "appearance": appearance,
            "clothing": "",
            "attributes": [],
            "timeline": [],
            "stats": None,
        }
        return snapshot, image_path, appearance, nsfw_mode

    async def _build_snapshot(
        self,
        source_session_id: str | None,
        source_history_id: str | None,
        *,
        source_prompt_expander_entry_id: str | None = None,
    ) -> tuple[dict[str, Any], Path, str, bool]:
        if source_prompt_expander_entry_id:
            return await self._build_prompt_expander_snapshot(
                source_prompt_expander_entry_id
            )
        if not source_session_id:
            raise AdventureError("source_not_found", "開始元セッションが見つかりません")
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
        speech_rule: str = "",
        romance: bool = False,
        script_names: tuple[str, str] | None = None,
    ) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        voice_rule = _narration_voice_instruction(narration_voice, narration_pronoun)
        if romance:
            # 対面会話モード(script_names あり)は半日枠でなく1往復の会話にする
            romance_rule = (
                romance_companion_narrative_guidance(*script_names)
                if script_names
                else ROMANCE_NARRATIVE_GUIDANCE
            )
            voice_rule = f"{romance_rule}\n{voice_rule}"
        if speech_rule:
            voice_rule = f"{voice_rule}\n{speech_rule}"
        if script_names:
            # 対面会話モード: 台本形式は最後に置き、最も新しい指示として効かせる
            voice_rule = (
                f"{voice_rule}\n{romance_script_format_guidance(*script_names)}"
            )
        return f"""You are the director of a short objective-based adventure game.
Return one JSON object only, in {response_language}, matching this schema:
{{"narrative":"...","choices":[{{"id":"...","label":"..."}},{{"id":"...","label":"..."}},{{"id":"...","label":"..."}}],"discovered_clues":[],"completed_milestones":[],"visual_state":{{"location":"...","appearance":"...","clothing":"...","surroundings":"...","main_characters":[{{"name":"...","description":"...","clothing":"...","action":"..."}}]}},"ending_status":"continue|success|partial|failure","ending_title":null,"ending_summary":null,"bgm":"{"|".join(get_bgm_keys())}","bgm_reason":"..."}}
Keep narrative under 800 characters and the entire JSON response compact. bgm selects the background music category for the scene and must be exactly one of: {get_bgm_prompt_guide()}. {BGM_SELECTION_RULES} bgm_reason briefly states, in {response_language}, why that bgm category fits this scene, in 200 characters or fewer. Never output a filename, a path, or any value outside this list. Never decide the player's feelings, consent, past wishes, bodily sensations, or voluntary actions unless the player's input explicitly states them. If the player's action objectively makes the mission impossible to continue, return a concise failure ending instead of refusing, truncating, or leaving the JSON incomplete. Describe observable events and NPC actions. Do not introduce an unrequested body transformation. Never grant the player another person's memories, personal knowledge, relationships, habits, skills, credentials, passwords, or authentication information unless the supplied source facts explicitly state them. A copied appearance or name does not imply copied memory or competence. Treat source_snapshot.appearance and required_visual_appearance as an immutable identity signature. Copy its sex, hair color, hair length, hairstyle, eye color, and body features exactly into visual_state.appearance; never replace or supplement those traits. Do not change the player's physical appearance unless scenario_capabilities or authored_template_resolution explicitly allows and triggers that change. Clothing may be offered, found, or discussed, but the player only puts on, removes, or changes clothing when their input explicitly chooses that action. When the player explicitly chooses to put on clothing, visual_state.clothing must show that garment as currently worn in the same turn. Unless the input explicitly requests layering, the new garment replaces the previous outfit instead of being worn over it. If the source snapshot explicitly establishes a transformed sex or body, it may create practical disguise or role opportunities without inventing further changes. Keep visual_state concrete enough to illustrate the main characters, their clothing, and the surrounding location. When authored_visual_style is provided, set visual_state.location and visual_state.surroundings from it and never describe the room as a basement, locker room, warehouse, or cold industrial cell. completed_milestones must contain milestone ID strings only, never objects. Complete milestones only when the narrated action actually earns them. When authored_template_resolution is provided, treat it as authoritative and never narrate a score, transformation, unlocked exit, or ending beyond its event.
{_CHOICES_PERSPECTIVE_INSTRUCTION}
{_CHOICES_LENGTH_INSTRUCTION}
{_CHOICES_FRESHNESS_INSTRUCTION}
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
        speech_rule: str = "",
        romance: bool = False,
        script_names: tuple[str, str] | None = None,
    ) -> AdventureDirectorOutput:
        system_prompt = self._director_system_prompt(
            language,
            narration_voice=narration_voice,
            narration_pronoun=narration_pronoun,
            speech_rule=speech_rule,
            romance=romance,
            script_names=script_names,
        )
        raw = await _generate_text(system_prompt, prompt, text_model=text_model)
        try:
            return _validate_model_json(
                AdventureDirectorOutput,
                raw,
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
{_narration_voice_instruction(narration_voice, narration_pronoun)}
{speech_rule}"""
            repair_prompt = (
                f"Fix these validation errors:\n{first_error}\n\n"
                "Invalid source output:\n\n" + raw
            )
            repaired = await _generate_text(
                repair_system_prompt, repair_prompt, text_model=text_model
            )
            try:
                return _validate_model_json(
                    AdventureDirectorOutput,
                    repaired,
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
                    len(raw),
                    len(repaired),
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
        speech_rule: str = "",
        romance: bool = False,
        script_names: tuple[str, str] | None = None,
        wardrobe: bool = False,
    ) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        voice_rule = _narration_voice_instruction(narration_voice, narration_pronoun)
        if romance:
            # 対面会話モード(script_names あり)は半日枠でなく1往復の会話にする
            romance_rule = (
                romance_companion_narrative_guidance(*script_names)
                if script_names
                else ROMANCE_NARRATIVE_GUIDANCE
            )
            voice_rule = f"{romance_rule}\n{ROMANCE_RECENT_TALK_GUIDANCE}\n{voice_rule}"
        if speech_rule:
            voice_rule = f"{voice_rule}\n{speech_rule}"
        if script_names:
            if wardrobe:
                # 衣装差分(turn_context.partner_wardrobe)がある手番だけ着替えを許す
                voice_rule = f"{voice_rule}\n{avatar_wardrobe_narrative_instruction()}"
            # 対面会話モード: 台本形式は最後に置き、最も新しい指示として効かせる
            voice_rule = (
                f"{voice_rule}\n{romance_script_format_guidance(*script_names)}"
            )
        return f"""You are the director of a short objective-based adventure game.
Write only the narrative for the next scene, as plain prose in {response_language}. Do not output JSON, markdown, headings, choices, labels, or commentary.
Keep the narrative under 800 characters. Never decide the player's feelings, consent, past wishes, bodily sensations, or voluntary actions unless the player's input explicitly states them. If the player's action objectively makes the mission impossible to continue, narrate a concise failure ending instead of refusing or truncating. Describe observable events and NPC actions. Do not introduce an unrequested body transformation. Never grant the player another person's memories, personal knowledge, relationships, habits, skills, credentials, passwords, or authentication information unless the supplied source facts explicitly state them. A copied appearance or name does not imply copied memory or competence. Treat state.appearance_lock and required_visual_appearance as an immutable identity signature, and never change the player's sex, hair color, hair length, hairstyle, eye color, or body features unless scenario_guidance or authored_template_resolution explicitly allows and triggers that change, or reality_rule_declared_this_turn declares a change to the player's own body or identity; in that case narrate the player already in the new body and keep every unaffected trait. Clothing may be offered, found, or discussed, but the player only puts on, removes, or changes clothing when their input explicitly chooses that action, or when a declared reality rule changes the player's body or identity; in that case clothing follows the body, so each person wears whatever their new body was already wearing, and a declared swap or exchange of bodies also exchanges their outfits. Separately, a reality_rules entry may itself state what the player wears or how the player looks; such a rule is already true, so narrate the player that way on every turn it remains in reality_rules rather than treating it as something they still have to do. Unless the input explicitly requests layering, a new garment replaces the previous outfit instead of being worn over it. If the source snapshot explicitly establishes a transformed sex or body, it may create practical disguise or role opportunities without inventing further changes. When authored_template_resolution is provided, treat it as authoritative and never narrate a score, transformation, unlocked exit, or ending beyond its event.
{_REALITY_RULES_INSTRUCTION}
{voice_rule}"""

    def _resolution_system_prompt(
        self,
        language: str,
        *,
        narration_voice: str = NARRATION_VOICE_DEFAULT,
        narration_pronoun: str = NARRATION_PRONOUN_DEFAULT,
        romance: bool = False,
        include_clues: bool = True,
        companion: bool = False,
        outfit_keys: tuple[str, ...] = (),
    ) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        # 選択肢ラベルは行動フレーズなので、人称を載せない旨を併記する
        voice_rule = (
            _narration_voice_instruction(narration_voice, narration_pronoun)
            + " choices[].label must remain a short neutral action phrase with no "
            "narration voice, no pronoun, no speech style, and no first-person or "
            "second-person subject."
        )
        if romance:
            # 対面会話モードは昼夜の枠が無く、選択肢も次の一言にする
            romance_rule = (
                ROMANCE_COMPANION_RESOLUTION_GUIDANCE
                if companion
                else ROMANCE_RESOLUTION_GUIDANCE
            )
            voice_rule = f"{romance_rule}\n{ROMANCE_RECENT_TALK_GUIDANCE}\n{voice_rule}"
            if companion:
                # 3D アバター向けの表情・身振り。語彙は consts/companion_avatar が唯一
                voice_rule = f"{avatar_resolution_instruction()}\n{voice_rule}"
                if outfit_keys:
                    # 衣装差分の切替。キーは手番ごとに組み直す短い番号
                    voice_rule = (
                        f"{avatar_wardrobe_resolution_instruction(outfit_keys)}\n"
                        f"{voice_rule}"
                    )
        else:
            # タイムリミット変更の申告。romance は日数ベースの専用フィールドを使う
            voice_rule = f"{_TIME_LIMIT_ALTER_INSTRUCTION}\n{voice_rule}"
        # 手掛かり抽出OFF時もスキーマは変えず、常に空リストを要求するだけに留める
        if not include_clues:
            voice_rule = (
                "Clue tracking is disabled for this turn: discovered_clues must "
                "always be an empty list.\n" + voice_rule
            )
        avatar_schema = (
            f',"partner_expression":"{"|".join(avatar_expression_keys())}"'
            f',"partner_gesture":"{"|".join(avatar_gesture_keys())}"'
            if romance and companion
            else ""
        )
        if avatar_schema and outfit_keys:
            avatar_schema += f',"partner_outfit":"{"|".join(outfit_keys)}"'
        return f"""You resolve the mechanical outcome of one adventure turn that has already been narrated.
Return one JSON object only, in {response_language}, matching this schema:
{{"choices":[{{"id":"...","label":"..."}},{{"id":"...","label":"..."}},{{"id":"...","label":"..."}}],"discovered_clues":[],"completed_milestones":[],"ending_status":"continue|success|partial|failure","ending_title":null,"ending_summary":null,"bgm":"{"|".join(get_bgm_keys())}","bgm_reason":"..."{avatar_schema}}}
Base every value strictly on the supplied narrative and game state, and never invent events the narrative does not contain. bgm selects the background music category for the scene and must be exactly one of: {get_bgm_prompt_guide()}. current_bgm is the music already playing: keep bgm identical to current_bgm unless the location, scene, mood, or story phase has clearly changed, and never change it for a single line of dialogue, a momentary emotion, or a brief reaction. {BGM_SELECTION_RULES} bgm_reason briefly states, in {response_language}, why that bgm category fits this scene, in 200 characters or fewer. Never output a filename, a path, or any value outside this list. choices must offer exactly three distinct actions the player could take next. discovered_clues must contain only new information the narrative actually revealed, and must not repeat state.clues. completed_milestones must contain milestone ID strings only, never objects, and only when the narrated action actually earns them. Keep ending_status as continue unless the narrative itself concludes the mission, and fill ending_title and ending_summary only in that case. Never decide the player's feelings, consent, or voluntary actions. When authored_template_resolution is provided, treat it as authoritative and never report a score, transformation, or ending beyond its event. Keep the entire response compact.
{_CHOICES_PERSPECTIVE_INSTRUCTION}
{_CHOICES_LENGTH_INSTRUCTION}
{_CHOICES_FRESHNESS_INSTRUCTION}
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
Derive visual_state from previous_visual_state, changing only what the narrative states. Treat required_visual_appearance as an immutable identity signature: copy its sex, hair color, hair length, hairstyle, eye color, and body features exactly into visual_state.appearance, and never replace or supplement those traits unless authored_template_resolution explicitly triggers that change, or reality_rule_declared_this_turn declares a change to the player's own body or identity; in that case rewrite visual_state.appearance to match the declared rule while keeping every unaffected trait, and when the declaration does not concern the player's own body, copy required_visual_appearance unchanged. reality_rules are established facts of this world; keep visual_state, player_tags, and npc_tags consistent with them. The player only puts on, removes, or changes clothing when player_input explicitly chose that action, or when reality_rule_declared_this_turn changes the player's own body or identity; in that case clothing follows the body, so rewrite visual_state.clothing to the outfit that body is actually wearing after the change, and when the declaration swaps or exchanges the player with another character the player now wears the clothing that character was wearing while that character now wears the player's previous clothing, which their entry in main_characters must reflect. Separately, a reality_rules entry may itself state what the player wears or how the player looks; such a rule outranks previous_visual_state, so visual_state.clothing and visual_state.appearance must satisfy it on every turn it remains in reality_rules, not only on the turn it was established. progressive_reality_rules lists the reality rules that describe a gradual, repeated, or per-turn ongoing change (for example, the player's body becoming more feminine every turn); on every turn each such rule advances by one clearly noticeable step, so rewrite the affected traits in visual_state.appearance and player_tags one visible step further advanced than previous_visual_state and required_visual_appearance, never reverting to an earlier stage while the rule remains, and the immutable-identity-signature rule does not protect the traits such a rule changes. Otherwise keep previous_visual_state.clothing unchanged. Unless layering was explicitly requested, a new garment replaces the previous outfit. Keep visual_state concrete enough to illustrate the main characters, their clothing, and the surrounding location. main_characters contains NPCs, never the player.
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
        raw = await _generate_text(system_prompt, user_prompt, text_model=text_model)
        try:
            return _validate_model_json(model, raw, context=context)
        except ValidationError as first_error:
            repaired = await _generate_text(
                system_prompt,
                "Repair the following output into one valid compact JSON object for "
                "the required schema. Return JSON only and do not add new facts. "
                "Respect every string length limit in the schema; when a value is "
                "too long, shorten it by dropping trailing details. "
                f"Fix these validation errors:\n{first_error}\n\n" + raw,
                text_model=text_model,
            )
            try:
                return _validate_model_json(model, repaired, context=context)
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
        include_clues: bool = True,
        companion: bool = False,
        outfit_keys: tuple[str, ...] = (),
    ) -> AdventureResolutionOutput:
        return await self._generate_structured_output(
            AdventureRomanceResolutionOutput if romance else AdventureResolutionOutput,
            system_prompt=self._resolution_system_prompt(
                language,
                narration_voice=narration_voice,
                narration_pronoun=narration_pronoun,
                romance=romance,
                include_clues=include_clues,
                companion=companion,
                outfit_keys=outfit_keys,
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

    async def _generate_fresh_choices(
        self,
        *,
        narrative: str,
        turn_context: dict[str, Any],
        run: AdventureRun,
        narration_voice: str,
        narration_pronoun: str,
        previous_choice_key: tuple[str, ...],
        romance_sim: dict[str, Any] | None = None,
        companion: bool = False,
    ) -> list[dict[str, str]]:
        """再生成専用。既出と同一の3択が返ったら1回だけ引き直す。

        選択肢の再生成はユーザーが「今の3択を変えたい」と押す操作なので、
        同じ内容を返すと操作が空振りになる。往復は最大2回までに抑える。
        romance では専用ボタンと重複する案をターン処理と同じ規則で落とす。
        """
        attempts = 2 if previous_choice_key else 1
        choices: list[dict[str, str]] = []
        for attempt in range(attempts):
            resolution = await self._generate_resolution_output(
                narrative=narrative,
                turn_context=turn_context,
                language=run.language,
                text_model=run.text_model,
                narration_voice=narration_voice,
                narration_pronoun=narration_pronoun,
                romance=romance_sim is not None,
                companion=companion,
            )
            choices = _sanitize_choices(
                [choice.model_dump() for choice in resolution.choices],
                language=run.language,
                source="regenerate_choices.resolution",
            )
            if romance_sim is not None:
                # 重複除去は既出判定より前に行う。除去後に既出と同じ3択へ
                # 収束することがあり、その場合も引き直しの対象にする
                choices = strip_duplicate_action_choices(
                    choices, romance_sim, run.language
                )
            if _choice_label_key(choices) != previous_choice_key:
                return choices
            logger.warning(
                "Adventure choice regeneration returned the previous choices: "
                "run_id=%s attempt=%s labels=%s",
                run.id,
                attempt + 1,
                _choices_preview(choices),
            )
            # 既出案を明示して引き直す。turn_context は呼び出し元と共有しない
            turn_context = {
                **turn_context,
                "task": (
                    "Regenerate next player choices only. The previous attempt "
                    "repeated previous_choices verbatim; produce different ones."
                ),
            }
        return choices

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
        romance_partner: dict[str, Any] | None = None,
    ) -> AdventureVisualOutput:
        authored_scene_tags = str(turn_context.get("authored_scene_tags") or "").strip()
        visual_output = await self._generate_structured_output(
            AdventureVisualOutput,
            system_prompt=self._visual_system_prompt(
                language,
                respect_clothing_layers=respect_clothing_layers,
                romance=romance,
            ),
            user_prompt=_visual_user_payload(
                narrative=narrative,
                turn_context=turn_context,
                previous_visual=previous_visual,
                appearance_lock=appearance_lock,
                previous_image_tags=previous_image_tags,
                romance_partner=romance_partner,
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
        draft: dict[str, Any] | None = None,
        companion: bool = False,
    ) -> str:
        response_language = "Japanese" if language == "ja" else "English"
        if preset == "romance":
            romance_turns = clamp_romance_max_turns(max_turns)
            days = romance_turns // ROMANCE_SLOTS_PER_DAY
            # 対面会話モードは日数でなくターン数(1ターン=1往復)で尺を示す
            horizon = (
                f"a romance simulation of {romance_turns} turns, where each turn is "
                "one face-to-face exchange with the partner and there are no days "
                "or times of day,"
                if companion
                else f"a {days}-day romance simulation"
            )
            within = (
                f"within {romance_turns} turns" if companion else f"within {days} days"
            )
            prompt = f"""You design a concise setup for {horizon} in which the player aims to start dating one partner character.
Return one JSON object only, in {response_language}, matching this schema:
{{"setting":"...","objective":"...","constraints":["...","..."]}}
The constraints array must contain between 1 and 4 items.
The partner is the character shown in source_snapshot; keep their appearance and situation consistent with it. source_snapshot deliberately contains no name for the partner: invent a fitting new name from their appearance and situation, and use that name in the objective. Never name the partner after the player. The player is a separate person courting that partner; never treat the snapshot character as the player. The setting describes where the player and the partner cross paths in daily life. The objective must name the partner and state that the player starts dating them {within}. Constraints must create romantic complications such as schedules, shyness, or circumstances, without dictating the player's feelings, consent, memories, bodily sensations, or voluntary actions. Do not introduce another body transformation or assign physical traits that conflict with source_snapshot.appearance."""
            if draft:
                prompt += _SETUP_DRAFT_GUIDANCE + _SETUP_DRAFT_ROMANCE_GUIDANCE
            return prompt
        turns = clamp_generated_max_turns(max_turns)
        prompt = f"""You design a concise setup for a {turns}-turn objective-based adventure game.
Return one JSON object only, in {response_language}, matching this schema:
{{"setting":"...","objective":"...","constraints":["...","..."]}}
The constraints array must contain between 1 and 4 items.
The objective must name a concrete target and an observable end condition that can be judged as achieved or failed within {turns} turns. Scale the scope of the objective to that turn budget: a longer budget should leave room for searching for clues and scouting the surroundings, not add unrelated sub-goals. Do not use vague goals such as succeed, investigate the situation, or reach the objective. The setting, objective, and constraints must fit the selected mission preset and supplied character snapshot. Constraints must create actionable complications without dictating the player's feelings, consent, memories, bodily sensations, or voluntary actions. Do not introduce another body transformation or assign physical traits that conflict with source_snapshot.appearance. For a disguise mission, generate the transformed person's name and role while keeping the supplied appearance exactly; the player does not have that person's memories, relationships, habits, skills, credentials, passwords, or authentication information."""
        if draft:
            prompt += _SETUP_DRAFT_GUIDANCE
        return prompt

    async def _generate_setup_output(
        self,
        *,
        prompt: str,
        language: str,
        text_model: str,
        max_turns: int = ADVENTURE_TURNS_DEFAULT,
        preset: str = "",
        draft: dict[str, Any] | None = None,
        companion: bool = False,
    ) -> AdventureSetupOutput:
        system_prompt = self._setup_system_prompt(
            language, max_turns, preset, draft, companion=companion
        )
        raw = await _generate_text(system_prompt, prompt, text_model=text_model)
        try:
            return _validate_model_json(AdventureSetupOutput, raw)
        except ValidationError as first_error:
            repair_prompt = (
                "Repair the following output into valid JSON for the required schema. "
                "Keep the same scenario and do not add new scenario facts. "
                "Fix these validation errors:\n"
                f"{first_error}\n\nOutput to repair:\n{raw}"
            )
            repaired = await _generate_text(
                system_prompt, repair_prompt, text_model=text_model
            )
            try:
                return _validate_model_json(AdventureSetupOutput, repaired)
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
        source_session_id: str | None,
        source_history_id: str | None,
        preset: str,
        source_prompt_expander_entry_id: str | None = None,
        max_turns: int = ADVENTURE_TURNS_DEFAULT,
        draft_setting: str = "",
        draft_objective: str = "",
        draft_constraints: Sequence[str] | None = None,
        companion_mode: bool = False,
    ) -> dict[str, Any]:
        preset_config = PRESETS.get(preset)
        if preset_config is None:
            raise AdventureError("invalid_preset", "シナリオ種別が不正です")
        turn_budget = (
            clamp_romance_max_turns(max_turns)
            if preset == "romance"
            else clamp_generated_max_turns(max_turns)
        )
        # ユーザーが入力済みの項目だけを下書きとして渡す。空なら従来どおり
        # キー自体を出さず、LLM にも下書き指示を付けない
        user_draft = _build_setup_user_draft(
            draft_setting, draft_objective, draft_constraints
        )

        snapshot, _, appearance, _ = await self._build_snapshot(
            source_session_id,
            source_history_id,
            source_prompt_expander_entry_id=source_prompt_expander_entry_id,
        )
        user_settings = await session_store.get_user_settings()
        language = str(user_settings.get("language") or "ja")
        text_model = str(
            user_settings.get("novelai_text_model") or settings.novelai_text_model
        )
        prompt_payload: dict[str, Any] = {
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
        }
        if user_draft:
            prompt_payload["user_draft"] = user_draft
        companion = preset == "romance" and bool(companion_mode)
        if companion:
            prompt_payload["companion_mode"] = True
        prompt = json.dumps(prompt_payload, ensure_ascii=False)
        tracker = _CostTracker()
        _cost_tracker.set(tracker)
        generated = await self._generate_setup_output(
            prompt=prompt,
            language=language,
            text_model=text_model,
            max_turns=turn_budget,
            preset=preset,
            draft=user_draft or None,
            companion=companion,
        )
        payload = generated.model_dump()
        if tracker.total_usd > 0:
            payload["cost_usd"] = tracker.total_usd
        return payload

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
        source_session_id: str | None,
        source_history_id: str | None,
        preset: str,
        source_prompt_expander_entry_id: str | None = None,
        custom_setup: str = "",
        scenario_setting: str = "",
        scenario_objective: str = "",
        scenario_constraints: list[str] | None = None,
        scenario_template_id: str | None = None,
        replay_run_id: str | None = None,
        scenario_max_turns: int = ADVENTURE_TURNS_DEFAULT,
        narration_voice: str = NARRATION_VOICE_DEFAULT,
        narration_pronoun: str = NARRATION_PRONOUN_DEFAULT,
        player_speech_style: str = SPEECH_STYLE_DEFAULT,
        player_speech_custom: str = "",
        use_precise_reference: bool = False,
        enable_composite_scene: bool = False,
        respect_clothing_layers: bool = False,
        romance_player_character_id: str | None = None,
        romance_player_session_id: str | None = None,
        romance_player_history_id: str | None = None,
        romance_player_name: str = "",
        romance_partner_speech_style: str = "",
        image_model: str | None = None,
        companion_mode: bool = False,
        companion_avatar_id: str | None = None,
    ) -> dict[str, Any]:
        # Run作成全体(セットアップLLM・開幕画像)のAPI料金を集計して応答へ載せる
        tracker = _CostTracker()
        _cost_tracker.set(tracker)
        # 対面会話モードの 3D アバター。LLM や画像生成に入る前に存在確認する
        companion_avatar = await _validate_companion_avatar(companion_avatar_id)
        # この run 専用の NovelAI 画像モデル上書き。未指定・未知名は
        # グローバル設定(nsfw_mode 別のユーザー設定)に従う
        image_model_override = (
            image_model if image_model in NOVELAI_IMAGE_MODELS else None
        )
        narration_voice = normalize_narration_voice(narration_voice)
        narration_pronoun = normalize_narration_pronoun(narration_pronoun)
        player_speech_style = normalize_speech_style(player_speech_style)
        player_speech_custom = normalize_speech_custom(player_speech_custom)
        romance_partner_speech_style = normalize_partner_speech_style(
            romance_partner_speech_style
        )
        # 主人公の呼び名の上書き。空ならテンプレート名・セッション名へ倒す
        player_name_override = normalize_player_name(romance_player_name)
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
            if preset == "romance":
                # 同一シナリオ・新規simのリプレイ。攻略対象の素材と主人公の選択は
                # 元runから引き継ぎ、相手プロフィール・ギフトカタログ・隠し好みは
                # 後段の共通処理で毎回再生成される(意図した仕様)
                replay_pe_entry_id = getattr(
                    replay_run, "source_prompt_expander_entry_id", None
                )
                if replay_pe_entry_id:
                    source_prompt_expander_entry_id = replay_pe_entry_id
                    source_session_id = None
                    source_history_id = None
                else:
                    source_session_id = (
                        replay_run.source_session_id or source_session_id
                    )
                    source_history_id = replay_run.source_history_id
                    source_prompt_expander_entry_id = None
                if not (romance_player_character_id or romance_player_session_id):
                    (
                        romance_player_character_id,
                        romance_player_session_id,
                        romance_player_history_id,
                    ) = _romance_replay_player_selection(replay_state)
                    # 主人公の選択ごと引き継ぐときは呼び名も元 run に揃える
                    if not player_name_override:
                        player_name_override = _romance_replay_player_name(replay_state)
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
        ) = await self._build_snapshot(
            source_session_id,
            source_history_id,
            source_prompt_expander_entry_id=source_prompt_expander_entry_id,
        )
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
        # run 単位の上書きがあれば開幕画像から一貫してそのモデルを使う
        image_model = image_model_override or resolve_user_image_model(
            user_settings, nsfw_mode
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
            if effective_preset == "romance":
                # 日数導出(max_turns//2)が旧runの異常値で壊れないよう境界へ丸める
                max_turns = clamp_romance_max_turns(max_turns)
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
            # セットアップで呼び名が指定されていればそちらを優先する
            if player_name_override:
                romance_player_name = player_name_override
            romance_days = max_turns // ROMANCE_SLOTS_PER_DAY
            romance_setup = await self._generate_structured_output(
                RomanceSetupOutput,
                system_prompt=romance_setup_system_prompt(
                    language,
                    romance_days,
                    companion=bool(companion_mode),
                    turns=max_turns,
                ),
                user_prompt=json.dumps(
                    {
                        "task": "Design the romance simulation setup.",
                        "days": romance_days,
                        "turns": max_turns,
                        "companion_mode": bool(companion_mode),
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
            # ユーザーがセットアップで書いた口調があれば LLM 生成値より優先する
            romance_partner_speech_style = (
                romance_partner_speech_style
                or normalize_partner_speech_style(romance_setup.partner_speech_style)
            )

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
                    "partner_speech_style": romance_partner_speech_style,
                    "partner_appearance": romance_partner_appearance,
                    "relationship_origin": romance_setup.relationship_origin,
                    "job_name": romance_setup.job_name,
                    "player_name": romance_player_name,
                    # 対面会話モードには昼夜の枠が無く、尺はターン数で示す
                    **(
                        {"total_turns": max_turns, "companion_mode": True}
                        if companion_mode
                        else {
                            "total_days": max_turns // ROMANCE_SLOTS_PER_DAY,
                            "opening_slot": {"day": 1, "slot": "day"},
                        }
                    ),
                }
                if romance_setup is not None
                else None,
            },
            ensure_ascii=False,
        )
        # 対面会話モードは romance 専用。開幕本文も台本形式で書かせる
        companion_mode = bool(companion_mode) and romance_setup is not None
        opening = await self._generate_director_output(
            prompt=prompt,
            language=language,
            text_model=text_model,
            narration_voice=narration_voice,
            narration_pronoun=narration_pronoun,
            speech_rule=_speech_style_instruction(
                player_speech_style,
                player_speech_custom,
                partner_style=romance_partner_speech_style,
                partner_name=romance_setup.partner_name if romance_setup else "",
                player_name=romance_player_name,
            ),
            romance=romance_setup is not None,
            script_names=romance_script_names(
                {
                    "partner_name": romance_setup.partner_name,
                    "player_name": romance_player_name,
                },
                language,
            )
            if companion_mode and romance_setup is not None
            else None,
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
            # 開始時の外見。現実改変で appearance_lock が動いたかの判定に使い、
            # 乖離後は元画像を参照に使わない(_appearance_diverged)
            "initial_appearance_lock": appearance,
            "scenario_template_id": scenario_template_id,
            "replayed_from_run_id": replay_run_id,
            "scenario_capabilities": start_state,
            "visual_state": opening.visual_state.model_dump(),
            "opening_narrative": opening.narrative,
            "opening_image_path": str(initial_path),
            "choices": opening_choices,
            # BGM は semantic key で保持し、ファイル解決はフロントエンドが担う。
            # 理由はキーが有効なときだけ保持し、キーと理由のペアを崩さない
            "bgm": opening.bgm or get_bgm_default(),
            "opening_bgm": opening.bgm or get_bgm_default(),
            "bgm_reason": opening.bgm_reason if opening.bgm else None,
            "opening_bgm_reason": opening.bgm_reason if opening.bgm else None,
            # 精密参照はユーザー明示ONのみ。未設定・旧runはOFF扱い。
            "use_precise_reference": bool(use_precise_reference),
            # 合成シーン生成はユーザー明示ONのみ。OFF時は中央の立ち絵のみ更新
            "enable_composite_scene": bool(enable_composite_scene),
            # 衣装レイヤー考慮。ONなら外衣に覆われた下着を画像タグから外す
            "respect_clothing_layers": bool(respect_clothing_layers),
            # NovelAI 画像モデルの run 単位上書き。空ならグローバル設定に従う
            "image_model_override": image_model_override,
            # 語りの人称。旧runは既定の二人称として扱う
            "narration_voice": narration_voice,
            "narration_pronoun": narration_pronoun,
            # 主人公のセリフの口調。旧runは既定の丁寧語として扱う
            "player_speech_style": player_speech_style,
            "player_speech_custom": player_speech_custom,
            # 対面会話モード(romance 専用)。ONなら手番の画像は背景+攻略対象だけ
            "companion_mode": companion_mode,
            # 対面会話モードで攻略対象の立ち絵の代わりに描く VRM の登録 ID
            "companion_avatar_id": companion_avatar,
        }
        if romance_setup is not None:
            state["sim"] = init_romance_state(
                romance_setup,
                max_turns,
                partner_appearance=romance_partner_appearance,
                player_name=romance_player_name,
                player_character_id=romance_player_ref,
                player_history_id=str(romance_player_history_id or "")
                if romance_player_session_id
                else "",
                partner_speech_style=romance_partner_speech_style,
            )
            # 攻略対象の開始時の外見。主人公側と同じく乖離判定にだけ使う
            state["initial_partner_appearance"] = romance_partner_appearance
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
            source_prompt_expander_entry_id=source_prompt_expander_entry_id,
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
            image_provider=_image_provider(),
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
        payload = await self.get_run(run_id)
        if tracker.total_usd > 0:
            payload["cost_usd"] = tracker.total_usd
        return payload

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
        await self._drop_missing_companion_avatar(run)
        turns = sorted(run.turns, key=lambda item: item.turn_number)
        return self._serialize_run(run, turns)

    async def _drop_missing_companion_avatar(self, run: AdventureRun) -> None:
        """登録が消えた 3D アバターの割り当てを run から外す(自己修復)。

        アバター削除時は detach_companion_avatar で外すが、それ以前に削除された
        run や手番中に削除された run には残り得る。残すと run を開くたびに
        ファイル配信が 404 になり 3D 表示が失敗するため、開く時点で存在を
        確かめて外す。
        """
        state = _json_load(run.state_json, {})
        avatar_id = _companion_avatar_id(run, state)
        if not avatar_id:
            return
        async with async_session_factory() as db:
            if await avatar_exists(db, avatar_id):
                return
        logger.warning(
            "Companion avatar %s assigned to run %s no longer exists; detaching",
            avatar_id,
            run.id,
        )
        state.pop("companion_avatar_id", None)
        run.state_json = json.dumps(state, ensure_ascii=False)
        async with self._persist_locks[run.id], async_session_factory() as db:
            persisted = await db.get(AdventureRun, run.id)
            if persisted is None:
                return
            persisted_state = _json_load(persisted.state_json, {})
            if str(persisted_state.get("companion_avatar_id") or "") != avatar_id:
                return
            persisted_state.pop("companion_avatar_id", None)
            persisted.state_json = json.dumps(persisted_state, ensure_ascii=False)
            persisted.updated_at = datetime.now()
            await db.commit()

    async def _companion_outfit_options(
        self, run: AdventureRun, state: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """表示中の 3D モデルと同じキャラクターとして登録された衣装差分。

        対面会話モードでモデルを表示中、かつ差分が 2 件以上あるときだけ返す。
        LLM には手番ごとに組み直す短いキー("1","2",…)で選ばせ、ID は見せない。
        取得に失敗しても手番は止めない(その手番は着替えが起きないだけ)。
        """
        if run.preset != "romance" or not state.get("companion_mode"):
            return []
        avatar_id = _companion_avatar_id(run, state)
        if not avatar_id:
            return []
        try:
            async with async_session_factory() as db:
                variants = await list_avatar_variants(db, avatar_id)
        except Exception as error:  # noqa: BLE001
            logger.warning(
                "Failed to load outfit variants for avatar %s: %s", avatar_id, error
            )
            return []
        if len(variants) < 2:
            return []
        return [
            {
                "key": str(index),
                "id": model.id,
                "label": avatar_variant_label(model),
                "current": model.id == avatar_id,
            }
            for index, model in enumerate(variants, start=1)
        ]

    async def detach_companion_avatar(self, avatar_id: str) -> int:
        """削除したアバターの割り当てを全 run の state から外し、件数を返す。

        残したままだと run を開くたびに削除済み ID のファイル配信が 404 になる。
        state_json に ID を含む run だけを候補にし、手番中の書き込みと競合
        しないよう run ごとの persist ロック下で最新 state を読み直して書き戻す。
        """
        value = str(avatar_id or "").strip()
        if not value:
            return 0
        async with async_session_factory() as db:
            run_ids = list(
                (
                    await db.execute(
                        select(AdventureRun.id).where(
                            AdventureRun.state_json.contains(value)
                        )
                    )
                )
                .scalars()
                .all()
            )
        detached = 0
        for run_id in run_ids:
            async with self._persist_locks[run_id], async_session_factory() as db:
                persisted = await db.get(AdventureRun, run_id)
                if persisted is None:
                    continue
                state = _json_load(persisted.state_json, {})
                if str(state.get("companion_avatar_id") or "").strip() != value:
                    continue
                state.pop("companion_avatar_id", None)
                persisted.state_json = json.dumps(state, ensure_ascii=False)
                persisted.updated_at = datetime.now()
                await db.commit()
                detached += 1
        if detached:
            logger.info(
                "Detached deleted avatar %s from %d adventure run(s)", value, detached
            )
        return detached

    async def regenerate_choices(self, run_id: str) -> dict[str, Any]:
        """現在場面の選択肢だけを再生成する。手番・物語・手掛かりは変更しない。"""
        tracker = _CostTracker()
        _cost_tracker.set(tracker)
        async with self._run_locks[run_id]:
            run = await self.get_run_orm(run_id, with_turns=True)
            state = _json_load(run.state_json, {})
            if run.status != "active" and not state.get("epilogue"):
                raise AdventureError("run_completed", "このシナリオは終了しています")

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
                # 現在の選択肢を state ごと渡すと LLM が書き写して
                # 「再生成しても変わらない」ため、避けるべき既出案として渡す
                previous_choice_labels = _previous_choice_labels(state)
                previous_choice_key = _choice_label_key(state.get("choices"))
                # romance ではターン処理と同じ sim を渡し、専用ボタン相当の
                # 選択肢(告白・プレゼント・バイト・属性付与)を除去する
                romance_sim = (
                    state.get("sim")
                    if run.preset == "romance" and isinstance(state.get("sim"), dict)
                    else None
                )
                turn_context = {
                    "task": "Regenerate next player choices only.",
                    "preset": run.preset,
                    "scenario_guidance": scenario_guidance,
                    "authored_template_resolution": template_resolution,
                    "objective": run.objective,
                    "max_turns": run.max_turns,
                    "next_turn": run.turn_count + 1,
                    "state": _lean_state_for_llm(state),
                    "recent_turns": previous_turns[-7:],
                    "player_input": last_input,
                    "previous_choices": previous_choice_labels,
                    "required_visual_appearance": appearance_lock,
                    "reality_rules": list(state.get("reality_rules", [])),
                }
                companion = romance_sim is not None and bool(
                    state.get("companion_mode")
                )
                if romance_sim is not None and not companion:
                    # 再生成される選択肢は「これから行動する枠」(turn_count+1)向け。
                    # 対面会話モードには昼夜の枠が無い
                    next_day, next_slot = romance_day_slot(run.turn_count + 1)
                    turn_context["romance_next_slot"] = {
                        "day": next_day,
                        "slot": next_slot,
                    }
                if companion:
                    turn_context["companion_mode"] = True
                try:
                    choices = await self._generate_fresh_choices(
                        narrative=narrative,
                        turn_context=turn_context,
                        run=run,
                        narration_voice=narration_voice,
                        narration_pronoun=narration_pronoun,
                        previous_choice_key=previous_choice_key,
                        romance_sim=romance_sim,
                        companion=companion,
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

            payload: dict[str, Any] = {"choices": choices}
            if tracker.total_usd > 0:
                payload["cost_usd"] = tracker.total_usd
            return payload

    async def stream_talk(
        self, *, run_id: str, user_input: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """トークモード: 手番を消費せずに攻略対象と会話する(romance 専用)。

        turn_count・status・sim・AdventureTurn には一切触れず、state_json の
        talk_log だけを更新する。会話は次の手番へ recent_talk として渡される。
        """
        tracker = _CostTracker()
        _cost_tracker.set(tracker)
        async with self._run_locks[run_id]:
            run = await self.get_run_orm(run_id, with_turns=True)
            state = _json_load(run.state_json, {})
            sim = state.get("sim") if run.preset == "romance" else None
            if not isinstance(sim, dict):
                raise AdventureError(
                    "talk_unavailable", "トークは恋愛シミュレーションでのみ使えます"
                )
            if run.status != "active" and not state.get("epilogue"):
                raise AdventureError("run_completed", "このシナリオは終了しています")
            message = normalize_talk_input(user_input)
            if not message:
                raise AdventureError("invalid_input", "メッセージが空です")

            partner_name, player_name = romance_script_names(sim, run.language)
            turns = sorted(run.turns, key=lambda item: item.turn_number)
            epilogue = bool(state.get("epilogue"))
            visual_state = state.get("visual_state", {})
            # 人物設定・関係性・場面は system prompt の context として渡し、
            # 会話そのものは過去ログを user/assistant メッセージ列、今回の
            # 発言を最後の user メッセージにして「会話の続き」として答えさせる。
            # (JSON の一項目に履歴を埋めるだけでは直前のやり取りを踏まえない)
            context = {
                "task": (
                    "Reply as the partner in a free chat between scenes. "
                    "Nothing in the story advances."
                ),
                "partner": {
                    "name": partner_name,
                    "profile": str(sim.get("partner_profile") or ""),
                    "speech_style": str(sim.get("partner_speech_style") or ""),
                    "appearance": str(sim.get("partner_appearance") or ""),
                },
                "player_name": player_name,
                "relationship": talk_relationship_context(
                    sim, state, run.turn_count, epilogue=epilogue
                ),
                "hidden_preferences": sim.get("hidden_preferences"),
                "current_scene": _sanitize_visual_state(visual_state),
                "reality_rules": list(state.get("reality_rules", [])),
                "recent_scenes": _talk_recent_scenes(turns),
            }
            history = talk_history_messages(state, run.turn_count)
            companion = bool(state.get("companion_mode"))
            yield {"event": "status", "data": {"phase": "talk"}}
            reply = ""
            # 対面会話モードでは先頭ヘッダ行 [expression=.. gesture=..] を
            # 表示前に剥がすため、1 行分だけ溜めてから流す
            header = _TalkHeaderBuffer(enabled=companion)
            async for chunk in llm_service.generate_feeling_stream(
                romance_talk_system_prompt(
                    run.language,
                    partner_name=partner_name,
                    player_name=player_name,
                    speech_rule=_speech_rule_from_state(state),
                    companion=companion,
                    context=context,
                ),
                message,
                provider_override=_text_provider(),
                novelai_model_override=run.text_model,
                usage_callback=_record_cost,
                history=history,
            ):
                if not chunk:
                    continue
                reply += chunk
                for visible in header.feed(chunk):
                    yield {"event": "talk_chunk", "data": {"chunk": visible}}
            for visible in header.flush():
                yield {"event": "talk_chunk", "data": {"chunk": visible}}
            talk_expression, talk_gesture, _ = parse_talk_header(
                _strip_json_fence(reply)
            )
            reply = normalize_talk_reply(_strip_json_fence(reply), partner_name)
            if not reply:
                raise AdventureError(
                    "invalid_model_output",
                    "返答を解析できませんでした。もう一度お試しください",
                )
            user_entry = append_talk_entry(
                state, role="user", text=message, after_turn=run.turn_count
            )
            partner_entry = append_talk_entry(
                state,
                role="partner",
                text=reply,
                after_turn=run.turn_count,
                expression=talk_expression,
                gesture=talk_gesture,
            )
            async with self._persist_locks[run_id], async_session_factory() as db:
                persisted = await db.get(AdventureRun, run.id)
                if persisted is None:
                    raise AdventureError(
                        "run_not_found", "アドベンチャーが見つかりません"
                    )
                # 手番中の生成と競合しないよう、talk_log だけを最新 state へ書き戻す
                persisted_state = _json_load(persisted.state_json, {})
                persisted_state["talk_log"] = state.get("talk_log", [])
                persisted.state_json = json.dumps(persisted_state, ensure_ascii=False)
                persisted.updated_at = datetime.now()
                await db.commit()
            yield {
                "event": "talk_done",
                "data": {
                    "user_entry": user_entry,
                    "partner_entry": partner_entry,
                    "turn_count": run.turn_count,
                },
            }
            if tracker.total_usd > 0:
                yield {"event": "cost", "data": {"cost_usd": tracker.total_usd}}
            yield {"event": "complete", "data": {"status": run.status}}

    async def delete_run(self, run_id: str) -> None:
        await self.get_run_orm(run_id)
        async with async_session_factory() as db:
            await db.execute(delete(AdventureRun).where(AdventureRun.id == run_id))
            await db.commit()
        shutil.rmtree(self._images_dir / run_id, ignore_errors=True)

    # 巻き戻し時にユーザー設定として現在値を引き継ぐ state キー。
    # ターン後に変えた画像設定や人称までは巻き戻さない
    _REWIND_KEEP_KEYS = (
        "use_precise_reference",
        "enable_composite_scene",
        "respect_clothing_layers",
        "narration_voice",
        "narration_pronoun",
        # 口調は物語の出来事ではなく設定なので、巻き戻しても最新の選択を残す
        "player_speech_style",
        "player_speech_custom",
        # 対面会話モードも表示設定。トークログは巻き戻し先のスナップショットに従う
        "companion_mode",
        "companion_avatar_id",
    )

    async def rewind_to_turn(self, run_id: str, turn_number: int) -> dict[str, Any]:
        """指定手番の完了時点まで巻き戻し、それ以降のターンを削除する。

        state_delta_json はターン適用後の全 state のスナップショットなので、
        逆適用は不要で代入だけで復元できる。終了済み run にも許可する
        (エンド前へ戻して結末を変えるのが主要ユースケース)。
        """
        async with self._run_locks[run_id]:
            run = await self.get_run_orm(run_id, with_turns=True)
            target = int(turn_number)
            if target == run.turn_count:
                # 二度押し・リトライは no-op 成功として現状を返す
                turns = sorted(run.turns, key=lambda item: item.turn_number)
                return self._serialize_run(run, turns)
            if target < 0 or target > run.turn_count:
                raise AdventureError(
                    "invalid_turn_number", "巻き戻し先の手番が不正です"
                )
            current_state = _json_load(run.state_json, {})
            if target == 0:
                opening = _json_load(getattr(run, "opening_state_json", None), {})
                if not isinstance(opening.get("state"), dict):
                    raise AdventureError(
                        "opening_state_unavailable",
                        "このシナリオは開始時点への巻き戻しに対応していません",
                    )
                restored_state = opening["state"]
                restored_image_path = str(
                    opening.get("current_image_path") or run.current_image_path
                )
                restored_portrait_path = opening.get("portrait_image_path")
                restored_background_path = opening.get("background_image_path")
            else:
                target_turn = next(
                    (item for item in run.turns if item.turn_number == target),
                    None,
                )
                if target_turn is None:
                    raise AdventureError(
                        "invalid_turn_number", "巻き戻し先の手番が見つかりません"
                    )
                restored_state = _json_load(target_turn.state_delta_json, {})
                restored_image_path = str(
                    target_turn.image_path or run.current_image_path
                )
                # 立ち絵は旧 run で欠落しうるため、対象手番から遡って補う
                restored_portrait_path = target_turn.portrait_image_path
                if not restored_portrait_path:
                    for item in sorted(
                        run.turns, key=lambda item: item.turn_number, reverse=True
                    ):
                        if item.turn_number < target and item.portrait_image_path:
                            restored_portrait_path = item.portrait_image_path
                            break
                # 背景キーは背景を作り直したターン以降にしか無い。欠落時は現状維持
                restored_background_path = restored_state.get(
                    "background_image_path"
                ) or getattr(run, "background_image_path", None)
            # 画像・人称のユーザー設定は現在値を引き継ぐ
            for key in self._REWIND_KEEP_KEYS:
                if key in current_state:
                    restored_state[key] = current_state[key]
            final_status = str(restored_state.get("final_status") or "")
            if final_status:
                # その手番時点で既に終了していた(エピローグ中の手番など)
                restored_status = final_status
                restored_ending_title = restored_state.get(
                    "final_ending_title"
                ) or _default_ending_title(run.preset, final_status)
                restored_ending_summary = restored_state.get("ending_summary")
            else:
                restored_status = "active"
                restored_ending_title = None
                restored_ending_summary = None
                for key in ("ending_summary", "epilogue"):
                    restored_state.pop(key, None)
            async with async_session_factory() as db:
                persisted = await db.get(AdventureRun, run_id)
                if persisted is None:
                    raise AdventureError(
                        "run_not_found", "アドベンチャーが見つかりません"
                    )
                await db.execute(
                    delete(AdventureTurn).where(
                        AdventureTurn.run_id == run_id,
                        AdventureTurn.turn_number > target,
                    )
                )
                persisted.state_json = json.dumps(restored_state, ensure_ascii=False)
                persisted.turn_count = target
                persisted.status = restored_status
                persisted.ending_title = restored_ending_title
                persisted.ending_summary = restored_ending_summary
                persisted.current_image_path = restored_image_path
                persisted.portrait_image_path = restored_portrait_path
                persisted.background_image_path = restored_background_path
                persisted.updated_at = datetime.now()
                await db.commit()
            # 削除ターンの画像はコミット後に best-effort で片付ける。
            # background-* はキャッシュ共有、turn-0-*/initial* は開幕解決に
            # 使われるため対象にしない
            run_dir = self._images_dir / run_id
            for prefix in ("turn", "portrait", "partner"):
                for path in run_dir.glob(f"{prefix}-*-*.png"):
                    try:
                        removed_turn = int(path.name.split("-")[1])
                    except (IndexError, ValueError):
                        continue
                    if removed_turn > target:
                        try:
                            path.unlink()
                        except OSError:
                            logger.warning(
                                "Adventure rewind could not remove image: %s", path
                            )
            refreshed = await self.get_run_orm(run_id, with_turns=True)
            turns = sorted(refreshed.turns, key=lambda item: item.turn_number)
            return self._serialize_run(refreshed, turns)

    async def start_epilogue(self, run_id: str) -> dict[str, Any]:
        """終了済み run をエピローグ(継続プレイ)へ移行する。

        run のステータスとリザルトは終了のまま保ち、以降のターン操作だけを
        許可する。既にエピローグなら no-op 成功。
        """
        async with self._run_locks[run_id]:
            run = await self.get_run_orm(run_id, with_turns=True)
            if run.status == "active":
                raise AdventureError(
                    "run_not_completed", "このシナリオはまだ終了していません"
                )
            state = _json_load(run.state_json, {})
            if not state.get("epilogue"):
                state["epilogue"] = True
                async with async_session_factory() as db:
                    persisted = await db.get(AdventureRun, run_id)
                    if persisted is None:
                        raise AdventureError(
                            "run_not_found", "アドベンチャーが見つかりません"
                        )
                    persisted.state_json = json.dumps(state, ensure_ascii=False)
                    persisted.updated_at = datetime.now()
                    await db.commit()
                run = await self.get_run_orm(run_id, with_turns=True)
            turns = sorted(run.turns, key=lambda item: item.turn_number)
            return self._serialize_run(run, turns)

    def _merge_output(
        self,
        run: AdventureRun,
        output: AdventureDirectorOutput,
        turn_number: int,
        state_override: dict[str, Any] | None = None,
        epilogue: bool = False,
    ) -> tuple[dict[str, Any], str, bool, bool]:
        state = (
            state_override
            if state_override is not None
            else _json_load(run.state_json, {})
        )
        valid_ids = {item["id"] for item in state.get("milestones", [])}
        previously_completed = set(state.get("completed_milestones", []))
        completed = set(previously_completed)
        completed.update(
            item for item in output.completed_milestones if item in valid_ids
        )
        clues = list(
            dict.fromkeys([*state.get("clues", []), *output.discovered_clues])
        )[:20]
        previous_visual = state.get("visual_state", {})
        # stream_turn は _merge_output より前に visual_producer 内で
        # _apply_appearance_lock を実行済み。reality_alter ターンでは
        # そこで state["appearance_lock"] が更新済みのため、この再適用は
        # 新ロックに対する no-op になる(順序依存に注意)
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
        if output.bgm:
            # None は「据え置き」で、前ターンの BGM と理由を維持する。
            # 理由はキー更新時だけ書き換え、キーと理由のペアを崩さない
            state["bgm"] = output.bgm
            state["bgm_reason"] = output.bgm_reason
        # 表情・身振りは手番ごとの表示用出力。据え置きせず毎手番上書きする
        state["partner_expression"] = output.partner_expression
        state["partner_gesture"] = output.partner_gesture

        if epilogue:
            # エピローグでは LLM 申告や max_turns 到達で run を終わらせない。
            # 成功エンド済み run は「全マイルストーン達成」が恒久的に真のため、
            # 「新規に全達成へ遷移したとき」だけ成功への逆転として扱う
            newly_complete = (
                bool(valid_ids)
                and completed == valid_ids
                and previously_completed != valid_ids
            )
            status = "success" if newly_complete else "continue"
        else:
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
        if not epilogue or status != "continue":
            # エピローグの continue ターンで None を書くと確定済みリザルトが消える
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
            # 本メソッドは非SSE版で現在未使用。エピローグ(継続プレイ)には
            # 対応していないため、終了済み run は従来どおり拒否する
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
                    "progressive_reality_rules": _progressive_reality_rules(
                        state.get("reality_rules", [])
                    ),
                },
                ensure_ascii=False,
            )
            output = await self._generate_director_output(
                prompt=prompt,
                language=run.language,
                text_model=run.text_model,
                narration_voice=narration_voice,
                narration_pronoun=narration_pronoun,
                speech_rule=_speech_rule_from_state(state),
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
        generate_portrait: bool = True,
        generate_partner_portrait: bool = True,
        generate_clues: bool = True,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """ナラティブを逐次配信し、手がかり抽出と画像生成を並列実行する。"""
        # このターンで発生したAPI料金(OpenRouter)を集計し、終端でcostイベントを送る
        cost_tracker = _CostTracker()
        _cost_tracker.set(cost_tracker)
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
            state = _json_load(run.state_json, {})
            epilogue = bool(state.get("epilogue"))
            if run.status != "active" and not epilogue:
                raise AdventureError("run_completed", "このシナリオは終了しています")

            # 開始時外見のバックフィル。旧runは「今の姿」を基準に採用するため
            # 過去の改変までは遡れないが、以後の改変は正しく追える。手番0の
            # スナップショットにも載るよう opening_state_json 保存の前で行う
            if "initial_appearance_lock" not in state:
                state["initial_appearance_lock"] = str(
                    state.get("appearance_lock") or ""
                )
            sim_backfill = state.get("sim")
            if (
                isinstance(sim_backfill, dict)
                and "initial_partner_appearance" not in state
            ):
                state["initial_partner_appearance"] = str(
                    sim_backfill.get("partner_appearance") or ""
                )

            # 手番0への巻き戻し用に、最初のターン処理前の状態を保存する。
            # 旧runの初回ターンでも拾えるようここで行う(create_run 直後とは
            # 開幕画像生成の分だけ state が違うため、この時点の値が正)
            if run.turn_count == 0 and not run.opening_state_json:
                run.opening_state_json = json.dumps(
                    {
                        "state": state,
                        "current_image_path": run.current_image_path,
                        "portrait_image_path": run.portrait_image_path,
                        "background_image_path": run.background_image_path,
                    },
                    ensure_ascii=False,
                )
                async with async_session_factory() as db:
                    persisted_run = await db.get(AdventureRun, run.id)
                    if persisted_run is not None:
                        persisted_run.opening_state_json = run.opening_state_json
                        await db.commit()

            # 衣装差分(同じキャラクターの VRM)があれば、物語と判定の両方へ渡す
            outfit_options = await self._companion_outfit_options(run, state)
            contexts = self._build_turn_contexts(
                run,
                state,
                user_input=user_input,
                input_kind=input_kind,
                gift_id=gift_id,
                epilogue=epilogue,
                outfit_options=outfit_options,
            )
            input_kind = contexts.input_kind
            narration_voice = contexts.narration_voice
            narration_pronoun = contexts.narration_pronoun
            appearance_update_allowed = contexts.appearance_update_allowed
            template = contexts.template
            template_resolution = contexts.template_resolution
            romance_sim = contexts.romance_sim
            romance_resolution = contexts.romance_resolution
            appearance_lock = contexts.appearance_lock
            previous_choice_key = contexts.previous_choice_key
            turn_context = contexts.turn_context
            visual_turn_context = contexts.visual_turn_context

            yield {"event": "status", "data": {"phase": "narrative"}}
            narrative = ""
            async for chunk in llm_service.generate_feeling_stream(
                self._narrative_system_prompt(
                    run.language,
                    narration_voice=narration_voice,
                    narration_pronoun=narration_pronoun,
                    speech_rule=contexts.speech_rule,
                    romance=romance_sim is not None,
                    script_names=contexts.script_names,
                    wardrobe=bool(contexts.outfit_options),
                ),
                json.dumps(turn_context, ensure_ascii=False),
                provider_override=_text_provider(),
                novelai_model_override=run.text_model,
                usage_callback=_record_cost,
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
                        include_clues=generate_clues,
                        companion=contexts.script_names is not None,
                        outfit_keys=tuple(
                            str(option["key"]) for option in contexts.outfit_options
                        ),
                    )
                    await queue.put(("resolution", resolution))
                except Exception as error:
                    logger.warning("Adventure resolution generation failed: %s", error)
                    await queue.put(("resolution_error", error))

            async def visual_producer() -> None:
                async def skip_partner(code: str) -> None:
                    # 攻略対象の立ち絵を描かなかった理由の記録(romance のみ)。
                    # 毎ターン描く OFF はどのゲートで止まっても not_requested にまとめる。
                    # 消費側は終了判定フラグを立てるメッセージで読み取りを止めるため、
                    # 必ずそれより前に積む
                    if romance_sim is None:
                        return
                    await queue.put(
                        (
                            "partner_skipped",
                            code
                            if generate_partner_portrait
                            else PARTNER_PORTRAIT_NOT_REQUESTED,
                        )
                    )

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
                        romance_partner={
                            "name": str(romance_sim.get("partner_name") or ""),
                            "appearance": str(
                                romance_sim.get("partner_appearance") or ""
                            ),
                        }
                        if romance_sim is not None
                        else None,
                    )
                except Exception as error:
                    logger.warning("Adventure visual generation failed: %s", error)
                    await skip_partner(PARTNER_PORTRAIT_VISUAL_FAILED)
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
                # 外見が変わり得る手番だけロックの更新を許可し、変化を以後の
                # ターンへ引き継ぐ。それ以外のターンは従来どおりロックで固定する
                self._apply_appearance_lock(
                    state,
                    visual.visual_state,
                    allow_update=appearance_update_allowed,
                )
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
                    await skip_partner(PARTNER_PORTRAIT_SCENE_UNCHANGED)
                    await queue.put(("portrait_skipped", None))
                    await queue.put(("image_skipped", None))
                    return
                # romance は現在地と時間帯ごとに背景を用意する。合成モードでは
                # この背景が img2img の下地、非合成モードではステージ背景になるため、
                # 合成シーンより前に確定させる
                fresh_background_path: Path | None = None
                # 対面会話モード(romance 専用): 手番の画像は背景+攻略対象だけ。
                # 背景は現在地が変わったときだけ描き直し、昼夜では変えない
                companion = romance_sim is not None and bool(
                    state.get("companion_mode")
                )
                location_changed = romance_location_key(
                    str(previous_visual.get("location") or "")
                ) != romance_location_key(str(next_visual.get("location") or ""))

                async def background_step() -> None:
                    nonlocal fresh_background_path
                    if romance_sim is None:
                        return
                    background_slot: str | None
                    if companion:
                        if not location_changed and getattr(
                            run, "background_image_path", None
                        ):
                            return
                        background_slot = None
                        background_tags = strip_romance_time_of_day(visual.scene_tags)
                    else:
                        _, background_slot = romance_day_slot(run.turn_count + 1)
                        background_tags = apply_romance_time_of_day(
                            visual.scene_tags, background_slot
                        )
                    try:
                        background_result = (
                            await self._ensure_romance_background_unlocked(
                                run.id,
                                scene_tags=background_tags,
                                location=str(visual.visual_state.location or ""),
                                slot=background_slot,
                                nsfw_mode=bool(run.nsfw_mode),
                            )
                        )
                    except Exception as error:
                        # 背景の失敗はターン進行を止めない。既存背景のまま続ける
                        logger.warning(
                            "Adventure romance background generation failed: %s", error
                        )
                        return
                    if background_result is not None:
                        fresh_background_path = background_result[0]
                        await queue.put(("background", background_result))

                # 旧 run のキー未設定時は _serialize_run と同じく合成モード扱いにする。
                # 既定を食い違わせると、UIは合成モード表示のままターン中は合成画像を
                # 描き直さないため、ステージの絵が更新されなくなる
                enable_composite = (
                    False
                    if companion
                    else bool(state.get("enable_composite_scene", True))
                )
                # 立ち絵の毎ターン生成OFF。合成モード・精密参照の有無に関わらず効く。
                # 主人公と攻略対象は個別に省略でき、省略した側は前ターンの1枚を
                # 使い回す。合成モードでは前ターンの立ち絵をキャラクター参照へ流用する。
                # 対面会話モードでは主人公立ち絵と合成シーンを設定に関わらず省く
                skip_player_portrait = True if companion else not generate_portrait
                draw_partner_portrait = (
                    romance_sim is not None and generate_partner_portrait
                )
                # 合成シーンは立ち絵の設定に関わらず毎ターン描き直すため、
                # 画像工程が全く無くなるのは非合成モードのときだけ
                if (
                    not enable_composite
                    and skip_player_portrait
                    and not draw_partner_portrait
                ):
                    await background_step()
                    await skip_partner(PARTNER_PORTRAIT_NOT_REQUESTED)
                    await queue.put(("portrait_skipped", None))
                    await queue.put(("image_skipped", None))
                    return
                # step 情報はフロントのプログレスバー用。phase は既存契約を維持する
                image_step_count = (
                    int(not skip_player_portrait)
                    + int(draw_partner_portrait)
                    + int(enable_composite)
                )
                # 立ち絵と合成シーンで同一シードを使い、衣装の描画差を抑える
                turn_seed = random.randint(0, 999_999_999)

                async def portrait_step() -> Path | None:
                    if skip_player_portrait:
                        await queue.put(("portrait_skipped", None))
                        return None
                    try:
                        path, _ = await self._generate_portrait_unlocked(
                            run.id,
                            None,
                            redraw_from_reference=clothing_changed or item_actions,
                            prompt_override=visual,
                            turn_number=run.turn_count + 1,
                            worn_items_override=resolved_worn_items,
                            seed_override=turn_seed,
                        )
                    except Exception as error:
                        logger.warning(
                            "Adventure turn portrait generation failed: %s", error
                        )
                        await queue.put(("portrait_error", error))
                        return None
                    await queue.put(("portrait", path))
                    return path

                # romance の攻略対象立ち絵。毎ターン生成してそのターンの表情・服装を
                # 反映する。非合成モードでは主人公と並置表示し、合成モードでは
                # 合成シーンの2枚目のキャラクター参照として使う
                partner_tags = ""
                if draw_partner_portrait:
                    partner_tags = _romance_partner_turn_portrait_tags(
                        list(visual.visual_state.main_characters),
                        list(visual.npc_tags),
                        str(romance_sim.get("partner_name") or ""),
                        str(romance_sim.get("partner_appearance") or ""),
                    )
                if romance_sim is not None and not partner_tags:
                    # 相手が場面に居ない(タグを組めない)手番は描き直さず前の1枚を残す。
                    # 合成モードで毎ターン描く OFF のときもここに落ちるが、
                    # skip_partner が not_requested に写す
                    await skip_partner(PARTNER_PORTRAIT_PARTNER_ABSENT)

                async def partner_step() -> Path | None:
                    if not partner_tags:
                        return None
                    try:
                        path = await self._generate_partner_portrait_unlocked(
                            run.id,
                            partner_tags=partner_tags,
                            turn_number=run.turn_count + 1,
                            seed_override=turn_seed,
                        )
                    except Exception as error:
                        # 相手立ち絵の失敗はターン進行を止めない
                        logger.warning(
                            "Adventure partner portrait generation failed: %s",
                            error,
                        )
                        await skip_partner(PARTNER_PORTRAIT_FAILED)
                        return None
                    await queue.put(("partner_portrait", path))
                    return path

                portrait_path: Path | None = None
                partner_path: Path | None = None
                if _image_calls_parallelizable():
                    # OpenRouterは従量課金のクラウドAPIなので、背景・主人公立ち絵・
                    # 攻略対象立ち絵を並列生成して待ち時間を短縮する。工程単位の
                    # 進捗は追えないため、先頭工程のstatusを1件だけ出す
                    if not skip_player_portrait or partner_tags:
                        await queue.put(
                            (
                                "status",
                                {
                                    "phase": "image_generation",
                                    "step": "portrait"
                                    if not skip_player_portrait
                                    else "partner",
                                    "step_index": 1,
                                    "step_count": image_step_count,
                                },
                            )
                        )
                    _, portrait_path, partner_path = await asyncio.gather(
                        background_step(), portrait_step(), partner_step()
                    )
                else:
                    # 主人公→攻略対象→合成シーンの順に直列生成する
                    await background_step()
                    if not skip_player_portrait:
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
                    portrait_path = await portrait_step()
                    if partner_tags:
                        await queue.put(
                            (
                                "status",
                                {
                                    "phase": "image_generation",
                                    "step": "partner",
                                    # 主人公を省略したターンでは先頭の工程になる
                                    "step_index": int(not skip_player_portrait) + 1,
                                    "step_count": image_step_count,
                                },
                            )
                        )
                    partner_path = await partner_step()
                if not enable_composite:
                    await queue.put(("image_skipped", None))
                    return
                await queue.put(
                    (
                        "status",
                        {
                            "phase": "image_generation",
                            "step": "composite",
                            "step_index": image_step_count,
                            "step_count": image_step_count,
                        },
                    )
                )
                try:
                    # このターンで背景を描き直した場合はその1枚を下地にする。
                    # run オブジェクトはターン開始時点の読みなので直接は使えない
                    background_path_str = (
                        str(fresh_background_path)
                        if fresh_background_path is not None
                        else getattr(run, "background_image_path", None)
                    )
                    background_bytes = (
                        Path(background_path_str).read_bytes()
                        if background_path_str and Path(background_path_str).is_file()
                        else None
                    )
                    # 立ち絵を省略したターンは前ターンの1枚を参照に流用する。
                    # 描き直した直後の1枚ではないため参照強度は弱める
                    reference_path = portrait_path
                    if reference_path is None:
                        previous_portrait = getattr(run, "portrait_image_path", None)
                        if previous_portrait and Path(previous_portrait).is_file():
                            reference_path = Path(previous_portrait)
                    image_path, _ = await self._generate_image_unlocked(
                        run.id,
                        None,
                        redraw_from_reference=clothing_changed or item_actions,
                        prompt_override=visual,
                        turn_number=run.turn_count + 1,
                        source_image_override=background_bytes,
                        character_reference_image_override=reference_path.read_bytes()
                        if reference_path is not None
                        else None,
                        character_reference_is_fresh=portrait_path is not None,
                        partner_reference_image_override=partner_path.read_bytes()
                        if partner_path is not None
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
            # 攻略対象の立ち絵を描いたか/据え置いた理由(romance のみ記録される)
            partner_portrait_status: str | None = None
            background_path: Path | None = None
            background_cache: dict[str, str] | None = None
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
                    elif kind == "background":
                        # romance の現在地・時間帯別背景。攻略対象立ち絵と同様、
                        # 最終の state コミットが古い値で上書きしないよう保持する
                        background_path, background_cache = payload
                        yield {
                            "event": "background_image",
                            "data": {
                                "image_url": self.image_url(run.id, background_path),
                            },
                        }
                    elif kind == "partner_portrait":
                        # romance の攻略対象立ち絵(非合成モードのみ)。
                        # 最終の state コミットが古いパスで上書きしないよう保持する
                        partner_sprite_path = payload
                        partner_portrait_status = PARTNER_PORTRAIT_GENERATED
                        yield {
                            "event": "partner_image",
                            "data": {
                                "image_url": self.image_url(run.id, payload),
                            },
                        }
                    elif kind == "partner_skipped":
                        # 攻略対象の立ち絵を据え置いた理由。表示用の記録だけで、
                        # 終了判定のフラグには関与しない
                        partner_portrait_status = str(payload)
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
                # romance では基底クラスに落とすと apply_romance_outcome が
                # affection_delta / money_* を読めず、好感度が黙って据え置きになる
                fallback_model: type[AdventureResolutionOutput] = (
                    AdventureRomanceResolutionOutput
                    if romance_sim is not None
                    else AdventureResolutionOutput
                )
                fallback_payload: dict[str, Any] = {
                    "choices": _default_director_choices(run.language)
                }
                if (
                    romance_sim is not None
                    and str((romance_resolution or {}).get("kind") or "") == "talk"
                ):
                    # 「友好的な働きかけは最低 +1」のガイダンスに合わせ、
                    # 生成失敗をプレイヤーへの減点にしない
                    fallback_payload["affection_delta"] = ROMANCE_TALK_FALLBACK_DELTA
                resolution = fallback_model.model_validate(
                    fallback_payload,
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

            if not generate_clues:
                # プロンプト指示に従わない出力への保険。作品シナリオの決定論的な
                # 手掛かりは後段の _enforce_template_output が別途追加するため無傷
                resolution.discovered_clues = []

            # 着替え(衣装差分の切替)。判定が返したキーを登録 ID へ写す。
            # 候補外・欠落は None で据え置き
            partner_avatar_id = _resolve_outfit_choice(
                resolution.partner_outfit, contexts.outfit_options
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
                bgm=resolution.bgm,
                bgm_reason=resolution.bgm_reason,
                partner_expression=resolution.partner_expression,
                partner_gesture=resolution.partner_gesture,
            )
            if romance_resolution is not None:
                # sim を更新し、milestone と ending_status を Python 算出値で上書き
                apply_romance_outcome(state, output, romance_resolution, resolution)
                # 攻略対象の外見は、実際にその手番を描いた visual 出力を優先する。
                # resolution は visual を見ない別呼び出しで、入れ替わりの宣言でも
                # 元の外見を restate してくることがあり、上書きされると次の手番で
                # 相手が元の姿へ戻ってしまう
                if appearance_update_allowed and visual_output is not None:
                    self._apply_partner_appearance_lock(state, visual_output)
                # 専用ボタンと重複する選択肢は選んでも機械処理が走らず空振りする。
                # プロンプトの禁止指示に LLM が従わないため、ここで確実に落とす
                output.choices = [
                    AdventureChoice.model_validate(item)
                    for item in strip_duplicate_action_choices(
                        [
                            {"id": choice.id, "label": choice.label}
                            for choice in output.choices
                        ],
                        romance_sim or {},
                        run.language,
                    )
                ]
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
            if (
                previous_choice_key
                and _choice_label_key(output.choices) == previous_choice_key
            ):
                # テンプレート作者 choices など据え置きが正しい場面もあるため
                # 警告に留める。頻発するならプロンプト側の焼き直しを疑う
                logger.warning(
                    "Adventure choices unchanged from previous turn: run_id=%s "
                    "turn=%s preset=%s input_kind=%s labels=%s",
                    run.id,
                    run.turn_count + 1,
                    run.preset,
                    input_kind,
                    _choices_preview(
                        [choice.model_dump() for choice in output.choices]
                    ),
                )
            turn_number = run.turn_count + 1
            # 現実改変宣言によるタイムリミット変更。_merge_output の手数切れ
            # 判定より前に run.max_turns(romance は sim["total_days"] も)へ反映する
            _apply_time_limit_alteration(
                run,
                state,
                resolution,
                input_kind=input_kind,
                turn_number=turn_number,
                epilogue=epilogue,
            )
            if partner_avatar_id and partner_avatar_id != _companion_avatar_id(
                run, state
            ):
                # state_override 経由で state_delta にも載り、_serialize_turn が
                # companion_avatar_id / url として配信する
                state["companion_avatar_id"] = partner_avatar_id
            next_state, next_status, _, _ = self._merge_output(
                run, output, turn_number, state_override=state, epilogue=epilogue
            )
            # 立ち絵(主人公または攻略対象)を描いた手番はタグを更新する。対面会話モードは
            # 主人公立ち絵を常に省くため、主人公側だけを条件にすると開幕値のまま凍り、
            # 「場面に変化なし」判定・visual LLM の previous_image_tags・↻ の再描画タグが
            # すべて開幕基準になる
            if visual_output is not None and (
                portrait_path is not None or partner_sprite_path is not None
            ):
                next_state["last_image_prompt"] = _image_prompt_payload(visual_output)
            # このターンで生成した攻略対象立ち絵を state と state_delta に反映する。
            # 生成ヘルパのDB保存はこの後の全stateコミットで上書きされるため必須
            if partner_sprite_path is not None:
                next_state["partner_portrait_path"] = str(partner_sprite_path)
            if romance_sim is not None:
                # state_delta は全 state なので、書かないと前手番の値が残る。
                # None は「記録なし」として FE が理由未記録の文言に倒す
                next_state["partner_portrait_status"] = partner_portrait_status
            # 背景キャッシュも同じ理由で state へ書き戻す
            if background_cache is not None:
                next_state["background_cache"] = background_cache
            if background_path is not None:
                next_state["background_image_path"] = str(background_path)

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

            # run へ書く status とエンディング文言を確定する。
            # エピローグの continue ターンでは確定済みリザルトを上書きしない
            if epilogue and next_status == "continue":
                resolved_status = run.status
                resolved_ending_title = run.ending_title
                resolved_ending_summary = run.ending_summary
            else:
                resolved_status = "active" if next_status == "continue" else next_status
                resolved_ending_title = output.ending_title or (
                    next_state.get("ending_summary")
                    and _default_ending_title(run.preset, next_status)
                )
                resolved_ending_summary = next_state.get("ending_summary")
                if next_status != "continue":
                    # 巻き戻し時に当時の run.status を復元できるよう、終了(と
                    # エピローグ中の逆転)ターンの state に記録する。
                    # フルスナップショットの伝播で以降のターンへ引き継がれる
                    next_state["final_status"] = next_status
                    next_state["final_ending_title"] = resolved_ending_title

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
                # 現実改変でタイムリミットが変わったターンを含めて常に同期する
                persisted.max_turns = run.max_turns
                persisted.status = resolved_status
                persisted.ending_title = resolved_ending_title
                persisted.ending_summary = resolved_ending_summary
                persisted.updated_at = datetime.now()
                db.add(turn)
                await db.commit()
                await db.refresh(turn)

            result = self._serialize_turn(turn, language=run.language)
            result["run_status"] = resolved_status
            result["remaining_turns"] = max(0, run.max_turns - turn_number)
            result["clues"] = next_state.get("clues", [])
            result["completed_milestones"] = next_state.get("completed_milestones", [])
            result["visual_state"] = _sanitize_visual_state(
                next_state.get("visual_state")
            )
            result["ending_title"] = resolved_ending_title or _default_ending_title(
                run.preset, next_status
            )
            result["ending_summary"] = resolved_ending_summary
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
            if cost_tracker.total_usd > 0:
                yield {
                    "event": "cost",
                    "data": {"cost_usd": cost_tracker.total_usd},
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
        self,
        state: dict[str, Any],
        visual_state: AdventureVisualState,
        *,
        allow_update: bool = False,
    ) -> None:
        template_state = state.get("template_state", {})
        transformed = bool(
            isinstance(template_state, dict) and template_state.get("transformed")
        )
        if allow_update:
            # reality_alter ターン限定: 宣言を織り込んでLLMが更新した外見を
            # 新しいロックとして採用する。以後のターンはこの外見で固定される。
            # 空の出力は採用せず、従来のロック適用へフォールスルーする
            new_appearance = str(visual_state.appearance or "").strip()
            if new_appearance:
                state["appearance_lock"] = new_appearance
                return
        appearance_lock = state.get("appearance_lock")
        if (
            not transformed
            and isinstance(appearance_lock, str)
            and appearance_lock.strip()
        ):
            visual_state.appearance = appearance_lock

    def _build_turn_contexts(
        self,
        run: AdventureRun,
        state: dict[str, Any],
        *,
        user_input: str,
        input_kind: str,
        gift_id: str | None,
        epilogue: bool,
        outfit_options: list[dict[str, Any]] | None = None,
    ) -> _TurnContexts:
        """1手番のLLMへ渡す文脈を組み立てる。

        state を破壊的に更新する(宣言ルールの追記・未反映付与の取り出し)ため、
        プレビュー用途では state のコピーを渡すこと。
        資金不足などはここで AdventureError を送出し、手番を消費させない。
        """
        narration_voice, narration_pronoun = _narration_from_state(state)
        # 宣言はこの手番から有効にする
        declared_rule = _detect_reality_declaration(user_input)
        if declared_rule:
            _append_reality_rule(state, declared_rule)
            input_kind = "reality_alter"
        # 手番を使わず付与されたルールも、この手番で初めて世界へ反映させる
        declared_this_turn = _take_established_reality_rules(state, declared_rule)
        reality_rules = list(state.get("reality_rules", []))
        # 進行型ルール(毎ターン徐々に変化する宣言)が残っている間は、宣言ターン
        # 以外でも毎ターン外見が進むため、外見ロックの更新を許し続ける
        progressive_rules = _progressive_reality_rules(reality_rules)
        # 外見ロックの更新は「外見が変わり得る手番」だけに許す。手番を使わない
        # 付与でも、その手番の visual 出力を新しいロックとして採用する
        appearance_update_allowed = (
            input_kind == "reality_alter"
            or declared_this_turn is not None
            or bool(progressive_rules)
        )
        template = SCENARIO_TEMPLATES.get(str(state.get("scenario_template_id")))
        template_resolution = self._resolve_template_action(template, state, user_input)
        scenario_guidance = PRESETS.get(run.preset, {}).get("guidance", "")
        if template:
            scenario_guidance = f"{scenario_guidance} {template['guidance']}"
        if epilogue:
            scenario_guidance = f"{scenario_guidance} {EPILOGUE_GUIDANCE}"
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
        turn_context: dict[str, Any] = {
            "task": "Resolve the player's next action.",
            "preset": run.preset,
            "scenario_guidance": scenario_guidance,
            "authored_template_resolution": template_resolution,
            "objective": run.objective,
            "max_turns": run.max_turns,
            "next_turn": run.turn_count + 1,
            "state": _lean_state_for_llm(state),
            "recent_turns": previous_turns[-7:],
            "player_input": user_input,
            "previous_choices": _previous_choice_labels(state),
            "reality_rules": reality_rules,
            "reality_rule_declared_this_turn": declared_this_turn,
            "progressive_reality_rules": progressive_rules,
            "required_visual_appearance": appearance_lock,
            # resolution プロンプトの current_bgm ルールが名前参照する
            "current_bgm": state.get("bgm") or get_bgm_default(),
        }
        script_names: tuple[str, str] | None = None
        if romance_resolution is not None:
            turn_context["romance_resolution"] = romance_resolution
        if romance_sim is not None:
            # トークモードで交わした会話を、直前の手番以降の分だけ文脈として渡す
            recent_talk = recent_talk_entries(state, run.turn_count)
            if recent_talk:
                turn_context["recent_talk"] = recent_talk
            if state.get("companion_mode"):
                script_names = romance_script_names(romance_sim, run.language)
                turn_context["companion_mode"] = True
                if outfit_options:
                    # 着替え先の候補。物語生成と判定の両方が同じ一覧を見る
                    turn_context["partner_wardrobe"] = _wardrobe_context(outfit_options)
                if romance_resolution is not None:
                    # 対面会話モードには昼夜の枠が無い。判定結果は残し、
                    # 時間帯のキーだけを LLM から隠す
                    turn_context["romance_resolution"] = {
                        key: value
                        for key, value in romance_resolution.items()
                        if key not in _COMPANION_HIDDEN_RESOLUTION_KEYS
                    }
        if epilogue:
            turn_context["epilogue"] = True
        visual_turn_context = {
            **turn_context,
            "authored_visual_style": _template_visual_style(template),
            "authored_scene_tags": _authored_scene_tags(template=template, state=state),
        }
        return _TurnContexts(
            turn_context=turn_context,
            visual_turn_context=visual_turn_context,
            input_kind=input_kind,
            narration_voice=narration_voice,
            narration_pronoun=narration_pronoun,
            speech_rule=_speech_rule_from_state(state),
            appearance_update_allowed=appearance_update_allowed,
            template=template,
            template_resolution=template_resolution,
            romance_sim=romance_sim,
            romance_resolution=romance_resolution,
            appearance_lock=appearance_lock,
            previous_choice_key=_choice_label_key(state.get("choices")),
            script_names=script_names,
            outfit_options=list(outfit_options or []) if script_names else [],
        )

    def _apply_partner_appearance_lock(
        self, state: dict[str, Any], visual_output: AdventureVisualOutput
    ) -> None:
        """現実改変ターンで攻略対象の外見を visual 出力から書き戻す。

        主人公の _apply_appearance_lock と対称の処理。resolution の
        updated_partner_appearance は宣言を取りこぼすことがあるため、その手番の
        絵をすでに正しく描いている visual 出力を安全網として採用する。
        攻略対象がその手番の場面に居ない、タグが取れない、服装しか無いといった
        場合はすべて no-op で、既存の外見を消さない。
        """
        sim = state.get("sim")
        if not isinstance(sim, dict):
            return
        _entry, partner_tags = _romance_partner_visual_entry(
            list(visual_output.visual_state.main_characters),
            list(visual_output.npc_tags),
            str(sim.get("partner_name") or ""),
        )
        identity = _identity_tags_only(partner_tags)
        if identity:
            sim["partner_appearance"] = identity

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
        raw = await _generate_text(
            system_prompt,
            json.dumps(payload, ensure_ascii=False),
            text_model=text_model,
        )
        try:
            image_prompt = _validate_model_json(AdventureImagePromptOutput, raw)
        except ValidationError as first_error:
            logger.warning(
                "Adventure image prompt JSON validation failed: %s", first_error
            )
            repaired = await _generate_text(
                system_prompt,
                "Repair this into valid JSON without adding facts. "
                f"Fix these validation errors:\n{first_error}\n\n" + raw,
                text_model=text_model,
            )
            try:
                image_prompt = _validate_model_json(
                    AdventureImagePromptOutput, repaired
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
        tracker = _CostTracker()
        _cost_tracker.set(tracker)
        async with self._run_locks[run_id]:
            image_path, effective_turn_id = await self._generate_image_unlocked(
                run_id,
                turn_id,
                redraw_from_reference=redraw_from_reference,
                prompt_override=prompt_override,
            )
        result: dict[str, Any] = {
            "image_url": self.image_url(run_id, image_path),
            "turn_id": effective_turn_id,
        }
        if tracker.total_usd > 0:
            result["cost_usd"] = tracker.total_usd
        return result

    async def generate_portrait(
        self,
        run_id: str,
        turn_id: str | None = None,
        *,
        redraw_from_reference: bool = False,
        prompt_override: AdventureImagePromptOutput | None = None,
    ) -> dict[str, Any]:
        """立ち絵だけを作り直す。生成失敗ターンからの復旧導線で使う。"""
        tracker = _CostTracker()
        _cost_tracker.set(tracker)
        async with self._run_locks[run_id]:
            portrait_path, effective_turn_id = await self._generate_portrait_unlocked(
                run_id,
                turn_id,
                redraw_from_reference=redraw_from_reference,
                prompt_override=prompt_override,
            )
        result: dict[str, Any] = {
            "image_url": self.image_url(run_id, portrait_path),
            "turn_id": effective_turn_id,
        }
        if tracker.total_usd > 0:
            result["cost_usd"] = tracker.total_usd
        return result

    @staticmethod
    def _partner_portrait_tags_from_state(
        state: dict[str, Any], *, npc_tags: list[str] | None = None
    ) -> str:
        """保存済み state から攻略対象の立ち絵タグを組み立てる。romance 以外は空。

        手番中と同じく main_characters の該当エントリと npc_tags を使い、
        取れなければ sim の外見と服装で補う。
        """
        sim_state = state.get("sim")
        if not isinstance(sim_state, dict):
            return ""
        stored_tags = npc_tags
        if stored_tags is None:
            last_prompt = state.get("last_image_prompt")
            stored_tags = (
                [str(tag) for tag in last_prompt.get("npc_tags", [])]
                if isinstance(last_prompt, dict)
                else []
            )
        main_characters = list(
            state.get("visual_state", {}).get("main_characters") or []
        )
        partner_name = str(sim_state.get("partner_name") or "")
        partner_appearance = str(sim_state.get("partner_appearance") or "")
        tags = _romance_partner_turn_portrait_tags(
            main_characters, stored_tags, partner_name, partner_appearance
        )
        if tags:
            return tags
        entry, _ = _romance_partner_visual_entry(
            main_characters, stored_tags, partner_name
        )
        clothing = entry["clothing"] if entry else ""
        return ", ".join(part for part in (partner_appearance, clothing) if part)

    async def generate_partner_portrait(self, run_id: str) -> dict[str, Any]:
        """romance の攻略対象の立ち絵だけを作り直す(対面会話モードの↻)。"""
        tracker = _CostTracker()
        _cost_tracker.set(tracker)
        async with self._run_locks[run_id]:
            run = await self.get_run_orm(run_id, with_turns=True)
            state = _json_load(run.state_json, {})
            partner_tags = self._partner_portrait_tags_from_state(state)
            if not partner_tags:
                raise AdventureError(
                    "partner_not_available",
                    "攻略対象の立ち絵を描く情報がありません",
                )
            partner_path = await self._generate_partner_portrait_unlocked(
                run_id, partner_tags=partner_tags, turn_number=run.turn_count
            )
            # 最新手番のスナップショットにも反映し、フレーム表示と巻き戻しを揃える
            turns = sorted(run.turns, key=lambda item: item.turn_number)
            latest_turn = turns[-1] if turns else None
            effective_turn_id = latest_turn.id if latest_turn is not None else None
            if latest_turn is not None:
                async with (
                    self._persist_locks[run_id],
                    async_session_factory() as db,
                ):
                    persisted_turn = await db.get(AdventureTurn, latest_turn.id)
                    if persisted_turn is not None:
                        delta = _json_load(persisted_turn.state_delta_json, {})
                        delta["partner_portrait_path"] = str(partner_path)
                        delta["partner_portrait_status"] = PARTNER_PORTRAIT_GENERATED
                        persisted_turn.state_delta_json = json.dumps(
                            delta, ensure_ascii=False
                        )
                        await db.commit()
        result: dict[str, Any] = {
            "image_url": self.image_url(run_id, partner_path),
            "turn_id": effective_turn_id,
        }
        if tracker.total_usd > 0:
            result["cost_usd"] = tracker.total_usd
        return result

    @staticmethod
    async def _resolve_image_model(
        nsfw_mode: bool, state: dict[str, Any] | None = None
    ) -> str:
        """NovelAI 画像生成モデルを解決する。

        run の state に image_model_override があればそれを最優先し、
        無ければ従来どおりユーザー設定と nsfw_mode から決める。
        """
        override = str((state or {}).get("image_model_override") or "")
        if override in NOVELAI_IMAGE_MODELS:
            return override
        user_settings = await session_store.get_user_settings()
        return resolve_user_image_model(user_settings, nsfw_mode)

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
        character_reference_is_fresh: bool = True,
        partner_reference_image_override: bytes | None = None,
        worn_items_override: list[str] | None = None,
        seed_override: int | None = None,
    ) -> tuple[Path, str | None]:
        """呼び出し側が既に run ロックを保持している前提で画像を生成する。

        character_reference_is_fresh は、渡された参照画像がこのターンに描き直した
        立ち絵かどうか。立ち絵の毎ターン生成をOFFにしたターンでは前ターンの
        立ち絵を流用するため False になり、衣装変更時の参照強度を弱める。
        """
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
                turn_number=effective_turn_number,
            )
            player_prompt = _enhance_adventure_prompt(
                image_prompt.player_tags + _PLAYER_PROMPT_SUFFIX,
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
                        npc_prompt + _NPC_PROMPT_SUFFIX,
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
            provider = _image_provider()
            effective_image_model: str | None = None
            if provider == "novelai":
                effective_image_model = await self._resolve_image_model(
                    nsfw_mode, state
                )
            character_references = None
            # V5系モデルは精密参照（character reference）非対応
            if use_precise_reference and not is_v5_image_model(effective_image_model):
                char_strength, char_fidelity = _character_reference_strength(
                    outfit_changed=outfit_changed,
                    has_fresh_portrait=(
                        character_reference_image_override is not None
                        and character_reference_is_fresh
                    ),
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
                # romance では攻略対象がシーンに登場するターンに限り、
                # そのターンの立ち絵(無ければ開始素材)を2枚目の参照として追加する
                partner_reference = _romance_partner_scene_reference(
                    state,
                    image_prompt,
                    reference_override=partner_reference_image_override,
                )
                if partner_reference is not None:
                    character_references.append(partner_reference)
            scene_prompt = _enhance_adventure_prompt(
                _compose_scene_base_tags(image_prompt) + _SCENE_PROMPT_SUFFIX,
                nsfw_mode=nsfw_mode,
            )
            if provider == "novelai":
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
            else:
                # キャラクター枠を持たないプロバイダーは単一プロンプトへ畳む。
                # OpenRouter は編集元が無いターンで立ち絵/初期画像を編集元に
                # 昇格させて同一性を保ち、ComfyUI は編集元画像が必須
                flat_prompt = _flatten_scene_prompt(
                    scene_prompt,
                    player_prompt,
                    [str(entry["prompt"]) for entry in characters[1:]],
                )
                edit_source = source_image
                reference_bytes = (
                    character_reference_image_override
                    if character_reference_image_override is not None
                    else initial_path.read_bytes()
                )
                if provider == "selfhost":
                    if edit_source is None:
                        edit_source = current_path.read_bytes()
                    # ComfyUIワークフローは参照画像を受けない
                    reference_bytes = None
                elif edit_source is None:
                    edit_source, reference_bytes = reference_bytes, None
                instruction = _scene_edit_instruction(
                    has_background=edit_source is not None,
                    has_reference=reference_bytes is not None,
                )
                result = await image_service.generate_image(
                    instruction + flat_prompt,
                    image_bytes=edit_source,
                    reference_image_bytes=reference_bytes,
                    provider_override=provider,
                    nsfw_mode=nsfw_mode,
                )
            _record_cost(getattr(result, "cost_usd", None))
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
        async with self._persist_locks[run.id], async_session_factory() as db:
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
        turn_number: int | None = None,
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
        romance の時間帯タグも同じ理由でここ（複製側）だけに適用する。
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
        # romance は昼/夜が turn_number から決まる。LLM 任せにすると夜のターンで
        # 真昼の絵が出るため、照明タグを決定論で確定させる
        if getattr(run, "preset", "") == "romance" and turn_number is not None:
            # 開幕(turn 0)は最初の枠(Day1 昼)として扱う
            _, romance_slot = romance_day_slot(max(1, int(turn_number)))
            image_prompt.scene_tags = apply_romance_time_of_day(
                image_prompt.scene_tags, romance_slot
            )
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
        filename: str = "background.png",
    ) -> Path:
        """背景画像を1枚生成して run の現在背景に設定する。

        既定の filename は開幕用。romance では現在地と時間帯ごとに別名で生成し、
        _ensure_romance_background_unlocked がキャッシュとして使い回す。
        """
        run = await self.get_run_orm(run_id)
        provider = _image_provider()
        if provider == "selfhost":
            # ComfyUIの編集ワークフローはtxt2imgを持たないため背景は作れない。
            # 呼び出し側は既存背景(無ければ初期画像)のまま続行する
            raise AdventureError(
                "image_generation_failed",
                "背景画像はセルフホストプロバイダーでは生成できません",
            )
        # scene_tags は「観察可能な相互作用」を含みうるため、no humans 等の
        # 除外タグを前置して人物非表示を強く指示する
        scenery_prompt = _enhance_adventure_prompt(
            "no humans, empty, uninhabited, scenery, background, " + scene_tags,
            nsfw_mode=nsfw_mode,
        )
        if provider == "novelai":
            result = await image_service.generate_scenery(
                prompt=scenery_prompt,
                size="landscape",
                nsfw_mode=nsfw_mode,
                include_people=False,
                provider_override="novelai",
                novelai_model_override=await self._resolve_image_model(
                    nsfw_mode, _json_load(getattr(run, "state_json", None), {})
                ),
            )
        else:
            result = await image_service.generate_image(
                "Generate one wide background scenery illustration containing "
                "no people at all.\n" + scenery_prompt,
                image_bytes=None,
                provider_override=provider,
                nsfw_mode=nsfw_mode,
            )
        _record_cost(getattr(result, "cost_usd", None))
        if not result.images:
            raise AdventureError(
                "image_generation_failed", "背景画像が生成されませんでした"
            )
        background_path = self._images_dir / run.id / Path(filename).name
        background_path.parent.mkdir(parents=True, exist_ok=True)
        background_path.write_bytes(result.images[0])
        async with self._persist_locks[run.id], async_session_factory() as db:
            persisted_run = await db.get(AdventureRun, run.id)
            if persisted_run is None:
                raise AdventureError("run_not_found", "アドベンチャーが見つかりません")
            persisted_run.background_image_path = str(background_path)
            persisted_run.updated_at = datetime.now()
            await db.commit()
        return background_path

    async def _ensure_romance_background_unlocked(
        self,
        run_id: str,
        *,
        scene_tags: str,
        location: str,
        slot: str | None,
        nsfw_mode: bool,
    ) -> tuple[Path, dict[str, str]] | None:
        """現在地と時間帯に対応する背景を用意し、(パス, キャッシュ) を返す。

        同じ (現在地, 時間帯) では生成せず既存画像を使い回す。生成上限に達した
        場合と現在地が不明な場合は None を返し、既存の背景をそのまま使わせる。
        slot が None のとき(対面会話モード)は現在地だけをキーにし、
        昼夜が変わっても同じ場所なら描き直さない。
        """
        # selfhost(ComfyUI)は背景のtxt2imgを生成できない。毎ターン例外と警告を
        # 出さないよう、ここで静かに既存背景のまま進める
        if _image_provider() == "selfhost":
            return None
        location_key = romance_location_key(location)
        if not location_key:
            return None
        key = location_key if slot is None else f"{location_key}|{slot}"
        run = await self.get_run_orm(run_id)
        state = _json_load(run.state_json, {})
        cache = state.get("background_cache")
        cache = dict(cache) if isinstance(cache, dict) else {}
        cached_name = cache.get(key)
        if cached_name:
            cached_path = self._images_dir / run_id / Path(str(cached_name)).name
            if cached_path.is_file():
                if str(run.background_image_path or "") != str(cached_path):
                    async with async_session_factory() as db:
                        persisted_run = await db.get(AdventureRun, run_id)
                        if persisted_run is not None:
                            persisted_run.background_image_path = str(cached_path)
                            persisted_run.updated_at = datetime.now()
                            await db.commit()
                return cached_path, cache
            cache.pop(key, None)
        if len(cache) >= ROMANCE_BACKGROUND_CACHE_MAX:
            logger.info(
                "Adventure romance background cache is full: run_id=%s key=%s",
                run_id,
                key,
            )
            return None
        filename = f"background-{uuid.uuid4().hex[:8]}.png"
        background_path = await self._generate_background_image_unlocked(
            run_id, scene_tags=scene_tags, nsfw_mode=nsfw_mode, filename=filename
        )
        cache[key] = background_path.name
        return background_path, cache

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
                turn_number=effective_turn_number,
            )
            provider = _image_provider()
            effective_image_model: str | None = None
            if provider == "novelai":
                effective_image_model = await self._resolve_image_model(
                    nsfw_mode, state
                )
            # 立ち絵はフロント側で背景を透過するため、必ず白背景で生成させる。
            # （V5モデルのみ透過背景をネイティブ生成させる）
            player_prompt = _enhance_adventure_prompt(
                image_prompt.player_tags
                + _portrait_prompt_suffix(effective_image_model),
                nsfw_mode=nsfw_mode,
            )
            # 現実改変で外見が変わった後の初期画像は元の姿のままで、参照に
            # 使うと毎ターン引き戻す。乖離後は直近の立ち絵へ、それも無ければ
            # 参照なしにする(古い姿を参照するより無参照の方が正しい)
            reference_path: Path | None = initial_path
            if _appearance_diverged(state):
                latest_portrait = getattr(run, "portrait_image_path", None)
                reference_path = (
                    Path(latest_portrait)
                    if latest_portrait and Path(latest_portrait).is_file()
                    else None
                )
            if provider == "novelai":
                character_references = None
                # V5系モデルは精密参照（character reference）非対応
                if (
                    use_precise_reference
                    and reference_path is not None
                    and not is_v5_image_model(effective_image_model)
                ):
                    # 参照は前ターン以前の1枚なので fresh portrait 扱いにしない
                    char_strength, char_fidelity = _character_reference_strength(
                        outfit_changed=outfit_changed, has_fresh_portrait=False
                    )
                    character_references = [
                        {
                            "image": reference_path.read_bytes(),
                            "type": "character",
                            "strength": char_strength,
                            "fidelity": char_fidelity,
                        }
                    ]
                result = await image_service.generate_image(
                    player_prompt,
                    image_bytes=None,
                    provider_override="novelai",
                    # 追加negativeを渡すと provider 側の既定UCが置き換わるため、
                    # 品質系の基本negativeを土台にして結合する
                    negative_prompt=merge_negative_prompt(
                        merge_negative_prompt(
                            settings.novelai_negative_prompt, extra_negative or ""
                        ),
                        _PORTRAIT_EXTRA_NEGATIVE,
                    ),
                    nsfw_mode=nsfw_mode,
                    character_references=character_references,
                    characters=None,
                    seed=seed_override,
                    size_override="portrait",
                    novelai_model_override=effective_image_model,
                )
            else:
                # 参照は追加課金なしで常に使い、同一性を保つ。OpenRouterは
                # 参照を編集元として渡し、ComfyUIは編集元画像が必須なので
                # 参照が無いときも初期画像を編集元に使う(引き戻しの懸念より
                # 生成不能の方が悪い)
                edit_source: bytes | None = (
                    reference_path.read_bytes()
                    if reference_path is not None and reference_path.is_file()
                    else None
                )
                if provider == "selfhost" and edit_source is None:
                    edit_source = initial_path.read_bytes()
                instruction = (
                    "Redraw the exact character from the attached image with the "
                    "same face, hair, and identity, as described below.\n"
                    if edit_source is not None
                    else ""
                )
                result = await image_service.generate_image(
                    instruction + player_prompt,
                    image_bytes=edit_source,
                    provider_override=provider,
                    nsfw_mode=nsfw_mode,
                )
            _record_cost(getattr(result, "cost_usd", None))
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
        async with self._persist_locks[run.id], async_session_factory() as db:
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

        主人公の立ち絵と同じく白背景で生成し、フロント側で透過する
        (V5モデルのみ透過背景をネイティブ生成させる)。
        最新の1枚だけを state["partner_portrait_path"] に保持する。
        """
        run = await self.get_run_orm(run_id)
        state = _json_load(run.state_json, {})
        nsfw_mode = bool(run.nsfw_mode)
        provider = _image_provider()
        effective_image_model: str | None = None
        if provider == "novelai":
            effective_image_model = await self._resolve_image_model(nsfw_mode, state)
        prompt = _enhance_adventure_prompt(
            partner_tags + _portrait_prompt_suffix(effective_image_model),
            nsfw_mode=nsfw_mode,
        )
        character_references = None
        # 参照は開始セッションの元画像。ただし現実改変で外見が変わった後は
        # その1枚が元の姿のままなので、直近の相手立ち絵へ切り替える。
        # 立ち絵が無ければ参照なしで描く
        reference_key = (
            "partner_portrait_path"
            if _partner_appearance_diverged(state)
            else "partner_image_path"
        )
        reference_path = Path(str(state.get(reference_key) or ""))
        if provider == "novelai":
            # V5系モデルは精密参照（character reference）非対応
            if (
                bool(state.get("use_precise_reference"))
                and reference_path.is_file()
                and not is_v5_image_model(effective_image_model)
            ):
                # 服装は変化し得るため弱めに参照する
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
            result = await image_service.generate_image(
                prompt,
                image_bytes=None,
                provider_override="novelai",
                negative_prompt=merge_negative_prompt(
                    settings.novelai_negative_prompt,
                    f"{_PORTRAIT_EXTRA_NEGATIVE}, {_PARTNER_SOLO_NEGATIVE}",
                ),
                nsfw_mode=nsfw_mode,
                character_references=character_references,
                characters=None,
                seed=seed_override,
                size_override="portrait",
                novelai_model_override=effective_image_model,
            )
        else:
            # 参照は追加課金なしで常に使い、同一性を保つ。参照が無いときは
            # OpenRouterはtxt2img、ComfyUIは生成不可なのでエラーにする
            edit_source: bytes | None = (
                reference_path.read_bytes() if reference_path.is_file() else None
            )
            if provider == "selfhost" and edit_source is None:
                raise AdventureError(
                    "image_generation_failed",
                    "相手の立ち絵の編集元画像が見つかりません",
                )
            instruction = (
                "Redraw the exact character from the attached image with the "
                "same face, hair, and identity, as described below.\n"
                if edit_source is not None
                else ""
            )
            result = await image_service.generate_image(
                instruction + prompt,
                image_bytes=edit_source,
                provider_override=provider,
                nsfw_mode=nsfw_mode,
            )
        _record_cost(getattr(result, "cost_usd", None))
        if not result.images:
            raise AdventureError(
                "image_generation_failed", "相手の立ち絵が生成されませんでした"
            )
        filename = f"partner-{turn_number}-{uuid.uuid4().hex[:8]}.png"
        partner_path = self._images_dir / run.id / filename
        partner_path.parent.mkdir(parents=True, exist_ok=True)
        partner_path.write_bytes(result.images[0])
        async with self._persist_locks[run.id], async_session_factory() as db:
            persisted_run = await db.get(AdventureRun, run.id)
            if persisted_run is None:
                raise AdventureError("run_not_found", "アドベンチャーが見つかりません")
            persisted_state = _json_load(persisted_run.state_json, {})
            persisted_state["partner_portrait_path"] = str(partner_path)
            # ↻(手番外の描き直し)で run の記録も「描いた」に戻す。stream_turn 経由は
            # 最終コミットが同値で上書きする
            persisted_state["partner_portrait_status"] = PARTNER_PORTRAIT_GENERATED
            if turn_number == 0:
                # 開幕フレーム表示用に、開幕時の1枚は別キーでも保持する
                persisted_state["opening_partner_portrait_path"] = str(partner_path)
            persisted_run.state_json = json.dumps(persisted_state, ensure_ascii=False)
            persisted_run.updated_at = datetime.now()
            await db.commit()
        return partner_path

    async def _generate_opening_visuals(self, run_id: str) -> None:
        """Run作成直後に、背景・ポートレート・（設定時のみ）合成シーンを生成する。

        NovelAI/セルフホストは従来どおり直列、OpenRouterは従量課金APIなので
        背景・主人公立ち絵・攻略対象立ち絵を並列生成して開幕を短縮する。
        """
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
                turn_number=1,
            )
            # 立ち絵と合成シーンで同一シードを使い、衣装の描画差を抑える
            opening_seed = random.randint(0, 999_999_999)

            # 対面会話モード: 開幕背景も現在地キーでキャッシュに登録し、
            # 手番1で同じ場所なら描き直さない(時間帯タグは落として生成する)
            companion = bool(state.get("companion_mode")) and isinstance(
                state.get("sim"), dict
            )
            seeded_background_cache: dict[str, str] | None = None

            async def background_step() -> Path | None:
                nonlocal seeded_background_cache
                # 背景には時間帯タグ適用済みの scene_tags を渡す。
                # image_prompt(変換前)は後続の prompt_override 用に温存する。
                # 背景の失敗で開幕全体を止めない(セルフホストは生成不可で常にここ)
                try:
                    if companion:
                        ensured = await self._ensure_romance_background_unlocked(
                            run_id,
                            scene_tags=strip_romance_time_of_day(
                                _prepared_prompt.scene_tags
                            ),
                            location=str(
                                state.get("visual_state", {}).get("location") or ""
                            ),
                            slot=None,
                            nsfw_mode=nsfw_mode,
                        )
                        if ensured is None:
                            return None
                        seeded_background_cache = ensured[1]
                        return ensured[0]
                    return await self._generate_background_image_unlocked(
                        run_id,
                        scene_tags=_prepared_prompt.scene_tags,
                        nsfw_mode=nsfw_mode,
                    )
                except Exception:
                    logger.warning(
                        "Adventure opening background generation failed: run_id=%s",
                        run_id,
                    )
                    return None

            async def portrait_step() -> Path:
                path, _ = await self._generate_portrait_unlocked(
                    run_id,
                    None,
                    redraw_from_reference=True,
                    prompt_override=image_prompt,
                    turn_number=0,
                    seed_override=opening_seed,
                )
                return path

            # romance では攻略対象の立ち絵も開幕時に用意する(非合成モードの
            # 並置表示用。合成へ切り替えた場合もそのまま無害)
            partner_tags = ""
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

            async def partner_step() -> None:
                if not partner_tags:
                    return
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

            if _image_calls_parallelizable():
                (
                    background_result,
                    portrait_result,
                    _partner_result,
                ) = await asyncio.gather(
                    background_step(),
                    portrait_step(),
                    partner_step(),
                    return_exceptions=True,
                )
                if isinstance(portrait_result, BaseException):
                    raise portrait_result
                portrait_path = portrait_result
                background_path = (
                    None
                    if isinstance(background_result, BaseException)
                    else background_result
                )
            else:
                background_path = await background_step()
                portrait_path = await portrait_step()
                await partner_step()

            # 立ち絵生成が state を更新するため読み直す
            run = await self.get_run_orm(run_id)
            state = _json_load(run.state_json, {})
            enable_composite_scene = bool(state.get("enable_composite_scene"))
            if enable_composite_scene and not companion:
                await self._generate_image_unlocked(
                    run_id,
                    None,
                    redraw_from_reference=True,
                    prompt_override=image_prompt,
                    turn_number=0,
                    source_image_override=background_path.read_bytes()
                    if background_path is not None
                    else None,
                    character_reference_image_override=portrait_path.read_bytes(),
                    seed_override=opening_seed,
                )
            elif background_path is not None:
                async with (
                    self._persist_locks[run_id],
                    async_session_factory() as db,
                ):
                    persisted_run = await db.get(AdventureRun, run_id)
                    if persisted_run is None:
                        raise AdventureError(
                            "run_not_found", "アドベンチャーが見つかりません"
                        )
                    persisted_run.current_image_path = str(background_path)
                    if seeded_background_cache is not None:
                        # 開幕背景を現在地キーで登録し、手番1の描き直しを防ぐ
                        persisted_state = _json_load(persisted_run.state_json, {})
                        persisted_state["background_cache"] = seeded_background_cache
                        persisted_state["background_image_path"] = str(background_path)
                        persisted_run.state_json = json.dumps(
                            persisted_state, ensure_ascii=False
                        )
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
            # state_delta はターン適用後の全 state なので、bgm 未出力(据え置き)の
            # ターンにも直近の有効キーと理由が入っている。旧 run は None
            "bgm": state_delta.get("bgm"),
            "bgm_reason": state_delta.get("bgm_reason"),
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
            # epilogue はその手番時点のフラグを使う(runの現stateではなく)
            result["sim"] = public_sim_view(
                sim_state,
                turn.turn_number,
                epilogue=bool(state_delta.get("epilogue")),
            )
            partner_entry, _ = _romance_partner_visual_entry(
                list((turn_visual or {}).get("main_characters") or []),
                [],
                str(sim_state.get("partner_name") or ""),
            )
            note = str((partner_entry or {}).get("description") or "").strip()
            result["partner_note"] = note or None
            # 対面会話モードの 3D アバター向け。旧ターンや語彙外は None
            result["partner_expression"] = normalize_avatar_expression(
                state_delta.get("partner_expression")
            )
            result["partner_gesture"] = normalize_avatar_gesture(
                state_delta.get("partner_gesture")
            )
            # このターン確定時点の 3D モデル。着替えで切り替わった手番で FE が
            # run 全体の再取得を待たずにモデルを差し替えるために配信する
            turn_avatar_id = str(state_delta.get("companion_avatar_id") or "").strip()
            result["companion_avatar_id"] = turn_avatar_id or None
            result["companion_avatar_url"] = (
                avatar_file_url(turn_avatar_id) if turn_avatar_id else None
            )
            # このターン確定時点の攻略対象立ち絵。過去フレーム表示に使う
            partner_sprite = Path(str(state_delta.get("partner_portrait_path") or ""))
            result["partner_portrait_url"] = (
                self.image_url(turn.run_id, partner_sprite)
                if partner_sprite.is_file()
                else None
            )
            # この手番で立ち絵を描いたか、据え置いた理由。旧ターンは None
            result["partner_portrait_status"] = normalize_partner_portrait_status(
                state_delta.get("partner_portrait_status")
            )
            # このターン確定時点の背景。過去フレームを当時の場所・時間帯で見せる
            turn_background = Path(str(state_delta.get("background_image_path") or ""))
            result["background_image_url"] = (
                self.image_url(turn.run_id, turn_background)
                if turn_background.is_file()
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
        player_speech_style: str | None = None,
        player_speech_custom: str | None = None,
        partner_speech_style: str | None = None,
        image_model: str | None = None,
        companion_mode: bool | None = None,
        companion_avatar_id: str | None = None,
    ) -> dict[str, Any]:
        """実行中シナリオの画像設定と口調を更新する（次の手番から反映）。

        口調はプロンプト注入だけの設定なので、現実改変ルールと同じく手番を
        消費しない。None の項目は既存値を維持する。
        image_model は "default" で上書き解除(グローバル設定へ復帰)、
        モデル名で run 単位の上書きを設定する。
        """
        async with self._run_locks[run_id]:
            run = await self.get_run_orm(run_id, with_turns=True)
            state = _json_load(run.state_json, {})
            state["use_precise_reference"] = bool(use_precise_reference)
            state["enable_composite_scene"] = bool(enable_composite_scene)
            if respect_clothing_layers is not None:
                state["respect_clothing_layers"] = bool(respect_clothing_layers)
            if image_model == "default":
                state.pop("image_model_override", None)
            elif image_model in NOVELAI_IMAGE_MODELS:
                state["image_model_override"] = image_model
            if player_speech_style is not None:
                state["player_speech_style"] = normalize_speech_style(
                    player_speech_style
                )
            if player_speech_custom is not None:
                state["player_speech_custom"] = normalize_speech_custom(
                    player_speech_custom
                )
            if partner_speech_style is not None and isinstance(state.get("sim"), dict):
                state["sim"]["partner_speech_style"] = normalize_partner_speech_style(
                    partner_speech_style
                )
            # 対面会話モードは romance 専用。他プリセットでは無視する
            if companion_mode is not None and run.preset == "romance":
                state["companion_mode"] = bool(companion_mode)
            # 3D アバターは "none"(または空)で解除、ID で設定。None は据え置き
            if companion_avatar_id is not None and run.preset == "romance":
                if companion_avatar_id.strip() in {"", "none"}:
                    state.pop("companion_avatar_id", None)
                else:
                    state["companion_avatar_id"] = await _validate_companion_avatar(
                        companion_avatar_id
                    )
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

    async def update_reality_rules(
        self, run_id: str, rules: list[str]
    ) -> dict[str, Any]:
        """付与済みの現実改変ルールを丸ごと置き換える(手番は消費しない)。

        通常ゲームの属性付与と同じく、次のターンのプロンプトへ反映されるだけで
        物語は進まない。turn_count / status / AdventureTurn には触れないため、
        手番切れで失敗エンドになることもない。
        既に確定した外見(appearance_lock / sim["partner_appearance"])はここでは
        戻さない。ルールは以後の判定に効く世界設定で、確定済みの姿とは別管理。
        巻き戻しは対象手番のスナップショットを復元するため、その手番より後に
        ここで加えた変更は巻き戻しで失われる。
        """
        # 検証はロック取得前に済ませ、拒否時はDBに触れない
        normalized = _normalize_reality_rules(rules)
        if len(normalized) > _MAX_REALITY_RULES:
            raise AdventureError(
                "too_many_reality_rules",
                f"付与できる属性は{_MAX_REALITY_RULES}件までです",
            )
        async with self._run_locks[run_id]:
            run = await self.get_run_orm(run_id, with_turns=True)
            state = _json_load(run.state_json, {})
            previous = _normalize_reality_rules(state.get("reality_rules", []))
            state["reality_rules"] = normalized
            # 手番を使わずに足したルールは「宣言された手番」を持たない。次の手番で
            # 一度だけ世界へ反映させるため、新規分をここで控えておく
            # (ターン送信前に複数回 PATCH されても取りこぼさないよう既存分と併合)
            pending = _normalize_reality_rules(
                [
                    *state.get("pending_reality_rules", []),
                    *[rule for rule in normalized if rule not in previous],
                ]
            )
            # 反映前に削除されたルールは持ち越さない
            state["pending_reality_rules"] = [
                rule for rule in pending if rule in normalized
            ]
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
            run.state_json = json.dumps(state, ensure_ascii=False)
            return self._serialize_run(run, turns)

    async def preview_turn_prompts(
        self,
        run_id: str,
        *,
        user_input: str,
        input_kind: str,
        gift_id: str | None = None,
    ) -> dict[str, Any]:
        """次の手番で送られるプロンプトを、LLMを呼ばずに組み立てて返す。

        ENABLE_PROMPT_PREVIEW が有効なときだけ使える確認用の機能。
        state は書き換えず(コピー上で組み立てる)、手番も消費しない。
        ビジュアル呼び出しの user prompt に入る narrative はこの手番の生成結果
        なので、プレビューでは占位文字列になる(narrative_is_placeholder=True)。
        画像工程は state["last_image_prompt"] を使って組み立てるため、
        「いまの場面のタグで生成したら何が送られるか」を示す。
        """
        if not settings.enable_prompt_preview:
            raise AdventureError(
                "prompt_preview_disabled", "プロンプトプレビューは無効です"
            )
        run = await self.get_run_orm(run_id, with_turns=True)
        # 宣言の追記や未反映付与の取り出しが走るため、必ずコピー上で組み立てる
        state = copy.deepcopy(_json_load(run.state_json, {}))
        epilogue = bool(state.get("epilogue"))
        outfit_options = await self._companion_outfit_options(run, state)
        contexts = self._build_turn_contexts(
            run,
            state,
            user_input=user_input,
            input_kind=input_kind,
            gift_id=gift_id,
            epilogue=epilogue,
            outfit_options=outfit_options,
        )
        romance = contexts.romance_sim is not None
        turn_user_prompt = json.dumps(contexts.turn_context, ensure_ascii=False)
        narrative_placeholder = (
            "(この手番の本文がここに入ります。物語生成の結果なので事前には確定しません)"
        )
        romance_partner = (
            {
                "name": str((contexts.romance_sim or {}).get("partner_name") or ""),
                "appearance": str(
                    (contexts.romance_sim or {}).get("partner_appearance") or ""
                ),
            }
            if romance
            else None
        )
        result: dict[str, Any] = {
            "input_kind": contexts.input_kind,
            "narrative": {
                "system": self._narrative_system_prompt(
                    run.language,
                    narration_voice=contexts.narration_voice,
                    narration_pronoun=contexts.narration_pronoun,
                    speech_rule=contexts.speech_rule,
                    romance=romance,
                    script_names=contexts.script_names,
                    wardrobe=bool(contexts.outfit_options),
                ),
                "user": turn_user_prompt,
            },
            "resolution": {
                "system": self._resolution_system_prompt(
                    run.language,
                    narration_voice=contexts.narration_voice,
                    narration_pronoun=contexts.narration_pronoun,
                    romance=romance,
                    companion=contexts.script_names is not None,
                    outfit_keys=tuple(
                        str(option["key"]) for option in contexts.outfit_options
                    ),
                ),
                "user": turn_user_prompt,
            },
            "visual": {
                "system": self._visual_system_prompt(
                    run.language,
                    respect_clothing_layers=bool(state.get("respect_clothing_layers")),
                    romance=romance,
                ),
                "user": _visual_user_payload(
                    narrative=narrative_placeholder,
                    turn_context=contexts.visual_turn_context,
                    previous_visual=state.get("visual_state", {}),
                    appearance_lock=contexts.appearance_lock,
                    previous_image_tags=state.get("last_image_prompt"),
                    romance_partner=romance_partner,
                ),
                "narrative_is_placeholder": True,
            },
            "image": await self._preview_image_prompts(run, state),
        }
        return result

    async def _preview_image_prompts(
        self, run: AdventureRun, state: dict[str, Any]
    ) -> dict[str, Any] | None:
        """いまの場面タグで画像生成したときに実際に送られる文字列を組み立てる。

        LLMを呼ばないよう、state["last_image_prompt"] を prompt_override として
        渡す(None を渡すと画像タグ生成のLLM呼び出しが走るため)。
        """
        stored = state.get("last_image_prompt")
        if not isinstance(stored, dict):
            return None
        try:
            override = AdventureImagePromptOutput.model_validate(stored)
        except ValidationError:
            return None
        (
            image_prompt,
            _outfit_changed,
            nsfw_mode,
            use_precise_reference,
            extra_negative,
            _raw,
        ) = await self._prepare_image_prompt(
            run,
            state,
            redraw_from_reference=False,
            prompt_override=override,
            turn_number=run.turn_count,
        )
        scene_prompt = _enhance_adventure_prompt(
            _compose_scene_base_tags(image_prompt) + _SCENE_PROMPT_SUFFIX,
            nsfw_mode=nsfw_mode,
        )
        player_prompt = _enhance_adventure_prompt(
            image_prompt.player_tags + _PLAYER_PROMPT_SUFFIX,
            nsfw_mode=nsfw_mode,
        )
        npc_prompts = [
            _enhance_adventure_prompt(
                npc_prompt + _NPC_PROMPT_SUFFIX, nsfw_mode=nsfw_mode
            )
            for npc_prompt in image_prompt.npc_tags[:3]
        ]
        provider = _image_provider()
        # 送信経路と同じサフィックス選択（V5のみ透過背景）になるようモデルを解決する
        preview_image_model: str | None = None
        if provider == "novelai":
            preview_image_model = await self._resolve_image_model(nsfw_mode, state)
        # 対面会話モードでは攻略対象の立ち絵だけを描くため、そのプロンプトも示す
        partner_tags = self._partner_portrait_tags_from_state(
            state, npc_tags=list(image_prompt.npc_tags)
        )
        payload = {
            "scene_prompt": scene_prompt,
            "player_prompt": player_prompt,
            "npc_prompts": npc_prompts,
            "portrait_prompt": _enhance_adventure_prompt(
                image_prompt.player_tags + _portrait_prompt_suffix(preview_image_model),
                nsfw_mode=nsfw_mode,
            ),
            "partner_prompt": _enhance_adventure_prompt(
                partner_tags + _portrait_prompt_suffix(preview_image_model),
                nsfw_mode=nsfw_mode,
            )
            if partner_tags
            else "",
            "companion_mode": bool(state.get("companion_mode"))
            and run.preset == "romance",
            "negative_prompt": merge_negative_prompt(
                settings.novelai_negative_prompt, extra_negative or ""
            ),
            "nsfw_mode": nsfw_mode,
            "use_precise_reference": use_precise_reference,
            "image_provider": provider,
        }
        if provider != "novelai":
            # 非NovelAIはキャラクター枠を持たず、送信経路と同じ関数で
            # 1本に畳んだプロンプトを送る。negative prompt も送られない
            payload["scene_prompt"] = _flatten_scene_prompt(
                scene_prompt, player_prompt, npc_prompts
            )
            payload["negative_prompt"] = ""
        return payload

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
            "source_prompt_expander_entry_id": getattr(
                run, "source_prompt_expander_entry_id", None
            ),
            "preset": run.preset,
            "scenario_template_id": state.get("scenario_template_id"),
            "title": run.title,
            "objective": run.objective,
            "setting": state.get("setting", ""),
            "constraints": _json_load(run.constraints_json, []),
            "status": run.status,
            "epilogue": bool(state.get("epilogue")),
            # 手番0への巻き戻しは開幕スナップショットを持つ run だけ可能
            "can_rewind_to_opening": bool(getattr(run, "opening_state_json", None)),
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
            # BGM は semantic key のみ返す。旧 run は None でフロントが daily に倒す
            "bgm": state.get("bgm"),
            "bgm_reason": state.get("bgm_reason"),
            "opening_bgm": state.get("opening_bgm"),
            "opening_bgm_reason": state.get("opening_bgm_reason"),
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
            # run 単位の NovelAI 画像モデル上書き。null ならグローバル設定に従う
            "image_model_override": str(state.get("image_model_override") or "")
            or None,
            # 環境変数由来のグローバル設定。通常ゲームは session stats 経由で受け取るが
            # Adventure はそこを見ないため、run のペイロードへ載せる
            "enable_prompt_preview": bool(settings.enable_prompt_preview),
            # 旧 run は既定の二人称・「僕」へ倒す
            "narration_voice": normalize_narration_voice(state.get("narration_voice")),
            "narration_pronoun": normalize_narration_pronoun(
                state.get("narration_pronoun")
            ),
            # 旧 run は既定の丁寧語へ倒す
            "player_speech_style": normalize_speech_style(
                state.get("player_speech_style")
            ),
            "player_speech_custom": normalize_speech_custom(
                state.get("player_speech_custom")
            ),
            # 対面会話モード(romance 専用)。旧 run・他プリセットは OFF
            "companion_mode": run.preset == "romance"
            and bool(state.get("companion_mode")),
            # 対面会話モードで描く 3D アバター(未設定は null。URL は DB を引かない)
            "companion_avatar_id": _companion_avatar_id(run, state),
            "companion_avatar_url": (
                avatar_file_url(_companion_avatar_id(run, state) or "")
                if _companion_avatar_id(run, state)
                else None
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
            response["sim"] = public_sim_view(
                sim_state, run.turn_count, epilogue=bool(state.get("epilogue"))
            )
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
            # 最新手番で立ち絵を描いたか、据え置いた理由。旧 run は None
            response["partner_portrait_status"] = normalize_partner_portrait_status(
                state.get("partner_portrait_status")
            )
            # トークモード(手番を消費しない会話)のログ
            response["talk_log"] = public_talk_log(state)
        if include_snapshot:
            response["snapshot"] = _json_load(run.snapshot_json, {})
        return response


adventure_service = AdventureService()
