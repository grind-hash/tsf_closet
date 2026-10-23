"""add_user_history_lookback_count

Revision ID: 026_add_user_history_lookback_count
Revises: 025_add_favorite_prompts
Create Date: 2026-10-17

Persist the history lookback count (number of recent history entries referenced
in LLM prompts) per user. It was previously held only in process memory and
reset to the default on every backend restart.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "026_add_user_history_lookback_count"
down_revision: str | None = "025_add_favorite_prompts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "history_lookback_count",
                sa.Integer(),
                nullable=False,
                server_default="10",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("history_lookback_count")
