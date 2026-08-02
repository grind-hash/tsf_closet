"""add_user_feeling_mode

Revision ID: 016_add_user_feeling_mode
Revises: 015_add_gender_congruence_llm
Create Date: 2026-07-20

Add feeling_mode to users.
- legacy: traditional TSF resistance monologues (default; no gender-congruence)
- gender_aware: suppress discomfort for gender-congruent outfits
  (mis-saved aliases new/experimental are normalized to gender_aware at runtime)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016_add_user_feeling_mode"
down_revision: Union[str, None] = "015_add_gender_congruence_llm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "feeling_mode",
            sa.String(),
            nullable=False,
            server_default="legacy",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "feeling_mode")
