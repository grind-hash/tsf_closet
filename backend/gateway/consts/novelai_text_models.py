"""NovelAI Text API で選択可能なテキストモデルの定義（唯一の情報源）。

設定画面と Prompt Expander の両方がこの定数を参照する。
"""

from __future__ import annotations

from typing import Final

NOVELAI_TEXT_MODEL_OPTIONS: Final[tuple[str, ...]] = ("glm-4-6", "xialong-v1")
DEFAULT_NOVELAI_TEXT_MODEL: Final[str] = "glm-4-6"

# 表示用ラベル（UI 側で上書きしてもよい）
NOVELAI_TEXT_MODEL_LABELS: Final[dict[str, str]] = {
    "glm-4-6": "NovelAI GLM 4.6",
    "xialong-v1": "NovelAI Xialong v1",
}


def is_novelai_text_model(name: str | None) -> bool:
    """選択可能なテキストモデル名かどうかを返す。"""
    return bool(name) and name in NOVELAI_TEXT_MODEL_OPTIONS
