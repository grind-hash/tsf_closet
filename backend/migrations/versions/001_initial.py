"""Initial migration - create all tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-01-26

This migration creates all initial tables matching the original schema.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Insert default user
    op.execute("INSERT OR IGNORE INTO users (id) VALUES ('default-user')")

    # Sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=True),
        sa.Column("current_image_path", sa.Text(), nullable=False),
        sa.Column("transformation_count", sa.Integer(), nullable=False, default=0),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])
    op.create_index("idx_sessions_active", "sessions", ["user_id", "is_active"])

    # History table
    op.create_table(
        "history",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("image_path", sa.Text(), nullable=False),
        sa.Column("feeling_text", sa.Text(), nullable=True),
        sa.Column("before_description", sa.Text(), nullable=True),
        sa.Column("after_description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_history_session_id", "history", ["session_id"])
    op.create_index("idx_history_created_at", "history", ["session_id", "created_at"])

    # Session stats table
    op.create_table(
        "session_stats",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("bloom", sa.Integer(), nullable=False, default=0),
        sa.Column("shame", sa.Integer(), nullable=False, default=50),
        sa.Column("adaptation", sa.Integer(), nullable=False, default=0),
        sa.Column("passed_critical_points", sa.Text(), nullable=False, default="[]"),
        sa.Column("difficulty", sa.String(), nullable=False, default="normal"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )

    # Transformation tags table
    op.create_table(
        "transformation_tags",
        sa.Column("history_id", sa.String(), nullable=False),
        sa.Column("costume_category", sa.String(), nullable=False, default="other"),
        sa.Column("exposure_level", sa.String(), nullable=False, default="medium"),
        sa.Column("age_impression", sa.String(), nullable=False, default="unknown"),
        sa.ForeignKeyConstraint(["history_id"], ["history.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("history_id"),
    )

    # Achieved endings table
    op.create_table(
        "achieved_endings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("ending_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column(
            "achieved_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_achieved_endings_unique",
        "achieved_endings",
        ["user_id", "ending_id"],
        unique=True,
    )
    op.create_index("idx_achieved_endings_user", "achieved_endings", ["user_id"])

    # Conversation table
    op.create_table(
        "conversation",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_conversation_session_id", "conversation", ["session_id"])
    op.create_index(
        "idx_conversation_created_at", "conversation", ["session_id", "created_at"]
    )

    # Session attributes table
    op.create_table(
        "session_attributes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("attribute_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_session_attributes_session_id", "session_attributes", ["session_id"]
    )


def downgrade() -> None:
    op.drop_table("session_attributes")
    op.drop_table("conversation")
    op.drop_table("achieved_endings")
    op.drop_table("transformation_tags")
    op.drop_table("session_stats")
    op.drop_table("history")
    op.drop_table("sessions")
    op.drop_table("users")
