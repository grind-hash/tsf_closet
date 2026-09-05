"""Adventure inventory (持ち物) system.

Pure functions and Pydantic models used by adventure_service:

- World Events: structured facts the resolution LLM returns after it has
  narrated the scene ("the partner handed the player a bra"). They are
  validated here against the actual inventory and only the valid ones are
  applied, so the prose and the inventory cannot drift apart and a player
  claim ("凛からブラをもらった") never becomes a possession by itself.
- Reality patches: on ``reality_alter`` turns the declaration rewrites the
  world directly, including possessions, their origin, and NPC memories.
- Item actions: buttons in the inventory panel. Wearing, taking off, and
  discarding the player's own item are resolved deterministically; giving
  and using need the scene (an NPC may refuse), so the LLM decides.

Everything mutates the run's state dict in place. The turn pipeline stores a
full state snapshot per turn, so rewinds restore the inventory for free.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from ..consts.adventure_inventory import (
    BOUNDARY_SEVERITIES,
    BOUNDARY_VIOLATIONS_MAX,
    INVENTORY_ACTIONS,
    INVENTORY_ACTOR_CHARACTER_PREFIX,
    INVENTORY_ACTOR_PLAYER,
    INVENTORY_ACTOR_REALITY,
    INVENTORY_ACTOR_WORLD,
    INVENTORY_CAPABILITIES,
    INVENTORY_CATEGORIES,
    INVENTORY_DEFAULT_CAPABILITIES,
    INVENTORY_DEFAULT_CATEGORY,
    INVENTORY_DETERMINISTIC_ACTIONS,
    INVENTORY_ITEM_ID_MAX,
    INVENTORY_ITEM_NAME_MAX,
    INVENTORY_ITEMS_MAX,
    INVENTORY_LOG_CONTEXT_MAX,
    INVENTORY_LOG_MAX,
    INVENTORY_NPC_NAME_MAX,
    INVENTORY_NPC_NOTE_MAX,
    INVENTORY_NPC_NOTES_MAX,
    INVENTORY_NPC_STATES_MAX,
    INVENTORY_QUANTITY_MAX,
    INVENTORY_REASON_MAX,
    INVENTORY_TAG_LENGTH_MAX,
    INVENTORY_TAGS_MAX,
    INVENTORY_WEARABLE_CATEGORIES,
    REALITY_PATCH_OPS_MAX,
    WORLD_EVENTS_MAX,
)
from ..consts.adventure_narration import (
    NARRATION_PRONOUN_DEFAULT,
    NARRATION_VOICE_DEFAULT,
    NARRATION_VOICES,
)

# ログの type は World Event の種別に、現実改変による書き換え(item_update)を加えたもの
INVENTORY_LOG_TYPE_UPDATE = "item_update"


class InventoryActionError(Exception):
    """持ち物パネル由来の行動が成立しないときの例外。手番は消費しない。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# --- 正規化 -----------------------------------------------------------------


def _clean_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _coerce_int(value: Any, *, default: int | None, low: int, high: int) -> int | None:
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _match_key(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


_HONORIFIC_SUFFIX = re.compile(r"(?:さん|ちゃん|くん|君|様|さま)$")


def _npc_key(value: Any) -> str:
    return _HONORIFIC_SUFFIX.sub("", _match_key(value))


def normalize_category(value: Any) -> str:
    category = _clean_text(value, 40).lower().replace(" ", "_")
    return category if category in INVENTORY_CATEGORIES else INVENTORY_DEFAULT_CATEGORY


def normalize_capabilities(value: Any, category: str) -> list[str]:
    """語彙外を落とし、wear は着用できる分類にだけ残す。None は分類別既定。

    捨てる(discard)はプレイヤー自身の持ち物なので常に付ける。
    """
    if value is None:
        raw: list[str] = list(
            INVENTORY_DEFAULT_CAPABILITIES.get(
                category, INVENTORY_DEFAULT_CAPABILITIES[INVENTORY_DEFAULT_CATEGORY]
            )
        )
    elif isinstance(value, str):
        raw = re.split(r"[,、/\s]+", value)
    elif isinstance(value, list):
        raw = [str(item) for item in value]
    else:
        raw = []
    chosen: set[str] = set()
    for item in raw:
        capability = _clean_text(item, 20).lower()
        if capability not in INVENTORY_CAPABILITIES:
            continue
        if capability == "wear" and category not in INVENTORY_WEARABLE_CATEGORIES:
            continue
        chosen.add(capability)
    chosen.add("discard")
    return [capability for capability in INVENTORY_CAPABILITIES if capability in chosen]


def normalize_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        parts: list[Any] = re.split(r"[,、]", value)
    elif isinstance(value, list):
        parts = value
    else:
        return []
    tags: list[str] = []
    for part in parts:
        tag = _clean_text(part, INVENTORY_TAG_LENGTH_MAX)
        if tag and tag not in tags:
            tags.append(tag)
        if len(tags) >= INVENTORY_TAGS_MAX:
            break
    return tags


_PLAYER_ALIASES = {"player", "self", "me", "you", "主人公", "自分", "私", "僕", "俺"}
_WORLD_ALIASES = {
    "world",
    "environment",
    "scene",
    "ground",
    "floor",
    "shop",
    "store",
    "nobody",
    "none",
    "null",
}
_CHARACTER_PREFIXES = (INVENTORY_ACTOR_CHARACTER_PREFIX, "npc:", "character：", "npc：")


def normalize_actor(value: Any) -> str | None:
    """所有者・入手元の表記を player / world / reality / character:<name> に揃える。"""
    text = _clean_text(value, INVENTORY_NPC_NAME_MAX + 16)
    if not text:
        return None
    lowered = text.lower()
    if lowered in _PLAYER_ALIASES:
        return INVENTORY_ACTOR_PLAYER
    if lowered in _WORLD_ALIASES:
        return INVENTORY_ACTOR_WORLD
    if lowered == INVENTORY_ACTOR_REALITY:
        return INVENTORY_ACTOR_REALITY
    for prefix in _CHARACTER_PREFIXES:
        if lowered.startswith(prefix):
            name = _clean_text(text[len(prefix) :], INVENTORY_NPC_NAME_MAX)
            return f"{INVENTORY_ACTOR_CHARACTER_PREFIX}{name}" if name else None
    return f"{INVENTORY_ACTOR_CHARACTER_PREFIX}{text[:INVENTORY_NPC_NAME_MAX]}"


def actor_character_name(actor: str | None) -> str | None:
    if actor and actor.startswith(INVENTORY_ACTOR_CHARACTER_PREFIX):
        return actor[len(INVENTORY_ACTOR_CHARACTER_PREFIX) :] or None
    return None


# --- LLM 出力モデル(寛容 validator。壊れた要素は捨て、修復リトライへ落とさない) ---


class InventoryItemSpec(BaseModel):
    """World Event / 現実改変で LLM が記述するアイテム。語彙外は既定へ倒す。"""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=INVENTORY_ITEM_NAME_MAX)
    category: str = INVENTORY_DEFAULT_CATEGORY
    tags: list[str] = Field(default_factory=list)
    quantity: int = Field(default=1, ge=1, le=INVENTORY_QUANTITY_MAX)
    capabilities: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = {"name": value}
        if not isinstance(value, dict):
            return value
        category = normalize_category(value.get("category"))
        return {
            "name": _clean_text(value.get("name"), INVENTORY_ITEM_NAME_MAX),
            "category": category,
            "tags": normalize_tags(value.get("tags")),
            "quantity": _coerce_int(
                value.get("quantity"), default=1, low=1, high=INVENTORY_QUANTITY_MAX
            ),
            "capabilities": normalize_capabilities(value.get("capabilities"), category),
        }


