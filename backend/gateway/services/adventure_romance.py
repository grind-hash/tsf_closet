"""romance プリセット(恋愛シミュレーション)の決定論ロジック。

金銭・日数・好感度・ギフト採点・告白成否は LLM に委ねず、ここの純関数が
確定する。adventure_service.stream_turn からは薄いフック呼び出しだけを行い、
day/slot は状態に保存せず turn_number から導出する(冪等リトライと整合)。
"""

from __future__ import annotations

import random
import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..consts.adventure_romance import (
    ROMANCE_AFFECTION_MAX,
    ROMANCE_AFFECTION_MIN,
    ROMANCE_AFFECTION_START,
    ROMANCE_ALTER_DELTA_LIMIT,
    ROMANCE_ALTER_MONEY_LIMIT,
    ROMANCE_CONFESSION_FAIL_PENALTY,
    ROMANCE_CONFESSION_PACE,
    ROMANCE_CONFESSION_THRESHOLD,
    ROMANCE_DAYS_MAX,
    ROMANCE_DAYS_MIN,
    ROMANCE_FALLBACK_CHOICES,
    ROMANCE_GIFT_POINTS,
    ROMANCE_GIFT_TIER_PRICES,
    ROMANCE_INITIAL_MONEY,
    ROMANCE_MILESTONES,
    ROMANCE_MONEY_MAX,
    ROMANCE_MONEY_MIN,
    ROMANCE_PLAYER_NAME_FALLBACK,
    ROMANCE_RESERVED_CHOICE_PATTERNS,
    ROMANCE_SLOT_CONFLICT_TAGS,
    ROMANCE_SLOT_SCENE_TAGS,
    ROMANCE_SLOTS_PER_DAY,
    ROMANCE_STAGE_MILESTONE_IDS,
    ROMANCE_STAGE_THRESHOLDS,
    ROMANCE_TALK_CONTEXT_MAX,
    ROMANCE_TALK_DELTA_LIMIT,
    ROMANCE_TALK_INPUT_MAX,
    ROMANCE_TALK_LOG_MAX,
    ROMANCE_TALK_REPLY_MAX,
    ROMANCE_WORK_ENCOUNTER_BONUS,
    ROMANCE_WORK_ENCOUNTER_RATE,
    ROMANCE_WORK_WAGE,
)
from ..consts.adventure_speech import PARTNER_SPEECH_STYLE_MAX_LENGTH

_RESERVED_CHOICE_RE = re.compile(
    "|".join(f"(?:{pattern})" for pattern in ROMANCE_RESERVED_CHOICE_PATTERNS),
    re.IGNORECASE,
)

# scene_tags の上限。AdventureImagePromptOutput.scene_tags と揃える
_SCENE_TAGS_MAX = 1800


