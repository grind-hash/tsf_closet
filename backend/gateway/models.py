"""
データモデル定義

変身インタラクティブゲームで使用するデータモデル。
Pydantic (APIリクエスト/レスポンス) と dataclass (内部状態) の両方を含む。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# 難易度プリセット定義 (T008)
# =============================================================================


@dataclass(frozen=True)
class DifficultyPreset:
    """難易度プリセット"""

    id: str
    name: str
    immersion_initial: int
    excitement_multiplier: float
    challenge_multiplier: float


DIFFICULTY_PRESETS: Dict[str, DifficultyPreset] = {
    "easy": DifficultyPreset("easy", "かんたん", 70, 0.5, 1.0),
    "normal": DifficultyPreset("normal", "ふつう", 50, 1.0, 1.0),
    "hard": DifficultyPreset("hard", "むずかしい", 30, 1.5, 1.2),
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


# 子供向け臨界点メッセージ（成長・達成系）
CRITICAL_POINTS: List[CriticalPointEvent] = [
    CriticalPointEvent(25, "レベル1", "flash", "へんしんって楽しいかも！"),
    CriticalPointEvent(50, "レベル2", "pulse", "だいぶ上手になってきた！"),
    CriticalPointEvent(75, "レベル3", "shake", "もうどんな変身もへっちゃら！"),
    CriticalPointEvent(100, "マスター", "full", "やった！変身マスターになった！"),
]


# =============================================================================
# セッション統計 (T007)
# =============================================================================


@dataclass
class SessionStats:
    """セッション統計（パラメータ状態）
    
    子供向けパラメータ:
    - excitement (ワクワク度): 0-100
    - immersion (なりきり度): 0-100
    - challenge (チャレンジ度): -50〜+50
    """

    session_id: str
    excitement: int = 0  # ワクワク度 0-100
    immersion: int = 50  # なりきり度 0-100
    challenge: int = 0  # チャレンジ度 -50〜+50
    passed_critical_points: List[int] = field(default_factory=list)
    difficulty: str = "normal"

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
            excitement=row.get("excitement", 0),
            immersion=row.get("immersion", 50),
            challenge=row.get("challenge", 0),
            passed_critical_points=passed_points,
            difficulty=row.get("difficulty", "normal"),
        )

    @classmethod
    def create_with_difficulty(
        cls, session_id: str, difficulty: str = "normal"
    ) -> "SessionStats":
        """難易度に応じた初期値でインスタンスを作成"""
        preset = DIFFICULTY_PRESETS.get(difficulty, DIFFICULTY_PRESETS["normal"])
        return cls(
            session_id=session_id,
            excitement=0,
            immersion=preset.immersion_initial,
            challenge=0,
            passed_critical_points=[],
            difficulty=difficulty,
        )


# =============================================================================
# 変身タグ (T007)
# =============================================================================


@dataclass
class TransformationTag:
    """変身タグ（履歴に関連付け）"""

    history_id: str
    costume_category: str = "other"  # swimsuit, uniform, maid, etc.
    sparkle_level: str = "medium"  # high, medium, low
    age_impression: str = "unknown"  # child, student, adult, unknown

    @classmethod
    def from_row(cls, row: dict) -> "TransformationTag":
        """SQLite行からインスタンスを作成"""
        return cls(
            history_id=row["history_id"],
            costume_category=row["costume_category"],
            sparkle_level=row["sparkle_level"],
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
# 会話メッセージ (Conversation)
# =============================================================================


@dataclass
class ConversationMessage:
    """会話メッセージ"""

    id: str
    session_id: str
    role: str  # "user" or "character"
    content: str
    created_at: str  # ISO形式

    @classmethod
    def from_row(cls, row: dict) -> "ConversationMessage":
        """SQLite行からインスタンスを作成"""
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
        )


# =============================================================================
# Pydantic モデル (API リクエスト/レスポンス)
# =============================================================================


class PlayRequest(BaseModel):
    """変身プレイリクエスト"""

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
        ..., description="変身指示テキスト", min_length=1, max_length=500
    )


class PlayResponse(BaseModel):
    """変身プレイレスポンス"""

    session_id: str = Field(..., description="セッションID")
    after_image: str = Field(..., description="Base64エンコードされた結果画像")
    feeling_text: str = Field(..., description="キャラクターの心境テキスト")
    before_description: str = Field(..., description="変身前の状態説明")
    after_description: str = Field(..., description="変身後の状態説明")


class CharacterInfo(BaseModel):
    """キャラクター情報 (API用)"""

    id: str = Field(..., description="キャラクターID")
    name: str = Field(..., description="キャラクター名")
    thumbnail: str = Field(..., description="Base64エンコードされたサムネイル画像")
    description: str = Field(..., description="キャラクター説明")
    gender: str = Field("unknown", description="性別 (girl/boy/unknown)")


class CharacterListResponse(BaseModel):
    """キャラクター一覧レスポンス"""

    characters: List[CharacterInfo] = Field(..., description="キャラクター一覧")


class HistoryItem(BaseModel):
    """履歴アイテム (API用)"""

    id: str = Field(..., description="履歴ID")
    instruction: str = Field(..., description="変身指示")
    image_url: str = Field(..., description="結果画像URL")
    feeling_text: str = Field(..., description="心境テキスト")
    before_description: str = Field(..., description="変身前の説明")
    after_description: str = Field(..., description="変身後の説明")
    timestamp: str = Field(..., description="実行日時 (ISO形式)")
    # T025: タグ情報を追加
    costume_category: Optional[str] = Field(
        None, description="衣装カテゴリ (cute/sexy/elegant/cool/casual)"
    )
    sparkle_level: Optional[str] = Field(
        None, description="きらめき度 (modest/moderate/bold/extreme)"
    )
    age_impression: Optional[str] = Field(
        None, description="年齢印象 (mature/neutral/youthful)"
    )


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
    stats: Optional[dict] = Field(None, description="パラメータ (excitement, immersion, challenge)")


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


class ConversationMessageResponse(BaseModel):
    """会話メッセージ（API用）"""

    id: str = Field(..., description="メッセージID")
    role: str = Field(..., description="発言者 (user/character)")
    content: str = Field(..., description="メッセージ内容")
    created_at: str = Field(..., description="送信日時 (ISO形式)")


class ConversationHistoryResponse(BaseModel):
    """会話履歴レスポンス"""

    session_id: str = Field(..., description="セッションID")
    messages: List[ConversationMessageResponse] = Field(
        ..., description="会話履歴"
    )


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
# パラメータシステム用 API モデル (T010)
# =============================================================================


class SessionStatsResponse(BaseModel):
    """セッション統計レスポンス"""

    excitement: int = Field(..., ge=0, le=100, description="ワクワク度")
    immersion: int = Field(..., ge=0, le=100, description="なりきり度")
    challenge: int = Field(..., ge=-50, le=50, description="チャレンジ度")
    passed_critical_points: List[int] = Field(..., description="通過済み臨界点")
    difficulty: str = Field(..., description="難易度")


class TransformationTagResponse(BaseModel):
    """変身タグレスポンス"""

    costume_category: str = Field(..., description="衣装カテゴリ")
    sparkle_level: str = Field(..., description="きらめき度")
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
    """ゲーム開始リクエスト"""

    character_id: Optional[str] = Field(None, description="キャラクターID")
    difficulty: str = Field("normal", description="難易度 (easy/normal/hard)")


class GameStartResponse(BaseModel):
    """ゲーム開始レスポンス"""

    session_id: str = Field(..., description="新規セッションID")
    difficulty: str = Field(..., description="選択された難易度")
    initial_stats: SessionStatsResponse = Field(..., description="初期パラメータ")


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

    excitement: int = Field(..., description="ワクワク度")
    immersion: int = Field(..., description="なりきり度")
    challenge: int = Field(..., description="チャレンジ度")
    excitement_delta: int = Field(..., description="ワクワク度変化量")
    immersion_delta: int = Field(..., description="なりきり度変化量")
    challenge_delta: int = Field(..., description="チャレンジ度変化量")


class SSETagsEvent(BaseModel):
    """SSE タグイベント"""

    costume_category: str = Field(..., description="衣装カテゴリ")
    sparkle_level: str = Field(..., description="きらめき度")
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
    gender: str = "unknown"  # "girl", "boy", "unknown"


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

    1回の変身操作の入力と結果を記録。
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

    変身ゲームの1回のプレイセッションを表す。
    キャラクター選択から複数回の変身までを管理。
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: Optional[str] = None
    character: Optional[Character] = None
    current_image: bytes = b""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    history: List[PlayHistory] = field(default_factory=list)

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
        )
