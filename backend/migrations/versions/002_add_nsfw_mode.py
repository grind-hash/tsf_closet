"""Add nsfw_mode column to session_stats.

Revision ID: 002_add_nsfw_mode
Revises: 001_initial
Create Date: 2026-01-28

This migration adds the nsfw_mode column to the session_stats table.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002_add_nsfw_mode"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nsfw_mode column to session_stats table
    # SQLite doesn't support adding columns with NOT NULL without default
    op.add_column(
        "session_stats",
        sa.Column("nsfw_mode", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    # SQLite doesn't support dropping columns directly,
    # but Alembic's batch mode handles this
    with op.batch_alter_table("session_stats") as batch_op:
        batch_op.drop_column("nsfw_mode")
