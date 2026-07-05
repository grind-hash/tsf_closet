"""add_user_memory_text

Revision ID: e8fdcc4c3a8e
Revises: a1f2e3d4c5b6
Create Date: 2026-07-05 10:52:52.983618

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e8fdcc4c3a8e"
down_revision: Union[str, None] = "a1f2e3d4c5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("memory_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "memory_text")
