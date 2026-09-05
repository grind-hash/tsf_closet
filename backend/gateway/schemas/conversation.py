"""会話（キャラクターとのチャット、指示候補生成）の API モデル。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConversationMessageResponse(BaseModel):
    """会話メッセージ（API用）"""

    id: str = Field(..., description="メッセージID")
    role: str = Field(..., description="発言者 (user/character)")
    content: str = Field(..., description="メッセージ内容")
    created_at: str = Field(..., description="送信日時 (ISO形式)")
    instruction_type: str | None = Field(
        None,
        description="指示タイプ (dress_up/reality_alter/conversation/action/image_only)",
    )


class SuggestInstructionRequest(BaseModel):
    """過去メッセージからの指示テキスト生成リクエスト"""

    session_id: str = Field(..., description="セッションID")
    instruction_type: str | None = Field(
        None,
        description="絞り込む指示タイプ (dress_up/reality_alter/action)。None/'all'は全種類を統合",
    )
    keyword: str | None = Field(
        None,
        description="生成に反映したいキーワード/自由入力テキスト（入力欄の内容等）",
        max_length=500,
    )
    use_memory: bool = Field(
        False,
        description="保存済みメモリテキスト（ユーザーの嗜好傾向）を生成に反映するか",
    )
    use_play_memory: bool = Field(
        False, description="セッション単位のプレイメモを生成に反映するか"
    )
    language: str = Field("ja", description="生成言語 (ja/en)")


class SuggestInstructionResponse(BaseModel):
    """過去メッセージからの指示テキスト生成レスポンス"""

    suggestion: str = Field(..., description="生成された指示テキスト")
