"""add_salon_tips_and_clue_level

Revision ID: 037_add_salon_tips_and_clue_level
Revises: 036_add_salon_visit_extra_cost
Create Date: 2026-11-03

The salon checkout adds a reputation tip and a regular customer's fee on top of
the course price, so the receipt records both. A request also stores how plainly
the customer's counselling answers hint at the hidden preferences.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "037_add_salon_tips_and_clue_level"
down_revision: str | None = "036_add_salon_visit_extra_cost"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("salon_visits") as batch_op:
        batch_op.add_column(
            sa.Column("tip", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("regular_fee", sa.Integer(), nullable=False, server_default="0")
        )
    with op.batch_alter_table("session_requests") as batch_op:
        batch_op.add_column(
            sa.Column(
                "clue_level", sa.String(), nullable=False, server_default="normal"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("session_requests") as batch_op:
        batch_op.drop_column("clue_level")
    with op.batch_alter_table("salon_visits") as batch_op:
        batch_op.drop_column("regular_fee")
        batch_op.drop_column("tip")
