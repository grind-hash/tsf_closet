"""
データモデル定義

着せ替えインタラクティブゲームで使用するデータモデル。
Pydantic (APIリクエスト/レスポンス) と dataclass (内部状態) の両方を含む。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# 難易度プリセット定義 (T008)
# =============================================================================


@dataclass(frozen=True)
class DifficultyPreset:
    """難易度プリセット"""

    id: str
    name: str
    shame_initial: int
    bloom_multiplier: float
    adaptation_multiplier: float


DIFFICULTY_PRESETS: Dict[str, DifficultyPreset] = {
    "easy": DifficultyPreset("easy", "抵抗しやすい", 70, 0.5, 1.0),
    "normal": DifficultyPreset("normal", "普通", 50, 1.0, 1.0),
    "hard": DifficultyPreset("hard", "堕ちやすい", 30, 1.5, 1.2),
}


# =============================================================================
# 臨界点イベント定義 (T007)
# =============================================================================


@dataclass(frozen=True)
class CriticalPointEvent:
    """臨界点イベント定義"""

    threshold: int  # 25, 50, 75, 100
    name: str
    effect_type: str  # "flash", "pulse", "shake", "full"
    speech: str


CRITICAL_POINTS: List[CriticalPointEvent] = [
    CriticalPointEvent(25, "第一臨界点", "flash", "なんか…頭がぼーっとしてきた…"),
    CriticalPointEvent(50, "第二臨界点", "pulse", "もう…元に戻れないのかな…"),
    CriticalPointEvent(75, "第三臨界点", "shake", "どうしよう…止まらない…"),
    CriticalPointEvent(100, "最終臨界点", "full", "もう…いいや…"),
]


# =============================================================================
# セッション統計 (T007)
# =============================================================================


@dataclass
class SessionStats:
    """セッション統計（パラメータ状態）

    Note:
        difficulty と nsfw_mode フィールドは DEPRECATED です。
        代わりに users テーブルの対応するフィールドを使用してください。
        session_store.get_user_settings(session_id) でユーザー設定を取得できます。
    """

    session_id: str
    bloom: int = 0  # 開花度 0-100 (旧: 開花度)
    shame: int = 50  # 羞恥心 0-100
    adaptation: int = 0  # 順応度 -50〜+50
    passed_critical_points: List[int] = field(default_factory=list)
    # DEPRECATED: users テーブルの difficulty を使用してください
    difficulty: str = "normal"
    # DEPRECATED: users テーブルの nsfw_mode を使用してください
    nsfw_mode: bool = False
    enable_prompt_preview: bool = False  # プロンプト確認有効化 (DB保存対象外)

    @classmethod
    def from_row(cls, row: dict) -> "SessionStats":
        """SQLite行からインスタンスを作成"""
        passed_points = (
            json.loads(row["passed_critical_points"])
            if row["passed_critical_points"]
            else []
        )
        return cls(
            session_id=row["session_id"],
            bloom=row.get("bloom", row.get("bloom", 0)),  # 後方互換性
            shame=row["shame"],
            adaptation=row["adaptation"],
            passed_critical_points=passed_points,
            difficulty=row["difficulty"],
            nsfw_mode=bool(row.get("nsfw_mode", 0)),
        )

    @classmethod
    def create_with_difficulty(
        cls, session_id: str, difficulty: str = "normal", nsfw_mode: bool = False
    ) -> "SessionStats":
        """難易度に応じた初期値でインスタンスを作成"""
        preset = DIFFICULTY_PRESETS.get(difficulty, DIFFICULTY_PRESETS["normal"])
        return cls(
            session_id=session_id,
            bloom=0,
            shame=preset.shame_initial,
            adaptation=0,
            passed_critical_points=[],
            difficulty=difficulty,
            nsfw_mode=nsfw_mode,
        )


# =============================================================================
# 変身タグ (T007)
# =============================================================================


@dataclass
class TransformationTag:
    """変身タグ（履歴に関連付け）"""

    history_id: str
    costume_category: str = "other"  # swimsuit, uniform, maid, etc.
    exposure_level: str = "medium"  # high, medium, low
    age_impression: str = "unknown"  # child, student, adult, unknown

    @classmethod
    def from_row(cls, row: dict) -> "TransformationTag":
        """SQLite行からインスタンスを作成"""
        return cls(
            history_id=row["history_id"],
            costume_category=row["costume_category"],
            exposure_level=row["exposure_level"],
            age_impression=row["age_impression"],
        )


# =============================================================================
# 達成エンディング (T047)
# =============================================================================


@dataclass
class AchievedEnding:
    """達成エンディング（ユーザーごとに記録）"""

    ending_id: str
    session_id: str
    achieved_at: str  # ISO形式

    @classmethod
    def from_row(cls, row: dict) -> "AchievedEnding":
        """SQLite行からインスタンスを作成"""
        return cls(
            ending_id=row["ending_id"],
            session_id=row["session_id"],
            achieved_at=row["achieved_at"],
        )


# =============================================================================
# ユーザー実績達成 (UserAchievement)
# =============================================================================


@dataclass
class UserAchievement:
    """ユーザー実績達成状態"""

    id: str  # UUID
    achievement_id: str  # 実績ID (Achievementへの参照)
    session_id: Optional[str]  # 達成時のセッションID（オプション）
    achieved_at: Optional[str]  # 達成日時 (ISO 8601)、未達成時はNone
    progress: int = 0  # 進捗 (条件値に対する現在値)

    @classmethod
    def from_row(cls, row: dict) -> "UserAchievement":
        """SQLite行からインスタンスを作成"""
        return cls(
            id=row["id"],
            achievement_id=row["achievement_id"],
            session_id=row.get("session_id"),
            achieved_at=row.get("achieved_at"),
            progress=row.get("progress", 0),
        )


# =============================================================================
# 会話メッセージ (Conversation)
# =============================================================================


@dataclass
class ConversationMessage:
    """会話メッセージ"""

    id: str
    session_id: str
    role: str  # "user" or "character" or "system"
    content: str
    created_at: str  # ISO形式
    # 007-chat-interactive-ux: 新規フィールド
    instruction_type: Optional[str] = (
        None  # "dress_up" | "reality_alter" | "conversation"
    )
    attached_image_url: Optional[str] = None  # 添付画像URL
    related_history_id: Optional[str] = None  # 関連する変身履歴ID

    @classmethod
    def from_row(cls, row: dict) -> "ConversationMessage":
        """SQLite行からインスタンスを作成"""
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
            instruction_type=row.get("instruction_type"),
            attached_image_url=row.get("attached_image_url"),
            related_history_id=row.get("related_history_id"),
        )


# =============================================================================
# Pydantic モデル (API リクエスト/レスポンス)
# =============================================================================


# =============================================================================
# SelfProfile (自分自身モード)
# =============================================================================

REACTION_STYLES = (
    "default",
    "bold",
    "gentle",
    "cheerful",
    "shy",
    "calm",
    "passionate",
)


class SelfProfile(BaseModel):
    """Self mode personality profile stored as JSON in User.self_profile_json."""

    display_name: str = Field(
        "", max_length=50, description="Display name shown in chat UI"
    )
    personality: str = Field(
        ..., min_length=1, max_length=200, description="Personality summary"
    )
    reaction_style: str = Field("default", description="Reaction style keyword")
    pronoun: str = Field(
        "僕", min_length=1, max_length=10, description="First-person pronoun"
    )
    interests: list[str] = Field(
        default_factory=list, max_length=10, description="Interest keywords"
    )
    tsf_attitude: str = Field("", max_length=200, description="Attitude towards TSF")
    raw_input: str = Field("", max_length=1000, description="Original input text")

    @field_validator("reaction_style")
    @classmethod
    def validate_reaction_style(cls, v: str) -> str:
        if v not in REACTION_STYLES:
            return "default"
        return v


class NovelAISubscriptionResponse(BaseModel):
    """NovelAIサブスクリプション情報レスポンス

    NovelAI API /user/subscription からの情報を返す。
    tier値: 0=Free, 1=Tablet, 2=Scroll, 3=Opus
    """

    tier: int = Field(..., description="サブスクリプションティア (0-3)")
    active: bool = Field(..., description="サブスクリプションがアクティブか")
    expires_at: Optional[str] = Field(None, description="有効期限 (ISO 8601)")
    usage: Optional[dict] = Field(
        None,
        description=(
            "V5 利用上限 {percent, is_negative, time_until_next_percent}。"
            "レスポンスに usage が無い場合は None"
        ),
    )


# =============================================================================
# NovelAI タグサジェスト (006-novelai-prompt-enhancement)
# =============================================================================


class TagSuggestion(BaseModel):
    """タグ候補

    NovelAI suggest-tags APIから返されるタグ候補。
    """

    tag: str = Field(..., min_length=1, description="タグ文字列 (例: tifa_lockhart)")
    count: Optional[int] = Field(None, ge=0, description="関連度/出現数スコア")


class TagSuggestResponse(BaseModel):
    """タグ検索レスポンス

    バックエンドからフロントエンドへのタグ検索レスポンス。
    """

    tags: List[TagSuggestion] = Field(..., description="タグ候補リスト")
    query: Optional[str] = Field(None, description="元のクエリ (デバッグ用)")


class PlayRequest(BaseModel):
    """着せ替えプレイリクエスト"""

    session_id: Optional[str] = Field(
        None, description="既存セッションID（継続プレイ時）"
    )
    character_id: Optional[str] = Field(
        None, description="キャラクターID（新規開始時）"
    )
    character_image: Optional[str] = Field(
        None, description="Base64エンコード画像（カスタム時）"
    )
    instruction: str = Field(
        ..., description="着せ替え指示テキスト", min_length=1, max_length=500
    )
    # 衣装参照画像
    costume_image: Optional[str] = Field(
        None, description="Base64エンコードされた参照衣装画像"
    )
    # NovelAI専用: マスク & プロンプト制御
    mask_image: Optional[str] = Field(
        None,
        description="Base64エンコードされたインペイント用マスク画像（透明=保持, 白=変更）",
    )
    mask_id: Optional[str] = Field(
        None, description="保存済みマスクID（/game/masks で取得）"
    )
    inpaint_strength: Optional[float] = Field(
        None, description="NovelAI inpaintImg2ImgStrength (0.05-0.99 推奨)"
    )
    inpaint_noise: Optional[float] = Field(
        None, description="NovelAI img2img noise (0-0.5 推奨)"
    )
    negative_prompt: Optional[str] = Field(
        None, description="NovelAI専用ネガティブプロンプト"
    )
    prompt_override: Optional[str] = Field(
        None,
        description="NovelAI専用: LLM生成をスキップしてこのプロンプトをそのまま使う",
    )
    # 変身タイプ: costume=衣装変更, reality=現実改変
    transformation_type: str = Field(
        "costume", description="変身タイプ (costume=衣装変更, reality=現実改変)"
    )
    # 指示タイプ: dress_up, reality_alter, action, conversation, image_only
    instruction_type: Optional[str] = Field(
        None,
        description=(
            "指示タイプ (dress_up, reality_alter, action, conversation, image_only)"
        ),
    )
    use_memory: bool = Field(
        False,
        description="保存済みメモリテキスト（ユーザーの嗜好傾向）を生成に反映するか",
    )
    use_play_memory: bool = Field(
        False, description="セッション単位のプレイメモを生成に反映するか"
    )
    use_history_lookback: Optional[bool] = Field(
        None,
        description="履歴遡及を利用するか（未指定時は操作種別の既定値を使用）",
    )
    respect_clothing_layers: bool = Field(
        False,
        description="外衣による下着・身体属性の被覆を画像と心境で考慮するか",
    )
    language: Optional[str] = Field(
        None, description="応答言語（ja/en、未指定時はユーザー設定を使用）"
    )


class PlayResponse(BaseModel):
    """着せ替えプレイレスポンス"""

    session_id: str = Field(..., description="セッションID")
    after_image: str = Field(..., description="Base64エンコードされた結果画像")
    feeling_text: str = Field(..., description="キャラクターの心境テキスト")
    before_description: str = Field(..., description="着せ替え前の状態説明")
    after_description: str = Field(..., description="着せ替え後の状態説明")


class CharacterInfo(BaseModel):
    """キャラクター情報 (API用)"""

    id: str = Field(..., description="キャラクターID")
    name: str = Field(..., description="キャラクター名")
    thumbnail: str = Field(..., description="Base64エンコードされたサムネイル画像")
    description: str = Field(..., description="キャラクター説明")


class CharacterListResponse(BaseModel):
    """キャラクター一覧レスポンス"""

    characters: List[CharacterInfo] = Field(..., description="キャラクター一覧")


class HistoryItem(BaseModel):
    """履歴アイテム (API用)"""

    id: str = Field(..., description="履歴ID")
    instruction: str = Field(..., description="着せ替え指示")
    image_url: str = Field(..., description="結果画像URL")
    feeling_text: str = Field(..., description="心境テキスト")
    before_description: str = Field(..., description="着せ替え前の説明")
    after_description: str = Field(..., description="着せ替え後の説明")
    timestamp: str = Field(..., description="実行日時 (ISO形式)")
    instruction_type: Optional[str] = Field(
        None, description="指示タイプ (dress_up/reality_alter/action/image_only)"
    )
    # T025: タグ情報を追加
    costume_category: Optional[str] = Field(
        None, description="衣装カテゴリ (cute/sexy/elegant/cool/casual)"
    )
    exposure_level: Optional[str] = Field(
        None, description="露出度 (modest/moderate/bold/extreme)"
    )
    age_impression: Optional[str] = Field(
        None, description="年齢印象 (mature/neutral/youthful)"
    )
    # US4: seed value
    seed: Optional[int] = Field(None, description="画像生成seed値")
    # US2: surroundings image
    surroundings_image_url: Optional[str] = Field(
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
    system_text: Optional[str] = None
    user_text: Optional[str] = None
    system_updated_at: Optional[str] = None


class PlayMemoryUpdateRequest(BaseModel):
    """プレイメモのユーザー変更可能項目。"""

    system_enabled: Optional[bool] = None
    user_enabled: Optional[bool] = None
    user_text: Optional[str] = Field(None, max_length=4000)


class SessionResponse(BaseModel):
    """セッション情報レスポンス"""

    session_id: str = Field(..., description="セッションID")
    character_id: Optional[str] = Field(None, description="キャラクターID")
    current_image_url: str = Field(..., description="現在の画像URL")
    transformation_count: int = Field(0, description="変身回数")
    history: List[HistoryItem] = Field(..., description="プレイ履歴")
    created_at: str = Field(..., description="作成日時 (ISO形式)")
    updated_at: str = Field(..., description="更新日時 (ISO形式)")
    # パラメータ情報
    stats: Optional[SessionStatsResponse] = Field(
        None, description="パラメータ (bloom, shame, adaptation)"
    )
    # 復帰用データ
    attributes: List[SessionAttributeResponse] = Field(
        default_factory=list, description="セッション属性"
    )
    conversation_history: List[ConversationMessageResponse] = Field(
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
    self_mode: Optional[bool] = Field(
        None,
        description=(
            "新規セッションの自分自身モード。未指定時は分岐元セッションの値を引き継ぐ"
        ),
    )


class BranchSessionResponse(SessionResponse):
    """分岐開始レスポンス（SessionResponse + メタ情報）"""

    branch_summary: str = Field("", description="初期historyに入れた状況サマリー")
    source_session_id: Optional[str] = Field(None, description="分岐元セッションID")
    source_history_id: Optional[str] = Field(None, description="分岐元履歴ID")
    inherit_stats: bool = Field(True, description="パラメータ引き継ぎの適用値")


class SessionSummary(BaseModel):
    """セッション概要（一覧表示用）"""

    session_id: str = Field(..., description="セッションID")
    character_id: Optional[str] = Field(None, description="キャラクターID")
    character_name: Optional[str] = Field(None, description="キャラクター名")
    thumbnail_url: Optional[str] = Field(None, description="サムネイルURL")
    transformation_count: int = Field(0, description="変身回数")
    is_active: bool = Field(..., description="アクティブセッションか")
    created_at: str = Field(..., description="作成日時 (ISO形式)")
    updated_at: str = Field(..., description="更新日時 (ISO形式)")
    last_instruction: Optional[str] = Field(None, description="最後の変身指示")


class SessionListResponse(BaseModel):
    """セッション一覧レスポンス"""

    sessions: List[SessionSummary] = Field(..., description="セッション一覧")
    total_count: int = Field(..., description="総セッション数")


class ErrorResponse(BaseModel):
    """エラーレスポンス"""

    error: str = Field(..., description="エラーコード")
    message: str = Field(..., description="エラーメッセージ")


class HealthResponse(BaseModel):
    """ヘルスチェックレスポンス"""

    status: str = Field(..., description="ステータス (healthy/degraded/unhealthy)")
    services: dict = Field(..., description="各サービスの状態")


class HistorySelectResponse(BaseModel):
    """履歴選択レスポンス"""

    message: str = Field(..., description="メッセージ")
    current_image_path: str = Field(..., description="選択された履歴画像のパス")


class SessionResetResponse(BaseModel):
    """セッションリセットレスポンス"""

    message: str = Field(..., description="メッセージ")


# =============================================================================
# 会話 API モデル (Conversation)
# =============================================================================


class ChatRequest(BaseModel):
    """会話リクエスト"""

    session_id: str = Field(..., description="セッションID")
    message: str = Field(
        ..., description="ユーザーのメッセージ", min_length=1, max_length=500
    )


class ChatResponse(BaseModel):
    """会話レスポンス"""

    session_id: str = Field(..., description="セッションID")
    character_response: str = Field(..., description="キャラクターの応答")
    psychological_state: str = Field(..., description="現在の心理段階名")


class SuggestInstructionRequest(BaseModel):
    """過去メッセージからの指示テキスト生成リクエスト"""

    session_id: str = Field(..., description="セッションID")
    instruction_type: Optional[str] = Field(
        None,
        description="絞り込む指示タイプ (dress_up/reality_alter/action)。None/'all'は全種類を統合",
    )
    keyword: Optional[str] = Field(
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


class ConversationMessageResponse(BaseModel):
    """会話メッセージ（API用）"""

    id: str = Field(..., description="メッセージID")
    role: str = Field(..., description="発言者 (user/character)")
    content: str = Field(..., description="メッセージ内容")
    created_at: str = Field(..., description="送信日時 (ISO形式)")
    instruction_type: Optional[str] = Field(
        None,
        description="指示タイプ (dress_up/reality_alter/conversation/action/image_only)",
    )


class ConversationHistoryResponse(BaseModel):
    """会話履歴レスポンス"""

    session_id: str = Field(..., description="セッションID")
    messages: List[ConversationMessageResponse] = Field(..., description="会話履歴")


# =============================================================================
# SSE イベントモデル
# =============================================================================


class SSETextEvent(BaseModel):
    """SSEテキストチャンクイベント"""

    chunk: str = Field(..., description="テキストチャンク")


class SSEImageEvent(BaseModel):
    """SSE画像完了イベント"""

    image: str = Field(..., description="Base64エンコード画像")
    history_id: str = Field(..., description="履歴ID")


class SSECompleteEvent(BaseModel):
    """SSE完了イベント"""

    session_id: str = Field(..., description="セッションID")
    transformation_count: int = Field(..., description="変身回数")


class SSEErrorEvent(BaseModel):
    """SSEエラーイベント"""

    message: str = Field(..., description="エラーメッセージ")


# =============================================================================
# マスク管理 (NovelAI専用)
# =============================================================================


class MaskSaveRequest(BaseModel):
    """マスク保存リクエスト"""

    mask_base64: str = Field(..., description="Base64エンコードされたマスクPNG")
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        description="プリセット名 (指定時はプリセットとして保存)",
    )
    auto_save: bool = Field(False, description="自動保存フラグ (変身時にtrue)")


class MaskInfo(BaseModel):
    """マスク情報"""

    id: str = Field(
        ..., description="マスクID (system:filename / history:uuid / preset:uuid)"
    )
    name: str = Field(..., description="表示名")
    type: Literal["system", "history", "preset"] = Field(..., description="マスク種別")
    url: str = Field(..., description="取得用URL")
    created_at: Optional[str] = Field(
        None, description="作成日時 (ISO) - history/presetのみ"
    )


class MaskListResponse(BaseModel):
    """マスク一覧レスポンス"""

    system: List[MaskInfo] = Field(..., description="システムデフォルトマスク")
    history: List[MaskInfo] = Field(..., description="保存済み履歴マスク（最大20件）")
    presets: List[MaskInfo] = Field(
        default_factory=list, description="ユーザープリセットマスク"
    )


# =============================================================================
# パラメータシステム用 API モデル (T010)
# =============================================================================


class SessionStatsResponse(BaseModel):
    """セッション統計レスポンス"""

    bloom: int = Field(..., ge=0, le=100, description="開花度")
    shame: int = Field(..., ge=0, le=100, description="羞恥心")
    adaptation: int = Field(..., ge=-50, le=50, description="順応度")
    passed_critical_points: List[int] = Field(
        ..., description="通過済み臨界点", alias="passedCriticalPoints"
    )
    difficulty: str = Field(..., description="難易度")
    nsfw_mode: bool = Field(False, description="NSFWモード", alias="nsfwMode")
    enable_prompt_preview: bool = Field(
        False, description="プロンプト確認有効化", alias="enablePromptPreview"
    )

    model_config = ConfigDict(populate_by_name=True)


class TransformationTagResponse(BaseModel):
    """変身タグレスポンス"""

    costume_category: str = Field(..., description="衣装カテゴリ")
    exposure_level: str = Field(..., description="露出度")
    age_impression: str = Field(..., description="年齢印象")


class CriticalPointEventResponse(BaseModel):
    """臨界点イベントレスポンス"""

    triggered: bool = Field(..., description="臨界点発火したか")
    threshold: Optional[int] = Field(None, description="発火した閾値")
    name: Optional[str] = Field(None, description="臨界点名")
    effect_type: Optional[str] = Field(None, description="エフェクトタイプ")
    speech: Optional[str] = Field(None, description="特別セリフ")


class EndingResponse(BaseModel):
    """エンディングレスポンス"""

    triggered: bool = Field(..., description="エンディング到達したか")
    ending_id: Optional[str] = Field(None, description="エンディングID")
    title: Optional[str] = Field(None, description="エンディングタイトル")
    description: Optional[str] = Field(None, description="エンディング説明")
    final_speech: Optional[str] = Field(None, description="最終セリフ")
    summary: Optional[str] = Field(None, description="総括テキスト")
    is_new: Optional[bool] = Field(None, description="初達成かどうか")


class DifficultyResponse(BaseModel):
    """難易度レスポンス"""

    id: str = Field(..., description="難易度ID")
    name: str = Field(..., description="難易度名")
    description: str = Field(..., description="難易度説明")


class DifficultyListResponse(BaseModel):
    """難易度一覧レスポンス"""

    difficulties: List[DifficultyResponse] = Field(..., description="難易度一覧")


class GameStartRequest(BaseModel):
    """Game start request."""

    character_id: Optional[str] = Field(None, description="Character ID")
    difficulty: str = Field("normal", description="Difficulty (easy/normal/hard)")
    nsfw_mode: bool = Field(False, description="NSFW mode")
    self_mode: bool = Field(False, description="Self mode (bypass parameters)")


class GameStartResponse(BaseModel):
    """ゲーム開始レスポンス"""

    session_id: str = Field(..., description="新規セッションID")


# =============================================================================
# Multi-character persistence (spec 005)
# =============================================================================


CharacterPositionLiteral = Literal[
    "left", "center-left", "center", "center-right", "right"
]


class SessionCharacterRead(BaseModel):
    """Read model for SessionCharacter."""

    id: str
    session_id: str
    slot_index: int
    name: str
    appearance_natural: str
    appearance_tags: str
    position: CharacterPositionLiteral
    is_protagonist: bool = False
    appearance_lock: bool = False
    exclude_from_effects: bool = False
    source_preset_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SessionCharacterCreate(BaseModel):
    """Create payload for adding a character to a session."""

    name: str = Field(..., min_length=1, max_length=120)
    appearance_natural: str = Field("", max_length=1000)
    appearance_tags: str = Field("", max_length=2000)
    position: CharacterPositionLiteral = "center"
    slot_index: Optional[int] = Field(None, ge=0, le=3)
    source_preset_id: Optional[str] = None
    appearance_lock: bool = False
    exclude_from_effects: bool = False


class SessionCharacterUpdate(BaseModel):
    """Partial update payload for an existing SessionCharacter."""

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    appearance_natural: Optional[str] = Field(None, max_length=1000)
    appearance_tags: Optional[str] = Field(None, max_length=2000)
    position: Optional[CharacterPositionLiteral] = None
    slot_index: Optional[int] = Field(None, ge=0, le=3)
    appearance_lock: Optional[bool] = None
    exclude_from_effects: Optional[bool] = None


class CharacterPresetRead(BaseModel):
    """Read model for CharacterPreset."""

    id: str
    name: str
    appearance_natural: str
    appearance_tags: str
    default_position: CharacterPositionLiteral
    created_at: datetime
    updated_at: datetime


class PresetCreateFromCharacter(BaseModel):
    """Create a preset by copying an existing SessionCharacter."""

    from_character_id: str
    name: str = Field(..., min_length=1, max_length=120)


class PresetCreateRaw(BaseModel):
    """Create a preset directly from raw fields."""

    name: str = Field(..., min_length=1, max_length=120)
    appearance_natural: str = Field("", max_length=1000)
    appearance_tags: str = Field("", max_length=2000)
    default_position: CharacterPositionLiteral = "center"


class CharacterPresetUpdate(BaseModel):
    """Partial update payload for a preset."""

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    appearance_natural: Optional[str] = Field(None, max_length=1000)
    appearance_tags: Optional[str] = Field(None, max_length=2000)
    default_position: Optional[CharacterPositionLiteral] = None


class GenerateTagsItem(BaseModel):
    """One natural-language input for batch tag generation."""

    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=120)
    natural: str = Field(..., max_length=1000)


class GenerateTagsRequest(BaseModel):
    """Batch tag-generation request body."""

    items: List[GenerateTagsItem] = Field(..., min_length=1, max_length=4)


class GenerateTagsResultItem(BaseModel):
    """One result entry for batch tag generation."""

    id: str
    tags: str


class GenerateTagsResponse(BaseModel):
    """Batch tag-generation response body."""

    results: List[GenerateTagsResultItem]


class SessionCharacterListResponse(BaseModel):
    """Wrapper for GET /game/session/{id}/characters."""

    characters: List[SessionCharacterRead]


class CharacterPresetListResponse(BaseModel):
    """Wrapper for GET /game/character-presets."""

    presets: List[CharacterPresetRead]


class GalleryEndingItem(BaseModel):
    """ギャラリーのエンディングアイテム"""

    ending_id: str = Field(..., description="エンディングID")
    title: str = Field(..., description="タイトル（未達成時は「???」）")
    achieved: bool = Field(..., description="達成済みか")
    achieved_at: Optional[str] = Field(None, description="達成日時")


class GalleryResponse(BaseModel):
    """ギャラリーレスポンス"""

    endings: List[GalleryEndingItem] = Field(..., description="エンディング一覧")
    total_count: int = Field(..., description="全エンディング数")
    achieved_count: int = Field(..., description="達成済みエンディング数")


class SSEStatsEvent(BaseModel):
    """SSE パラメータ更新イベント"""

    bloom: int = Field(..., description="開花度")
    shame: int = Field(..., description="羞恥心")
    adaptation: int = Field(..., description="順応度")
    bloom_delta: int = Field(..., description="開花度変化量")
    shame_delta: int = Field(..., description="羞恥心変化量")
    adaptation_delta: int = Field(..., description="順応度変化量")


class SSETagsEvent(BaseModel):
    """SSE タグイベント"""

    costume_category: str = Field(..., description="衣装カテゴリ")
    exposure_level: str = Field(..., description="露出度")
    age_impression: str = Field(..., description="年齢印象")


class SSECriticalEvent(BaseModel):
    """SSE 臨界点イベント"""

    threshold: int = Field(..., description="閾値")
    name: str = Field(..., description="臨界点名")
    effect_type: str = Field(..., description="エフェクトタイプ")
    speech: str = Field(..., description="特別セリフ")


class SSEEndingEvent(BaseModel):
    """SSE エンディングイベント"""

    ending_id: str = Field(..., description="エンディングID")
    title: str = Field(..., description="タイトル")
    final_speech: str = Field(..., description="最終セリフ")
    summary: str = Field(..., description="総括")
    is_new: bool = Field(..., description="初達成か")


# =============================================================================
# Dataclass モデル (内部状態管理)
# =============================================================================


@dataclass
class Character:
    """キャラクター定義

    ゲームで選択可能なキャラクターのプリセット。
    """

    id: str
    name: str
    image_path: str
    description: str
    pronoun: str = "僕"
    personality: str = ""
    gender: str = "man"
    base_tags: str = ""


@dataclass
class PersistedHistory:
    """永続化された履歴レコード

    SQLiteに保存される履歴データ。
    """

    id: str
    session_id: str
    instruction: str
    image_path: str
    feeling_text: Optional[str]
    before_description: Optional[str]
    after_description: Optional[str]
    created_at: datetime
    instruction_type: Optional[str] = None
    seed: Optional[int] = None
    surroundings_image_path: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "PersistedHistory":
        """SQLite行からインスタンスを作成"""
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            instruction=row["instruction"],
            image_path=row["image_path"],
            feeling_text=row["feeling_text"],
            before_description=row["before_description"],
            after_description=row["after_description"],
            created_at=datetime.fromisoformat(row["created_at"]),
            instruction_type=row.get("instruction_type"),
        )


@dataclass
class PersistedSession:
    """永続化されたセッションレコード

    SQLiteに保存されるセッションデータ。
    """

    id: str
    user_id: str
    character_id: Optional[str]
    current_image_path: str
    transformation_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    self_mode: bool = False
    play_memory_system_text: Optional[str] = None
    play_memory_user_text: Optional[str] = None
    play_memory_system_enabled: bool = True
    play_memory_user_enabled: bool = True
    play_memory_system_updated_at: Optional[datetime] = None
    history: List[PersistedHistory] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: dict) -> "PersistedSession":
        """SQLite行からインスタンスを作成"""
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            character_id=row["character_id"],
            current_image_path=row["current_image_path"],
            transformation_count=row["transformation_count"],
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


@dataclass
class PlayHistory:
    """プレイ履歴

    1回の着せ替え操作の入力と結果を記録。
    """

    instruction: str
    before_image: bytes
    after_image: bytes
    before_description: str
    after_description: str
    feeling_text: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_api_model(self) -> HistoryItem:
        """API用モデルに変換"""
        import base64

        return HistoryItem(
            instruction=self.instruction,
            after_image=base64.b64encode(self.after_image).decode("utf-8"),
            feeling_text=self.feeling_text,
            before_description=self.before_description,
            after_description=self.after_description,
            timestamp=self.timestamp.isoformat(),
        )


@dataclass
class GameSession:
    """ゲームセッション

    着せ替えゲームの1回のプレイセッションを表す。
    キャラクター選択から複数回の着せ替えまでを管理。
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: Optional[str] = None
    character: Optional[Character] = None
    current_image: bytes = b""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    history: List[PlayHistory] = field(default_factory=list)
    stats: Optional[SessionStats] = None

    def update_image(self, new_image: bytes) -> None:
        """現在の画像を更新"""
        self.current_image = new_image
        self.updated_at = datetime.now()

    def add_history(self, history: PlayHistory) -> None:
        """履歴を追加"""
        self.history.append(history)
        self.updated_at = datetime.now()

    def to_api_model(self) -> SessionResponse:
        """API用モデルに変換"""
        import base64

        return SessionResponse(
            session_id=self.session_id,
            character_id=self.character_id,
            current_image=base64.b64encode(self.current_image).decode("utf-8"),
            history=[h.to_api_model() for h in self.history],
            stats=SessionStatsResponse(
                bloom=self.stats.bloom,
                shame=self.stats.shame,
                adaptation=self.stats.adaptation,
                passed_critical_points=self.stats.passed_critical_points,
                difficulty=self.stats.difficulty,
                nsfw_mode=self.stats.nsfw_mode,
                enable_prompt_preview=self.stats.enable_prompt_preview,
            )
            if self.stats
            else None,
        )
