"""キャラチャットのリクエストモデル。"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from ..consts.character_chat import MESSAGE_MAX


class CharacterChatSourceRequest(BaseModel):
    """姿・人物の元にするセッション / 履歴 / Prompt Expander エントリ。"""

    source_session_id: str | None = Field(None, min_length=1)
    source_history_id: str | None = None
    source_prompt_expander_entry_id: str | None = Field(None, max_length=80)

    @model_validator(mode="after")
    def _require_source(self) -> CharacterChatSourceRequest:
        if not self.source_session_id and not self.source_prompt_expander_entry_id:
            raise ValueError(
                "source_session_id or source_prompt_expander_entry_id is required"
            )
        return self


class CharacterChatCreateRequest(CharacterChatSourceRequest):
    """セッション由来キャラの作成。"""


class CharacterChatAppearanceRequest(CharacterChatSourceRequest):
    """既存スレッドの姿の差し替え。"""


class CharacterChatMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=MESSAGE_MAX)
