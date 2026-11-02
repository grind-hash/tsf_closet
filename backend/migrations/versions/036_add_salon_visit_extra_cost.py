"""add_salon_visit_extra_cost

Revision ID: 036_add_salon_visit_extra_cost
Revises: 035_add_salon_visit_experience_bonus
Create Date: 2026-11-02

The owner can pay for one extra styling turn after the turns run out. The
visit records what was paid so the receipt and the ledger can show it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "036_add_salon_visit_extra_cost"
down_revision: str | None = "035_add_salon_visit_experience_bonus"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("salon_visits") as batch_op:
        batch_op.add_column(
            sa.Column("extra_cost", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("salon_visits") as batch_op:
        batch_op.drop_column("extra_cost")
