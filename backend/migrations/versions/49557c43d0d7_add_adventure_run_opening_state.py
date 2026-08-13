"""add_adventure_run_opening_state

Revision ID: 49557c43d0d7
Revises: 15605ab968c2
Create Date: 2026-08-13 11:50:22.186681

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "49557c43d0d7"
down_revision: Union[str, None] = "15605ab968c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("adventure_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("opening_state_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("adventure_runs", schema=None) as batch_op:
        batch_op.drop_column("opening_state_json")
