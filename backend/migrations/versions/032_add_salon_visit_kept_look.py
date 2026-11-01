"""add_salon_visit_kept_look

Revision ID: 032_add_salon_visit_kept_look
Revises: 031_add_request_emphasize_hints
Create Date: 2026-11-01

A customer whose wish came true keeps the styled look and comes back the next
week in it: the visit records the history of the kept look, and the next
week's booking records the history its serving session branches from.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "032_add_salon_visit_kept_look"
down_revision: str | None = "031_add_request_emphasize_hints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("salon_visits") as batch_op:
        batch_op.add_column(sa.Column("kept_history_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("start_history_id", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("salon_visits") as batch_op:
        batch_op.drop_column("start_history_id")
        batch_op.drop_column("kept_history_id")
