"""add conversation_messages columns

Revision ID: 004
Revises: 003_add_user_achievements
Create Date: 2026-02-02
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "004_add_conversation_columns"
down_revision: Union[str, None] = "003_add_user_achievements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add instruction_type, attached_image_url, related_history_id to conversation table."""
    # SQLite ALTER TABLE ADD COLUMN
    op.execute("ALTER TABLE conversation ADD COLUMN instruction_type TEXT")
    op.execute("ALTER TABLE conversation ADD COLUMN attached_image_url TEXT")
    op.execute("ALTER TABLE conversation ADD COLUMN related_history_id TEXT")


def downgrade() -> None:
    """SQLite does not support DROP COLUMN easily, recreate table if needed."""
    # For SQLite, we would need to recreate the table to remove columns
    # This is a no-op for simplicity; columns remain but unused
    pass
