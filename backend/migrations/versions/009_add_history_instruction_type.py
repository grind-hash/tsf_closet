"""Add instruction_type to history table.

Revision ID: 009_add_history_instruction_type
Revises: 008_add_self_mode
Create Date: 2026-02-22
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "009_add_history_instruction_type"
down_revision: Union[str, None] = "008_add_self_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add instruction_type column to history table."""
    op.execute("ALTER TABLE history ADD COLUMN instruction_type TEXT")


def downgrade() -> None:
    """Remove instruction_type column from history (SQLite limitations)."""
    # SQLite does not support DROP COLUMN before 3.35.0; use
    # batch mode or recreate table if needed.
    pass
