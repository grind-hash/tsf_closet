"""add_salon_runs

Revision ID: 030_add_salon_runs
Revises: 029_add_request_turn_and_question_limits
Create Date: 2026-10-31

Salon management mode: a season of a salon (salon_runs) and its customer
visits (salon_visits). Each visit is served in an ordinary game session with a
request, linked by session_id (kept as NULL if the session is deleted).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "030_add_salon_runs"
down_revision: str | None = "029_add_request_turn_and_question_limits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "salon_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("total_weeks", sa.Integer(), nullable=False),
        sa.Column("cash", sa.Integer(), nullable=False),
        sa.Column("reputation", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_salon_runs_user_updated",
        "salon_runs",
        ["user_id", "updated_at"],
        unique=False,
    )
    op.create_table(
        "salon_visits",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("salon_id", sa.String(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("customer_source", sa.String(), nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("customer_name", sa.String(length=120), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("satisfaction", sa.Integer(), nullable=True),
        sa.Column("fulfilled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("payment", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reputation_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["salon_id"], ["salon_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_salon_visits_salon_week",
        "salon_visits",
        ["salon_id", "week", "slot"],
        unique=False,
    )
    op.create_index(
        "idx_salon_visits_session", "salon_visits", ["session_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_salon_visits_session", table_name="salon_visits")
    op.drop_index("idx_salon_visits_salon_week", table_name="salon_visits")
    op.drop_table("salon_visits")
    op.drop_index("idx_salon_runs_user_updated", table_name="salon_runs")
    op.drop_table("salon_runs")
