"""add_character_chat_source_run

Revision ID: 022_add_character_chat_source_run
Revises: 021_add_character_chat
Create Date: 2026-09-06

Link a character chat thread to the TSF scenario (AdventureRun) it was opened
from. The Adventure "talk" mode moved into character chat; the thread reads the
run state live on every message.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "022_add_character_chat_source_run"
down_revision: str | None = "021_add_character_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("character_chat_threads") as batch_op:
        batch_op.add_column(sa.Column("source_run_id", sa.String(), nullable=True))
        batch_op.create_index(
            "idx_character_chat_threads_source_run", ["source_run_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("character_chat_threads") as batch_op:
        batch_op.drop_index("idx_character_chat_threads_source_run")
        batch_op.drop_column("source_run_id")
