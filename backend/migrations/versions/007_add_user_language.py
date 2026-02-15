"""Add language column to users table.

Revision ID: 007_add_user_language
Revises: 006_add_achievement_counts
Create Date: 2026-02-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007_add_user_language"
down_revision: Union[str, None] = "006_add_achievement_counts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("PRAGMA table_info(users)")).fetchall()
    has_language = any(row[1] == "language" for row in rows)

    if not has_language:
        op.execute("ALTER TABLE users ADD COLUMN language TEXT NOT NULL DEFAULT 'ja'")


def downgrade() -> None:
    pass
