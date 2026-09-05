"""ルーターの統合テストで使う軽量スタブ。

DB を使わずに固定値を返す。DB を伴う検証には ``isolated_db`` フィクスチャを使う。
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any


class StubSessionStore:
    """会話 API 向け。セッション 1 件と空の履歴・会話を返す。"""

    def __init__(
        self, *, language: str = "ja", nsfw_mode: bool = False, bloom: int = 40
    ) -> None:
        self.language = language
        self.nsfw_mode = nsfw_mode
        self.bloom = bloom
        self.calls: list[str] = []

    async def get_session_by_id(self, session_id: str):
        return SimpleNamespace(character_id=None, transformation_count=1)

    async def get_session_stats(self, session_id: str):
        return SimpleNamespace(bloom=self.bloom, nsfw_mode=self.nsfw_mode)

    async def create_session_stats(self, session_id: str):
        return SimpleNamespace(bloom=self.bloom, nsfw_mode=self.nsfw_mode)

    async def get_conversation_history(self, session_id: str, limit: int = 20):
        self.calls.append("conversation_history")
        return []

    async def get_recent_instructions(self, session_id: str, limit: int = 20):
        self.calls.append("timeline")
        return []

    async def get_history(self, session_id: str):
        return []

    async def add_conversation(
        self, session_id: str, role: str, content: str, **kwargs: Any
    ):
        self.calls.append(f"save:{role}")
        return None

    async def get_session_attribute_texts(self, session_id: str):
        return []

    async def get_user_settings(self, user_id: str = "default-user"):
        return {
            "language": self.language,
            "difficulty": "normal",
            "nsfw_mode": self.nsfw_mode,
        }


class StubSettingsService:
    """settings_router 向け。``state`` 辞書をそのまま読み書きする。"""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.state: dict[str, Any] = (
            state
            if state is not None
            else {"nsfw_mode": False, "difficulty": "normal", "language": "ja"}
        )

    async def get_user_settings(self, user_id: str = "default-user"):
        return dict(self.state)

    async def update_user_settings(self, user_id: str = "default-user", **fields: Any):
        for key, value in fields.items():
            if value is not None:
                self.state[key] = value
        return dict(self.state)

    def get_settings_for_session(self, session_id: str, settings_model_cls):
        return settings_model_cls()

    def update_settings_for_session(
        self,
        session_id: str,
        updates,
        settings_model_cls,
        inpaint_model_cls,
        change_model_cls,
    ):
        return settings_model_cls()

    def reset_settings_for_session(self, session_id: str):
        return {"message": "Settings reset to defaults", "session_id": session_id}

    @staticmethod
    def utc_now_iso() -> str:
        return datetime.now(UTC).isoformat()
