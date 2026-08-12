"""romance プリセット(恋愛シミュレーション)の決定論ロジック。

金銭・日数・好感度・ギフト採点・告白成否は LLM に委ねず、ここの純関数が
確定する。adventure_service.stream_turn からは薄いフック呼び出しだけを行い、
day/slot は状態に保存せず turn_number から導出する(冪等リトライと整合)。
"""

from __future__ import annotations

import random
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..consts.adventure_romance import (
    ROMANCE_AFFECTION_MAX,
    ROMANCE_AFFECTION_MIN,
    ROMANCE_AFFECTION_START,
    ROMANCE_ALTER_DELTA_LIMIT,
    ROMANCE_CONFESSION_FAIL_PENALTY,
    ROMANCE_CONFESSION_THRESHOLD,
    ROMANCE_DAYS_MAX,
    ROMANCE_DAYS_MIN,
    ROMANCE_GIFT_POINTS,
    ROMANCE_GIFT_TIER_PRICES,
    ROMANCE_INITIAL_MONEY,
    ROMANCE_MILESTONES,
    ROMANCE_SLOTS_PER_DAY,
    ROMANCE_STAGE_MILESTONE_IDS,
    ROMANCE_STAGE_THRESHOLDS,
    ROMANCE_TALK_DELTA_LIMIT,
    ROMANCE_WORK_ENCOUNTER_BONUS,
    ROMANCE_WORK_ENCOUNTER_RATE,
    ROMANCE_WORK_WAGE,
)


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


