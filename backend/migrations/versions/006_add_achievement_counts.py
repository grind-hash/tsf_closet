"""Add achievement_counts table for tracking classification counts.

Revision ID: 006_add_achievement_counts
Revises: 005_add_user_settings
Create Date: 2026-02-07

This migration adds the achievement_counts table to track global counts for
crossdress, gender_change, and reality_alter classifications.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "006_add_achievement_counts"
down_revision: Union[str, None] = "005_add_user_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create achievement_counts table
    op.execute("""
        CREATE TABLE IF NOT EXISTS achievement_counts (
            id TEXT PRIMARY KEY,
            crossdress_count INTEGER NOT NULL DEFAULT 0,
            gender_change_count INTEGER NOT NULL DEFAULT 0,
            reality_alter_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
    """)
    # Insert initial record
    op.execute("""
        INSERT OR IGNORE INTO achievement_counts
        (id, crossdress_count, gender_change_count, reality_alter_count, updated_at)
        VALUES ('global', 0, 0, 0, datetime('now'))
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS achievement_counts")
