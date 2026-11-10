"""AI箱庭の「物語の厚み」の状態遷移(純粋関数)。

世界の違和感と対面・本人の適応・世界の側の適応・名残・住民の記憶・物語の弧を扱う。
各関数は引数を書き換えずに新しい状態を返す。文の組み立ては hakoniwa_story_text が担い、
ここでは種類と参照(住民 id・数値)だけを状態に残す。

状態に足す項目:
    dissonance_enabled, dissonance, dissonance_last_change_day, dissonance_acknowledged,
    world_adaptation: {姿キー: {kind, stage, progress, since_day}},
    memories: {住民 id: [{day, kind, weight, partner_id?, change?, title?, delta?,
                          rule_id?, rule_name?}]},
    story_arcs: [{id, kind, resident_ids, started_day, progress, beats_to_climax,
                  status, closed_day, close_reason, log: [{day, title, event_id}]}]
住民に足す項目:
    adaptation: {kind, stage, progress, since_day} | None
    remnant: {kind, stage, variant, partner_id, set_day, days_left} | None
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

from ..consts.hakoniwa import HAKONIWA_PRESET_MAP, HAKONIWA_RULE_MAP
from ..consts.hakoniwa_story import (
    ADAPTATION_MAX_STAGE,
    ADAPTATION_SPEED_DEFAULT,
    ADAPTATION_SPEED_KEYWORDS,
    ARC_BEATS_TO_CLIMAX,
    ARC_BOND_AFFINITY_THRESHOLD,
    ARC_CLOSED_KEEP,
    ARC_LOG_MAX,
    ARC_MAX_ACTIVE,
    ARC_MAX_AGE_DAYS,
    ARC_REOPEN_COOLDOWN_DAYS,
    DISSONANCE_AFTER_CONFRONTATION,
    DISSONANCE_CONFRONTATION_THRESHOLD,
    DISSONANCE_DAILY_DECAY,
    DISSONANCE_INVESTIGATION_STAGES,
    DISSONANCE_MAX,
    DISSONANCE_MIN,
    DISSONANCE_STAGES,
    INVESTIGATOR_KEYWORDS,
    INVESTIGATOR_PREFERENCE,
    MEMORY_AFFINITY_THRESHOLD,
    MEMORY_MAX,
    MEMORY_TEXT_MAX,
    MEMORY_WEIGHT_MAJOR,
    MEMORY_WEIGHT_MINOR,
    MEMORY_WEIGHT_NOTABLE,
    REMNANT_BASE_DAYS,
    REMNANT_HABIT_VARIANTS,
    WORLD_ADAPTATION_DAILY_PROGRESS,
    WORLD_ADAPTATION_MAX_STAGE,
)

ADAPTATION_KINDS = ("swap", "transform")
ARC_KINDS = ("investigation", "swap", "transform", "bond")
MEMORY_KINDS = (
    "transform_self",
    "transform_witness",
    "confrontation",
    "bond",
    "rule_start",
    "rule_end",
    "swap_start",
    "swap_end",
)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _day(state: dict[str, Any]) -> int:
    return max(1, _int(state.get("day"), 1))


def _personality_text(resident: dict[str, Any]) -> str:
    """性格の文。プリセットで編集していなければ日本語の既定文(言語で結果を変えない)。"""
    if resident.get("personality"):
        return str(resident["personality"])
    preset = HAKONIWA_PRESET_MAP.get(str(resident.get("preset_id") or ""))
    return str(preset["text"]["ja"]["personality"]) if preset else ""


def _swap_active(state: dict[str, Any]) -> list[str] | None:
    pair = state.get("swap_pair")
    if "swap" in state.get("active_rules", []) and pair and len(pair) == 2:
        return [str(pair[0]), str(pair[1])]
    return None


def body_of(state: dict[str, Any], resident: dict[str, Any]) -> dict[str, Any]:
    """住民がいまいる体のエントリ。入れ替わり中は相手のエントリ。

    変身は体に付く(体のエントリに保存する)ので、人として見た「いまの変身」はここから読む。
    """
    pair = _swap_active(state)
    if pair and resident["id"] in pair:
        partner_id = pair[1] if resident["id"] == pair[0] else pair[0]
        partner = next(
            (item for item in state.get("residents", []) if item["id"] == partner_id),
            None,
        )
        if partner is not None:
            return partner
    return resident


def current_transformation(
    state: dict[str, Any], resident: dict[str, Any]
) -> dict[str, Any] | None:
    """住民がいまいる体の変身(無ければ None)。"""
    transformation = body_of(state, resident).get("transformation")
    return (
        transformation if isinstance(transformation, dict) and transformation else None
    )


# --- 状態の正規化 ---


def normalize_story(source: dict[str, Any], normalized: dict[str, Any]) -> None:
    """読み込んだ状態の物語の項目を、正規化中の状態 normalized へ写す。"""
    ids = {resident["id"] for resident in normalized["residents"]}
    normalized["dissonance_enabled"] = source.get("dissonance_enabled") is not False
    normalized["dissonance"] = int(
        _clamp(_int(source.get("dissonance")), DISSONANCE_MIN, DISSONANCE_MAX)
    )
    last_change = source.get("dissonance_last_change_day")
    normalized["dissonance_last_change_day"] = (
        _int(last_change) if last_change is not None else None
    )
    normalized["dissonance_acknowledged"] = bool(source.get("dissonance_acknowledged"))
    world_adaptation = source.get("world_adaptation")
    normalized["world_adaptation"] = {
        str(key): dict(value)
        for key, value in (
            world_adaptation.items() if isinstance(world_adaptation, dict) else []
        )
        if isinstance(value, dict)
    }
    memories = source.get("memories")
    normalized["memories"] = {
        str(key): [dict(item) for item in value if isinstance(item, dict)]
        for key, value in (memories.items() if isinstance(memories, dict) else [])
        if str(key) in ids and isinstance(value, list)
    }
    normalized["story_arcs"] = [
        deepcopy(arc)
        for arc in source.get("story_arcs") or []
        if isinstance(arc, dict) and arc.get("kind") in ARC_KINDS
    ]
    for resident in normalized["residents"]:
        if not isinstance(resident.get("adaptation"), dict):
            resident["adaptation"] = None
        if not isinstance(resident.get("remnant"), dict):
            resident["remnant"] = None


def initial_story_state(*, dissonance_enabled: bool = True) -> dict[str, Any]:
    return {
        "dissonance_enabled": bool(dissonance_enabled),
        "dissonance": 0,
        "dissonance_last_change_day": None,
        "dissonance_acknowledged": False,
        "world_adaptation": {},
        "memories": {},
        "story_arcs": [],
    }


# --- 世界の違和感 ---


def dissonance_enabled(state: dict[str, Any]) -> bool:
    return state.get("dissonance_enabled") is not False


def dissonance_value(state: dict[str, Any]) -> int:
    return int(_clamp(_int(state.get("dissonance")), DISSONANCE_MIN, DISSONANCE_MAX))


def dissonance_stage(value: int) -> str:
    for minimum, stage in DISSONANCE_STAGES:
        if value >= minimum:
            return stage
    return "stillness"


def next_dissonance_stage(value: int) -> dict[str, Any] | None:
    """次の段階と、そこまでの残り。最上段なら None。"""
    for minimum, stage in sorted(DISSONANCE_STAGES):
        if minimum > value:
            return {"stage": stage, "remaining": minimum - value}
    return None


def investigation_active(state: dict[str, Any]) -> bool:
    """調べ役の寄せと調査の弧が働くか(違和感が有効・公認前・探り合い以上)。"""
    return (
        dissonance_enabled(state)
        and not state.get("dissonance_acknowledged")
        and dissonance_stage(dissonance_value(state)) in DISSONANCE_INVESTIGATION_STAGES
    )


def dissonance_gain_factor(state: dict[str, Any]) -> float:
    """世界の側の適応が進んだ姿があるほど、書き換えに気づかれにくくなる。"""
    best = -1
    for resident in state.get("residents", []):
        entry = world_adaptation_entry(state, resident)
        if entry is not None:
            best = max(best, entry["stage"])
    if best >= 3:
        return 0.25
    if best == 2:
        return 0.5
    return 1.0


def add_dissonance(state: dict[str, Any], amount: int) -> dict[str, Any]:
    """書き換えの加算。世界の適応で緩めても最低1は残す。違和感が無効なら何もしない。"""
    if not dissonance_enabled(state) or amount <= 0:
        return state
    gain = max(1, int(amount * dissonance_gain_factor(state)))
    return {
        **state,
        "dissonance": int(
            _clamp(dissonance_value(state) + gain, DISSONANCE_MIN, DISSONANCE_MAX)
        ),
        "dissonance_last_change_day": _day(state),
    }


def decay_dissonance(state: dict[str, Any]) -> dict[str, Any]:
    """書き換えの無かった日の終わりに少し静める(日を進める前に呼ぶ)。"""
    if not dissonance_enabled(state):
        return state
    if state.get("dissonance_last_change_day") == _day(state):
        return state
    return {
        **state,
        "dissonance": int(
            _clamp(
                dissonance_value(state) - DISSONANCE_DAILY_DECAY,
                DISSONANCE_MIN,
                DISSONANCE_MAX,
            )
        ),
    }


def confrontation_pending(state: dict[str, Any]) -> bool:
    return (
        dissonance_enabled(state)
        and not state.get("dissonance_acknowledged")
        and len(state.get("residents", [])) >= 2
        and dissonance_value(state) >= DISSONANCE_CONFRONTATION_THRESHOLD
    )


def resolve_confrontation(state: dict[str, Any]) -> dict[str, Any]:
    return {
        **state,
        "dissonance": DISSONANCE_AFTER_CONFRONTATION,
        "dissonance_acknowledged": True,
        "dissonance_last_change_day": _day(state),
    }


def investigator(state: dict[str, Any]) -> dict[str, Any] | None:
    """世界の変化を調べる役回りの住民(薫→栞→性格に好奇心→先頭)。"""
    residents = state.get("residents", [])
    by_id = {resident["id"]: resident for resident in residents}
    for resident_id in INVESTIGATOR_PREFERENCE:
        if resident_id in by_id:
            return by_id[resident_id]
    for resident in residents:
        text = _personality_text(resident).lower()
        if any(keyword in text for keyword in INVESTIGATOR_KEYWORDS):
            return resident
    return residents[0] if residents else None


def confrontation_pair(
    state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    residents = state.get("residents", [])
    lead = investigator(state)
    if lead is None or len(residents) < 2:
        return None
    partner = next(item for item in residents if item["id"] != lead["id"])
    return lead, partner


def ensure_investigator(
    state: dict[str, Any], groups: list[tuple[dict[str, Any], ...]]
) -> list[tuple[dict[str, Any], ...]]:
    """探り合い以上では、調べ役がどこかの組に入るよう最後の組を差し替える。

    入れ替わりの当事者の組は差し替えない。
    """
    if not groups or not investigation_active(state):
        return groups
    lead = investigator(state)
    if lead is None or any(
        lead["id"] in {item["id"] for item in group} for group in groups
    ):
        return groups
    partner = next(
        (item for item in state["residents"] if item["id"] != lead["id"]), None
    )
    if partner is None:
        return groups
    swap_key = frozenset(_swap_active(state) or [])
    for index in range(len(groups) - 1, -1, -1):
        if frozenset(item["id"] for item in groups[index]) != swap_key:
            updated = list(groups)
            updated[index] = (lead, partner)
            return updated
    return groups


def is_investigation_group(
    state: dict[str, Any], group: tuple[dict[str, Any], ...]
) -> bool:
    if not investigation_active(state):
        return False
    lead = investigator(state)
    return lead is not None and lead["id"] in {item["id"] for item in group}


# --- 本人の適応 ---


def adaptation_speed(resident: dict[str, Any]) -> float:
    text = _personality_text(resident).lower()
    for keywords, speed in ADAPTATION_SPEED_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return speed
    return ADAPTATION_SPEED_DEFAULT


def new_adaptation(kind: str, day: int) -> dict[str, Any]:
    return {"kind": kind, "stage": 0, "progress": 0.0, "since_day": int(day)}


def _adaptation_condition_met(state: dict[str, Any], resident: dict[str, Any]) -> bool:
    adaptation = resident.get("adaptation")
    if not isinstance(adaptation, dict):
        return False
    if adaptation.get("kind") == "transform":
        return current_transformation(state, resident) is not None
    if adaptation.get("kind") == "swap":
        return resident["id"] in (_swap_active(state) or [])
    return False


def resident_adaptation(
    state: dict[str, Any], resident: dict[str, Any]
) -> dict[str, Any] | None:
    if _adaptation_condition_met(state, resident):
        return resident["adaptation"]
    return None


def advance_adaptations(
    state: dict[str, Any], bonus: float = 0.0
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """日の終わりに適応を進める。条件の消えた適応は外す。段階が上がった住民を返す。"""
    new_state = deepcopy(state)
    progressions: list[dict[str, Any]] = []
    extra = max(0.0, float(bonus or 0.0))
    for resident in new_state["residents"]:
        adaptation = resident.get("adaptation")
        if not isinstance(adaptation, dict):
            continue
        if not _adaptation_condition_met(new_state, resident):
            resident["adaptation"] = None
            continue
        stage = _int(adaptation.get("stage"))
        if stage >= ADAPTATION_MAX_STAGE:
            continue
        progress = (
            _float(adaptation.get("progress")) + adaptation_speed(resident) + extra
        )
        new_stage = stage
        while progress >= 1.0 and new_stage < ADAPTATION_MAX_STAGE:
            new_stage += 1
            progress -= 1.0
        if new_stage >= ADAPTATION_MAX_STAGE:
            progress = 0.0
        resident["adaptation"] = {
            **adaptation,
            "stage": new_stage,
            "progress": round(progress, 4),
        }
        if new_stage > stage:
            progressions.append(
                {
                    "id": resident["id"],
                    "kind": adaptation.get("kind"),
                    "stage": new_stage,
                }
            )
    return new_state, progressions


# --- 世界の側の適応 ---


def form_key(state: dict[str, Any], resident: dict[str, Any]) -> str | None:
    """いま世界に出ている姿のキー。変身を入れ替わりより優先する。通常の姿は None。"""
    transformation = current_transformation(state, resident)
    if transformation:
        marker = str(transformation.get("image") or "") or (
            f"day{_int(transformation.get('day'))}"
        )
        return f"transform:{resident['id']}:{marker}"
    pair = _swap_active(state)
    if pair and resident["id"] in pair:
        a_id, b_id = sorted(pair)
        return f"swap:{a_id}:{b_id}"
    return None


def world_adaptation_entry(
    state: dict[str, Any], resident: dict[str, Any]
) -> dict[str, Any] | None:
    """住民のいまの姿への世界の適応。記録の無い姿は段階0として扱う。"""
    key = form_key(state, resident)
    if key is None:
        return None
    stored = (state.get("world_adaptation") or {}).get(key)
    kind = key.split(":", 1)[0]
    if not isinstance(stored, dict):
        return {"key": key, "kind": kind, "stage": 0, "progress": 0.0}
    return {
        "key": key,
        "kind": kind,
        "stage": int(_clamp(_int(stored.get("stage")), 0, WORLD_ADAPTATION_MAX_STAGE)),
        "progress": _clamp(_float(stored.get("progress")), 0.0, 1.0),
    }


def advance_world_adaptations(
    state: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """姿が続く限り世界の適応を進め、消えた姿の記録を捨てる。段階が上がった姿を返す。"""
    day = _day(state)
    active: dict[str, list[str]] = {}
    for resident in state.get("residents", []):
        key = form_key(state, resident)
        if key is not None:
            active.setdefault(key, []).append(resident["id"])
    stored_all = state.get("world_adaptation") or {}
    entries: dict[str, dict[str, Any]] = {}
    progressions: list[dict[str, Any]] = []
    for key, resident_ids in active.items():
        stored = stored_all.get(key) if isinstance(stored_all.get(key), dict) else {}
        stage = int(_clamp(_int(stored.get("stage")), 0, WORLD_ADAPTATION_MAX_STAGE))
        progress = _float(stored.get("progress"))
        since_day = _int(stored.get("since_day"), day)
        start = stage
        if stage < WORLD_ADAPTATION_MAX_STAGE:
            progress += WORLD_ADAPTATION_DAILY_PROGRESS
            while progress >= 1.0 and stage < WORLD_ADAPTATION_MAX_STAGE:
                stage += 1
                progress -= 1.0
            if stage >= WORLD_ADAPTATION_MAX_STAGE:
                progress = 0.0
        kind = key.split(":", 1)[0]
        entries[key] = {
            "kind": kind,
            "stage": stage,
            "progress": round(progress, 4),
            "since_day": since_day,
        }
        if stage > start:
            progressions.append({"ids": resident_ids, "kind": kind, "stage": stage})
    return {**state, "world_adaptation": entries}, progressions


# --- 名残 ---


def make_remnant(
    kind: str, stage: int, resident_id: str, day: int, partner_id: str | None = None
) -> dict[str, Any]:
    """適応が解けた住民に残す名残。適応が進んでいたほど具体的で、長く残る。"""
    stage = int(_clamp(stage, 0, ADAPTATION_MAX_STAGE))
    if stage <= 0:
        variant = "faint"
    elif stage == 1:
        variant = "recall" if (kind == "transform" or partner_id) else "faint"
    else:
        options = REMNANT_HABIT_VARIANTS.get(kind, REMNANT_HABIT_VARIANTS["transform"])
        variant = options[
            (stage + sum(ord(char) for char in resident_id)) % len(options)
        ]
    return {
        "kind": kind,
        "stage": stage,
        "variant": variant,
        "partner_id": partner_id,
        "set_day": int(day),
        "days_left": stage + REMNANT_BASE_DAYS,
    }


def resident_remnant(resident: dict[str, Any]) -> dict[str, Any] | None:
    remnant = resident.get("remnant")
    if isinstance(remnant, dict) and _int(remnant.get("days_left")) > 0:
        return remnant
    return None


def decay_remnants(state: dict[str, Any]) -> dict[str, Any]:
    new_state = deepcopy(state)
    for resident in new_state["residents"]:
        remnant = resident.get("remnant")
        if not isinstance(remnant, dict):
            continue
        days_left = _int(remnant.get("days_left")) - 1
        resident["remnant"] = (
            {**remnant, "days_left": days_left} if days_left > 0 else None
        )
    return new_state


def start_adaptation(resident: dict[str, Any], kind: str, day: int) -> dict[str, Any]:
    """住民エントリ(コピー済み)に適応を始め、名残を消す。"""
    resident["adaptation"] = new_adaptation(kind, day)
    resident["remnant"] = None
    return resident


def end_adaptation(
    resident: dict[str, Any], kind: str, day: int, partner_id: str | None = None
) -> dict[str, Any]:
    """住民エントリ(コピー済み)の適応を終え、進み具合に応じた名残を付ける。"""
    adaptation = resident.get("adaptation")
    if isinstance(adaptation, dict) and adaptation.get("kind") == kind:
        resident["remnant"] = make_remnant(
            kind,
            _int(adaptation.get("stage")),
            resident["id"],
            day,
            partner_id,
        )
        resident["adaptation"] = None
    return resident


# --- 住民の記憶 ---


def add_memory(
    state: dict[str, Any], resident_id: str, entry: dict[str, Any]
) -> dict[str, Any]:
    """記憶を1件足す。上限を超えたら重みの高いもの・新しいものから残す(並びは日付順)。"""
    if resident_id not in {resident["id"] for resident in state.get("residents", [])}:
        return state
    memories = {
        key: [dict(item) for item in value]
        for key, value in (state.get("memories") or {}).items()
    }
    record = {
        "day": _int(entry.get("day"), _day(state)),
        "kind": str(entry.get("kind") or ""),
        "weight": _int(entry.get("weight"), MEMORY_WEIGHT_MINOR),
    }
    for key in ("partner_id", "change", "title", "delta", "rule_id", "rule_name"):
        if entry.get(key) is not None:
            value = entry[key]
            record[key] = value[:MEMORY_TEXT_MAX] if isinstance(value, str) else value
    items = [*memories.get(resident_id, []), record]
    if len(items) > MEMORY_MAX:
        ranked = sorted(
            enumerate(items),
            key=lambda pair: (
                _int(pair[1].get("weight")),
                _int(pair[1].get("day")),
                pair[0],
            ),
            reverse=True,
        )
        keep = {index for index, _ in ranked[:MEMORY_MAX]}
        items = [item for index, item in enumerate(items) if index in keep]
    memories[resident_id] = items
    return {**state, "memories": memories}


def resident_memories(state: dict[str, Any], resident_id: str) -> list[dict[str, Any]]:
    items = (state.get("memories") or {}).get(resident_id)
    return [dict(item) for item in items] if isinstance(items, list) else []


def record_event_memories(
    state: dict[str, Any], record: dict[str, Any]
) -> dict[str, Any]:
    """年代記に積んだ出来事のうち、大きなものだけを参加者の記憶に残す。

    変身(本人と居合わせた住民)・対面・好感度が大きく動いた出来事(相手との因縁)。
    """
    ids = {resident["id"] for resident in state.get("residents", [])}
    participants = [pid for pid in record.get("participants") or [] if pid in ids]
    if not participants:
        return state
    day = _int(record.get("day"), _day(state))
    kind = record.get("kind")
    new_state = state
    if kind == "transform" and record.get("change_text"):
        target_id = participants[0]
        change = str(record["change_text"])
        new_state = add_memory(
            new_state,
            target_id,
            {
                "day": day,
                "kind": "transform_self",
                "weight": MEMORY_WEIGHT_MAJOR,
                "change": change,
            },
        )
        for other_id in participants[1:]:
            new_state = add_memory(
                new_state,
                other_id,
                {
                    "day": day,
                    "kind": "transform_witness",
                    "weight": MEMORY_WEIGHT_NOTABLE,
                    "partner_id": target_id,
                    "change": change,
                },
            )
        return new_state
    if kind == "confrontation":
        for resident_id in participants:
            new_state = add_memory(
                new_state,
                resident_id,
                {"day": day, "kind": "confrontation", "weight": MEMORY_WEIGHT_MAJOR},
            )
        return new_state
    delta = _int(record.get("affinity_delta"))
    if len(participants) >= 2 and abs(delta) >= MEMORY_AFFINITY_THRESHOLD:
        for index, a_id in enumerate(participants):
            for b_id in participants[index + 1 :]:
                for owner_id, other_id in ((a_id, b_id), (b_id, a_id)):
                    new_state = add_memory(
                        new_state,
                        owner_id,
                        {
                            "day": day,
                            "kind": "bond",
                            "weight": MEMORY_WEIGHT_NOTABLE,
                            "partner_id": other_id,
                            "delta": delta,
                            "title": str(record.get("title") or ""),
                        },
                    )
    return new_state


def record_rule_toggle_memories(
    state: dict[str, Any],
    card_id: str,
    active: bool,
    swap_pair_before: list[str] | None,
) -> dict[str, Any]:
    """掟の始まり・終わりを全員の記憶に、入れ替わりの始まり・終わりは当事者に重く残す。"""
    day = _day(state)
    custom = next(
        (rule for rule in state.get("custom_rules", []) if rule["id"] == card_id), None
    )
    base: dict[str, Any] = {
        "day": day,
        "kind": "rule_start" if active else "rule_end",
        "weight": MEMORY_WEIGHT_MINOR,
        "rule_id": card_id,
    }
    if custom is not None:
        base["rule_name"] = str(custom.get("name") or "")
    elif card_id not in HAKONIWA_RULE_MAP:
        return state
    new_state = state
    for resident in state.get("residents", []):
        new_state = add_memory(new_state, resident["id"], dict(base))
    if card_id == "swap":
        pair = (
            list(state.get("swap_pair") or [])
            if active
            else list(swap_pair_before or [])
        )
        for resident_id in pair:
            partner_id = next((pid for pid in pair if pid != resident_id), None)
            if partner_id is None:
                continue
            new_state = add_memory(
                new_state,
                resident_id,
                {
                    "day": day,
                    "kind": "swap_start" if active else "swap_end",
                    "weight": MEMORY_WEIGHT_MAJOR if active else MEMORY_WEIGHT_NOTABLE,
                    "partner_id": partner_id,
                },
            )
    return new_state


def forget_resident(state: dict[str, Any], resident_id: str) -> dict[str, Any]:
    """外した住民の記憶を捨て、その住民が担う弧を閉じる。"""
    memories = {
        key: [dict(item) for item in value]
        for key, value in (state.get("memories") or {}).items()
        if key != resident_id
    }
    arcs = [dict(arc) for arc in state.get("story_arcs") or []]
    for arc in arcs:
        if arc.get("status") == "active" and resident_id in (
            arc.get("resident_ids") or []
        ):
            _close_arc(arc, _day(state), "resolved")
    return {**state, "memories": memories, "story_arcs": arcs}


# --- 物語の弧 ---


def active_arcs(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        arc
        for arc in state.get("story_arcs") or []
        if isinstance(arc, dict) and arc.get("status") == "active"
    ]


def arc_by_id(state: dict[str, Any], arc_id: str | None) -> dict[str, Any] | None:
    if not arc_id:
        return None
    return next(
        (arc for arc in state.get("story_arcs") or [] if arc.get("id") == arc_id), None
    )


def _close_arc(arc: dict[str, Any], day: int, reason: str) -> None:
    arc["status"] = "closed"
    arc["closed_day"] = int(day)
    arc["close_reason"] = reason


def _arc_condition_gone(state: dict[str, Any], arc: dict[str, Any]) -> bool:
    by_id = {resident["id"]: resident for resident in state.get("residents", [])}
    resident_ids = list(arc.get("resident_ids") or [])
    if not resident_ids or any(rid not in by_id for rid in resident_ids):
        return True
    kind = arc.get("kind")
    if kind == "swap":
        return set(_swap_active(state) or []) != set(resident_ids)
    if kind == "transform":
        return current_transformation(state, by_id[resident_ids[0]]) is None
    if kind == "investigation":
        return not investigation_active(state)
    if kind == "bond":
        return _int(by_id[resident_ids[0]]["affinities"].get(resident_ids[1])) < 0
    return True


def _new_arc(kind: str, resident_ids: list[str], day: int) -> dict[str, Any]:
    return {
        "id": "arc_" + uuid.uuid4().hex[:10],
        "kind": kind,
        "resident_ids": list(resident_ids),
        "started_day": day,
        "progress": 0,
        "beats_to_climax": ARC_BEATS_TO_CLIMAX,
        "status": "active",
        "closed_day": None,
        "close_reason": None,
        "log": [],
    }


def _detect_arc_candidate(
    state: dict[str, Any], arcs: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """新しい弧の候補(調査 > 入れ替わり > 変身 > 関係)。同じ弧の重複と閉じた直後は避ける。"""
    day = _day(state)
    blocked: set[tuple[str, frozenset[str]]] = set()
    for arc in arcs:
        key = (str(arc.get("kind")), frozenset(arc.get("resident_ids") or []))
        recently_closed = (
            day - _int(arc.get("closed_day"), -999) < ARC_REOPEN_COOLDOWN_DAYS
        )
        if arc.get("status") == "active" or recently_closed:
            blocked.add(key)

    def candidate(kind: str, resident_ids: list[str]) -> dict[str, Any] | None:
        if (kind, frozenset(resident_ids)) in blocked:
            return None
        return _new_arc(kind, resident_ids, day)

    by_id = {resident["id"]: resident for resident in state.get("residents", [])}
    if investigation_active(state):
        pair = confrontation_pair(state)
        if pair is not None:
            found = candidate("investigation", [pair[0]["id"], pair[1]["id"]])
            if found:
                return found
    swap = _swap_active(state)
    if swap and all(rid in by_id for rid in swap):
        continuing = all(
            isinstance(by_id[rid].get("adaptation"), dict)
            and by_id[rid]["adaptation"].get("kind") == "swap"
            and _int(by_id[rid]["adaptation"].get("since_day"), day) <= day - 1
            for rid in swap
        )
        if continuing:
            found = candidate("swap", swap)
            if found:
                return found
    for resident in state.get("residents", []):
        transformation = current_transformation(state, resident)
        if not transformation or _int(transformation.get("day"), day) > day - 1:
            continue
        others = [item for item in state["residents"] if item["id"] != resident["id"]]
        if not others:
            continue
        partner = max(
            others, key=lambda item: _int(resident["affinities"].get(item["id"]))
        )
        found = candidate("transform", [resident["id"], partner["id"]])
        if found:
            return found
    best: tuple[int, str, str] | None = None
    residents = state.get("residents", [])
    for index, a in enumerate(residents):
        for b in residents[index + 1 :]:
            value = _int(a["affinities"].get(b["id"]))
            if value >= ARC_BOND_AFFINITY_THRESHOLD and (
                best is None or value > best[0]
            ):
                best = (value, a["id"], b["id"])
    if best is not None:
        return candidate("bond", [best[1], best[2]])
    return None


def refresh_story_arcs(state: dict[str, Any]) -> dict[str, Any]:
    """日の始めに、前提の消えた弧・長く進まない弧を閉じ、新しい弧を上限まで立てる。"""
    day = _day(state)
    arcs = [deepcopy(arc) for arc in state.get("story_arcs") or []]
    for arc in arcs:
        if arc.get("status") != "active":
            continue
        if _arc_condition_gone(state, arc):
            _close_arc(arc, day, "resolved")
        elif day - _int(arc.get("started_day"), day) > ARC_MAX_AGE_DAYS:
            _close_arc(arc, day, "faded")
    while sum(1 for arc in arcs if arc.get("status") == "active") < ARC_MAX_ACTIVE:
        found = _detect_arc_candidate(state, arcs)
        if found is None:
            break
        arcs.append(found)
    return {**state, "story_arcs": _trim_closed_arcs(arcs)}


def _trim_closed_arcs(arcs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    closed = [arc for arc in arcs if arc.get("status") != "active"]
    overflow = len(closed) - ARC_CLOSED_KEEP
    if overflow <= 0:
        return arcs
    drop = {id(arc) for arc in closed[:overflow]}
    return [arc for arc in arcs if id(arc) not in drop]


def arc_focus_assignments(
    state: dict[str, Any], groups: list[tuple[dict[str, Any], ...]]
) -> dict[int, dict[str, Any]]:
    """弧ごとに続きを描く出来事を1件割り当てる {出来事の位置: {arc_id, climax}}。

    担い手全員を含む組を優先し、無ければ誰かを含む組。山場まで残り1件なら山場にする。
    """
    assignments: dict[int, dict[str, Any]] = {}
    for arc in active_arcs(state):
        members = set(arc.get("resident_ids") or [])
        best_index, best_score = None, 0
        for index, group in enumerate(groups):
            if index in assignments:
                continue
            ids = {item["id"] for item in group}
            if not members & ids:
                continue
            score = 2 if members <= ids else 1
            if score > best_score:
                best_index, best_score = index, score
        if best_index is None:
            continue
        beats = _int(arc.get("beats_to_climax"), ARC_BEATS_TO_CLIMAX)
        assignments[best_index] = {
            "arc_id": arc["id"],
            "climax": _int(arc.get("progress")) + 1 >= beats,
        }
    return assignments


def record_arc_event(
    state: dict[str, Any], arc_id: str, record: dict[str, Any], climax: bool
) -> dict[str, Any]:
    """弧の出来事を積んだことを記録する。山場ならその場で閉じる。"""
    arcs = []
    for arc in state.get("story_arcs") or []:
        entry = deepcopy(arc)
        if entry.get("id") == arc_id and entry.get("status") == "active":
            day = _int(record.get("day"), _day(state))
            entry["progress"] = _int(entry.get("progress")) + 1
            log = [
                *(entry.get("log") or []),
                {
                    "day": day,
                    "title": str(record.get("title") or ""),
                    "event_id": record.get("id"),
                },
            ]
            entry["log"] = log[-ARC_LOG_MAX:]
            if climax:
                _close_arc(entry, day, "climax")
        arcs.append(entry)
    return {**state, "story_arcs": arcs}