WorldEventType = Literal[
    "item_transfer",
    "item_use",
    "item_discard",
    "item_wear",
    "item_unwear",
    "boundary_violation",
]

# LLM が言い換えた種別を正規の種別へ寄せる。受領系は to=player、譲渡系は from=player
_EVENT_TYPE_ALIASES: dict[str, str] = {
    "item_acquire": "item_transfer",
    "item_receive": "item_transfer",
    "item_obtain": "item_transfer",
    "item_pickup": "item_transfer",
    "item_pick_up": "item_transfer",
    "item_buy": "item_transfer",
    "item_purchase": "item_transfer",
    "item_give": "item_transfer",
    "item_gift": "item_transfer",
    "item_hand_over": "item_transfer",
    "item_drop": "item_discard",
    "item_throw_away": "item_discard",
    "item_put_on": "item_wear",
    "item_equip": "item_wear",
    "item_remove": "item_unwear",
    "item_take_off": "item_unwear",
    "item_unequip": "item_unwear",
    "boundary": "boundary_violation",
    "violation": "boundary_violation",
    "social_violation": "boundary_violation",
}
_RECEIVE_ALIASES = {
    "item_acquire",
    "item_receive",
    "item_obtain",
    "item_pickup",
    "item_pick_up",
    "item_buy",
    "item_purchase",
}
_GIVE_ALIASES = {"item_give", "item_gift", "item_hand_over"}


class WorldEvent(BaseModel):
    """判定 LLM が返す「物語が実際に示した」機械的事実。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    type: WorldEventType
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    item: InventoryItemSpec | None = None
    item_id: str | None = None
    quantity: int | None = None
    npc: str | None = None
    severity: Literal["minor", "major"] | None = None
    reason: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        raw_type = _clean_text(value.get("type"), 40).lower().replace(" ", "_")
        event_type = _EVENT_TYPE_ALIASES.get(raw_type, raw_type)
        item = value.get("item")
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict) or not _clean_text(
            item.get("name"), INVENTORY_ITEM_NAME_MAX
        ):
            # 名前の無いアイテムは無しとして扱い、種別ごとの必須判定に任せる
            item = None
        source = normalize_actor(value.get("from", value.get("from_")))
        target = normalize_actor(value.get("to"))
        if raw_type in _RECEIVE_ALIASES and target is None:
            target = INVENTORY_ACTOR_PLAYER
        if raw_type in _GIVE_ALIASES and source is None:
            source = INVENTORY_ACTOR_PLAYER
        severity = _clean_text(value.get("severity"), 10).lower()
        return {
            "type": event_type,
            "from": source,
            "to": target,
            "item": item,
            "item_id": _clean_text(value.get("item_id"), INVENTORY_ITEM_ID_MAX) or None,
            "quantity": _coerce_int(
                value.get("quantity"), default=None, low=1, high=INVENTORY_QUANTITY_MAX
            ),
            "npc": _clean_text(value.get("npc"), INVENTORY_NPC_NAME_MAX) or None,
            "severity": severity if severity in BOUNDARY_SEVERITIES else None,
            "reason": _clean_text(value.get("reason"), INVENTORY_REASON_MAX) or None,
        }

    @model_validator(mode="after")
    def require_subject(self) -> WorldEvent:
        # 種別ごとの必須項目を欠く要素は coerce_world_events が捨てる
        if self.type == "boundary_violation":
            if not self.npc:
                raise ValueError("boundary_violation requires npc")
        elif self.item is None and not self.item_id:
            raise ValueError(f"{self.type} requires item or item_id")
        return self


def coerce_world_events(value: Any) -> list[dict[str, Any]]:
    """LLM 出力の world_events を検証済み dict の列に落とす。壊れた要素は捨てる。"""
    if not isinstance(value, list):
        return []
    events: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        try:
            event = WorldEvent.model_validate(raw)
        except ValidationError:
            continue
        events.append(event.model_dump(by_alias=True))
        if len(events) >= WORLD_EVENTS_MAX:
            break
    return events


class NpcNote(BaseModel):
    npc: str = Field(min_length=1, max_length=INVENTORY_NPC_NAME_MAX)
    note: str = Field(min_length=1, max_length=INVENTORY_NPC_NOTE_MAX)

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return {
            "npc": _clean_text(value.get("npc"), INVENTORY_NPC_NAME_MAX),
            "note": _clean_text(value.get("note"), INVENTORY_NPC_NOTE_MAX),
        }


RealityPatchOpKind = Literal[
    "add", "remove", "replace", "set_quantity", "update", "transfer"
]


def _partial_item_fields(value: Any) -> dict[str, Any] | None:
    """現実改変の item 記述。update では部分指定なので Spec で縛らず項目ごとに整える。"""
    if isinstance(value, str):
        value = {"name": value}
    if not isinstance(value, dict):
        return None
    fields: dict[str, Any] = {}
    if value.get("name") is not None:
        name = _clean_text(value.get("name"), INVENTORY_ITEM_NAME_MAX)
        if name:
            fields["name"] = name
    if value.get("category") is not None:
        fields["category"] = normalize_category(value.get("category"))
    if value.get("tags") is not None:
        fields["tags"] = normalize_tags(value.get("tags"))
    if value.get("quantity") is not None:
        fields["quantity"] = _coerce_int(
            value.get("quantity"), default=1, low=1, high=INVENTORY_QUANTITY_MAX
        )
    if value.get("capabilities") is not None:
        fields["capabilities"] = value.get("capabilities")
    return fields or None


class RealityPatchOp(BaseModel):
    """現実改変ターンの持ち物書き換え1件。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    op: RealityPatchOpKind
    item_id: str | None = None
    name: str | None = None
    item: dict[str, Any] | None = None
    quantity: int | None = None
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    worn: bool | None = None
    obtained_when: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        worn = value.get("worn")
        if isinstance(worn, str):
            lowered = worn.strip().lower()
            worn = (
                True
                if lowered in {"true", "1", "yes"}
                else False
                if lowered
                in {
                    "false",
                    "0",
                    "no",
                }
                else None
            )
        elif worn is not None:
            worn = bool(worn)
        return {
            "op": _clean_text(value.get("op"), 20).lower(),
            "item_id": _clean_text(value.get("item_id"), INVENTORY_ITEM_ID_MAX) or None,
            "name": _clean_text(value.get("name"), INVENTORY_ITEM_NAME_MAX) or None,
            "item": _partial_item_fields(value.get("item")),
            "quantity": _coerce_int(
                value.get("quantity"), default=None, low=0, high=INVENTORY_QUANTITY_MAX
            ),
            "from": normalize_actor(value.get("from", value.get("from_"))),
            "to": normalize_actor(value.get("to")),
            "worn": worn,
            "obtained_when": _clean_text(value.get("obtained_when"), 60) or None,
        }


