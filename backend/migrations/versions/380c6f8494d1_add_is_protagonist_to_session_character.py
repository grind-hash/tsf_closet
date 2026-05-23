"""add_is_protagonist_to_session_character

Revision ID: 380c6f8494d1
Revises: 81b450196ddd
Create Date: 2026-05-05 13:17:55.752344

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "380c6f8494d1"
down_revision: Union[str, None] = "81b450196ddd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("session_character", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_protagonist", sa.Boolean(), server_default="0", nullable=False
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("session_character", schema=None) as batch_op:
        batch_op.drop_column("is_protagonist")
