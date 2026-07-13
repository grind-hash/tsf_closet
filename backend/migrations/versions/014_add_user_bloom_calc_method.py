"""add_user_bloom_calc_method

Revision ID: 014_add_user_bloom_calc_method
Revises: f3a1b2c4d5e6
Create Date: 2026-07-13

Add bloom_calc_method to users. Selects the bloom increment calculation
method: "legacy" (existing behavior, default) or "new" (gentler growth so
the resistance_limit ending remains reachable).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "014_add_user_bloom_calc_method"
down_revision: Union[str, None] = "f3a1b2c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "bloom_calc_method",
            sa.String(),
            nullable=False,
            server_default="legacy",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "bloom_calc_method")