class RealityPatch(BaseModel):
    """現実改変ターンで持ち物と NPC の記憶を直接書き換える指示。"""

    model_config = ConfigDict(extra="ignore")

    inventory: list[RealityPatchOp] = Field(default_factory=list)
    npc_notes: list[NpcNote] = Field(default_factory=list)
    npc_boundary_reset: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        ops: list[Any] = []
        for raw in value.get("inventory") or []:
            if not isinstance(raw, dict):
                continue
            try:
                ops.append(RealityPatchOp.model_validate(raw))
            except ValidationError:
                continue
            if len(ops) >= REALITY_PATCH_OPS_MAX:
                break
        notes: list[Any] = []
        for raw in value.get("npc_notes") or []:
            if isinstance(raw, str):
                raw = {"npc": "", "note": raw}
            if not isinstance(raw, dict):
                continue
            try:
                notes.append(NpcNote.model_validate(raw))
            except ValidationError:
                continue
            if len(notes) >= INVENTORY_NPC_NOTES_MAX:
                break
        resets: list[str] = []
        raw_resets = value.get("npc_boundary_reset") or value.get("npc_boundary_resets")
        for raw in raw_resets or []:
            name = _clean_text(raw, INVENTORY_NPC_NAME_MAX)
            if name and name not in resets:
                resets.append(name)
            if len(resets) >= INVENTORY_NPC_STATES_MAX:
                break
        return {"inventory": ops, "npc_notes": notes, "npc_boundary_reset": resets}


def coerce_reality_patch(value: Any) -> dict[str, Any] | None:
    """LLM 出力の reality_patch を検証済み dict にする。空・不正は None。"""
    if not isinstance(value, dict):
        return None
    try:
        patch = RealityPatch.model_validate(value)
    except ValidationError:
        return None
    if not patch.inventory and not patch.npc_notes and not patch.npc_boundary_reset:
        return None
    return patch.model_dump(by_alias=True)


# --- state 操作 ---------------------------------------------------------------


def inventory_enabled(state: dict[str, Any]) -> bool:
    return bool(state.get("inventory_enabled"))


def init_inventory_state() -> dict[str, Any]:
    return {"items": [], "next_id": 1, "log": []}


def ensure_inventory(state: dict[str, Any]) -> dict[str, Any]:
    inventory = state.get("inventory")
    if not isinstance(inventory, dict):
        inventory = init_inventory_state()
        state["inventory"] = inventory
    if not isinstance(inventory.get("items"), list):
        inventory["items"] = []
    if not isinstance(inventory.get("log"), list):
        inventory["log"] = []
    inventory["next_id"] = max(
        1, _coerce_int(inventory.get("next_id"), default=1, low=1, high=10**9) or 1
    )
    return inventory


def ensure_npc_states(state: dict[str, Any]) -> dict[str, Any]:
    npc_states = state.get("npc_states")
    if not isinstance(npc_states, dict):
        npc_states = {}
        state["npc_states"] = npc_states
    return npc_states


def _npc_candidates(state: dict[str, Any]) -> list[str]:
    names: list[str] = []
    sim = state.get("sim")
    if isinstance(sim, dict) and sim.get("partner_name"):
        names.append(str(sim["partner_name"]))
    npc_states = state.get("npc_states")
    if isinstance(npc_states, dict):
        names.extend(str(key) for key in npc_states)
    visual = state.get("visual_state")
    if isinstance(visual, dict):
        for entry in visual.get("main_characters") or []:
            if isinstance(entry, dict) and entry.get("name"):
                names.append(str(entry["name"]))
    return names


def resolve_npc_name(name: Any, state: dict[str, Any]) -> str:
    """NPC 名を state 内の表記へ寄せる。敬称と character: 接頭辞は剥がす。

    攻略対象名・既存の npc_states・場面の登場人物と大小/空白無視で照合し、
    一致しなければ整形した入力をそのまま返す。
    """
    text = _clean_text(name, INVENTORY_NPC_NAME_MAX + 16)
    for prefix in _CHARACTER_PREFIXES:
        if text.lower().startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    text = _HONORIFIC_SUFFIX.sub("", text).strip()[:INVENTORY_NPC_NAME_MAX]
    if not text:
        return ""
    key = _npc_key(text)
    for candidate in _npc_candidates(state):
        if _fuzzy_name_match(_npc_key(candidate), key):
            return candidate.strip()[:INVENTORY_NPC_NAME_MAX]
    return text


def _fuzzy_name_match(candidate_key: str, key: str) -> bool:
    """名前の照合。完全一致か、片方がもう片方を含む(「ミナ」と「店員のミナ」)。

    差分が数字・英字だけ(「通行人1」と「通行人10」、「Ann」と「Anna」)なら
    別人とみなす。1文字の名前は日本語(「凛」)だけ包含を許す。
    """
    if not candidate_key or not key:
        return False
    if candidate_key == key:
        return True
    shorter, longer = sorted((candidate_key, key), key=len)
    if len(shorter) < 2 and shorter.isascii():
        return False
    index = longer.find(shorter)
    if index < 0:
        return False
    around = longer[:index] + longer[index + len(shorter) :]
    return not all(char.isascii() and char.isalnum() for char in around)


def _canonical_actor(actor: str | None, state: dict[str, Any]) -> str | None:
    """character:<name> の名前を state の表記へ寄せる。それ以外はそのまま。"""
    character = actor_character_name(actor)
    if character is None:
        return actor
    resolved = resolve_npc_name(character, state)
    return f"{INVENTORY_ACTOR_CHARACTER_PREFIX}{resolved}" if resolved else None


