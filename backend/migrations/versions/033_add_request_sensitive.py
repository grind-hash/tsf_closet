"""add_request_sensitive

Revision ID: 033_add_request_sensitive
Revises: 032_add_salon_visit_kept_look
Create Date: 2026-11-01

A request can be an adult one (the salon's sensitive treatment mode). It then
also carries what the customer wants to do in the styled look, which becomes
the instruction for the experience scene shown at the reveal.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "033_add_request_sensitive"
down_revision: str | None = "032_add_salon_visit_kept_look"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("session_requests") as batch_op:
        batch_op.add_column(
            sa.Column("sensitive", sa.Boolean(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("experience_text", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("session_requests") as batch_op:
        batch_op.drop_column("experience_text")
        batch_op.drop_column("sensitive")
