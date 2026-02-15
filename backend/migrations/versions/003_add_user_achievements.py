"""add user_achievements table

Revision ID: 003
Revises: 002_add_nsfw_mode
Create Date: 2026-02-02
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "003_add_user_achievements"
down_revision: Union[str, None] = "002_add_nsfw_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add user_achievements table for achievement system."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_achievements (
            id TEXT PRIMARY KEY,
            achievement_id TEXT NOT NULL UNIQUE,
            session_id TEXT,
            achieved_at TEXT,
            progress INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_achievements_achievement_id ON user_achievements(achievement_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_achievements_achieved_at ON user_achievements(achieved_at)"
    )


def downgrade() -> None:
    """Remove user_achievements table."""
    op.execute("DROP INDEX IF EXISTS idx_user_achievements_achieved_at")
    op.execute("DROP INDEX IF EXISTS idx_user_achievements_achievement_id")
    op.execute("DROP TABLE IF EXISTS user_achievements")