def find_item(
    inventory: dict[str, Any],
    *,
    item_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any] | None:
    """ID → 名前の完全一致 → 一意な部分一致の順で所持品を引く。"""
    items = [item for item in inventory.get("items") or [] if isinstance(item, dict)]
    if item_id:
        for item in items:
            if str(item.get("id")) == str(item_id):
                return item
    key = _match_key(name)
    if key:
        for item in items:
            if _match_key(item.get("name")) == key:
                return item
        partial = [item for item in items if key in _match_key(item.get("name"))]
        if len(partial) == 1:
            return partial[0]
    return None


def add_item(
    inventory: dict[str, Any],
    spec: dict[str, Any] | str,
    *,
    turn: int,
    obtained_from: str,
) -> dict[str, Any] | None:
    """所持品を追加する。同名・同分類・未着用は数量を合算。上限超過は None。"""
    try:
        parsed = InventoryItemSpec.model_validate(spec)
    except ValidationError:
        return None
    items = inventory["items"]
    for item in items:
        if (
            isinstance(item, dict)
            and not item.get("worn")
            and _match_key(item.get("name")) == _match_key(parsed.name)
            and item.get("category") == parsed.category
        ):
            item["quantity"] = min(
                INVENTORY_QUANTITY_MAX, int(item.get("quantity") or 0) + parsed.quantity
            )
            return item
    if len(items) >= INVENTORY_ITEMS_MAX:
        return None
    next_id = int(inventory.get("next_id") or 1)
    item = {
        "id": f"i{next_id}",
        "name": parsed.name,
        "category": parsed.category,
        "tags": parsed.tags,
        "quantity": parsed.quantity,
        "obtained_from": obtained_from,
        "obtained_turn": turn,
        "capabilities": parsed.capabilities,
        "worn": False,
        "metadata": {},
    }
    inventory["next_id"] = next_id + 1
    items.append(item)
    return item


def remove_item_quantity(
    inventory: dict[str, Any], item: dict[str, Any], quantity: int | None
) -> int:
    """数量を減らし、0 になれば所持品から外す。None は全数。減った数を返す。"""
    owned = int(item.get("quantity") or 0)
    count = owned if quantity is None else max(0, min(int(quantity), owned))
    if count <= 0:
        return 0
    remaining = owned - count
    if remaining <= 0:
        inventory["items"] = [
            other for other in inventory.get("items") or [] if other is not item
        ]
    else:
        item["quantity"] = remaining
    return count


def _log_entry(
    *,
    turn: int,
    type: str,
    origin: str,
    item: str | None = None,
    item_id: str | None = None,
    quantity: int | None = None,
    from_: str | None = None,
    to: str | None = None,
    npc: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "turn": turn,
        "type": type,
        "item": item,
        "item_id": item_id,
        "quantity": quantity,
        "from": from_,
        "to": to,
        "npc": npc,
        "reason": reason,
        "origin": origin,
    }


