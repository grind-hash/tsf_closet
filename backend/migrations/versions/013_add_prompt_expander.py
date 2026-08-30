"""add_prompt_expander

Revision ID: 013_add_prompt_expander
Revises: 012_add_user_novelai_image_models
Create Date: 2026-08-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "013_add_prompt_expander"
down_revision: Union[str, None] = "012_add_user_novelai_image_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_expander_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_prompt_expander_sessions_user_updated",
        "prompt_expander_sessions",
        ["user_id", "updated_at"],
        unique=False,
    )
    op.create_table(
        "prompt_expander_entries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=True),
        sa.Column(
            "positive_expand_mode", sa.String(), nullable=False, server_default="off"
        ),
        sa.Column(
            "negative_expand_mode", sa.String(), nullable=False, server_default="off"
        ),
        sa.Column("character_mode", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("final_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "final_negative_prompt", sa.Text(), nullable=False, server_default=""
        ),
        sa.Column(
            "character_prompts_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column("image_model", sa.String(), nullable=True),
        sa.Column("text_model", sa.String(), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("i2i_strength", sa.Float(), nullable=True),
        sa.Column("i2i_noise", sa.Float(), nullable=True),
        sa.Column("image_size", sa.String(), nullable=True),
        sa.Column("source_kind", sa.String(), nullable=False, server_default="none"),
        sa.Column("source_history_id", sa.String(), nullable=True),
        sa.Column("source_entry_id", sa.String(), nullable=True),
        sa.Column("image_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["prompt_expander_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_history_id"], ["history.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_entry_id"], ["prompt_expander_entries.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_prompt_expander_entries_session_created",
        "prompt_expander_entries",
        ["session_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_prompt_expander_entries_created",
        "prompt_expander_entries",
        ["created_at"],
        unique=False,
    )
    op.add_column(
        "users",
        sa.Column("prompt_expander_settings_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "adventure_runs",
        sa.Column("source_prompt_expander_entry_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("adventure_runs") as batch_op:
        batch_op.drop_column("source_prompt_expander_entry_id")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("prompt_expander_settings_json")
    op.drop_index(
        "idx_prompt_expander_entries_created", table_name="prompt_expander_entries"
    )
    op.drop_index(
        "idx_prompt_expander_entries_session_created",
        table_name="prompt_expander_entries",
    )
    op.drop_table("prompt_expander_entries")
    op.drop_index(
        "idx_prompt_expander_sessions_user_updated",
        table_name="prompt_expander_sessions",
    )
    op.drop_table("prompt_expander_sessions")