class RomanceActionError(RuntimeError):
    """ターン消費前に弾く利用者向けエラー(資金不足など)。

    adventure_service 側で AdventureError へ変換する(循環 import 回避)。
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RomanceGift(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    price: int = Field(ge=1, le=50000)
    tier: Literal["budget", "standard", "luxury"] = "standard"

    @field_validator("name", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def clamp_price_to_tier(self) -> RomanceGift:
        low, high = ROMANCE_GIFT_TIER_PRICES[self.tier]
        self.price = max(low, min(high, self.price))
        return self


class RomanceAlteredGift(BaseModel):
    """現実改変でギフトカタログを書き換えるときの1品目。

    RomanceGift と違い tier 帯への価格クランプを行わない(「全品無料になる」の
    ような宣言を許すため)。preference は宣言が同時に好みを定めた場合だけ入る。
    """

    name: str = Field(min_length=1, max_length=80)
    price: int = Field(default=0, ge=0, le=999_999)
    tier: Literal["budget", "standard", "luxury"] = "standard"
    preference: Literal["liked", "disliked", "neutral"] | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("price", mode="before")
    @classmethod
    def clamp_price(cls, value: Any) -> Any:
        # LLM の過大値・文字列で検証エラー→修復リトライへ落とさない
        try:
            return max(0, min(999_999, int(value)))
        except (TypeError, ValueError):
            return 0

    @field_validator("tier", mode="before")
    @classmethod
    def coerce_tier(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().lower() in {
            "budget",
            "standard",
            "luxury",
        }:
            return value.strip().lower()
        return "standard"

    @field_validator("preference", mode="before")
    @classmethod
    def coerce_preference(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().lower() in {
            "liked",
            "disliked",
            "neutral",
        }:
            return value.strip().lower()
        return None


class RomanceSetupOutput(BaseModel):
    """LLM が1回だけ生成する恋愛シナリオの初期素材。

    好みの ID 採番と名前→ID の名寄せは Python 後処理で行う。
    """

    partner_name: str = Field(min_length=1, max_length=80)
    partner_profile: str = Field(min_length=1, max_length=600)
    # 話し方だけを取り出した1文。既存 run と生成失敗に備えて必須にしない
    partner_speech_style: str = Field(
        default="", max_length=PARTNER_SPEECH_STYLE_MAX_LENGTH
    )
    relationship_origin: str = Field(min_length=1, max_length=400)
    job_name: str = Field(min_length=1, max_length=80)
    gift_catalog: list[RomanceGift] = Field(min_length=8, max_length=12)
    liked_gift_names: list[str] = Field(default_factory=list, max_length=4)
    disliked_gift_names: list[str] = Field(default_factory=list, max_length=4)
    likes_hint: str = Field(default="", max_length=300)
    dislikes_hint: str = Field(default="", max_length=300)


def clamp_romance_max_turns(value: int) -> int:
    """日数×2 のターン予算を偶数かつ許容範囲へ丸める。"""
    low = ROMANCE_DAYS_MIN * ROMANCE_SLOTS_PER_DAY
    high = ROMANCE_DAYS_MAX * ROMANCE_SLOTS_PER_DAY
    clamped = max(low, min(high, int(value)))
    return clamped - (clamped % ROMANCE_SLOTS_PER_DAY)


def romance_day_slot(turn_number: int) -> tuple[int, str]:
    """turn_number(1始まり)から日付と時間帯を導出する。奇数=昼、偶数=夜。"""
    number = max(1, int(turn_number))
    day = (number + 1) // ROMANCE_SLOTS_PER_DAY
    slot = "day" if number % ROMANCE_SLOTS_PER_DAY == 1 else "night"
    return day, slot


def apply_romance_time_of_day(scene_tags: str, slot: str) -> str:
    """scene_tags の時間帯を slot で確定させる。

    LLM は previous_image_tags から前ターンの照明タグを引き継ぐため、単に前置
    するだけでは昼と夜のタグが同居する。反対の時間帯を示すタグを取り除いてから
    当該 slot のタグを前置する。既に含まれている場合は重複させない。
    """
    tags = ROMANCE_SLOT_SCENE_TAGS.get(slot)
    if not tags:
        return scene_tags
    conflicts = {item.casefold() for item in ROMANCE_SLOT_CONFLICT_TAGS.get(slot, ())}
    wanted = [item.strip() for item in tags.split(",") if item.strip()]
    wanted_keys = {item.casefold() for item in wanted}
    kept: list[str] = []
    for raw in scene_tags.split(","):
        item = raw.strip()
        if not item:
            continue
        key = item.casefold()
        if key in conflicts or key in wanted_keys:
            continue
        kept.append(item)
    merged = ", ".join([*wanted, *kept])
    return merged[:_SCENE_TAGS_MAX].rstrip(", ")


_TIME_OF_DAY_TAG_KEYS: frozenset[str] = frozenset(
    {
        *(
            item.strip().casefold()
            for tags in ROMANCE_SLOT_SCENE_TAGS.values()
            for item in tags.split(",")
            if item.strip()
        ),
        *(
            item.casefold()
            for conflicts in ROMANCE_SLOT_CONFLICT_TAGS.values()
            for item in conflicts
        ),
    }
)


def strip_romance_time_of_day(scene_tags: str) -> str:
    """scene_tags から昼夜を示すタグをすべて取り除く。

    1on1 立ち絵モードの背景は現在地ごとに1枚だけ持ち、時間帯では描き直さない。
    LLM は previous_image_tags から前ターンの照明タグを引き継ぐため、生成前に
    昼夜どちらのタグも落として時間帯に依存しない背景にする。
    """
    kept: list[str] = []
    for raw in scene_tags.split(","):
        item = raw.strip()
        if not item or item.casefold() in _TIME_OF_DAY_TAG_KEYS:
            continue
        kept.append(item)
    return ", ".join(kept)[:_SCENE_TAGS_MAX].rstrip(", ")


def romance_location_key(location: str) -> str:
    """背景キャッシュと現在地変化判定に使う現在地の正規化キー。"""
    return str(location or "").strip().casefold()[:80]


def strip_duplicate_action_choices(
    choices: list[dict[str, Any]],
    sim: dict[str, Any],
    language: str,
) -> list[dict[str, Any]]:
    """専用ボタンと重複する選択肢を落とし、会話ビートで補充する。

    告白・プレゼント・バイト・属性付与は専用ボタンだけが機械処理を走らせる。
    同じ内容が choice として出ると選んでも何も起きないため、ここで除去する。
    """
    catalog_names = [
        str(item.get("name") or "").strip()
        for item in sim.get("gift_catalog", [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    job = sim.get("job") if isinstance(sim.get("job"), dict) else {}
    job_name = str(job.get("name") or "").strip()
    kept: list[dict[str, Any]] = []
    for choice in choices:
        label = str(choice.get("label") or "").strip()
        if not label:
            continue
        if _RESERVED_CHOICE_RE.search(label):
            continue
        # カタログの品名やバイト先の名指しも専用ボタンの領分とみなす
        if any(name and name in label for name in catalog_names):
            continue
        if job_name and job_name in label:
            continue
        kept.append(choice)
    if len(kept) >= len(choices) or len(kept) >= 3:
        return kept
    used_ids = {str(item.get("id") or "") for item in kept}
    used_labels = {str(item.get("label") or "") for item in kept}
    fallbacks = ROMANCE_FALLBACK_CHOICES.get(language, ROMANCE_FALLBACK_CHOICES["en"])
    for item in fallbacks:
        if len(kept) >= 3:
            break
        if item["id"] in used_ids or item["label"] in used_labels:
            continue
        kept.append(dict(item))
    return kept


def romance_confession_threshold(total_days: int) -> int:
    """告白の成功ライン。短いランでも正攻法で届くよう日数へスケールする。

    実測の獲得ペース(会話+ギフト)を前提に、1手あたり ROMANCE_CONFESSION_PACE
    を見込む。ROMANCE_CONFESSION_THRESHOLD は最長ラン用の上限。
    total_days が不明(旧データ等)の場合は従来の固定値に倒す。
    """
    days = int(total_days)
    if days <= 0:
        return ROMANCE_CONFESSION_THRESHOLD
    total_turns = days * ROMANCE_SLOTS_PER_DAY
    scaled = ROMANCE_AFFECTION_START + round(total_turns * ROMANCE_CONFESSION_PACE)
    return min(ROMANCE_CONFESSION_THRESHOLD, scaled)


def romance_stage(affection: int) -> str:
    """好感度から関係段階 ID を返す。"""
    if affection >= ROMANCE_STAGE_THRESHOLDS["mutual"]:
        return "mutual"
    if affection >= ROMANCE_STAGE_THRESHOLDS["aware"]:
        return "aware"
    if affection >= ROMANCE_STAGE_THRESHOLDS["friend"]:
        return "friend"
    return "stranger"


def _normalize_gift_name(name: str) -> str:
    return name.strip().casefold()


def _match_gift_ids(names: list[str], catalog: list[dict[str, Any]]) -> set[str]:
    """名前の集合をカタログ ID へ名寄せする。完全一致を優先し、次に部分一致。"""
    matched: set[str] = set()
    by_name = {
        _normalize_gift_name(str(item["name"])): str(item["id"]) for item in catalog
    }
    for raw in names:
        key = _normalize_gift_name(str(raw))
        if not key:
            continue
        if key in by_name:
            matched.add(by_name[key])
            continue
        for item in catalog:
            item_key = _normalize_gift_name(str(item["name"]))
            if key in item_key or item_key in key:
                matched.add(str(item["id"]))
                break
    return matched


def init_romance_state(
    setup: RomanceSetupOutput,
    max_turns: int,
    rng: random.Random | None = None,
    *,
    partner_appearance: str = "",
    player_name: str = "",
    player_character_id: str = "",
    player_history_id: str = "",
    partner_speech_style: str = "",
) -> dict[str, Any]:
    """state_json["sim"] の初期値を組み立てる。hidden_preferences は隠し情報。

    開始セッションの人物は攻略対象(partner)であり、主人公(player)は
    別途選択されたテンプレートキャラクター。player_history_id は
    player_character_id が "session:{id}" 形式のときの時点IDで、
    リプレイ時に同じ変身状態から始め直すために保存する。
    partner_speech_style はユーザーがセットアップで指定した上書き値で、
    空なら LLM が生成した setup.partner_speech_style を使う。
    """
    rng = rng or random.Random()
    catalog = [
        {
            "id": f"g{index}",
            "name": gift.name,
            "price": gift.price,
            "tier": gift.tier,
        }
        for index, gift in enumerate(setup.gift_catalog, start=1)
    ]
    all_ids = [str(item["id"]) for item in catalog]
    liked = _match_gift_ids(setup.liked_gift_names, catalog)
    disliked = _match_gift_ids(setup.disliked_gift_names, catalog) - liked
    # 名寄せに失敗しても推理対象が空にならないよう補完する
    if not liked:
        candidates = [item for item in all_ids if item not in disliked]
        liked = set(rng.sample(candidates, min(2, len(candidates))))
    if not disliked:
        candidates = [item for item in all_ids if item not in liked]
        disliked = set(rng.sample(candidates, min(2, len(candidates))))
    return {
        "total_days": int(max_turns) // ROMANCE_SLOTS_PER_DAY,
        "affection": ROMANCE_AFFECTION_START,
        "money": ROMANCE_INITIAL_MONEY,
        "partner_name": setup.partner_name,
        "partner_profile": setup.partner_profile,
        "partner_speech_style": " ".join(
            (partner_speech_style or setup.partner_speech_style).split()
        ).strip()[:PARTNER_SPEECH_STYLE_MAX_LENGTH],
        "partner_appearance": partner_appearance,
        "relationship_origin": setup.relationship_origin,
        "player_name": player_name,
        "player_character_id": player_character_id,
        "player_history_id": player_history_id,
        "job": {"name": setup.job_name, "wage": ROMANCE_WORK_WAGE},
        "gift_catalog": catalog,
        "hidden_preferences": {
            "liked_gift_ids": sorted(liked),
            "disliked_gift_ids": sorted(disliked),
            "likes_hint": setup.likes_hint,
            "dislikes_hint": setup.dislikes_hint,
        },
        "given_gifts": [],
        "confessed": False,
    }


def resolve_romance_action(
    sim: dict[str, Any],
    *,
    user_input: str,
    input_kind: str,
    gift_id: str | None = None,
    turn_number: int,
    total_turns: int,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """ターンの機械的な結果を確定する。LLM へは確定事実として渡す。"""
    rng = rng or random.Random()
    day, slot = romance_day_slot(turn_number)
    # 選択肢は「次の枠」向けの行動なので、次枠の日付・時間帯も確定して渡す。
    # 最終ターンでは next_day が total_days を超えるが、これはエピローグ初枠を
    # 指す意図的な値で、public_sim_view の epilogue 挙動(day クランプ解除)と一致する
    next_day, next_slot = romance_day_slot(int(turn_number) + 1)
    resolution: dict[str, Any] = {
        "kind": "talk",
        "day": day,
        "slot": slot,
        "next_day": next_day,
        "next_slot": next_slot,
        "total_days": int(total_turns) // ROMANCE_SLOTS_PER_DAY,
        "money_delta": 0,
        "affection_delta": 0,
    }
    if input_kind == "work":
        job = sim.get("job") if isinstance(sim.get("job"), dict) else {}
        wage = int(job.get("wage") or ROMANCE_WORK_WAGE)
        encountered = rng.random() < ROMANCE_WORK_ENCOUNTER_RATE
        resolution.update(
            {
                "kind": "work",
                "job_name": str(job.get("name") or ""),
                "money_delta": wage,
                "partner_encountered": encountered,
                "affection_delta": ROMANCE_WORK_ENCOUNTER_BONUS if encountered else 0,
            }
        )
        return resolution
    if input_kind == "gift":
        catalog = [
            item for item in sim.get("gift_catalog", []) if isinstance(item, dict)
        ]
        gift = next(
            (item for item in catalog if str(item.get("id")) == str(gift_id or "")),
            None,
        )
        if gift is None:
            raise RomanceActionError("invalid_gift", "そのプレゼントは購入できません")
        price = int(gift.get("price") or 0)
        if int(sim.get("money") or 0) < price:
            raise RomanceActionError(
                "insufficient_funds", "所持金が足りず、そのプレゼントを購入できません"
            )
        hidden = (
            sim.get("hidden_preferences")
            if isinstance(sim.get("hidden_preferences"), dict)
            else {}
        )
        given = [str(item) for item in sim.get("given_gifts", [])]
        if str(gift.get("id")) in given:
            # 満額を払って中立加点しか得られない罠になるため、ターン未消費で弾く
            raise RomanceActionError(
                "gift_already_given", "そのプレゼントは既に贈っています"
            )
        if str(gift.get("id")) in set(hidden.get("liked_gift_ids", [])):
            match = "liked"
        elif str(gift.get("id")) in set(hidden.get("disliked_gift_ids", [])):
            match = "disliked"
        else:
            match = "neutral"
        tier = str(gift.get("tier") or "standard")
        points = ROMANCE_GIFT_POINTS.get(tier, ROMANCE_GIFT_POINTS["standard"])[match]
        resolution.update(
            {
                "kind": "gift",
                "gift": {
                    "id": str(gift.get("id")),
                    "name": str(gift.get("name") or ""),
                    "price": price,
                    "tier": tier,
                },
                "money_delta": -price,
                "affection_delta": points,
                "preference_match": match,
            }
        )
        return resolution
    if input_kind == "confess":
        # FE は交際成立後に告白ボタンを消すが、stale なクライアントからの
        # 再演をサーバ側でも弾く(ターン未消費)
        if bool(sim.get("confessed")):
            raise RomanceActionError("already_dating", "既に想いは通じ合っています")
        success = int(sim.get("affection") or 0) >= romance_confession_threshold(
            int(sim.get("total_days") or 0)
        )
        resolution.update(
            {
                "kind": "confess",
                "success": success,
                "affection_delta": 0 if success else ROMANCE_CONFESSION_FAIL_PENALTY,
            }
        )
        return resolution
    if input_kind == "reality_alter":
        resolution["kind"] = "alter"
    return resolution


def _clamp_affection(value: int) -> int:
    return max(ROMANCE_AFFECTION_MIN, min(ROMANCE_AFFECTION_MAX, int(value)))


def _clamp_money(value: int) -> int:
    return max(ROMANCE_MONEY_MIN, min(ROMANCE_MONEY_MAX, int(value)))


def _apply_preference_updates(sim: dict[str, Any], romance_output: Any) -> None:
    """属性付与ターンの好み書換をカタログ照合のうえ適用する。未知 ID は捨てる。"""
    hidden = sim.get("hidden_preferences")
    if not isinstance(hidden, dict):
        return
    catalog_ids = {
        str(item.get("id"))
        for item in sim.get("gift_catalog", [])
        if isinstance(item, dict)
    }
    liked_updates = [
        str(item)
        for item in (getattr(romance_output, "updated_liked_gift_ids", None) or [])
        if str(item) in catalog_ids
    ]
    disliked_updates = [
        str(item)
        for item in (getattr(romance_output, "updated_disliked_gift_ids", None) or [])
        if str(item) in catalog_ids
    ]
    if not liked_updates and not disliked_updates:
        return
    liked = {str(item) for item in hidden.get("liked_gift_ids", [])}
    disliked = {str(item) for item in hidden.get("disliked_gift_ids", [])}
    # 集合間の移動として適用し、同一ターンで両方に載った ID は liked を優先する
    for gift_id in disliked_updates:
        liked.discard(gift_id)
        disliked.add(gift_id)
    for gift_id in liked_updates:
        disliked.discard(gift_id)
        liked.add(gift_id)
    hidden["liked_gift_ids"] = sorted(liked)
    hidden["disliked_gift_ids"] = sorted(disliked)


def apply_gift_catalog_update(sim: dict[str, Any], gifts: list[Any]) -> None:
    """現実改変ターンのギフトカタログ書換を適用する(全品目の置き換え)。

    宣言後の品揃え全体を受け取り、既存カタログと名前が一致する品目は ID を
    引き継ぐ(隠し好み・贈答済み記録の参照を壊さないため)。新しい品目には
    既存 ID と衝突しない連番を振る。空リストは「変更なし」の番兵として no-op。
    好み(hidden_preferences)と贈答済み(given_gifts)は存続する ID だけ残し、
    各品目の preference が指定されていればその集合へ移す。
    """
    if not gifts:
        return
    old_catalog = [
        item for item in sim.get("gift_catalog", []) if isinstance(item, dict)
    ]
    id_by_name = {
        _normalize_gift_name(str(item.get("name") or "")): str(item.get("id"))
        for item in old_catalog
        if str(item.get("name") or "").strip()
    }
    used_ids = {str(item.get("id")) for item in old_catalog}
    next_index = len(old_catalog) + 1
    new_catalog: list[dict[str, Any]] = []
    preferences: dict[str, str] = {}
    seen_names: set[str] = set()
    for gift in gifts:
        name = str(getattr(gift, "name", "") or "").strip()
        key = _normalize_gift_name(name)
        if not name or key in seen_names:
            continue
        seen_names.add(key)
        gift_id = id_by_name.get(key)
        if gift_id is None:
            while f"g{next_index}" in used_ids:
                next_index += 1
            gift_id = f"g{next_index}"
            next_index += 1
        used_ids.add(gift_id)
        new_catalog.append(
            {
                "id": gift_id,
                "name": name,
                "price": int(getattr(gift, "price", 0) or 0),
                "tier": str(getattr(gift, "tier", "standard") or "standard"),
            }
        )
        preference = getattr(gift, "preference", None)
        if preference in {"liked", "disliked", "neutral"}:
            preferences[gift_id] = str(preference)
    if not new_catalog:
        return
    sim["gift_catalog"] = new_catalog
    surviving_ids = {str(item["id"]) for item in new_catalog}
    sim["given_gifts"] = [
        str(item) for item in sim.get("given_gifts", []) if str(item) in surviving_ids
    ]
    hidden = sim.get("hidden_preferences")
    if not isinstance(hidden, dict):
        return
    liked = {
        str(item)
        for item in hidden.get("liked_gift_ids", [])
        if str(item) in surviving_ids
    }
    disliked = {
        str(item)
        for item in hidden.get("disliked_gift_ids", [])
        if str(item) in surviving_ids
    } - liked
    for gift_id, preference in preferences.items():
        liked.discard(gift_id)
        disliked.discard(gift_id)
        if preference == "liked":
            liked.add(gift_id)
        elif preference == "disliked":
            disliked.add(gift_id)
    hidden["liked_gift_ids"] = sorted(liked)
    hidden["disliked_gift_ids"] = sorted(disliked)


def apply_romance_outcome(
    state: dict[str, Any],
    output: Any,
    romance_resolution: dict[str, Any],
    romance_output: Any = None,
) -> None:
    """sim を更新し、milestones と ending_status を Python 算出値で上書きする。

    output は AdventureDirectorOutput 互換(completed_milestones/ending_status
    を持つ)を想定。romance_output は LLM の resolution 出力で、None や
    romance フィールド欠落にも耐える。
    """
    sim = state.get("sim")
    if not isinstance(sim, dict):
        return
    kind = str(romance_resolution.get("kind") or "talk")
    affection = int(sim.get("affection") or 0)
    llm_delta = int(getattr(romance_output, "affection_delta", 0) or 0)
    affection_set = getattr(romance_output, "affection_set", None)
    if kind == "talk":
        limit = ROMANCE_TALK_DELTA_LIMIT
        affection += max(-limit, min(limit, llm_delta))
    elif kind == "alter":
        if isinstance(affection_set, int):
            affection = affection_set
        else:
            limit = ROMANCE_ALTER_DELTA_LIMIT
            affection += max(-limit, min(limit, llm_delta))
        # カタログ書換を好み書換より先に適用する(ID 照合を新カタログで行うため)
        apply_gift_catalog_update(
            sim, list(getattr(romance_output, "updated_gift_catalog", None) or [])
        )
        _apply_preference_updates(sim, romance_output)
        # 宣言が攻略対象の外見を書き換えた場合は sim へ反映し、以後のターンの
        # 立ち絵フォールバック・ビジュアルプロンプトが新しい外見を使うようにする
        updated_appearance = getattr(romance_output, "updated_partner_appearance", None)
        if isinstance(updated_appearance, str) and updated_appearance.strip():
            sim["partner_appearance"] = updated_appearance.strip()
    else:
        # work / gift / confess は Python 計算値のみを使う
        affection += int(romance_resolution.get("affection_delta") or 0)
    sim["affection"] = _clamp_affection(affection)
    money = int(sim.get("money") or 0)
    if kind == "alter":
        # 現実改変だけは所持金の書き換えを認める。affection_set と同じ非対称扱い
        money_set = getattr(romance_output, "money_set", None)
        if isinstance(money_set, int):
            money = money_set
        else:
            limit = ROMANCE_ALTER_MONEY_LIMIT
            money += max(
                -limit,
                min(limit, int(getattr(romance_output, "money_delta", 0) or 0)),
            )
    else:
        # talk / work / gift / confess は Python 計算値のみを使う
        money += int(romance_resolution.get("money_delta") or 0)
    sim["money"] = _clamp_money(money)
    if kind == "gift":
        gift = romance_resolution.get("gift") or {}
        sim["given_gifts"] = [
            *[str(item) for item in sim.get("given_gifts", [])],
            str(gift.get("id")),
        ]
    confessed_success = kind == "confess" and bool(romance_resolution.get("success"))
    # 制限なし方針: 現実改変で「交際を始める」と宣言した場合も成立として扱う。
    # start_dating は reality_alter ターンでのみ有効
    declared_dating = kind == "alter" and bool(
        getattr(romance_output, "start_dating", False)
    )
    # 既に交際中なら成立イベントを再発火させない。エピローグ中に LLM が
    # start_dating を立て続けても、毎ターン成功エンドが再演されるのを防ぐ
    already_dating = bool(sim.get("confessed"))
    dating_started = (confessed_success or declared_dating) and not already_dating
    if dating_started:
        sim["confessed"] = True

    achieved = [
        milestone_id
        for stage_key, milestone_id in ROMANCE_STAGE_MILESTONE_IDS.items()
        if sim["affection"] >= ROMANCE_STAGE_THRESHOLDS[stage_key]
    ]
    if dating_started:
        achieved = [item["id"] for item in ROMANCE_MILESTONES]
    # LLM が申告した milestone/ending は信用せず、Python 算出値で置き換える
    output.completed_milestones = achieved
    output.ending_status = "success" if dating_started else "continue"


def opening_sim_view(sim: dict[str, Any]) -> dict[str, Any]:
    """開幕(手番0)時点の公開ビュー。

    開始値(好感度・所持金・贈答/告白なし)は定数のため、進行後の sim からも
    正確に再構成できる。相手・カタログ・バイトはターンで変化しない。
    例外は partner_appearance で、現実改変で書き換わると開幕時の値には戻せない
    ため現在値が入る。開幕フレームの表示にこの項目を使わないこと。
    """
    opening = {
        **sim,
        "affection": ROMANCE_AFFECTION_START,
        "money": ROMANCE_INITIAL_MONEY,
        "given_gifts": [],
        "confessed": False,
    }
    return public_sim_view(opening, 0)


def public_sim_view(
    sim: dict[str, Any], turn_count: int, *, epilogue: bool = False
) -> dict[str, Any]:
    """hidden_preferences を除いた公開ビュー。

    day/slot は次に行動する枠、scene_day/scene_slot は turn_count が確定させた枠
    (= その手番の画像と本文が描いている枠)を示す。両者は常に半日ずれるため、
    HUD とライトボックスが同じ絵について別の枠を出さないよう両方を配信する。
    epilogue ではシナリオ期限が意味を失うため、day/slot を total_days で
    クランプせずそのまま進める。
    """
    total_days = int(sim.get("total_days") or 0)
    total_turns = total_days * ROMANCE_SLOTS_PER_DAY
    next_turn = int(turn_count) + 1
    if total_turns and not epilogue:
        next_turn = min(next_turn, total_turns)
    day, slot = romance_day_slot(next_turn)
    scene_turn = int(turn_count)
    if total_turns and not epilogue:
        scene_turn = min(scene_turn, total_turns)
    scene_day, scene_slot = (
        romance_day_slot(scene_turn) if scene_turn >= 1 else (None, None)
    )
    affection = _clamp_affection(int(sim.get("affection") or 0))
    job = sim.get("job") if isinstance(sim.get("job"), dict) else {}
    return {
        "total_days": total_days,
        "day": day,
        "slot": slot,
        "scene_day": scene_day,
        "scene_slot": scene_slot,
        "epilogue": bool(epilogue),
        "affection": affection,
        "stage": romance_stage(affection),
        "money": _clamp_money(int(sim.get("money") or 0)),
        "partner_name": str(sim.get("partner_name") or ""),
        # 主人公の口調表示と対にして並べるため公開する。partner_profile は
        # 隠し好みの推理材料を含むので従来どおり非公開のまま
        "partner_speech_style": str(sim.get("partner_speech_style") or ""),
        # 現実改変で書き換わりうるため、主人公の外見表示と対にして配信する
        "partner_appearance": str(sim.get("partner_appearance") or ""),
        "player_name": str(sim.get("player_name") or ""),
        "player_character_id": str(sim.get("player_character_id") or ""),
        "job": {
            "name": str(job.get("name") or ""),
            "wage": int(job.get("wage") or ROMANCE_WORK_WAGE),
        },
        "gift_catalog": [
            {
                "id": str(item.get("id")),
                "name": str(item.get("name") or ""),
                "price": int(item.get("price") or 0),
                "tier": str(item.get("tier") or "standard"),
            }
            for item in sim.get("gift_catalog", [])
            if isinstance(item, dict)
        ],
        "given_gift_ids": [str(item) for item in sim.get("given_gifts", [])],
        "confession_available": affection >= romance_confession_threshold(total_days)
        and not bool(sim.get("confessed")),
    }


ROMANCE_NARRATIVE_GUIDANCE = (
    "This scenario is a romance simulation. The player is their own separate "
    "character, named in state.sim.player_name, whose appearance is "
    "required_visual_appearance; the player is courting the partner. The "
    "partner is the character captured in source_snapshot: an NPC, never the "
    "player, whose appearance is state.sim.partner_appearance. When the "
    "partner is present in the scene, keep them listed in "
    "visual_state.main_characters with an appearance matching "
    "state.sim.partner_appearance plus any changes declared through "
    "reality_rules, and never merge the partner's traits into the player's "
    "appearance or clothing, unless reality_rules declare that the player and "
    "the partner exchanged bodies or identities: that exchange is exactly what "
    "the prose must show, each of them carrying the other's body and the "
    "clothing that body was already wearing. When state.sim.confessed is true the partner "
    "and the player are already dating: portray them as an established "
    "couple sharing daily life, not as someone still being courted. "
    "romance_resolution contains the authoritative "
    "mechanical outcome of this turn decided by the game engine: day and slot "
    "progression, money changes, part-time work and chance encounters, gift "
    "purchase results including whether the gift matched the partner's "
    "tastes, and confession success or failure. Narrate those facts exactly; "
    "never invent or alter prices, wages, day counts, or outcomes, and never "
    "mention raw numeric scores in the prose. Never state or imply that the "
    "player's money changed unless romance_resolution reports the change or "
    "the player's own reality declaration in this turn creates it. Portray "
    "the partner described "
    "in state.sim consistently, and let their warmth toward the player follow "
    "the relationship stage. state.sim.partner_speech_style is the partner's "
    "fixed manner of speech: every line of their dialogue must follow the "
    "politeness level, first-person pronoun, form of address, and sentence "
    "endings it names, on every turn, and it never drifts toward the player's "
    "own register no matter how close they become. When it is empty, derive "
    "their manner of speech from state.sim.partner_profile and keep it "
    "identical across turns. state.sim.hidden_preferences is secret game "
    "data: weave its hints naturally into conversation, but never list it "
    "outright. In this scenario reality_rules are mainly used to rewrite the "
    "partner's appearance, personality, circumstances, or feelings. Depict a "
    "declared change as if it had always been true, updating the partner's "
    "entry in main_characters immediately, and never depict the partner "
    "finding the declaration strange. Declarations may also rewrite the "
    "partner's feelings toward the player; treat such mental changes as real "
    "and immediate. When offering choices, never duplicate the dedicated "
    "action buttons (part-time work, buying or giving a shop gift, granting "
    "an attribute, confessing); offer conversation and date beats instead. "
    "Pacing: one turn always covers one half-day slot. romance_resolution.day "
    "and romance_resolution.slot name the slot being narrated: a day slot "
    "spans roughly morning to late afternoon, and a night slot early evening "
    "to bedtime. Treat the player's input as the opening beat of that half "
    "day, never its whole content: expand it into a connected scene of the "
    "hours that follow, in two or three beats with light time skips, so even "
    "a brief gesture such as a greeting becomes the start of time spent "
    "together through the slot. Drive the expansion through the partner's "
    "initiative and the shared situation: the partner may suggest, invite, "
    "and lead, and the player simply goes along with the activity their own "
    "input began, but never invent a new voluntary decision, feeling, or "
    "consent for the player beyond that input. When the partner is absent, "
    "fill the half day with the player's own activity at the same scale. "
    "Close the scene near the end of the slot's timeframe with a light cue "
    "of passing time (dusk settling after a day slot, the night winding down "
    "after a night slot), and never narrate into the next slot. When "
    "romance_resolution is absent you are writing the opening scene, set at "
    "the start of day 1's day slot; establish the setting and the "
    "relationship at the same half-day scale. Any choices you offer must "
    "each be a plan that fills the upcoming half-day slot (sharing lunch, "
    "walking through town after class, cooking dinner together), never a "
    "momentary micro-action such as only greeting, waving, or shaking hands. "
    "Name that plan in a few words, as the examples above are worded; the slot "
    "it covers is set by the plan itself, not by how long the label is."
)

ROMANCE_VISUAL_GUIDANCE = (
    "This scene is from a romance simulation. The player is the primary "
    "subject as usual and required_visual_appearance is the player's identity "
    "signature. player_tags must restate the player's sex tokens from that "
    "signature (for example male, 1boy or female, 1girl) so the player is "
    "never drawn as a different sex, unless reality_rule_declared_this_turn "
    "changes the player's own body or identity, in which case restate the sex "
    "tokens of the player's new body instead. The romance partner is an NPC whose "
    "appearance is romance_partner.appearance plus any changes declared "
    "through reality_rules: when the partner is present in the scene, include "
    "them in main_characters and npc_tags with that appearance, and never "
    "merge the partner's hair, face, body, or clothing into player_tags or "
    "visual_state.appearance, unless reality_rules declare that the player and "
    "the partner exchanged bodies or identities, in which case that exchange is "
    "exactly what the tags must show: each of them carries the other's body and "
    "the clothing that body was already wearing. The partner's entry in npc_tags "
    "must always begin with the partner's explicit sex tokens (for example "
    "female, 1girl or male, 1boy) taken from the partner's body after any change "
    "declared through reality_rules, so a partner whose body has become male is "
    "never drawn female."
)

# 背景キャッシュは visual_state.location をキーにする。言い換えで別キーになると
# 同じ場所の背景を無駄に描き直すため、移動しない限り前手番の文字列を写させる
ROMANCE_LOCATION_STABILITY_GUIDANCE = (
    "visual_state.location is a stable place identifier used to decide whether "
    "the background must be redrawn. When the characters stay in the same "
    "place, copy previous_visual_state.location verbatim, character for "
    "character, even if the time of day, weather, lighting, or mood changed. "
    "Change it only when the narrative actually moves the characters somewhere "
    "else, and then name the new place in a few concrete words (a building or "
    "spot, not a time, weather, or feeling)."
)
ROMANCE_VISUAL_GUIDANCE = (
    f"{ROMANCE_VISUAL_GUIDANCE} {ROMANCE_LOCATION_STABILITY_GUIDANCE}"
)

# トークモード(手番を消費しない会話)の内容を次の手番へ渡すときの扱い。
# 物語の連続性には使うが、採点(好感度・金銭)には一切影響させない
ROMANCE_RECENT_TALK_GUIDANCE = (
    "recent_talk, when present, is a free chat the player and the partner had "
    "after the previous scene and before this one, in chronological order "
    "(role user = the player, role partner = the partner). Treat it as things "
    "they actually said to each other in the meantime: keep the partner's "
    "memory of it and let it colour tone and callbacks, but do not retell it "
    "as new events. It consumed no story time and is not a player action for "
    "this turn; the player's action is player_input. It must never change "
    "affection_delta, money, or any other score: score only this turn's action."
)

ROMANCE_RESOLUTION_GUIDANCE = (
    'Add these extra fields to the JSON object: "affection_delta" (integer), '
    '"affection_set" (integer or null), "money_delta" (integer), '
    '"money_set" (integer or null), "start_dating" (boolean), '
    '"updated_liked_gift_ids" (list of gift id strings), '
    '"updated_disliked_gift_ids" (list of gift id strings), '
    '"updated_partner_appearance" (string or null), '
    '"updated_total_days" (integer or null), '
    '"updated_gift_catalog" (list of {"name","price","tier","preference"} '
    "objects, normally an empty list). "
    "For an ordinary conversation turn score affection_delta with this "
    "rubric: +2 when the partner receives the player's words positively, +3 "
    "when they strike her stated interests, dropped hints, or hidden wishes, "
    "+1 for a flat but pleasant exchange, 0 only when the exchange is "
    "awkward or merely repeats an earlier beat, and negative only for rude "
    "or hurtful behavior. A friendly effort deserves at least +1; do not "
    "default to 0. Keep affection_set null, start_dating false, and both "
    "updated lists empty on conversation turns. When romance_resolution.kind "
    "is work, gift, or confess the engine has already decided every number: "
    "keep affection_delta 0, affection_set null, start_dating false, and the "
    "updated lists empty. When romance_resolution.kind is alter the player "
    "declared a reality alteration: if the declaration rewrites the "
    "partner's feelings toward the player, express the resulting feeling as "
    "affection_set (0-100, use 100 for complete love); if it explicitly "
    "establishes that the partner and the player are now lovers or dating, "
    "set start_dating true, but keep start_dating false whenever "
    "state.sim.confessed is already true; if it rewrites the partner's gift "
    "tastes, put "
    "the matching gift ids from state.sim.gift_catalog into the updated "
    "lists; if it changes the partner's body, hair, face, sex, age, species, "
    "or overall appearance in any way, including any swap, exchange, or "
    "transfer of bodies or identities between the partner and the player or "
    "anyone else, in which case the partner now has that other person's body, "
    "restate the partner's complete new appearance in "
    "updated_partner_appearance as concise English comma-separated tags "
    "beginning with explicit sex tokens (for example female, 1girl or male, "
    "1boy) and describing only the body, hair, eyes, build, and distinguishing "
    "features, never clothing; otherwise keep affection_set null, "
    "start_dating false, the lists empty, and updated_partner_appearance "
    "null. Keep updated_partner_appearance null on every non-alter turn. "
    "updated_total_days and updated_gift_catalog also apply only when "
    "romance_resolution.kind is alter. If the declaration changes the "
    "scenario's time limit (the total number of days the player has, shown "
    "as state.sim.total_days), report the new total as updated_total_days; "
    "otherwise keep it null. If the declaration rewrites the gift shop's "
    "lineup in any way (adding, removing, renaming, or repricing gifts), "
    "output in updated_gift_catalog the complete catalog after the change, "
    "listing every gift the shop now sells, reusing the exact names of "
    "unchanged gifts from state.sim.gift_catalog verbatim so they keep "
    "their identity; set each entry's price in yen and tier "
    "(budget, standard, or luxury), and set preference to liked, disliked, "
    "or neutral only when the declaration also states the partner's taste "
    "for that gift, leaving it null otherwise. Keep updated_gift_catalog an "
    "empty list whenever the declaration does not change the shop. "
    "Money follows the same rule as affection. Keep money_delta "
    "0 and money_set null on conversation turns and whenever "
    "romance_resolution.kind is work, gift, or confess, because the engine "
    "has already applied every payment. Only when romance_resolution.kind is "
    "alter and the declaration rewrites the player's finances, report the "
    "result as money_set (the player's new total in yen) when the "
    "declaration states an amount or a state of wealth, or as money_delta (a "
    "signed change in yen) when it states a gain or a loss. Leave "
    "completed_milestones empty and keep ending_status "
    "continue; the engine decides milestones and endings. choices must stay "
    "romance-flavoured actions for the next slot, and must never duplicate "
    "the dedicated action buttons (part-time work, buying or giving a shop "
    "gift, granting an attribute, confessing). "
    "romance_resolution.next_day and romance_resolution.next_slot (or "
    "romance_next_slot when only regenerating choices) identify the upcoming "
    "slot those choices belong to: a day slot spans roughly morning to late "
    "afternoon, and a night slot early evening to bedtime. Write every "
    "choice as a plan that fills that half day (for a day slot, plans like "
    "sharing lunch or an afternoon outing; for a night slot, plans like "
    "dinner together or an evening walk), never a momentary micro-action "
    "such as only greeting, waving, or shaking hands. Name that plan in a few "
    "words, as those examples are worded; the slot a choice covers is set by "
    "the plan itself, not by how long the label is. When neither field is "
    "supplied, keep the same half-day scale for the scene the narrative has "
    "just reached."
)


def romance_setup_system_prompt(language: str, days: int) -> str:
    """RomanceSetupOutput 生成用のシステムプロンプト。"""
    response_language = "Japanese" if language == "ja" else "English"
    return f"""You design the setup of a {days}-day romance simulation where the player tries to start dating one partner character.
