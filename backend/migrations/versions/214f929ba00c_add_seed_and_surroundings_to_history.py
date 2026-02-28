"""add_seed_and_surroundings_to_history

Revision ID: 214f929ba00c
Revises: 009_add_history_instruction_type
Create Date: 2026-02-28 03:53:55.704515

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "214f929ba00c"
down_revision: Union[str, None] = "009_add_history_instruction_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("history", sa.Column("seed", sa.Integer(), nullable=True))
    op.add_column(
        "history", sa.Column("surroundings_image_path", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("history", "surroundings_image_path")
    op.drop_column("history", "seed")