def append_log(inventory: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    log = inventory["log"]
    log.append(entry)
    if len(log) > INVENTORY_LOG_MAX:
        del log[: len(log) - INVENTORY_LOG_MAX]
    return entry


def _ensure_npc_entry(state: dict[str, Any], npc: str) -> dict[str, Any]:
    npc_states = ensure_npc_states(state)
    entry = npc_states.get(npc)
    if isinstance(entry, dict):
        entry.setdefault("notes", [])
        return entry
    if len(npc_states) >= INVENTORY_NPC_STATES_MAX:
        # 最も古い違反記録の NPC を落とす(記録の無い NPC は最古扱い)
        oldest = min(
            npc_states.items(),
            key=lambda pair: int(
                (pair[1] or {}).get("last_violation_turn")
                if isinstance(pair[1], dict)
                and pair[1].get("last_violation_turn") is not None
                else -1
            ),
        )
        npc_states.pop(oldest[0], None)
    entry = {
        "boundary_violations": 0,
        "last_violation_turn": None,
        "last_violation": None,
        "last_violation_severity": None,
        "notes": [],
    }
    npc_states[npc] = entry
    return entry


def bump_boundary_violation(
    state: dict[str, Any],
    npc: str,
    *,
    turn: int,
    reason: str | None,
    severity: str | None,
) -> dict[str, Any]:
    entry = _ensure_npc_entry(state, npc)
    entry["boundary_violations"] = min(
        BOUNDARY_VIOLATIONS_MAX, int(entry.get("boundary_violations") or 0) + 1
    )
    entry["last_violation_turn"] = turn
    entry["last_violation"] = reason
    entry["last_violation_severity"] = (
        severity if severity in BOUNDARY_SEVERITIES else "minor"
    )
    return entry


# --- World Event の適用 ---------------------------------------------------------


def _apply_world_event(
    state: dict[str, Any],
    inventory: dict[str, Any],
    event: WorldEvent,
    *,
    turn_number: int,
    input_kind: str,
) -> dict[str, Any] | None:
    kind = event.type
    if kind == "boundary_violation":
        # 現実改変の宣言そのものは境界侵害にならない
        if input_kind == "reality_alter" or not event.npc:
            return None
        npc = resolve_npc_name(event.npc, state)
        if not npc:
            return None
        bump_boundary_violation(
            state, npc, turn=turn_number, reason=event.reason, severity=event.severity
        )
        return _log_entry(
            turn=turn_number, type=kind, origin="event", npc=npc, reason=event.reason
        )
    if kind == "item_transfer":
        source, target = event.from_, event.to
        if target == INVENTORY_ACTOR_PLAYER and source != INVENTORY_ACTOR_PLAYER:
            if event.item is None:
                return None
            obtained_from = _canonical_actor(source, state) or INVENTORY_ACTOR_WORLD
            if obtained_from == INVENTORY_ACTOR_REALITY:
                obtained_from = INVENTORY_ACTOR_WORLD
            item = add_item(
                inventory,
                event.item.model_dump(),
                turn=turn_number,
                obtained_from=obtained_from,
            )
            if item is None:
                return None
            return _log_entry(
                turn=turn_number,
                type=kind,
                origin="event",
                item=item["name"],
                item_id=item["id"],
                quantity=event.item.quantity,
                from_=obtained_from,
                to=INVENTORY_ACTOR_PLAYER,
            )
        if source == INVENTORY_ACTOR_PLAYER and target != INVENTORY_ACTOR_PLAYER:
            item = find_item(
                inventory,
                item_id=event.item_id,
                name=event.item.name if event.item else None,
            )
            if item is None:
                return None
            quantity = event.quantity or 1
            if quantity > int(item.get("quantity") or 0):
                return None
            name, item_id = str(item["name"]), str(item["id"])
            remove_item_quantity(inventory, item, quantity)
            recipient = _canonical_actor(target, state) or INVENTORY_ACTOR_WORLD
            return _log_entry(
                turn=turn_number,
                type=kind,
                origin="event",
                item=name,
                item_id=item_id,
                quantity=quantity,
                from_=INVENTORY_ACTOR_PLAYER,
                to=recipient,
            )
        # NPC 同士の受け渡しは所持品の対象外
        return None
    item = find_item(
        inventory, item_id=event.item_id, name=event.item.name if event.item else None
    )
    if item is None:
        return None
    owned = int(item.get("quantity") or 0)
    name, item_id = str(item["name"]), str(item["id"])
    if kind == "item_use":
        quantity = event.quantity or 1
        if quantity > owned:
            return None
        if item.get("category") == "consumable":
            remove_item_quantity(inventory, item, quantity)
        return _log_entry(
            turn=turn_number,
            type=kind,
            origin="event",
            item=name,
            item_id=item_id,
            quantity=quantity,
        )
    if kind == "item_discard":
        if event.quantity is not None and event.quantity > owned:
            return None
        removed = remove_item_quantity(inventory, item, event.quantity)
        if removed <= 0:
            return None
        return _log_entry(
            turn=turn_number,
            type=kind,
            origin="event",
            item=name,
            item_id=item_id,
            quantity=removed,
            from_=INVENTORY_ACTOR_PLAYER,
            to=INVENTORY_ACTOR_WORLD,
        )
    if kind == "item_wear":
        if "wear" not in (item.get("capabilities") or []) or item.get("worn"):
            return None
        item["worn"] = True
        return _log_entry(
            turn=turn_number, type=kind, origin="event", item=name, item_id=item_id
        )
    if kind == "item_unwear":
        if not item.get("worn"):
            return None
        item["worn"] = False
        return _log_entry(
            turn=turn_number, type=kind, origin="event", item=name, item_id=item_id
        )
    return None


def apply_world_events(
    state: dict[str, Any],
    events: Any,
    *,
    turn_number: int,
    input_kind: str,
) -> list[dict[str, Any]]:
    """判定 LLM の world_events を検証しながら state へ反映し、適用分のログを返す。

    持ち物システムが無効な run では何もしない。所持していない品の譲渡・使用、
    能力の無い着用、NPC 同士の受け渡しは黙って捨てる。
    """
    if not inventory_enabled(state) or not isinstance(events, list):
        return []
    inventory = ensure_inventory(state)
    applied: list[dict[str, Any]] = []
    for raw in events[:WORLD_EVENTS_MAX]:
        if isinstance(raw, WorldEvent):
            event = raw
        elif isinstance(raw, dict):
            try:
                event = WorldEvent.model_validate(raw)
            except ValidationError:
                continue
        else:
            continue
        entry = _apply_world_event(
            state, inventory, event, turn_number=turn_number, input_kind=input_kind
        )
        if entry is not None:
            applied.append(append_log(inventory, entry))
    return applied


# --- 現実改変パッチの適用 -------------------------------------------------------


def _reality_add(
    inventory: dict[str, Any],
    spec: dict[str, Any],
    *,
    turn_number: int,
    obtained_from: str,
    obtained_when: str | None,
    log_type: str = "item_transfer",
) -> dict[str, Any] | None:
    item = add_item(inventory, spec, turn=turn_number, obtained_from=obtained_from)
    if item is None:
        return None
    if obtained_when:
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            item["metadata"] = metadata
        metadata["obtained_when"] = obtained_when
    return _log_entry(
        turn=turn_number,
        type=log_type,
        origin="reality",
        item=item["name"],
        item_id=item["id"],
        quantity=int(spec.get("quantity") or 1),
        from_=obtained_from,
        to=INVENTORY_ACTOR_PLAYER,
    )


def _apply_reality_op(
    state: dict[str, Any],
    inventory: dict[str, Any],
    op: RealityPatchOp,
    *,
    turn_number: int,
) -> dict[str, Any] | None:
    spec = dict(op.item or {})
    if op.op == "add":
        if not spec.get("name"):
            return None
        obtained_from = _canonical_actor(op.from_, state) or INVENTORY_ACTOR_REALITY
        if obtained_from == INVENTORY_ACTOR_PLAYER:
            obtained_from = INVENTORY_ACTOR_REALITY
        return _reality_add(
            inventory,
            spec,
            turn_number=turn_number,
            obtained_from=obtained_from,
            obtained_when=op.obtained_when,
        )
    if op.op == "transfer":
        if op.to == INVENTORY_ACTOR_PLAYER and op.from_ != INVENTORY_ACTOR_PLAYER:
            if not spec.get("name"):
                if not op.name:
                    return None
                spec = {"name": op.name}
            obtained_from = _canonical_actor(op.from_, state) or INVENTORY_ACTOR_REALITY
            return _reality_add(
                inventory,
                spec,
                turn_number=turn_number,
                obtained_from=obtained_from,
                obtained_when=op.obtained_when,
            )
        if op.from_ == INVENTORY_ACTOR_PLAYER and op.to != INVENTORY_ACTOR_PLAYER:
            existing = find_item(
                inventory, item_id=op.item_id, name=op.name or spec.get("name")
            )
            if existing is None:
                return None
            name, item_id = str(existing["name"]), str(existing["id"])
            removed = remove_item_quantity(inventory, existing, op.quantity or None)
            if removed <= 0:
                return None
            return _log_entry(
                turn=turn_number,
                type="item_transfer",
                origin="reality",
                item=name,
                item_id=item_id,
                quantity=removed,
                from_=INVENTORY_ACTOR_PLAYER,
                to=_canonical_actor(op.to, state) or INVENTORY_ACTOR_WORLD,
            )
        return None
    existing = find_item(
        inventory, item_id=op.item_id, name=op.name or spec.get("name")
    )
    if existing is None:
        return None
    name, item_id = str(existing["name"]), str(existing["id"])
    if op.op == "remove":
        removed = remove_item_quantity(inventory, existing, op.quantity or None)
        if removed <= 0:
            return None
        return _log_entry(
            turn=turn_number,
            type="item_discard",
            origin="reality",
            item=name,
            item_id=item_id,
            quantity=removed,
            from_=INVENTORY_ACTOR_PLAYER,
        )
    if op.op == "set_quantity":
        if op.quantity is None:
            return None
        if op.quantity <= 0:
            remove_item_quantity(inventory, existing, None)
            return _log_entry(
                turn=turn_number,
                type="item_discard",
                origin="reality",
                item=name,
                item_id=item_id,
                quantity=0,
                from_=INVENTORY_ACTOR_PLAYER,
            )
        existing["quantity"] = op.quantity
        return _log_entry(
            turn=turn_number,
            type=INVENTORY_LOG_TYPE_UPDATE,
            origin="reality",
            item=name,
            item_id=item_id,
            quantity=op.quantity,
        )
    if op.op == "replace":
        if not spec.get("name"):
            return None
        obtained_from = _canonical_actor(op.from_, state) or str(
            existing.get("obtained_from") or INVENTORY_ACTOR_REALITY
        )
        obtained_turn = int(existing.get("obtained_turn") or turn_number)
        if "quantity" not in spec:
            # 同じ品の描写を差し替えるだけなら数量は元のまま
            spec["quantity"] = int(existing.get("quantity") or 1)
        remove_item_quantity(inventory, existing, None)
        item = add_item(
            inventory, spec, turn=obtained_turn, obtained_from=obtained_from
        )
        if item is None:
            return None
        if op.worn is not None and "wear" in (item.get("capabilities") or []):
            item["worn"] = bool(op.worn)
        if op.obtained_when:
            item.setdefault("metadata", {})["obtained_when"] = op.obtained_when
        return _log_entry(
            turn=turn_number,
            type=INVENTORY_LOG_TYPE_UPDATE,
            origin="reality",
            item=item["name"],
            item_id=item["id"],
            quantity=int(item.get("quantity") or 1),
            reason=name,
        )
    if op.op == "update":
        if "name" in spec:
            existing["name"] = spec["name"]
        if "category" in spec:
            existing["category"] = spec["category"]
        if "tags" in spec:
            existing["tags"] = spec["tags"]
        if "quantity" in spec:
            existing["quantity"] = spec["quantity"]
        if op.quantity is not None and op.quantity > 0:
            existing["quantity"] = op.quantity
        category = str(existing.get("category") or INVENTORY_DEFAULT_CATEGORY)
        if "capabilities" in spec or "category" in spec:
            existing["capabilities"] = normalize_capabilities(
                spec.get("capabilities", existing.get("capabilities")), category
            )
        if op.worn is not None:
            existing["worn"] = bool(op.worn) and "wear" in (
                existing.get("capabilities") or []
            )
        if op.from_ is not None:
            existing["obtained_from"] = (
                _canonical_actor(op.from_, state) or INVENTORY_ACTOR_REALITY
            )
        if op.obtained_when:
            metadata = existing.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
                existing["metadata"] = metadata
            metadata["obtained_when"] = op.obtained_when
        return _log_entry(
            turn=turn_number,
            type=INVENTORY_LOG_TYPE_UPDATE,
            origin="reality",
            item=str(existing["name"]),
            item_id=item_id,
            quantity=int(existing.get("quantity") or 1),
        )
    return None


def apply_reality_patch(
    state: dict[str, Any], patch: Any, *, turn_number: int
) -> list[dict[str, Any]]:
    """現実改変ターンの reality_patch を state へ反映し、適用分のログを返す。

    通常の World Event と違い所有権や能力の検証はせず、宣言どおりに書き換える。
    構造が壊れた要素だけ捨てる。
    """
    if not inventory_enabled(state) or not isinstance(patch, dict):
        return []
    try:
        parsed = RealityPatch.model_validate(patch)
    except ValidationError:
        return []
    inventory = ensure_inventory(state)
    applied: list[dict[str, Any]] = []
    for op in parsed.inventory:
        entry = _apply_reality_op(state, inventory, op, turn_number=turn_number)
        if entry is not None:
            applied.append(append_log(inventory, entry))
    for note in parsed.npc_notes:
        npc = resolve_npc_name(note.npc, state)
        if not npc:
            continue
        entry = _ensure_npc_entry(state, npc)
        notes = entry.setdefault("notes", [])
        if note.note not in notes:
            notes.append(note.note)
            if len(notes) > INVENTORY_NPC_NOTES_MAX:
                del notes[: len(notes) - INVENTORY_NPC_NOTES_MAX]
    npc_states = state.get("npc_states")
    if isinstance(npc_states, dict):
        for raw_name in parsed.npc_boundary_reset:
            npc = resolve_npc_name(raw_name, state)
            entry = npc_states.get(npc)
            if isinstance(entry, dict):
                entry["boundary_violations"] = 0
                entry["last_violation_turn"] = None
                entry["last_violation"] = None
                entry["last_violation_severity"] = None
    return applied


# --- 持ち物パネルの行動 -----------------------------------------------------------


def _item_view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or ""),
        "category": str(item.get("category") or INVENTORY_DEFAULT_CATEGORY),
        "tags": [str(tag) for tag in item.get("tags") or []],
        "quantity": int(item.get("quantity") or 0),
        "worn": bool(item.get("worn")),
        "capabilities": [str(cap) for cap in item.get("capabilities") or []],
        "obtained_from": str(item.get("obtained_from") or INVENTORY_ACTOR_WORLD),
        "obtained_turn": int(item.get("obtained_turn") or 0),
    }