class RomanceSetupOutput(BaseModel):
    """LLM が1回だけ生成する恋愛シナリオの初期素材。

    好みの ID 採番と名前→ID の名寄せは Python 後処理で行う。
    """

    partner_name: str = Field(min_length=1, max_length=80)
    partner_profile: str = Field(min_length=1, max_length=600)
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
) -> dict[str, Any]:
    """state_json["sim"] の初期値を組み立てる。hidden_preferences は隠し情報。

    開始セッションの人物は攻略対象(partner)であり、主人公(player)は
    別途選択されたテンプレートキャラクター。
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
        "partner_appearance": partner_appearance,
        "relationship_origin": setup.relationship_origin,
        "player_name": player_name,
        "player_character_id": player_character_id,
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
    resolution: dict[str, Any] = {
        "kind": "talk",
        "day": day,
        "slot": slot,
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
        repeated = str(gift.get("id")) in given
        if repeated:
            # 再贈呈は中立扱いにして連打による加点稼ぎを防ぐ
            match = "neutral"
        elif str(gift.get("id")) in set(hidden.get("liked_gift_ids", [])):
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
                "repeated_gift": repeated,
            }
        )
        return resolution
    if input_kind == "confess":
        success = int(sim.get("affection") or 0) >= ROMANCE_CONFESSION_THRESHOLD
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
        _apply_preference_updates(sim, romance_output)
    else:
        # work / gift / confess は Python 計算値のみを使う
        affection += int(romance_resolution.get("affection_delta") or 0)
    sim["affection"] = _clamp_affection(affection)
    sim["money"] = int(sim.get("money") or 0) + int(
        romance_resolution.get("money_delta") or 0
    )
    if kind == "gift":
        gift = romance_resolution.get("gift") or {}
        sim["given_gifts"] = [
            *[str(item) for item in sim.get("given_gifts", [])],
            str(gift.get("id")),
        ]
    confessed_success = kind == "confess" and bool(romance_resolution.get("success"))
    if confessed_success:
        sim["confessed"] = True

    achieved = [
        milestone_id
        for stage_key, milestone_id in ROMANCE_STAGE_MILESTONE_IDS.items()
        if sim["affection"] >= ROMANCE_STAGE_THRESHOLDS[stage_key]
    ]
    if confessed_success:
        achieved = [item["id"] for item in ROMANCE_MILESTONES]
    # LLM が申告した milestone/ending は信用せず、Python 算出値で置き換える
    output.completed_milestones = achieved
    output.ending_status = "success" if confessed_success else "continue"


def public_sim_view(sim: dict[str, Any], turn_count: int) -> dict[str, Any]:
    """hidden_preferences を除いた公開ビュー。day/slot は次に行動する枠を示す。"""
    total_days = int(sim.get("total_days") or 0)
    total_turns = total_days * ROMANCE_SLOTS_PER_DAY
    next_turn = int(turn_count) + 1
    if total_turns:
        next_turn = min(next_turn, total_turns)
    day, slot = romance_day_slot(next_turn)
    affection = _clamp_affection(int(sim.get("affection") or 0))
    job = sim.get("job") if isinstance(sim.get("job"), dict) else {}
    return {
        "total_days": total_days,
        "day": day,
        "slot": slot,
        "affection": affection,
        "stage": romance_stage(affection),
        "money": int(sim.get("money") or 0),
        "partner_name": str(sim.get("partner_name") or ""),
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
        "confession_available": affection >= ROMANCE_CONFESSION_THRESHOLD
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
    "appearance or clothing. romance_resolution contains the authoritative "
    "mechanical outcome of this turn decided by the game engine: day and slot "
    "progression, money changes, part-time work and chance encounters, gift "
    "purchase results including whether the gift matched the partner's "
    "tastes, and confession success or failure. Narrate those facts exactly; "
    "never invent or alter prices, wages, day counts, or outcomes, and never "
    "mention raw numeric scores in the prose. Portray the partner described "
    "in state.sim consistently, and let their warmth toward the player follow "
    "the relationship stage. state.sim.hidden_preferences is secret game "
    "data: weave its hints naturally into conversation, but never list it "
    "outright. In this scenario reality_rules are mainly used to rewrite the "
    "partner's appearance, personality, circumstances, or feelings. Depict a "
    "declared change as if it had always been true, updating the partner's "
    "entry in main_characters immediately, and never depict the partner "
    "finding the declaration strange. Declarations may also rewrite the "
    "partner's feelings toward the player; treat such mental changes as real "
    "and immediate."
)

ROMANCE_VISUAL_GUIDANCE = (
    "This scene is from a romance simulation. The player is the primary "
    "subject as usual and required_visual_appearance is the player's identity "
    "signature. The romance partner is an NPC whose appearance is "
    "state.sim.partner_appearance plus any changes declared through "
    "reality_rules: when the partner is present in the scene, include them in "
    "main_characters and npc_tags with that appearance, and never merge the "
    "partner's hair, face, body, or clothing into player_tags or "
    "visual_state.appearance."
)

ROMANCE_RESOLUTION_GUIDANCE = (
    'Add these extra fields to the JSON object: "affection_delta" (integer), '
    '"affection_set" (integer or null), "updated_liked_gift_ids" (list of '
    'gift id strings), "updated_disliked_gift_ids" (list of gift id strings). '
    "For an ordinary conversation turn set affection_delta between -3 and 3 "
    "based on how the partner received the player's words, keep affection_set "
    "null, and keep both updated lists empty. When romance_resolution.kind is "
    "work, gift, or confess the engine has already decided every number: keep "
    "affection_delta 0, affection_set null, and the updated lists empty. When "
    "romance_resolution.kind is alter the player declared a reality "
    "alteration: if the declaration rewrites the partner's feelings toward "
    "the player, express the resulting feeling as affection_set (0-100, use "
    "100 for complete love); if it rewrites the partner's gift tastes, put "
    "the matching gift ids from state.sim.gift_catalog into the updated "
    "lists; otherwise keep affection_set null and the lists empty. Leave "
    "completed_milestones empty and keep ending_status continue; the engine "
    "decides milestones and endings. choices must stay romance-flavoured "
    "actions for the next slot."
)


def romance_setup_system_prompt(language: str, days: int) -> str:
    """RomanceSetupOutput 生成用のシステムプロンプト。"""
    response_language = "Japanese" if language == "ja" else "English"
    return f"""You design the setup of a {days}-day romance simulation where the player tries to start dating one partner character.
Return one JSON object only, in {response_language}, matching this schema:
{{"partner_name":"...","partner_profile":"...","relationship_origin":"...","job_name":"...","gift_catalog":[{{"name":"...","price":1500,"tier":"budget|standard|luxury"}}],"liked_gift_names":["..."],"disliked_gift_names":["..."],"likes_hint":"...","dislikes_hint":"..."}}
The partner is the character shown in source_snapshot; keep their appearance and situation consistent with it. The player is a separate person courting that partner; never treat the snapshot character as the player. partner_profile describes personality, daily life, and how they speak. relationship_origin describes how the player and the partner currently know each other, at an acquaintance level that can grow into dating within {days} days. job_name is a part-time job the player can work at, where the partner occasionally appears. gift_catalog must contain 8 to 12 concrete purchasable gifts with prices inside their tier band: budget 500-2000, standard 2001-6000, luxury 6001-15000. liked_gift_names and disliked_gift_names must each pick exactly 2 or 3 names verbatim from gift_catalog, reflecting the partner's personality. likes_hint and dislikes_hint describe those tastes indirectly, as hints the partner might drop in conversation, without naming the exact gifts. Keep every value concise."""
