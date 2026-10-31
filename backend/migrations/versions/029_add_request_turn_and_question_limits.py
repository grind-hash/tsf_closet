"""add_request_turn_and_question_limits

Revision ID: 029_add_request_turn_and_question_limits
Revises: 028_add_session_requests
Create Date: 2026-10-31

Request mode foundation shared by normal play and the salon: a request can cap
the number of dress-up turns (turn_limit, NULL means unlimited) and allows a
few counselling questions whose answers hint at the hidden preferences.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "029_add_request_turn_and_question_limits"
down_revision: str | None = "028_add_session_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("session_requests") as batch_op:
        batch_op.add_column(sa.Column("turn_limit", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "question_limit", sa.Integer(), nullable=False, server_default="2"
            )
        )
        batch_op.add_column(
            sa.Column("questions_json", sa.Text(), nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("session_requests") as batch_op:
        batch_op.drop_column("questions_json")
        batch_op.drop_column("question_limit")
        batch_op.drop_column("turn_limit")