def resolve_item_action(
    state: dict[str, Any], item_action: Any, language: str = "ja"
) -> dict[str, Any]:
    """持ち物パネルの行動を検証する。state は変更しない(プレビューでも安全)。

    wear / unwear / discard はプレイヤー自身の行為なので resolved=True で確定し、
    give / use は NPC の意思・状況が要るため resolved=False で LLM に委ねる。
    成立しない行動は InventoryActionError(手番未消費)。
    """
    if not isinstance(item_action, dict):
        raise InventoryActionError("invalid_item", "持ち物の指定が不正です")
    action = _clean_text(item_action.get("action"), 20).lower()
    if action not in INVENTORY_ACTIONS:
        raise InventoryActionError("item_action_unavailable", "その操作はできません")
    inventory = (
        state.get("inventory") if isinstance(state.get("inventory"), dict) else {}
    )
    item = find_item(
        inventory,
        item_id=_clean_text(item_action.get("item_id"), INVENTORY_ITEM_ID_MAX),
    )
    if item is None:
        raise InventoryActionError("invalid_item", "その持ち物は所持していません")
    capabilities = [str(cap) for cap in item.get("capabilities") or []]
    worn = bool(item.get("worn"))
    if action in {"give", "use"} and action not in capabilities:
        raise InventoryActionError(
            "item_action_unavailable", "その持ち物ではできない操作です"
        )
    if action == "wear":
        if "wear" not in capabilities:
            raise InventoryActionError(
                "item_action_unavailable", "その持ち物は着用できません"
            )
        if worn:
            raise InventoryActionError(
                "item_action_unavailable", "すでに着用しています"
            )
    if action == "unwear" and not worn:
        raise InventoryActionError("item_action_unavailable", "着用していません")
    target: str | None = None
    if action == "give":
        raw_target = _clean_text(item_action.get("target"), INVENTORY_NPC_NAME_MAX)
        if raw_target:
            resolved = resolve_npc_name(raw_target, state)
            target = (
                f"{INVENTORY_ACTOR_CHARACTER_PREFIX}{resolved}" if resolved else None
            )
        else:
            sim = state.get("sim")
            partner = (
                str(sim.get("partner_name") or "") if isinstance(sim, dict) else ""
            )
            if partner:
                target = f"{INVENTORY_ACTOR_CHARACTER_PREFIX}{partner}"
    outcome = {"wear": "worn", "unwear": "removed", "discard": "discarded"}.get(action)
    return {
        "action": action,
        "item": _item_view(item),
        "target": target,
        "resolved": action in INVENTORY_DETERMINISTIC_ACTIONS,
        "outcome": outcome,
    }


