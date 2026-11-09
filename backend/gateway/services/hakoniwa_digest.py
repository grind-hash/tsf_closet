"""AI箱庭の「1日のまとめ」(純粋関数)。

1日進める前後の状態とその日の出来事から、山場の出来事・大きな変化・明日の予感を決める。
生成に失敗した日でも必ず作れるよう、LLM は使わない。文は表示側が言語ごとに組み立てるので、
ここでは種類と参照(住民 id・数値)だけを返す。
"""

from __future__ import annotations

from typing import Any

from ..consts.hakoniwa import HAKONIWA_MAX_ACTIVE_RULES

# 「親密」とみなす好感度と、「親密まであと少し」とみなす下限
AFFINITY_CLOSE = 30
AFFINITY_NEAR_CLOSE = 22
# 気分の変化を「大きく動いた」とみなす幅
MOOD_NOTABLE_DELTA = 8
# 明日の予感の定型の数(日数で巡らせる)
GENERIC_HINTS = 3
# 変化の行の上限
CHANGES_MAX = 3

_KIND_RANK = {"transform": 1}


def _movement(event: dict[str, Any]) -> int:
    return abs(int(event.get("affinity_delta") or 0)) + sum(
        abs(int(value)) for value in (event.get("mood_delta") or {}).values()
    )


def _highlight(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """その日の山場。特別な出来事(変身など)を優先し、次に関係と気分の動きの大きさ。"""
    best: dict[str, Any] | None = None
    best_score: tuple[int, int] | None = None
    for event in events:
        score = (_KIND_RANK.get(str(event.get("kind") or ""), 0), _movement(event))
        if best_score is None or score > best_score:
            best, best_score = event, score
    if best is None or best_score is None:
        return None
    if best.get("kind") == "transform":
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


def _tomorrow_hint(after: dict[str, Any]) -> dict[str, Any]:
    """明日の予感(最初に当てはまったもの)。"""
    pair = after.get("swap_pair")
    if "swap" in after.get("active_rules", []) and pair:
        return {"type": "swap", "ids": list(pair)}
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


def build_day_digest(
    before: dict[str, Any], after: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    """1日のまとめ。day は進める前の日(まとめた日)。"""
    return {
        "day": int(before.get("day") or 1),
        "highlight": _highlight(events),
        "changes": _changes(before, after, events),
        "hint": _tomorrow_hint(after),
    }
