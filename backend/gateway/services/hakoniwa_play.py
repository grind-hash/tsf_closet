"""AI箱庭の「関わり方」の状態遷移(純粋関数)。

世界のメモ・掟の相性・1日1回の介入・タッチの気分の変化・住民との会話の履歴と、
会話文が変身・元に戻す指示かどうかの判定(言い回しの規則)を扱う。

状態に足す項目:
    world_memo: str
    intervention: 次の「1日進める」で効かせる介入(watch は何もしない)
    chat_histories: {住民 id: [{role: player | resident | system, text, kind?}]}
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from ..consts.hakoniwa import HAKONIWA_AFFINITY_MAX, HAKONIWA_AFFINITY_MIN
from ..consts.hakoniwa_play import (
    CHAT_ALTERATION_MARKERS,
    CHAT_CLEAR_PATTERNS,
    CHAT_CONTINUATION_CHARS,
    CHAT_TRANSFORM_PATTERNS,
    HAKONIWA_CHAT_HISTORY_MAX,
    HAKONIWA_CHAT_MESSAGE_MAX,
    HAKONIWA_INTERVENTIONS,
    HAKONIWA_RULE_SYNERGIES,
    HAKONIWA_WORLD_MEMO_MAX,
    INTERVENTION_ARC_BOOST_AFFINITY,
    TOUCH_PARTS,
    TOUCH_TOLERANT_MOOD,
)
from . import hakoniwa_story as story
from .hakoniwa_errors import HakoniwaError

CHAT_ROLES = ("player", "resident", "system")


def normalize_play(source: dict[str, Any], normalized: dict[str, Any]) -> None:
    """読み込んだ状態の関わり方の項目を、正規化中の状態 normalized へ写す。"""
    normalized["world_memo"] = str(source.get("world_memo") or "")[
        :HAKONIWA_WORLD_MEMO_MAX
    ]
    choice = source.get("intervention")
    normalized["intervention"] = choice if choice in HAKONIWA_INTERVENTIONS else "watch"
    ids = {resident["id"] for resident in normalized["residents"]}
    histories = source.get("chat_histories")
    normalized["chat_histories"] = {
        str(key): [
            dict(item)
            for item in value
            if isinstance(item, dict) and item.get("role") in CHAT_ROLES
        ][-HAKONIWA_CHAT_HISTORY_MAX:]
        for key, value in (histories.items() if isinstance(histories, dict) else [])
        if str(key) in ids and isinstance(value, list)
    }


def initial_play_state() -> dict[str, Any]:
    return {"world_memo": "", "intervention": "watch", "chat_histories": {}}


# --- 世界のメモ ---


def validate_world_memo(memo: Any) -> str:
    text = str(memo or "").strip()
    if len(text) > HAKONIWA_WORLD_MEMO_MAX:
        raise HakoniwaError(
            "invalid_world_memo", f"世界のメモは{HAKONIWA_WORLD_MEMO_MAX}文字までです"
        )
    return text


def world_memo(state: dict[str, Any]) -> str:
    return str(state.get("world_memo") or "").strip()


# --- 掟の相性 ---


def active_synergies(state: dict[str, Any]) -> list[dict[str, Any]]:
    active = set(state.get("active_rules", []))
    return [
        synergy
        for synergy in HAKONIWA_RULE_SYNERGIES
        if all(card_id in active for card_id in synergy["cards"])
    ]


def card_synergies(
    state: dict[str, Any], card_id: str, language: str
) -> list[dict[str, Any]]:
    """掟カードに出す相性の案内(相手の掟・名前・一言・発動中か)。"""
    lang = "ja" if language == "ja" else "en"
    active = set(state.get("active_rules", []))
    return [
        {
            "with_id": next(other for other in synergy["cards"] if other != card_id),
            "label": synergy["text"][lang]["label"],
            "hint": synergy["text"][lang]["hint"],
            "active": all(item in active for item in synergy["cards"]),
        }
        for synergy in HAKONIWA_RULE_SYNERGIES
        if card_id in synergy["cards"]
    ]


# --- 1日1回の介入 ---


def available_interventions(state: dict[str, Any]) -> list[str]:
    """選べる介入。見守る・後押しの枠・書き換えの枠の3つを、世界の状況で出し分ける。

    後押しの枠は、物語の弧があれば arc_boost、適応中の住民がいれば adaptation_care、
    どちらも無ければ nudge。書き換えの枠は、違和感が「ざわめき」以上で公認前なら
    dissonance_push、それ以外は rewrite。
    """
    if story.active_arcs(state):
        support = "arc_boost"
    elif any(
        story.resident_adaptation(state, resident) is not None
        for resident in state.get("residents", [])
    ):
        support = "adaptation_care"
    else:
        support = "nudge"
    stirring = (
        story.dissonance_enabled(state)
        and not state.get("dissonance_acknowledged")
        and story.dissonance_stage(story.dissonance_value(state)) != "stillness"
    )
    return ["watch", support, "dissonance_push" if stirring else "rewrite"]


def set_intervention(state: dict[str, Any], choice: str) -> dict[str, Any]:
    """次の「1日進める」で効かせる介入を選ぶ(進めるまでは選び直せる)。"""
    if choice not in available_interventions(state):
        raise HakoniwaError("invalid_intervention", "いまは選べない介入です")
    return {**state, "intervention": choice}


def pending_intervention(state: dict[str, Any]) -> str | None:
    """1日進めるときに効かせる介入。見守るか、いまの状況で選べないものなら None。"""
    choice = state.get("intervention")
    if choice == "watch" or choice not in available_interventions(state):
        return None
    return str(choice)


def boost_arc_relationships(state: dict[str, Any]) -> dict[str, Any]:
    """物語の弧の後押し: 最初の弧の担い手どうしの好感度を少し上げる。"""
    arcs = story.active_arcs(state)
    if not arcs:
        return state
    members = list(arcs[0].get("resident_ids") or [])
    new_state = deepcopy(state)
    for resident in new_state["residents"]:
        if resident["id"] not in members:
            continue
        for other in members:
            if other != resident["id"] and other in resident["affinities"]:
                resident["affinities"][other] = max(
                    HAKONIWA_AFFINITY_MIN,
                    min(
                        HAKONIWA_AFFINITY_MAX,
                        int(resident["affinities"][other])
                        + INTERVENTION_ARC_BOOST_AFFINITY,
                    ),
                )
    return new_state


# --- タッチ ---


def validate_touch_part(part: Any) -> str:
    if part not in TOUCH_PARTS:
        raise HakoniwaError("invalid_touch_part", "触れた部位が正しくありません")
    return str(part)


def touch_mood_delta(resident: dict[str, Any], part: str) -> int:
    """頭は好意的(+2)。胸・腰は、機嫌が良ければ照れつつ受け入れ、悪ければ下がる。"""
    tolerant = int(resident.get("mood") or 50) >= TOUCH_TOLERANT_MOOD
    if part == "head":
        return 2
    if part == "chest":
        return 1 if tolerant else -2
    return 0 if tolerant else -3


def adjust_mood(state: dict[str, Any], resident_id: str, delta: int) -> dict[str, Any]:
    new_state = deepcopy(state)
    for resident in new_state["residents"]:
        if resident["id"] == resident_id:
            resident["mood"] = max(0, min(100, int(resident["mood"]) + int(delta)))
    return new_state


# --- 会話 ---


def validate_chat_message(message: Any) -> str:
    text = str(message or "").strip()
    if not text:
        raise HakoniwaError("empty_message", "メッセージを入力してください")
    if len(text) > HAKONIWA_CHAT_MESSAGE_MAX:
        raise HakoniwaError(
            "invalid_message",
            f"メッセージは{HAKONIWA_CHAT_MESSAGE_MAX}文字までです",
        )
    return text


def _instruction_match(pattern: str, text: str) -> bool:
    """言い回しに一致し、直後が「〜してる」「〜てた」のような様子の言い方でないか。"""
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        following = text[match.end() : match.end() + 1]
        if not following or following not in CHAT_CONTINUATION_CHARS:
            return True
    return False


def detect_chat_alteration(message: str) -> dict[str, str]:
    """会話文が、変身(transform)か元に戻す(clear)指示かを言い回しで判定する。

    戻り値 {action: transform | clear | none, instruction}。疑問文や感想は none。
    """
    text = str(message or "").strip()
    if not text:
        return {"action": "none", "instruction": ""}
    if any(_instruction_match(pattern, text) for pattern in CHAT_CLEAR_PATTERNS):
        return {"action": "clear", "instruction": text}
    if "?" in text or "？" in text:
        return {"action": "none", "instruction": ""}
    if any(_instruction_match(pattern, text) for pattern in CHAT_TRANSFORM_PATTERNS):
        return {"action": "transform", "instruction": text}
    return {"action": "none", "instruction": ""}


def alteration_candidate(message: str) -> bool:
    """言い回しで決まらなかった文のうち、LLM の分類に回す価値があるもの。"""
    text = str(message or "").strip().lower()
    if not text or "?" in text or "？" in text:
        return False
    return any(marker in text for marker in CHAT_ALTERATION_MARKERS)


def chat_history(state: dict[str, Any], resident_id: str) -> list[dict[str, Any]]:
    items = (state.get("chat_histories") or {}).get(resident_id)
    return [dict(item) for item in items] if isinstance(items, list) else []


def append_chat(
    state: dict[str, Any], resident_id: str, entries: list[dict[str, Any]]
) -> dict[str, Any]:
    """会話の履歴に足す(住民ごとに直近 HAKONIWA_CHAT_HISTORY_MAX 件)。"""
    histories = {
        key: [dict(item) for item in value]
        for key, value in (state.get("chat_histories") or {}).items()
    }
    items = [*histories.get(resident_id, []), *[dict(item) for item in entries]]
    histories[resident_id] = items[-HAKONIWA_CHAT_HISTORY_MAX:]
    return {**state, "chat_histories": histories}


def forget_chat(state: dict[str, Any], resident_id: str) -> dict[str, Any]:
    histories = {
        key: value
        for key, value in (state.get("chat_histories") or {}).items()
        if key != resident_id
    }
    return {**state, "chat_histories": histories}