def apply_item_resolution(
    state: dict[str, Any], item_resolution: Any, *, turn_number: int
) -> list[dict[str, Any]]:
    """resolve_item_action の確定結果(wear/unwear/discard)を state へ反映する。

    判定 LLM が同じ出来事を world_events として先に適用していれば何もしない。
    """
    if (
        not inventory_enabled(state)
        or not isinstance(item_resolution, dict)
        or not item_resolution.get("resolved")
    ):
        return []
    inventory = ensure_inventory(state)
    item_info = item_resolution.get("item") or {}
    item = find_item(inventory, item_id=str(item_info.get("id") or ""))
    if item is None:
        return []
    action = str(item_resolution.get("action") or "")
    name, item_id = str(item["name"]), str(item["id"])
    if action == "wear":
        if item.get("worn"):
            return []
        item["worn"] = True
        entry = _log_entry(
            turn=turn_number,
            type="item_wear",
            origin="action",
            item=name,
            item_id=item_id,
        )
    elif action == "unwear":
        if not item.get("worn"):
            return []
        item["worn"] = False
        entry = _log_entry(
            turn=turn_number,
            type="item_unwear",
            origin="action",
            item=name,
            item_id=item_id,
        )
    elif action == "discard":
        removed = remove_item_quantity(inventory, item, None)
        if removed <= 0:
            return []
        entry = _log_entry(
            turn=turn_number,
            type="item_discard",
            origin="action",
            item=name,
            item_id=item_id,
            quantity=removed,
            from_=INVENTORY_ACTOR_PLAYER,
            to=INVENTORY_ACTOR_WORLD,
        )
    else:
        return []
    return [append_log(inventory, entry)]


def item_resolution_narrative_suffix(
    item_resolution: Any,
    narrative: str,
    language: str,
    *,
    narration_voice: str = NARRATION_VOICE_DEFAULT,
    narration_pronoun: str = NARRATION_PRONOUN_DEFAULT,
) -> str:
    """確定した持ち物行動を本文が書き落としたときに補う1文。人称規則に従う。"""
    if not isinstance(item_resolution, dict) or not item_resolution.get("resolved"):
        return ""
    name = str((item_resolution.get("item") or {}).get("name") or "").strip()
    action = str(item_resolution.get("action") or "")
    if not name or name in narrative:
        return ""
    voice = (
        narration_voice
        if narration_voice in NARRATION_VOICES
        else NARRATION_VOICE_DEFAULT
    )
    pronoun = (
        re.sub(r"\s+", "", str(narration_pronoun or "")) or NARRATION_PRONOUN_DEFAULT
    )
    if language == "ja":
        verbs = {
            "wear": "を身につけた。",
            "unwear": "を脱いだ。",
            "discard": "を捨てた。",
        }
        verb = verbs.get(action)
        if verb is None:
            return ""
        if voice == "first_person":
            subject = f"{pronoun}は"
        elif voice == "third_person":
            # 変身で性別が変わりうるため主語は補わず省略する
            subject = ""
        else:
            subject = "君は"
        return f"{subject}{name}{verb}"
    verbs_en = {"wear": "put on", "unwear": "took off", "discard": "threw away"}
    verb_en = verbs_en.get(action)
    if verb_en is None:
        return ""
    subject_en = {"first_person": "I", "third_person": "They"}.get(voice, "You")
    return f"{subject_en} {verb_en} {name}."


# --- LLM / 配信用ビュー -----------------------------------------------------------


