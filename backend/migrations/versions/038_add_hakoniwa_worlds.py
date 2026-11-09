"""add_hakoniwa_worlds

Revision ID: 038_add_hakoniwa_worlds
Revises: 037_add_salon_tips_and_clue_level
Create Date: 2026-11-08

AI hakoniwa (dollhouse) mode: one row per world. Residents, rule cards and
the chronicle of events are kept together in state_json.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "038_add_hakoniwa_worlds"
down_revision: str | None = "037_add_salon_tips_and_clue_level"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hakoniwa_worlds",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_hakoniwa_worlds_user_updated",
        "hakoniwa_worlds",
        ["user_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_hakoniwa_worlds_user_updated", table_name="hakoniwa_worlds")
    op.drop_table("hakoniwa_worlds")
