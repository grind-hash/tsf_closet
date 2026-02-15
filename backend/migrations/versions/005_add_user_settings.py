"""Add nsfw_mode and difficulty columns to users table.

Revision ID: 005_add_user_settings
Revises: 004_add_conversation_columns
Create Date: 2026-02-05

This migration adds user-level settings (nsfw_mode, difficulty) to the users table.
These settings are now managed per-user instead of per-session.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005_add_user_settings"
down_revision: Union[str, None] = "004_add_conversation_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nsfw_mode column to users table (default: false = 0)
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("nsfw_mode", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column(
                "difficulty", sa.String(), nullable=False, server_default="normal"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("nsfw_mode")
        batch_op.drop_column("difficulty")
