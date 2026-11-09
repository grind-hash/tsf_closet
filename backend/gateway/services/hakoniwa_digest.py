"""AI箱庭の「1日のまとめ」(純粋関数)。

1日進める前後の状態とその日の出来事から、山場の出来事・大きな変化・明日の予感を決める。
生成に失敗した日でも必ず作れるよう、LLM は使わない。文は表示側が言語ごとに組み立てるので、
ここでは種類と参照(住民 id・数値)だけを返す。
"""

from __future__ import annotations

from typing import Any

from ..consts.hakoniwa import HAKONIWA_MAX_ACTIVE_RULES
from . import hakoniwa_story as story

# 「親密」とみなす好感度と、「親密まであと少し」とみなす下限
AFFINITY_CLOSE = 30
AFFINITY_NEAR_CLOSE = 22
# 気分の変化を「大きく動いた」とみなす幅
MOOD_NOTABLE_DELTA = 8
# 明日の予感の定型の数(日数で巡らせる)
GENERIC_HINTS = 3
# 変化の行の上限
CHANGES_MAX = 3
# 違和感の「次の段階まであと少し」とみなす残り
DISSONANCE_NEAR_STAGE = 15

_KIND_RANK = {"confrontation": 3, "transform": 1}
# 物語の弧の山場の出来事の順位(変身より上、対面より下)
_ARC_CLIMAX_RANK = 2


def _rank(event: dict[str, Any]) -> int:
    rank = _KIND_RANK.get(str(event.get("kind") or ""), 0)
    if event.get("arc_climax"):
        rank = max(rank, _ARC_CLIMAX_RANK)
    return rank


def _movement(event: dict[str, Any]) -> int:
    return abs(int(event.get("affinity_delta") or 0)) + sum(
        abs(int(value)) for value in (event.get("mood_delta") or {}).values()
    )