Return one JSON object only, in {response_language}, matching this schema:
{{"partner_name":"...","partner_profile":"...","partner_speech_style":"...","relationship_origin":"...","job_name":"...","gift_catalog":[{{"name":"...","price":1500,"tier":"budget|standard|luxury"}}],"liked_gift_names":["..."],"disliked_gift_names":["..."],"likes_hint":"...","dislikes_hint":"..."}}
The partner is the character shown in source_snapshot; keep their appearance and situation consistent with it. source_snapshot deliberately contains no name for the partner: when the supplied setting or objective already names the partner, reuse that name as partner_name; otherwise invent a fitting new name from their appearance. Never use player_name as the partner's name. The player is a separate person courting that partner; never treat the snapshot character as the player. partner_profile describes personality and daily life. partner_speech_style states, in {response_language}, exactly how the partner speaks, in one short sentence a writer can follow verbatim: politeness level (敬体 or 常体), first-person pronoun, how they address the player, sentence endings, and any verbal tic. Make it match the personality in partner_profile, so a brash or casual personality actually speaks casually rather than politely. relationship_origin describes how the player and the partner currently know each other, at an acquaintance level that can grow into dating within {days} days. job_name is a part-time job the player can work at, where the partner occasionally appears. gift_catalog must contain 8 to 12 concrete purchasable gifts with prices inside their tier band: budget 500-2000, standard 2001-6000, luxury 6001-15000. liked_gift_names and disliked_gift_names must each pick exactly 2 or 3 names verbatim from gift_catalog, reflecting the partner's personality. likes_hint and dislikes_hint describe those tastes indirectly, as hints the partner might drop in conversation, without naming the exact gifts. Keep every value concise."""


def romance_script_names(sim: dict[str, Any], language: str) -> tuple[str, str]:
    """台本形式・トークで使う (攻略対象名, 主人公名)。主人公名が無ければ既定呼称。"""
    partner_name = str(sim.get("partner_name") or "").strip()
    player_name = str(sim.get("player_name") or "").strip()
    if not player_name:
        player_name = ROMANCE_PLAYER_NAME_FALLBACK.get(
            language, ROMANCE_PLAYER_NAME_FALLBACK["en"]
        )
    return partner_name, player_name


def romance_script_format_guidance(partner_name: str, player_name: str) -> str:
    """1on1 立ち絵モードの台本形式ルール。

    攻略対象のセリフを `名前「…」` の独立行にさせ、フロントが話者ラベル表示と
    読み上げ対象の抽出を機械的に行えるようにする。
    """
    return (
        "SCRIPT FORMAT: Write the scene as a visual-novel script. Put every "
        "spoken line on its own line, starting with the speaker's name followed "
        "immediately by the line in corner brackets, with nothing else on that "
        f"line: {partner_name}「...」 for the partner and {player_name}「...」 for "
        "the player. Never put two speakers on one line and never wrap a spoken "
        "line in quotation marks other than 「」. Everything that is not speech "
        "is narration: plain prose lines with no name prefix and no corner "
        "brackets, following the narration voice rule. Keep stage directions "
        "inside narration, not inside the brackets. Alternate narration and "
        "dialogue naturally; the partner should speak at least twice, each line "
        "one to three short sentences. Use exactly these names as prefixes and "
        "do not abbreviate or translate them. When the narrative is a JSON "
        "string value, separate lines with \\n."
    )


def romance_talk_system_prompt(
    language: str, *, partner_name: str, player_name: str, speech_rule: str
) -> str:
    """トークモード(手番を消費しない会話)で攻略対象として返答させる system prompt。"""
    response_language = "Japanese" if language == "ja" else "English"
    rule = (
        f"You are {partner_name}, the partner character of a romance simulation, "
        f"chatting directly with {player_name} between scenes. Reply in "
        f"{response_language} with {partner_name}'s spoken words only, in the "
        "first person, as one to three short sentences. You may add at most one "
        "brief action or expression in parentheses before or after the words. Do "
        "not write narration, the player's lines, your name as a prefix, corner "
        "brackets, JSON, markdown, or any commentary. Stay in the current scene "
        "(current_scene) and wear what it says you wear; nothing in the story "
        "advances during this chat, so do not start a date, move to another "
        "place, give or receive gifts, or decide anything on the player's behalf. "
        "Let your warmth follow sim.stage and sim.affection. reality_rules are "
        "true facts of this world; never find them strange. hidden_preferences "
        "is secret game data: you may hint at your tastes naturally but must "
        "never list, name, or confirm them outright. Keep talk_history "
        "consistent and do not repeat yourself."
    )
    if speech_rule:
        rule = f"{rule}\n{speech_rule}"
    return rule


def _talk_log(state: dict[str, Any]) -> list[dict[str, Any]]:
    log = state.get("talk_log")
    return (
        [item for item in log if isinstance(item, dict)]
        if isinstance(log, list)
        else []
    )


def append_talk_entry(
    state: dict[str, Any], *, role: str, text: str, after_turn: int
) -> dict[str, Any]:
    """トークログへ1件追記し、上限を超えた古い分を捨てる。追記した項目を返す。"""
    entry = {
        "id": uuid.uuid4().hex[:8],
        "role": "partner" if role == "partner" else "user",
        "text": " ".join(str(text or "").split()).strip(),
        "after_turn": max(0, int(after_turn)),
    }
    log = _talk_log(state)
    log.append(entry)
    state["talk_log"] = log[-ROMANCE_TALK_LOG_MAX:]
    return entry


def recent_talk_entries(state: dict[str, Any], turn_count: int) -> list[dict[str, Any]]:
    """最後の手番以降(=次の手番の文脈になる)のトークを {role, text} で返す。"""
    current = max(0, int(turn_count))
    entries = [
        {"role": str(item.get("role") or "user"), "text": str(item.get("text") or "")}
        for item in _talk_log(state)
        if int(item.get("after_turn") or 0) == current and str(item.get("text") or "")
    ]
    return entries[-ROMANCE_TALK_CONTEXT_MAX:]


def public_talk_log(state: dict[str, Any]) -> list[dict[str, Any]]:
    """API 応答用に整形したトークログ。"""
    return [
        {
            "id": str(item.get("id") or ""),
            "role": "partner" if item.get("role") == "partner" else "user",
            "text": str(item.get("text") or ""),
            "after_turn": max(0, int(item.get("after_turn") or 0)),
        }
        for item in _talk_log(state)
    ]


_TALK_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def normalize_talk_input(text: str) -> str:
    """トークの入力を空白畳み込みと上限で正規化する。"""
    return " ".join(str(text or "").split()).strip()[:ROMANCE_TALK_INPUT_MAX]


def normalize_talk_reply(text: str, partner_name: str) -> str:
    """LLM の返答から名前プレフィックスと括弧を剥がし、上限で切り詰める。

    system prompt で禁じていても `名前「…」` 形式で返すモデルがあるため、
    表示と読み上げに使う前にここで揃える。
    """
    reply = _TALK_FENCE_RE.sub("", str(text or "").strip()).strip()
    name = str(partner_name or "").strip()
    if name:
        prefix = re.compile(rf"^\s*{re.escape(name)}\s*[「『:：]\s*")
        reply = prefix.sub("", reply, count=1)
    reply = reply.strip()
    if reply[:1] in "「『" and reply[-1:] in "」』":
        reply = reply[1:-1].strip()
    elif reply[-1:] in "」』" and reply.count("「") + reply.count("『") < reply.count(
        "」"
    ) + reply.count("』"):
        # 名前プレフィックスを剥がした後に閉じ括弧だけが残ったケース
        reply = reply[:-1].strip()
    reply = " ".join(reply.split())
    return reply[:ROMANCE_TALK_REPLY_MAX].strip()
