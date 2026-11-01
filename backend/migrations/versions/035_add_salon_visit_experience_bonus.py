"""add_salon_visit_experience_bonus

Revision ID: 035_add_salon_visit_experience_bonus
Revises: 034_add_preset_salon_enabled
Create Date: 2026-11-02

A sensitive visit whose reveal drew the experience scene earns a satisfaction
bonus at checkout. The visit records it so the receipt can show it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "035_add_salon_visit_experience_bonus"
down_revision: str | None = "034_add_preset_salon_enabled"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("salon_visits") as batch_op:
        batch_op.add_column(
            sa.Column(
                "experience_bonus", sa.Integer(), nullable=False, server_default="0"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("salon_visits") as batch_op:
        batch_op.drop_column("experience_bonus")
