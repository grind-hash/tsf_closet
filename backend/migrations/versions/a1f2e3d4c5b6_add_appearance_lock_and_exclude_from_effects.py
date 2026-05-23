"""add_appearance_lock_and_exclude_from_effects_to_session_character

Revision ID: a1f2e3d4c5b6
Revises: 380c6f8494d1
Create Date: 2026-05-06 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1f2e3d4c5b6"
down_revision: Union[str, None] = "380c6f8494d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("session_character", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "appearance_lock",
                sa.Boolean(),
                server_default="0",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "exclude_from_effects",
                sa.Boolean(),
                server_default="0",
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("session_character", schema=None) as batch_op:
        batch_op.drop_column("exclude_from_effects")
        batch_op.drop_column("appearance_lock")
