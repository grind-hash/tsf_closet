"""add_preset_salon_enabled

Revision ID: 034_add_preset_salon_enabled
Revises: 033_add_request_sensitive
Create Date: 2026-11-01

Characters made in the character maker can visit the salon as customers.
Each character can opt out; existing characters visit by default.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "034_add_preset_salon_enabled"
down_revision: str | None = "033_add_request_sensitive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("character_preset") as batch_op:
        batch_op.add_column(
            sa.Column("salon_enabled", sa.Boolean(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    with op.batch_alter_table("character_preset") as batch_op:
        batch_op.drop_column("salon_enabled")
