"""fix_user_achievements_fk

Revision ID: 013_fix_user_achievements_fk
Revises: 012_add_parameter_change_log
Create Date: 2026-05-04

Fix broken FK in user_achievements: session_id referenced sessions(session_id)
which does not exist. The sessions PK is 'id', so this caused
'foreign key mismatch' errors when PRAGMA foreign_keys is ON.

Recreates user_achievements with the corrected FK:
    REFERENCES sessions(id) ON DELETE SET NULL
"""

from typing import Sequence, Union

from alembic import op

revision: str = "013_fix_user_achievements_fk"
down_revision: Union[str, None] = "012_add_parameter_change_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite does not support ALTER TABLE ... DROP CONSTRAINT / ADD CONSTRAINT.
    # Recreate the table with the correct FK using the recommended batch migration.

    # Step 1: rename old table
    op.execute("ALTER TABLE user_achievements RENAME TO user_achievements_old")

    # Step 2: create corrected table
    op.execute(
        """
        CREATE TABLE user_achievements (
            id TEXT PRIMARY KEY,
            achievement_id TEXT NOT NULL UNIQUE,
            session_id TEXT,
            achieved_at TEXT,
            progress INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
        )
        """
    )

    # Step 3: copy existing data
    op.execute(
        """
        INSERT INTO user_achievements
            (id, achievement_id, session_id, achieved_at, progress, created_at, updated_at)
        SELECT
            id, achievement_id, session_id, achieved_at, progress, created_at, updated_at
        FROM user_achievements_old
        """
    )

    # Step 4: drop backup
    op.execute("DROP TABLE user_achievements_old")

    # Step 5: recreate indexes
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_achievements_achievement_id "
        "ON user_achievements (achievement_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_achievements_achieved_at "
        "ON user_achievements (achieved_at)"
    )


def downgrade() -> None:
    # Restore the (broken) original schema
    op.execute("ALTER TABLE user_achievements RENAME TO user_achievements_new")

    op.execute(
        """
        CREATE TABLE user_achievements (
            id TEXT PRIMARY KEY,
            achievement_id TEXT NOT NULL UNIQUE,
            session_id TEXT,
            achieved_at TEXT,
            progress INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        )
        """
    )

    op.execute(
        """
        INSERT INTO user_achievements
            (id, achievement_id, session_id, achieved_at, progress, created_at, updated_at)
        SELECT
            id, achievement_id, session_id, achieved_at, progress, created_at, updated_at
        FROM user_achievements_new
        """
    )

    op.execute("DROP TABLE user_achievements_new")