def _items(state: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = state.get("inventory")
    if not isinstance(inventory, dict):
        return []
    return [item for item in inventory.get("items") or [] if isinstance(item, dict)]


def _log(state: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = state.get("inventory")
    if not isinstance(inventory, dict):
        return []
    return [entry for entry in inventory.get("log") or [] if isinstance(entry, dict)]


def lean_inventory_for_llm(state: dict[str, Any]) -> dict[str, Any] | None:
    """物語・判定へ渡す所持品。メタデータを落とし、ログは直近分だけ。"""
    if not inventory_enabled(state):
        return None
    log = _log(state)
    return {
        "items": [_item_view(item) for item in _items(state)],
        "recent_log": log[-INVENTORY_LOG_CONTEXT_MAX:] if log else [],
    }


def npc_states_for_llm(state: dict[str, Any]) -> dict[str, Any]:
    """違反記録かノートのある NPC だけを LLM へ渡す。"""
    npc_states = state.get("npc_states")
    if not isinstance(npc_states, dict):
        return {}
    result: dict[str, Any] = {}
    for name, entry in npc_states.items():
        if not isinstance(entry, dict):
            continue
        violations = int(entry.get("boundary_violations") or 0)
        notes = [str(note) for note in entry.get("notes") or []]
        if violations <= 0 and not notes:
            continue
        result[str(name)] = {
            "boundary_violations": violations,
            "last_violation_turn": entry.get("last_violation_turn"),
            "last_violation": entry.get("last_violation"),
            "last_violation_severity": entry.get("last_violation_severity"),
            "notes": notes,
        }
    return result


def worn_inventory_items(
    state: dict[str, Any], *, pending: Any = None
) -> list[dict[str, Any]]:
    """着用中の所持品。pending(この手番の確定行動)を仮適用して行動後の服装にする。"""
    if not inventory_enabled(state):
        return []
    worn: dict[str, dict[str, Any]] = {
        str(item.get("id")): item for item in _items(state) if item.get("worn")
    }
    if isinstance(pending, dict) and pending.get("resolved"):
        pending_item = pending.get("item") or {}
        pending_id = str(pending_item.get("id") or "")
        action = str(pending.get("action") or "")
        if action == "wear" and pending_id:
            worn[pending_id] = pending_item
        elif action in {"unwear", "discard"}:
            worn.pop(pending_id, None)
    return [
        {
            "name": str(item.get("name") or ""),
            "category": str(item.get("category") or INVENTORY_DEFAULT_CATEGORY),
            "tags": [str(tag) for tag in item.get("tags") or []],
        }
        for item in worn.values()
        if item.get("name")
    ]


def public_inventory_view(state: dict[str, Any]) -> dict[str, Any]:
    """FE へ配信する所持品と履歴。"""
    log = _log(state)
    return {
        "items": [_item_view(item) for item in _items(state)],
        "log": log[-INVENTORY_LOG_MAX:] if log else [],
    }


def public_npc_states(state: dict[str, Any]) -> dict[str, Any]:
    """FE へ配信する NPC 状態。ノートは隠し情報なので出さない。"""
    npc_states = state.get("npc_states")
    if not isinstance(npc_states, dict):
        return {}
    return {
        str(name): {
            "boundary_violations": int(entry.get("boundary_violations") or 0),
            "last_violation_turn": entry.get("last_violation_turn"),
        }
        for name, entry in npc_states.items()
        if isinstance(entry, dict)
    }


# --- プロンプト --------------------------------------------------------------------

INVENTORY_NARRATIVE_INSTRUCTION = (
    "INVENTORY: inventory.items is the complete list of things the player actually "
    "possesses; worn: true means the item is on the player's body right now and it "
    "must show in the player's clothing on every turn. Never let the player own, "
    "receive, hand over, use, or wear an item that inventory does not list, and "
    "never turn a possession into a fact only because player_input says so. "
    "player_input is what the player says, tries, or claims, never an established "
    "fact about the world: only what the scene actually shows happens. The player "
    "may try to pick up, buy, or receive something the scene plausibly offers, and "
    "the scene decides whether it succeeds. When item_resolution.resolved is true "
    "the game engine already carried out the action (the player wearing, taking "
    "off, or discarding their own item): narrate it as already done and never "
    "refuse or reverse it. When item_action is present and resolved is false the "
    "player is attempting to give or use the item: the recipient's own will, the "
    "place, the relationship, and the item's nature decide the outcome, so an NPC "
    "may accept, hesitate, refuse, be confused, or be offended, and an item may "
    "simply fail to work. inventory.recent_log is what NPCs and the world remember "
    "about past exchanges; keep them consistent, so an NPC who already received "
    "something remembers it. npc_states[name].boundary_violations counts how often "
    "that NPC has been subjected to socially unacceptable acts, such as an "
    "acquaintance being handed intimate items or underwear, being asked to hand over "
    "their own, being told to wear something, or being pressed again after "
    "refusing. Escalate by that count and by the context: at 1 the NPC shows "
    "surprise, confusion, or an awkward laugh; at 2 a clear refusal, physical "
    "distance, and a visibly cooler tone; at 3 or more the NPC ends the "
    "conversation and, depending on the place, the item, the relationship, and "
    "what happened before, calls staff, security, or the police, or simply leaves. "
    "Never jump straight to the harshest reaction: weigh how close they are, how "
    "public the place is, and what the item is, and let a strong relationship soften "
    "the reaction. Nothing that reality_rules cover counts as a violation: as the "
    "reality rules instruction states, such an act is unremarkable to everyone. "
    "Choices must never duplicate the inventory buttons (giving, using, wearing, "
    "removing, or discarding a specific owned item); offer conversation and action "
    "beats instead."
)

WORLD_EVENTS_INSTRUCTION = (
    'Add "world_events": a list of at most 6 mechanical facts that the narrative '
    "actually shows, normally an empty list. Each entry is "
    '{"type":"item_transfer|item_use|item_discard|item_wear|item_unwear|boundary_violation",'
    '"from":"player|world|character:<name>","to":"player|world|character:<name>",'
    '"item":{"name":"...","category":"clothing|underwear|accessory|consumable|tool|document|key|gift|other",'
    '"tags":["..."],"quantity":1,"capabilities":["give","use","wear","discard"]},'
    '"item_id":null,"npc":null,"severity":"minor|major","reason":null}. '
    "Report an item_transfer only when the narrative shows the handover completed: "
    "an offer, a request, a promise, a refusal, or the player merely claiming to "
    "have received or given something is not a transfer. Something the player picks "
    "up or buys is a transfer from world to player; a gift the NPC accepts is a "
    "transfer from player to character:<name>; a refused gift produces no event. "
    "Name characters exactly as the state does (use state.sim.partner_name for the "
    "partner). For an item the player already owns, set item_id from inventory.items "
    "and item may be omitted. Use item_use only when the item was actually used, "
    "item_wear and item_unwear only when the player actually put it on or took it "
    "off, and item_discard only when it was actually thrown away or left behind. "
    "Emit boundary_violation, with npc set to the character concerned and reason "
    "stating what the player did, only when that NPC treated the player's act as a "
    "violation of social norms and no entry in reality_rules covers the act. Events "
    "for what item_resolution already resolved may be omitted. Keep the list empty "
    "when nothing changed hands."
)

ROMANCE_BOUNDARY_SCORING_INSTRUCTION = (
    "When you emit a boundary_violation in world_events, affection_delta must be "
    "negative on this turn."
)

REALITY_PATCH_INSTRUCTION = (
    'Add "reality_patch": {"inventory":[],"npc_notes":[],"npc_boundary_reset":[]}. '
    "This turn is a reality alteration: the declaration rewrites the world directly, "
    "and what it states about possessions is fact. Fill inventory only with the "
    "possession changes the declaration itself states, each as "
    '{"op":"add|remove|replace|set_quantity|update|transfer","item_id":null,"name":null,'
    '"item":{"name":"...","category":"...","tags":[],"quantity":1,"capabilities":[]},'
    '"quantity":null,"from":null,"to":null,"worn":null,"obtained_when":null}: '
    "add creates a possession the player now has (set from to character:<name> and "
    "obtained_when when the declaration says who gave it and when); remove and "
    "set_quantity adjust or delete an owned item, identified by item_id from "
    "inventory.items or by name; replace swaps an owned item for the described one; "
    "update changes an owned item's name, category, tags, capabilities, worn state, "
    "or origin; transfer moves an item between the player and a character in either "
    "direction. Fill npc_notes with what a character now remembers because of the "
    'declaration, as {"npc":"...","note":"..."}, and npc_boundary_reset with the '
    "names of characters whose memory of the player's past boundary violations the "
    "declaration erases. Leave every list empty when the declaration does not concern "
    "possessions or memories. The other alteration fields keep their own rules."
)

INVENTORY_VISUAL_INSTRUCTION = (
    "worn_inventory_items lists garments and accessories the player is currently "
    "wearing from their inventory. visual_state.clothing and player_tags must include "
    "every one of them on this turn (underwear covered by outer clothing follows the "
    "clothing layer rule), and an item the player just took off or discarded must no "
    "longer appear."
)
