"""SQLAlchemy ORM models.

All database models using SQLAlchemy 2.0 declarative style.
Maintains the same schema structure as the original raw SQL.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )
    nsfw_mode: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    difficulty: Mapped[str] = mapped_column(String, default="normal", nullable=False)
    bloom_calc_method: Mapped[str] = mapped_column(
        String, default="legacy", nullable=False, server_default="legacy"
    )
    gender_congruence_llm_enabled: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
    # legacy | gender_aware
    feeling_mode: Mapped[str] = mapped_column(
        String, default="legacy", nullable=False, server_default="legacy"
    )
    language: Mapped[str] = mapped_column(String, default="ja", nullable=False)
    novelai_text_model: Mapped[str] = mapped_column(
        String, default="glm-4-6", nullable=False, server_default="glm-4-6"
    )
    # NovelAI 画像生成モデル（NSFW ON 時 / OFF 時）
    novelai_image_model: Mapped[str] = mapped_column(
        String,
        default="nai-diffusion-4-5-full",
        nullable=False,
        server_default="nai-diffusion-4-5-full",
    )
    novelai_curated_image_model: Mapped[str] = mapped_column(
        String,
        default="nai-diffusion-4-5-curated",
        nullable=False,
        server_default="nai-diffusion-4-5-curated",
    )
    tts_enabled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tts_use_gpu: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tts_engine_dir: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 音声合成エンジンの待ち受けポート。NULL のときは AIVIS_ENGINE_BASE_URL の
    # ポートを使う。既定の 10101 が他用途で使用済みの場合などに変更する。
    tts_engine_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tts_model_dir: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tts_speaker_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tts_style_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tts_output_format: Mapped[str] = mapped_column(
        String, default="wav", nullable=False, server_default="wav"
    )
    self_profile_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    memory_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Prompt Expander 専用設定（JSON）。スキーマは services/prompt_expander_service.PromptExpanderSettings
    prompt_expander_settings_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )

    sessions: Mapped[List["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    achieved_endings: Mapped[List["AchievedEnding"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    adventure_runs: Mapped[List["AdventureRun"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    prompt_expander_sessions: Mapped[List["PromptExpanderSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    character_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    current_image_path: Mapped[str] = mapped_column(Text, nullable=False)
    transformation_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    self_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    play_memory_system_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    play_memory_user_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    play_memory_system_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    play_memory_user_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    play_memory_system_updated_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="sessions")
    history: Mapped[List["History"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    stats: Mapped[Optional["SessionStats"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    conversations: Mapped[List["Conversation"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    attributes: Mapped[List["SessionAttribute"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    session_characters: Mapped[List["SessionCharacter"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_sessions_user_id", "user_id"),
        Index("idx_sessions_active", "user_id", "is_active"),
    )


class History(Base):
    __tablename__ = "history"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    feeling_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    before_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    after_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    instruction_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    surroundings_image_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )

    session: Mapped["Session"] = relationship(back_populates="history")
    tag: Mapped[Optional["TransformationTag"]] = relationship(
        back_populates="history", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        Index("idx_history_session_id", "session_id"),
        Index("idx_history_created_at", "session_id", "created_at"),
    )


class SessionStats(Base):
    __tablename__ = "session_stats"

    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    bloom: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shame: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    adaptation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_critical_points: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False
    )
    difficulty: Mapped[str] = mapped_column(String, default="normal", nullable=False)
    nsfw_mode: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    session: Mapped["Session"] = relationship(back_populates="stats")

    @property
    def passed_critical_points_list(self) -> List[int]:
        return json.loads(self.passed_critical_points)

    @passed_critical_points_list.setter
    def passed_critical_points_list(self, value: List[int]) -> None:
        self.passed_critical_points = json.dumps(value)


class TransformationTag(Base):
    __tablename__ = "transformation_tags"

    history_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("history.id", ondelete="CASCADE"),
        primary_key=True,
    )
    costume_category: Mapped[str] = mapped_column(
        String, default="other", nullable=False
    )
    exposure_level: Mapped[str] = mapped_column(
        String, default="medium", nullable=False
    )
    age_impression: Mapped[str] = mapped_column(
        String, default="unknown", nullable=False
    )

    history: Mapped["History"] = relationship(back_populates="tag")


class AchievedEnding(Base):
    __tablename__ = "achieved_endings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ending_id: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    achieved_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="achieved_endings")

    __table_args__ = (
        Index("idx_achieved_endings_unique", "user_id", "ending_id", unique=True),
        Index("idx_achieved_endings_user", "user_id"),
    )


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    instruction_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attached_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    related_history_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )

    session: Mapped["Session"] = relationship(back_populates="conversations")

    __table_args__ = (
        Index("idx_conversation_session_id", "session_id"),
        Index("idx_conversation_created_at", "session_id", "created_at"),
    )


class SessionAttribute(Base):
    __tablename__ = "session_attributes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    attribute_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )

    session: Mapped["Session"] = relationship(back_populates="attributes")

    __table_args__ = (Index("idx_session_attributes_session_id", "session_id"),)


class AdventureRun(Base):
    __tablename__ = "adventure_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_session_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    source_history_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("history.id", ondelete="SET NULL"), nullable=True
    )
    # Prompt Expander のエントリを開始素材にした場合の ID。
    # run は開始画像をコピーして保持するため FK は張らない（SQLite の table rebuild 回避）
    source_prompt_expander_entry_id: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    preset: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    constraints_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    state_json: Mapped[str] = mapped_column(Text, nullable=False)
    # 開幕(手番0)時点の復元素材。手番0への巻き戻しに使う。
    # {"state": {...}, "current_image_path": ..., "portrait_image_path": ...,
    #  "background_image_path": ...} を保存する。旧runでは NULL
    opening_state_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_image_path: Mapped[str] = mapped_column(Text, nullable=False)
    initial_image_path: Mapped[str] = mapped_column(Text, nullable=False)
    background_image_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    portrait_image_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)
    turn_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_turns: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    ending_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ending_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String, default="ja", nullable=False)
    nsfw_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    text_model: Mapped[str] = mapped_column(String, nullable=False)
    image_provider: Mapped[str] = mapped_column(String, nullable=False)
    image_model: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="adventure_runs")
    turns: Mapped[List["AdventureTurn"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_adventure_runs_user_updated", "user_id", "updated_at"),
        Index("idx_adventure_runs_source_session", "source_session_id"),
    )


class AdventureTurn(Base):
    __tablename__ = "adventure_turns"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("adventure_runs.id", ondelete="CASCADE"), nullable=False
    )
    client_turn_id: Mapped[str] = mapped_column(String, nullable=False)
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    input_kind: Mapped[str] = mapped_column(String, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    choices_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    state_delta_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_status: Mapped[str] = mapped_column(
        String, default="not_requested", nullable=False
    )
    portrait_image_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    portrait_status: Mapped[str] = mapped_column(
        String, default="not_requested", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )

    run: Mapped["AdventureRun"] = relationship(back_populates="turns")

    __table_args__ = (
        Index("idx_adventure_turns_run_number", "run_id", "turn_number", unique=True),
        Index("idx_adventure_turns_client", "run_id", "client_turn_id", unique=True),
    )


class AchievementCount(Base):
    __tablename__ = "achievement_counts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    crossdress_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gender_change_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reality_alter_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class UserAchievement(Base):
    __tablename__ = "user_achievements"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    achievement_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    session_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    achieved_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index("idx_user_achievements_achievement_id", "achievement_id"),
        Index("idx_user_achievements_achieved_at", "achieved_at"),
    )


class SessionCharacter(Base):
    """Per-session character record (spec 005).

    Belongs to one Session. Cascade-deleted when session is removed.
    Multiple characters per session (max 4 enforced at service layer).
    """

    __tablename__ = "session_character"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    slot_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    appearance_natural: Mapped[str] = mapped_column(Text, default="", nullable=False)
    appearance_tags: Mapped[str] = mapped_column(Text, default="", nullable=False)
    position: Mapped[str] = mapped_column(String(16), default="center", nullable=False)
    is_protagonist: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0"
    )
    appearance_lock: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0"
    )
    exclude_from_effects: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0"
    )
    source_preset_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    session: Mapped["Session"] = relationship(back_populates="session_characters")

    __table_args__ = (
        Index("idx_session_character_session_slot", "session_id", "slot_index"),
    )


class CharacterPreset(Base):
    """Global character preset reusable across sessions (spec 005).

    No FK relationship to SessionCharacter; deletion is independent.
    """

    __tablename__ = "character_preset"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    appearance_natural: Mapped[str] = mapped_column(Text, default="", nullable=False)
    appearance_tags: Mapped[str] = mapped_column(Text, default="", nullable=False)
    default_position: Mapped[str] = mapped_column(
        String(16), default="center", nullable=False
    )
    tags_meta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    __table_args__ = (Index("idx_character_preset_name", "name"),)


class PlaySummary(Base):
    """LLM-generated play summary and title for a session."""

    __tablename__ = "play_summaries"

    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    timeline_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    session: Mapped["Session"] = relationship(backref="play_summary")


class ParameterChangeLog(Base):
    """Per-stat parameter change record per history entry.

    Used for traceability and revert-on-history-delete (spec 004).
    """

    __tablename__ = "parameter_change_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    history_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("history.id", ondelete="CASCADE"),
        nullable=False,
    )
    stat_name: Mapped[str] = mapped_column(String, nullable=False)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    prev_value: Mapped[int] = mapped_column(Integer, nullable=False)
    new_value: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )

    __table_args__ = (
        Index("idx_pcl_history_id", "history_id"),
        Index("idx_pcl_session_id", "session_id"),
    )


class FavoriteOutfit(Base):
    """履歴画像へのお気に入りブックマーク（衣装スナップショット）."""

    __tablename__ = "favorite_outfits"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    history_id: Mapped[str] = mapped_column(
        String, ForeignKey("history.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )

    __table_args__ = (
        Index(
            "idx_favorite_outfits_user_history",
            "user_id",
            "history_id",
            unique=True,
        ),
        Index("idx_favorite_outfits_user_created", "user_id", "created_at"),
        Index("idx_favorite_outfits_history_id", "history_id"),
    )


class PromptExpanderSession(Base):
    """Prompt Expander のセッション（1セッション複数エントリ）."""

    __tablename__ = "prompt_expander_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(
        String(120), default="", nullable=False, server_default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="prompt_expander_sessions")
    entries: Mapped[List["PromptExpanderEntry"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_prompt_expander_sessions_user_updated", "user_id", "updated_at"),
    )


class PromptExpanderEntry(Base):
    """Prompt Expander の履歴エントリ（生成画像またはアップロード画像）."""

    __tablename__ = "prompt_expander_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("prompt_expander_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # generated | uploaded
    kind: Mapped[str] = mapped_column(String, nullable=False, default="generated")
    # 拡張前のユーザー指示（拡張 OFF のときは final_prompt と同じ文面）
    instruction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # off | japanese | tags
    positive_expand_mode: Mapped[str] = mapped_column(
        String, default="off", nullable=False, server_default="off"
    )
    negative_expand_mode: Mapped[str] = mapped_column(
        String, default="off", nullable=False, server_default="off"
    )
    character_mode: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0"
    )
    final_prompt: Mapped[str] = mapped_column(
        Text, default="", nullable=False, server_default=""
    )
    final_negative_prompt: Mapped[str] = mapped_column(
        Text, default="", nullable=False, server_default=""
    )
    # list[str] を JSON で保持
    character_prompts_json: Mapped[str] = mapped_column(
        Text, default="[]", nullable=False, server_default="[]"
    )
    image_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    text_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    i2i_strength: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    i2i_noise: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    image_size: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 漫画モード（V5 のコマ割り）で拡張したプロンプトか。panel_count は None がおまかせ
    manga_mode: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0"
    )
    manga_panel_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # none | history | entry | upload
    source_kind: Mapped[str] = mapped_column(
        String, default="none", nullable=False, server_default="none"
    )
    source_history_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("history.id", ondelete="SET NULL"), nullable=True
    )
    source_entry_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("prompt_expander_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 背景透過で生成したか（接尾辞は保存せず、生成時に image_model から導出する）
    transparent_background: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0"
    )
    # 精密参照（character reference）の参照元。none | history | entry | upload
    reference_kind: Mapped[str] = mapped_column(
        String, default="none", nullable=False, server_default="none"
    )
    reference_history_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("history.id", ondelete="SET NULL"), nullable=True
    )
    reference_entry_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("prompt_expander_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    # character | style | character&style（参照ありのときだけ値を持つ）
    reference_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reference_strength: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reference_fidelity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # インペイント（部分修正）で生成したか。マスクは画像と同じ場所へ _mask.png で残す
    inpaint: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0"
    )
    inpaint_mask_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # data/ からの相対パス（例: data/prompt_expander_images/{session_id}/{entry_id}.png）
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=func.current_timestamp(), nullable=False
    )

    session: Mapped["PromptExpanderSession"] = relationship(back_populates="entries")

    __table_args__ = (
        Index(
            "idx_prompt_expander_entries_session_created",
            "session_id",
            "created_at",
        ),
        Index("idx_prompt_expander_entries_created", "created_at"),
    )
