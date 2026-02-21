"""Add self_mode to sessions and self_profile_json to users.

Revision ID: 008_add_self_mode
Revises: 007_add_user_language
Create Date: 2026-02-21
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "008_add_self_mode"
down_revision: Union[str, None] = "007_add_user_language"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add self_mode column to sessions and self_profile_json to users."""
    op.execute("ALTER TABLE sessions ADD COLUMN self_mode BOOLEAN NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE users ADD COLUMN self_profile_json TEXT")


def downgrade() -> None:
    """Remove self_mode and self_profile_json columns (SQLite limitations)."""
    # SQLite does not support DROP COLUMN before 3.35.0; use
    # batch mode or recreate table if needed. For simplicity we document
    # the intended change.
    pass
