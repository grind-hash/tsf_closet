"""add_character_chat

Revision ID: 021_add_character_chat
Revises: 020_add_avatar_character_variant
Create Date: 2026-09-06

Character chat: 1-on-1 conversations with a character outside the TSF
scenario. ``character_chat_threads`` holds the persona / appearance snapshot
and a rolling summary, ``character_chat_messages`` holds the transcript.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021_add_character_chat"
down_revision: str | None = "020_add_avatar_character_variant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "character_chat_threads",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("pronoun", sa.String(length=16), nullable=False),
        sa.Column("persona_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("appearance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("portrait_path", sa.Text(), nullable=True),
        sa.Column("source_session_id", sa.String(), nullable=True),
        sa.Column("source_history_id", sa.String(), nullable=True),
        sa.Column("source_prompt_expander_entry_id", sa.String(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column(
            "summary_message_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("language", sa.String(), nullable=False, server_default="ja"),
        sa.Column("nsfw_mode", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_session_id"], ["sessions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_history_id"], ["history.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_character_chat_threads_user_updated",
        "character_chat_threads",
        ["user_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "idx_character_chat_threads_user_kind",
        "character_chat_threads",
        ["user_id", "kind"],
        unique=False,
    )
    op.create_table(
        "character_chat_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["character_chat_threads.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_character_chat_messages_thread_created",
        "character_chat_messages",
        ["thread_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_character_chat_messages_thread_created",
        table_name="character_chat_messages",
    )
    op.drop_table("character_chat_messages")
    op.drop_index(
        "idx_character_chat_threads_user_kind", table_name="character_chat_threads"
    )
    op.drop_index(
        "idx_character_chat_threads_user_updated",
        table_name="character_chat_threads",
    )
    op.drop_table("character_chat_threads")
