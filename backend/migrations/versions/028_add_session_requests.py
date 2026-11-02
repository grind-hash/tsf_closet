"""add_session_requests

Revision ID: 028_add_session_requests
Revises: 027_add_character_maker_fields
Create Date: 2026-10-31

Request mode: a character asks for the look they want to have. The request
(a visible wish and hidden preferences) lives in session_requests, one row per
session, and each turn's evaluation is stored on the history row so that
reverting history also reverts the satisfaction.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "028_add_session_requests"
down_revision: str | None = "027_add_character_maker_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_requests",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("wish_text", sa.Text(), nullable=False),
        sa.Column("preferences_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("language", sa.String(), nullable=False, server_default="ja"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("fulfilled_history_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    with op.batch_alter_table("history") as batch_op:
        batch_op.add_column(
            sa.Column("request_evaluation_json", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("history") as batch_op:
        batch_op.drop_column("request_evaluation_json")
    op.drop_table("session_requests")
