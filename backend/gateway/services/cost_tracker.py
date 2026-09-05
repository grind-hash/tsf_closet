"""1 操作（手番・Run 作成・画像再生成など）の API 料金（USD）を集計する。

各サービスは LLM / 画像 API の結果を受け取ったら ``record_cost`` を呼ぶだけでよく、
操作の入口で ``begin_cost_tracking`` したトラッカーに合算される。トラッカーは
``contextvars`` で受け渡すため、``asyncio.create_task`` で分岐した producer 内の
加算も（コンテキストが複製されても同じオブジェクトを指すので）呼び出し元へ反映される。
入口でトラッカーを開始していない経路では ``record_cost`` は何もしない。
"""

from __future__ import annotations

import contextvars


class CostTracker:
    __slots__ = ("total_usd",)

    def __init__(self) -> None:
        self.total_usd = 0.0

    def add(self, cost_usd: float | None) -> None:
        if cost_usd:
            self.total_usd += float(cost_usd)


_current: contextvars.ContextVar[CostTracker | None] = contextvars.ContextVar(
    "cost_tracker", default=None
)


def begin_cost_tracking() -> CostTracker:
    """新しいトラッカーを現在のコンテキストに設定して返す。"""
    tracker = CostTracker()
    _current.set(tracker)
    return tracker


def current_cost_tracker() -> CostTracker | None:
    return _current.get()


def record_cost(cost_usd: float | None) -> None:
    """現在のトラッカーに料金を加算する。トラッカーが無ければ何もしない。"""
    tracker = _current.get()
    if tracker is not None:
        tracker.add(cost_usd)
