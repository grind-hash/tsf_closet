"""履歴遡及の対象判定とプロンプト用コンテキストを提供する。"""

from __future__ import annotations

from ..consts.history_lookback import (
    HISTORY_LOOKBACK_DEFAULT,
    HISTORY_LOOKBACK_MAX,
    HISTORY_LOOKBACK_MIN,
)

_TYPE_LABELS = {
    "dress_up": "着替",
    "reality_alter": "改変",
    "action": "行動",
    "conversation": "会話",
}


def resolve_history_lookback_enabled(
    explicit: bool | None,
    *,
    instruction_type: str | None = None,
    transformation_type: str | None = None,
) -> bool:
    """明示値または操作種別から履歴遡及の有効状態を解決する。"""
    if explicit is not None:
        return explicit
    if instruction_type in {"action", "conversation"}:
        return True
    if transformation_type == "reality":
        return False
    return False


def clamp_history_lookback_count(value: object) -> int:
    """履歴遡及件数を [MIN, MAX] に収める。数値でなければ既定値を返す。"""
    try:
        ivalue = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return HISTORY_LOOKBACK_DEFAULT
    return max(HISTORY_LOOKBACK_MIN, min(HISTORY_LOOKBACK_MAX, ivalue))


def build_history_context(entries: list[tuple[str, str]] | None) -> str:
    """統合タイムラインをプロンプトへ追加できる参考情報へ整形する。"""
    if not entries:
        return ""

    lines = [
        f"- [{_TYPE_LABELS.get(instruction_type, instruction_type)}] {text}"
        for instruction_type, text in entries
    ]
    return (
        "\n\n【これまでの履歴（参考情報）】\n"
        + "\n".join(lines)
        + "\n上記は現在状態に至る経緯としてのみ参照し、"
        "現在の指示にない過去の変更を再実行しないでください。"
    )
