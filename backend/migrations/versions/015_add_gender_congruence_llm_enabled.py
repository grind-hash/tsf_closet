"""add_gender_congruence_llm_enabled

Revision ID: 015_add_gender_congruence_llm
Revises: 014_add_user_bloom_calc_method
Create Date: 2026-07-20

Add gender_congruence_llm_enabled to users. When enabled, a dedicated LLM
judges gender-outfit congruence using conversation timeline context.
Default is disabled (0); rule-based judgment still runs when off.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "015_add_gender_congruence_llm"
down_revision: Union[str, None] = "014_add_user_bloom_calc_method"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "gender_congruence_llm_enabled",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "gender_congruence_llm_enabled")
