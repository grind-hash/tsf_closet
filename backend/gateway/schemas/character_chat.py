"""キャラチャットのリクエストモデル。"""

from __future__ import annotations

from typing import Literal

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
    # 設定画面のトグル。案内役キャラのスレッドで、サーバーにキー・地点があるときだけ効く
    use_web_search: bool = False
    use_weather: bool = False
    # 「おすすめのプレイを聞く」ボタンからの送信。案内役キャラのスレッドでだけ、判定 LLM を
    # 待たずに必ず提案を作る
    request_play_proposal: bool = False


class CharacterChatAdventureAppearanceRequest(BaseModel):
    """adventure 種の姿の切り替え。

    default = 表示モードで決める既定(シナリオの姿に合わせる)、partner_portrait =
    最新の攻略対象立ち絵、scene = 攻略対象が写る最新の場面画像。
    """

    mode: Literal["default", "partner_portrait", "scene"] = "default"


class CharacterChatAvatarRequest(BaseModel):
    """アバターの表示の指定。

    auto = 自動(案内役は同梱モデル → run の対面会話モデル → character_name が
    一致する登録済みモデル → 2D 立ち絵)、none = 2D 立ち絵を使う、
    model = avatar_id の登録済みモデル、live2d = 案内役専用の試作を明示する。
    """

    mode: Literal["auto", "none", "model", "live2d"] = "auto"
    avatar_id: str | None = None


class CharacterChatPortraitRequest(BaseModel):
    """立ち絵の描き直し。

    reference は参照にする画像(current = いまの姿、scene / partner = adventure 種の
    run が持つ画像)。use_precise_reference は NovelAI の精密参照(Anlas 消費)を使うか。
    """

    reference: Literal["current", "scene", "partner"] = "current"
    use_precise_reference: bool = False
