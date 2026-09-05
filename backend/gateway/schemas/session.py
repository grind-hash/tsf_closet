"""セッション・履歴・プレイメモ・分岐開始の API モデル。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .conversation import ConversationMessageResponse
from .parameters import SessionStatsResponse


class HistoryItem(BaseModel):
    """履歴アイテム (API用)"""

    id: str = Field(..., description="履歴ID")
    instruction: str = Field(..., description="着せ替え指示")
    image_url: str = Field(..., description="結果画像URL")
    feeling_text: str = Field(..., description="心境テキスト")
    before_description: str = Field(..., description="着せ替え前の説明")
    after_description: str = Field(..., description="着せ替え後の説明")
    timestamp: str = Field(..., description="実行日時 (ISO形式)")
    instruction_type: str | None = Field(
        None, description="指示タイプ (dress_up/reality_alter/action/image_only)"
    )
    # T025: タグ情報を追加
    costume_category: str | None = Field(
        None, description="衣装カテゴリ (cute/sexy/elegant/cool/casual)"
    )
    exposure_level: str | None = Field(
        None, description="露出度 (modest/moderate/bold/extreme)"
    )
    age_impression: str | None = Field(
        None, description="年齢印象 (mature/neutral/youthful)"
    )
    # US4: seed value
    seed: int | None = Field(None, description="画像生成seed値")
    # US2: surroundings image
    surroundings_image_url: str | None = Field(
        None, description="周囲状況画像URL (action時のみ)"
    )


class SessionAttributeResponse(BaseModel):
    """セッション属性（API用）"""

    id: str = Field(..., description="属性ID")
    text: str = Field(..., description="属性テキスト")


class PlayMemoryResponse(BaseModel):
    """セッション単位のプレイメモ。"""

    system_enabled: bool = True
    user_enabled: bool = True
    system_text: str | None = None
    user_text: str | None = None
    system_updated_at: str | None = None


class PlayMemoryUpdateRequest(BaseModel):
    """プレイメモのユーザー変更可能項目。"""

    system_enabled: bool | None = None
    user_enabled: bool | None = None
    user_text: str | None = Field(None, max_length=4000)


class SessionResponse(BaseModel):
    """セッション情報レスポンス"""

    session_id: str = Field(..., description="セッションID")
    character_id: str | None = Field(None, description="キャラクターID")
    current_image_url: str = Field(..., description="現在の画像URL")
    transformation_count: int = Field(0, description="変身回数")
    history: list[HistoryItem] = Field(..., description="プレイ履歴")
    created_at: str = Field(..., description="作成日時 (ISO形式)")
    updated_at: str = Field(..., description="更新日時 (ISO形式)")
    # パラメータ情報
    stats: SessionStatsResponse | None = Field(
        None, description="パラメータ (bloom, shame, adaptation)"
    )
    # 復帰用データ
    attributes: list[SessionAttributeResponse] = Field(
        default_factory=list, description="セッション属性"
    )
    conversation_history: list[ConversationMessageResponse] = Field(
        default_factory=list, description="Conversation history"
    )
    self_mode: bool = Field(False, description="Self mode enabled")
    play_memory: PlayMemoryResponse = Field(default_factory=PlayMemoryResponse)


class BranchSessionRequest(BaseModel):
    """履歴画像から新規セッションを分岐開始するリクエスト"""

    inherit_stats: bool = Field(
        True,
        description="開花度・羞恥・適応などのパラメータを分岐点から引き継ぐか",
    )
    self_mode: bool | None = Field(
        None,
        description=(
            "新規セッションの自分自身モード。未指定時は分岐元セッションの値を引き継ぐ"
        ),
    )


class BranchSessionResponse(SessionResponse):
    """分岐開始レスポンス（SessionResponse + メタ情報）"""

    branch_summary: str = Field("", description="初期historyに入れた状況サマリー")
    source_session_id: str | None = Field(None, description="分岐元セッションID")
    source_history_id: str | None = Field(None, description="分岐元履歴ID")
    inherit_stats: bool = Field(True, description="パラメータ引き継ぎの適用値")


class SessionSummary(BaseModel):
    """セッション概要（一覧表示用）"""

    session_id: str = Field(..., description="セッションID")
    character_id: str | None = Field(None, description="キャラクターID")
    character_name: str | None = Field(None, description="キャラクター名")
    thumbnail_url: str | None = Field(None, description="サムネイルURL")
    transformation_count: int = Field(0, description="変身回数")
    is_active: bool = Field(..., description="アクティブセッションか")
    created_at: str = Field(..., description="作成日時 (ISO形式)")
    updated_at: str = Field(..., description="更新日時 (ISO形式)")
    last_instruction: str | None = Field(None, description="最後の変身指示")


class SessionListResponse(BaseModel):
    """セッション一覧レスポンス"""

    sessions: list[SessionSummary] = Field(..., description="セッション一覧")
    total_count: int = Field(..., description="総セッション数")


class HistorySelectResponse(BaseModel):
    """履歴選択レスポンス"""

    message: str = Field(..., description="メッセージ")
    current_image_path: str = Field(..., description="選択された履歴画像のパス")


class SessionResetResponse(BaseModel):
    """セッションリセットレスポンス"""

    message: str = Field(..., description="メッセージ")


class GameStartRequest(BaseModel):
    """Game start request."""

    character_id: str | None = Field(None, description="Character ID")
    difficulty: str = Field("normal", description="Difficulty (easy/normal/hard)")
    nsfw_mode: bool = Field(False, description="NSFW mode")
    self_mode: bool = Field(False, description="Self mode (bypass parameters)")


class GameStartResponse(BaseModel):
    """ゲーム開始レスポンス"""

    session_id: str = Field(..., description="新規セッションID")


class CustomStartRequest(BaseModel):
    """カスタム画像でのセッション開始リクエスト"""

    image: str | None = Field(None, description="Base64エンコードされた画像")
    custom_character_id: str | None = Field(
        None, description="再利用するカスタムキャラID"
    )
    difficulty: str = Field("normal", description="難易度")
    nsfw_mode: bool = Field(False, description="NSFWモード")
    name: str = Field("カスタムキャラクター", description="キャラクター名")
    description: str = Field("", description="説明")
    pronoun: str = Field("僕", description="一人称")
    personality: str = Field("", description="パーソナリティ")
    gender: str = Field("other", description="性別 (man/woman/other)")
    base_tags: str = Field("", description="Danbooru形式の外見タグ (英語)")
    self_mode: bool = Field(False, description="自分自身モード")
