"""Boundary values and vocabulary for the Adventure inventory (持ち物) system.

Items live in ``AdventureRun.state_json["inventory"]`` and change only through
World Events returned by the resolution LLM (validated in Python), reality
patches on ``reality_alter`` turns, or deterministic item actions from the UI.
The vocabulary here is the single source of truth shared by the prompts, the
validators, and the frontend labels.
"""

from __future__ import annotations

# アイテム分類。語彙外は other へ倒す
INVENTORY_CATEGORIES: tuple[str, ...] = (
    "clothing",
    "underwear",
    "accessory",
    "consumable",
    "tool",
    "document",
    "key",
    "gift",
    "other",
)
INVENTORY_DEFAULT_CATEGORY: str = "other"
# 着用できる分類。wear 能力はこの分類にしか付かない
INVENTORY_WEARABLE_CATEGORIES: frozenset[str] = frozenset(
    {"clothing", "underwear", "accessory"}
)

# アイテムに付く操作能力
INVENTORY_CAPABILITIES: tuple[str, ...] = ("give", "use", "wear", "discard")
# LLM が capabilities を省いたときの分類別既定値
INVENTORY_DEFAULT_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "clothing": ("give", "wear", "discard"),
    "underwear": ("give", "wear", "discard"),
    "accessory": ("give", "wear", "discard"),
    "consumable": ("give", "use", "discard"),
    "tool": ("give", "use", "discard"),
    "document": ("give", "use", "discard"),
    "key": ("give", "use", "discard"),
    "gift": ("give", "discard"),
    "other": ("give", "discard"),
}

# 判定 LLM が返す World Event の種別
WORLD_EVENT_TYPES: tuple[str, ...] = (
    "item_transfer",
    "item_use",
    "item_discard",
    "item_wear",
    "item_unwear",
    "boundary_violation",
)
BOUNDARY_SEVERITIES: tuple[str, ...] = ("minor", "major")

# 持ち物パネルのボタンから送る行動。wear/unwear/discard はプレイヤー自身の
# 行為なので Python 側で確定し、give/use は NPC の意思・状況を LLM が判定する
INVENTORY_ACTIONS: tuple[str, ...] = ("give", "use", "wear", "unwear", "discard")
INVENTORY_DETERMINISTIC_ACTIONS: tuple[str, ...] = ("wear", "unwear", "discard")

# 現実改変(reality_alter)ターンだけが使える持ち物の直接書き換え
REALITY_PATCH_OPS: tuple[str, ...] = (
    "add",
    "remove",
    "replace",
    "set_quantity",
    "update",
    "transfer",
)

# 所有者・入手元の表記
INVENTORY_ACTOR_PLAYER: str = "player"
INVENTORY_ACTOR_WORLD: str = "world"
INVENTORY_ACTOR_REALITY: str = "reality"
INVENTORY_ACTOR_CHARACTER_PREFIX: str = "character:"

# ログの由来。event=判定 LLM の World Event、reality=現実改変、action=UI の行動
INVENTORY_LOG_ORIGINS: tuple[str, ...] = ("event", "reality", "action")

# 上限
INVENTORY_ITEMS_MAX: int = 24
INVENTORY_QUANTITY_MAX: int = 99
INVENTORY_LOG_MAX: int = 30
# LLM へ渡す直近ログ件数
INVENTORY_LOG_CONTEXT_MAX: int = 8
WORLD_EVENTS_MAX: int = 6
REALITY_PATCH_OPS_MAX: int = 8
INVENTORY_ITEM_NAME_MAX: int = 60
INVENTORY_ITEM_ID_MAX: int = 40
INVENTORY_TAGS_MAX: int = 8
INVENTORY_TAG_LENGTH_MAX: int = 30
INVENTORY_REASON_MAX: int = 200
INVENTORY_NPC_NAME_MAX: int = 60
INVENTORY_NPC_STATES_MAX: int = 12
INVENTORY_NPC_NOTES_MAX: int = 6
INVENTORY_NPC_NOTE_MAX: int = 200
BOUNDARY_VIOLATIONS_MAX: int = 9
# romance で境界侵害が起きた手番に affection_delta へ強制する下限(負値の幅)
BOUNDARY_AFFECTION_FLOOR: int = 1

__all__ = [
    "BOUNDARY_AFFECTION_FLOOR",
    "BOUNDARY_SEVERITIES",
    "BOUNDARY_VIOLATIONS_MAX",
    "INVENTORY_ACTIONS",
    "INVENTORY_ACTOR_CHARACTER_PREFIX",
    "INVENTORY_ACTOR_PLAYER",
    "INVENTORY_ACTOR_REALITY",
    "INVENTORY_ACTOR_WORLD",
    "INVENTORY_CAPABILITIES",
    "INVENTORY_CATEGORIES",
    "INVENTORY_DEFAULT_CAPABILITIES",
    "INVENTORY_DEFAULT_CATEGORY",
    "INVENTORY_DETERMINISTIC_ACTIONS",
    "INVENTORY_ITEMS_MAX",
    "INVENTORY_ITEM_ID_MAX",
    "INVENTORY_ITEM_NAME_MAX",
    "INVENTORY_LOG_CONTEXT_MAX",
    "INVENTORY_LOG_MAX",
    "INVENTORY_LOG_ORIGINS",
    "INVENTORY_NPC_NAME_MAX",
    "INVENTORY_NPC_NOTES_MAX",
    "INVENTORY_NPC_NOTE_MAX",
    "INVENTORY_NPC_STATES_MAX",
    "INVENTORY_QUANTITY_MAX",
    "INVENTORY_REASON_MAX",
    "INVENTORY_TAGS_MAX",
    "INVENTORY_TAG_LENGTH_MAX",
    "INVENTORY_WEARABLE_CATEGORIES",
    "REALITY_PATCH_OPS",
    "REALITY_PATCH_OPS_MAX",
    "WORLD_EVENTS_MAX",
    "WORLD_EVENT_TYPES",
]