def _highlight(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """その日の山場。対面 > 物語の山場 > 変身 > 関係と気分の動きの大きさ。"""
    best: dict[str, Any] | None = None
    best_score: tuple[int, int] | None = None
    for event in events:
        score = (_rank(event), _movement(event))
        if best_score is None or score > best_score:
            best, best_score = event, score
    if best is None or best_score is None:
        return None
    if best.get("kind") == "confrontation":
        reason = "confrontation"
    elif best.get("arc_climax"):
        reason = "arc_climax"
    elif best.get("kind") == "transform":
        reason = "transform"
    elif best_score[1] > 0:
        reason = "trio" if len(best.get("participants") or []) >= 3 else "movement"
    else:
        reason = "center"
    return {
        "event_id": best["id"],
        "title": best.get("title", ""),
        "reason": reason,
        "participants": list(best.get("participants") or [])[:3],
    }


def _changes(
    before: dict[str, Any], after: dict[str, Any], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    by_id = {resident["id"]: resident for resident in after["residents"]}
    paired = [
        event
        for event in events
        if len(event.get("participants") or []) >= 2
        and int(event.get("affinity_delta") or 0)
    ]
    if paired:
        event = max(paired, key=lambda item: abs(int(item["affinity_delta"])))
        ids = [pid for pid in event["participants"] if pid in by_id]
        if len(ids) >= 2:
            changes.append(
                {
                    "type": "affinity",
                    "ids": ids[:3],
                    "delta": int(event["affinity_delta"]),
                    "value": int(by_id[ids[0]]["affinities"].get(ids[1], 0)),
                }
            )
    moods_before = {
        resident["id"]: resident["mood"] for resident in before["residents"]
    }
    swings = [
        (resident["id"], int(resident["mood"]) - int(moods_before[resident["id"]]))
        for resident in after["residents"]
        if resident["id"] in moods_before
    ]
    swings = [item for item in swings if abs(item[1]) >= MOOD_NOTABLE_DELTA]
    if swings:
        resident_id, delta = max(swings, key=lambda item: abs(item[1]))
        changes.append(
            {
                "type": "mood",
                "id": resident_id,
                "delta": delta,
                "mood": int(by_id[resident_id]["mood"]),
            }
        )
    return changes[:CHANGES_MAX]


def _near_close_pair(state: dict[str, Any]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for resident in state["residents"]:
        for other_id, value in resident["affinities"].items():
            if AFFINITY_NEAR_CLOSE <= value < AFFINITY_CLOSE and (
                best is None or value > best["value"]
            ):
                best = {"ids": [resident["id"], other_id], "value": int(value)}
    return best


def _dissonance_near(state: dict[str, Any]) -> dict[str, Any] | None:
    if not story.dissonance_enabled(state) or state.get("dissonance_acknowledged"):
        return None
    upcoming = story.next_dissonance_stage(story.dissonance_value(state))
    if upcoming is None or upcoming["remaining"] > DISSONANCE_NEAR_STAGE:
        return None
    return upcoming


def _arc_near_climax(state: dict[str, Any]) -> dict[str, Any] | None:
    for arc in story.active_arcs(state):
        remaining = int(arc.get("beats_to_climax") or 0) - int(arc.get("progress") or 0)
        if remaining <= 1:
            return arc
    return None


def _tomorrow_hint(
    after: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    """明日の予感(最初に当てはまったもの)。"""
    if any(event.get("kind") == "confrontation" for event in events):
        return {"type": "acknowledged"}
    near_stage = _dissonance_near(after)
    if near_stage is not None:
        return {
            "type": "dissonance_near",
            "stage": near_stage["stage"],
            "remaining": near_stage["remaining"],
        }
    pair = after.get("swap_pair")
    if "swap" in after.get("active_rules", []) and pair:
        return {"type": "swap", "ids": list(pair)}
    arc = _arc_near_climax(after)
    if arc is not None:
        return {
            "type": "arc_near_climax",
            "arc_id": arc["id"],
            "kind": arc["kind"],
            "ids": list(arc.get("resident_ids") or []),
        }
    near = _near_close_pair(after)
    if near is not None:
        return {
            "type": "near_close",
            "ids": near["ids"],
            "value": near["value"],
            "remaining": AFFINITY_CLOSE - near["value"],
        }
    active = len(after.get("active_rules", []))
    if active == 0:
        return {"type": "no_rules"}
    if active < HAKONIWA_MAX_ACTIVE_RULES:
        return {"type": "more_rules", "remaining": HAKONIWA_MAX_ACTIVE_RULES - active}
    return {"type": "generic", "index": int(after.get("day") or 1) % GENERIC_HINTS}


def _arcs(after: dict[str, Any], day: int) -> list[dict[str, Any]]:
    """続いている弧と、その日に閉じた弧。status は started / active / climax / faded / resolved。"""
    items = []
    for arc in after.get("story_arcs") or []:
        if arc.get("status") == "active":
            status = "started" if int(arc.get("started_day") or 0) == day else "active"
        elif arc.get("closed_day") == day:
            status = str(arc.get("close_reason") or "resolved")
        else:
            continue
        items.append(
            {
                "id": arc["id"],
                "kind": arc["kind"],
                "ids": list(arc.get("resident_ids") or []),
                "progress": int(arc.get("progress") or 0),
                "beats": int(arc.get("beats_to_climax") or 0),
                "status": status,
            }
        )
    return items


def _dissonance(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any] | None:
    if not story.dissonance_enabled(after):
        return None
    start = story.dissonance_value(before)
    end = story.dissonance_value(after)
    upcoming = story.next_dissonance_stage(end)
    return {
        "from": start,
        "to": end,
        "from_stage": story.dissonance_stage(start),
        "to_stage": story.dissonance_stage(end),
        "acknowledged": bool(after.get("dissonance_acknowledged")),
        "next_stage": upcoming["stage"] if upcoming else None,
        "remaining": upcoming["remaining"] if upcoming else None,
    }


def build_day_digest(
    before: dict[str, Any],
    after: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    adaptations: list[dict[str, Any]] | None = None,
    world_adaptations: list[dict[str, Any]] | None = None,
    intervention: str | None = None,
    theme: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """1日のまとめ。day は進める前の日(まとめた日)。theme は実験テーマの進み具合(数値)。

    after は日の終わりの処理(適応・名残・違和感)を済ませ、日を進める前の状態。
    """
    day = int(before.get("day") or 1)
    return {
        "day": day,
        "highlight": _highlight(events),
        "changes": _changes(before, after, events),
        "hint": _tomorrow_hint(after, events),
        "adaptations": list(adaptations or []),
        "world_adaptations": list(world_adaptations or []),
        "arcs": _arcs(after, day),
        "dissonance": _dissonance(before, after),
        "intervention": intervention,
        "theme": theme,
    }
