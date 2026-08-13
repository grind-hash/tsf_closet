"""romance プリセット(恋愛シミュレーション)の決定論ロジック。

金銭・日数・好感度・ギフト採点・告白成否は LLM に委ねず、ここの純関数が
確定する。adventure_service.stream_turn からは薄いフック呼び出しだけを行い、
day/slot は状態に保存せず turn_number から導出する(冪等リトライと整合)。
"""

from __future__ import annotations

import random
import re
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
    ROMANCE_RESERVED_CHOICE_PATTERNS,
    ROMANCE_SLOT_CONFLICT_TAGS,
    ROMANCE_SLOT_SCENE_TAGS,
    ROMANCE_SLOTS_PER_DAY,
    ROMANCE_STAGE_MILESTONE_IDS,
    ROMANCE_STAGE_THRESHOLDS,
    ROMANCE_TALK_DELTA_LIMIT,
    ROMANCE_WORK_ENCOUNTER_BONUS,
    ROMANCE_WORK_ENCOUNTER_RATE,
    ROMANCE_WORK_WAGE,
)

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
    "appearance or clothing. When state.sim.confessed is true the partner "
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
    "the relationship stage. state.sim.hidden_preferences is secret game "
    "data: weave its hints naturally into conversation, but never list it "
    "outright. In this scenario reality_rules are mainly used to rewrite the "
    "partner's appearance, personality, circumstances, or feelings. Depict a "
    "declared change as if it had always been true, updating the partner's "
    "entry in main_characters immediately, and never depict the partner "
    "finding the declaration strange. Declarations may also rewrite the "
    "partner's feelings toward the player; treat such mental changes as real "
    "and immediate. When offering choices, never duplicate the dedicated "
    "action buttons (part-time work, buying or giving a shop gift, granting "
    "an attribute, confessing); offer conversation and date beats instead."
)

ROMANCE_VISUAL_GUIDANCE = (
    "This scene is from a romance simulation. The player is the primary "
    "subject as usual and required_visual_appearance is the player's identity "
    "signature. player_tags must restate the player's sex tokens from that "
    "signature (for example male, 1boy or female, 1girl) so the player is "
    "never drawn as a different sex. The romance partner is an NPC whose "
    "appearance is state.sim.partner_appearance plus any changes declared "
    "through reality_rules: when the partner is present in the scene, include "
    "them in main_characters and npc_tags with that appearance, and never "
    "merge the partner's hair, face, body, or clothing into player_tags or "
    "visual_state.appearance."
)

ROMANCE_RESOLUTION_GUIDANCE = (
    'Add these extra fields to the JSON object: "affection_delta" (integer), '
    '"affection_set" (integer or null), "money_delta" (integer), '
    '"money_set" (integer or null), "start_dating" (boolean), '
    '"updated_liked_gift_ids" (list of gift id strings), '
    '"updated_disliked_gift_ids" (list of gift id strings). '
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
    "lists; otherwise keep affection_set null, start_dating false, and the "
    "lists empty. Money follows the same rule as affection. Keep money_delta "
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
    "gift, granting an attribute, confessing)."
)


def romance_setup_system_prompt(language: str, days: int) -> str:
    """RomanceSetupOutput 生成用のシステムプロンプト。"""
    response_language = "Japanese" if language == "ja" else "English"
    return f"""You design the setup of a {days}-day romance simulation where the player tries to start dating one partner character.
Return one JSON object only, in {response_language}, matching this schema:
{{"partner_name":"...","partner_profile":"...","relationship_origin":"...","job_name":"...","gift_catalog":[{{"name":"...","price":1500,"tier":"budget|standard|luxury"}}],"liked_gift_names":["..."],"disliked_gift_names":["..."],"likes_hint":"...","dislikes_hint":"..."}}
The partner is the character shown in source_snapshot; keep their appearance and situation consistent with it. source_snapshot deliberately contains no name for the partner: when the supplied setting or objective already names the partner, reuse that name as partner_name; otherwise invent a fitting new name from their appearance. Never use player_name as the partner's name. The player is a separate person courting that partner; never treat the snapshot character as the player. partner_profile describes personality, daily life, and how they speak. relationship_origin describes how the player and the partner currently know each other, at an acquaintance level that can grow into dating within {days} days. job_name is a part-time job the player can work at, where the partner occasionally appears. gift_catalog must contain 8 to 12 concrete purchasable gifts with prices inside their tier band: budget 500-2000, standard 2001-6000, luxury 6001-15000. liked_gift_names and disliked_gift_names must each pick exactly 2 or 3 names verbatim from gift_catalog, reflecting the partner's personality. likes_hint and dislikes_hint describe those tastes indirectly, as hints the partner might drop in conversation, without naming the exact gifts. Keep every value concise."""
