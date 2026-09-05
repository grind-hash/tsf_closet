"""
内部状態のデータモデル定義

着せ替えインタラクティブゲームの難易度・臨界点・セッション統計・永続化用 dataclass。
API リクエスト / レスポンスの Pydantic モデルは `gateway/schemas/` に置く。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

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


DIFFICULTY_PRESETS: dict[str, DifficultyPreset] = {
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


CRITICAL_POINTS: list[CriticalPointEvent] = [
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
    passed_critical_points: list[int] = field(default_factory=list)
    # DEPRECATED: users テーブルの difficulty を使用してください
    difficulty: str = "normal"
    # DEPRECATED: users テーブルの nsfw_mode を使用してください
    nsfw_mode: bool = False
    enable_prompt_preview: bool = False  # プロンプト確認有効化 (DB保存対象外)

    @classmethod
    def from_row(cls, row: dict) -> SessionStats:
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
    ) -> SessionStats:
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
    def from_row(cls, row: dict) -> TransformationTag:
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
    def from_row(cls, row: dict) -> AchievedEnding:
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
    session_id: str | None  # 達成時のセッションID（オプション）
    achieved_at: str | None  # 達成日時 (ISO 8601)、未達成時はNone
    progress: int = 0  # 進捗 (条件値に対する現在値)

    @classmethod
    def from_row(cls, row: dict) -> UserAchievement:
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
    instruction_type: str | None = None  # "dress_up" | "reality_alter" | "conversation"
    attached_image_url: str | None = None  # 添付画像URL
    related_history_id: str | None = None  # 関連する変身履歴ID

    @classmethod
    def from_row(cls, row: dict) -> ConversationMessage:
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
    feeling_text: str | None
    before_description: str | None
    after_description: str | None
    created_at: datetime
    instruction_type: str | None = None
    seed: int | None = None
    surroundings_image_path: str | None = None

    @classmethod
    def from_row(cls, row: dict) -> PersistedHistory:
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
    character_id: str | None
    current_image_path: str
    transformation_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    self_mode: bool = False
    play_memory_system_text: str | None = None
    play_memory_user_text: str | None = None
    play_memory_system_enabled: bool = True
    play_memory_user_enabled: bool = True
    play_memory_system_updated_at: datetime | None = None
    history: list[PersistedHistory] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: dict) -> PersistedSession:
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
