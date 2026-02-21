"""SQLAlchemy ORM models.

All database models using SQLAlchemy 2.0 declarative style.
Maintains the same schema structure as the original raw SQL.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, func
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
    language: Mapped[str] = mapped_column(String, default="ja", nullable=False)
    self_profile_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    sessions: Mapped[List["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    achieved_endings: Mapped[List["AchievedEnding"]] = relationship(
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
