"""アドベンチャーの LLM 出力モデル（Pydantic）と選択肢の正規化。

ディレクター / セットアップ / 解決 / 画像プロンプトの各出力を検証し、
LLM の崩れた出力を検証エラーへ落とさず切り詰め・既定値で受け入れる。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from annotated_types import MaxLen
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from ..consts.adventure_bgm import get_bgm_keys
from ..consts.adventure_setup import SCENARIO_CONSTRAINTS_MAX_ITEMS
from ..consts.companion_avatar import (
    normalize_avatar_expression,
    normalize_avatar_gesture,
    normalize_avatar_outfit_key,
)
from .adventure_inventory import coerce_reality_patch, coerce_world_events
from .adventure_romance import RomanceAlteredGift

logger = logging.getLogger(__name__)


# 選択肢ラベルの上限。行動パネルは幅 260〜360px の縦長カラムなので、長い
# ラベルは何行にも折り返して選択肢一覧が読めなくなる。プロンプト側で
# 20字程度を要求したうえで、この値は超過分を静かに切り詰める最後の砦として使う
_CHOICE_LABEL_MAX_LENGTH = 60


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
        return {"id": item.id, "label": item.label}
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
    # 持ち物システム(inventory_enabled)の World Event。物語が実際に示した受け渡し・
    # 使用・着脱・境界侵害だけを、Python 側が所持品と照合して適用する。
    # reality_patch は reality_alter ターン限定で所持品と NPC の記憶を直接書き換える。
    # 既存の alter 限定フィールド(affection_set / money_set / updated_total_days /
    # updated_gift_catalog / updated_partner_appearance / start_dating /
    # updated_max_turns)と合わせたものが「現実改変パッチ」で、既存分は従来どおり
    # apply_romance_outcome / _apply_time_limit_alteration が適用する
    world_events: list[dict[str, Any]] = Field(default_factory=list)
    reality_patch: dict[str, Any] | None = None

    @field_validator("world_events", mode="before")
    @classmethod
    def coerce_world_events_field(cls, value: Any) -> Any:
        # 壊れた要素は捨て、検証エラー→修復リトライへ落とさない
        return coerce_world_events(value)

    @field_validator("reality_patch", mode="before")
    @classmethod
    def coerce_reality_patch_field(cls, value: Any) -> Any:
        return coerce_reality_patch(value)

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


def _image_prompt_payload(prompt: AdventureImagePromptOutput) -> dict[str, Any]:
    return {
        "scene_tags": prompt.scene_tags,
        "player_tags": prompt.player_tags,
        "npc_tags": list(prompt.npc_tags),
    }
