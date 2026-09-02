"""romance の攻略対象立ち絵を、その手番で描いたか / なぜ据え置いたかの記録。

``state_json["partner_portrait_status"]`` に 1 手番 1 値で入り、
``_serialize_turn`` / ``_serialize_run`` が配信する。フロントエンドは同じ
集合を ``apis/adventure.ts`` の ``AdventurePartnerPortraitStatus`` に持ち、
表示文言へ写す。LLM には見せない(``_lean_state_for_llm`` で除外)。
"""

from __future__ import annotations

# この手番で新しい立ち絵を描いた
PARTNER_PORTRAIT_GENERATED = "generated"
# 毎ターン描く設定が OFF、または 3D モデル表示中で FE が生成を求めなかった
PARTNER_PORTRAIT_NOT_REQUESTED = "not_requested"
# visual_state と画像タグが前手番と一致し、画像工程ごと省いた
PARTNER_PORTRAIT_SCENE_UNCHANGED = "scene_unchanged"
# その手番の main_characters に相手が居ず、立ち絵のタグを組めなかった
PARTNER_PORTRAIT_PARTNER_ABSENT = "partner_absent"
# 画像生成ヘルパが例外で失敗した(ターン進行は止めない)
PARTNER_PORTRAIT_FAILED = "failed"
# 場面判定(visual LLM)が失敗し、画像工程に入れなかった
PARTNER_PORTRAIT_VISUAL_FAILED = "visual_failed"

PARTNER_PORTRAIT_STATUSES: tuple[str, ...] = (
    PARTNER_PORTRAIT_GENERATED,
    PARTNER_PORTRAIT_NOT_REQUESTED,
    PARTNER_PORTRAIT_SCENE_UNCHANGED,
    PARTNER_PORTRAIT_PARTNER_ABSENT,
    PARTNER_PORTRAIT_FAILED,
    PARTNER_PORTRAIT_VISUAL_FAILED,
)


def normalize_partner_portrait_status(value: object) -> str | None:
    """集合に無い値(旧 run のキー欠落を含む)は None にする。"""
    text = str(value or "").strip()
    return text if text in PARTNER_PORTRAIT_STATUSES else None


__all__ = [
    "PARTNER_PORTRAIT_FAILED",
    "PARTNER_PORTRAIT_GENERATED",
    "PARTNER_PORTRAIT_NOT_REQUESTED",
    "PARTNER_PORTRAIT_PARTNER_ABSENT",
    "PARTNER_PORTRAIT_SCENE_UNCHANGED",
    "PARTNER_PORTRAIT_STATUSES",
    "PARTNER_PORTRAIT_VISUAL_FAILED",
    "normalize_partner_portrait_status",
]
