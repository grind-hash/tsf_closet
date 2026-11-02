"""add_request_emphasize_hints

Revision ID: 031_add_request_emphasize_hints
Revises: 030_add_salon_runs
Create Date: 2026-11-01

A request can ask the feeling text to mark the one sentence that hints at a
not-yet-satisfied preference, so the salon screen can emphasize it (easy and
normal difficulty only).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "031_add_request_emphasize_hints"
down_revision: str | None = "030_add_salon_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("session_requests") as batch_op:
        batch_op.add_column(
            sa.Column(
                "emphasize_hints", sa.Boolean(), nullable=False, server_default="0"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("session_requests") as batch_op:
        batch_op.drop_column("emphasize_hints")
