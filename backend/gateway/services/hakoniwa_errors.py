"""AI箱庭の操作エラー(状態遷移の各モジュールで共有する)。"""

from __future__ import annotations


class HakoniwaError(Exception):
    """箱庭の操作を受け付けられないときの例外。code は API のエラーコード。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
