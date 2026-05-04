"""add_parameter_change_log

Revision ID: 012_add_parameter_change_log
Revises: 011_add_user_novelai_text_model
Create Date: 2026-05-04

Adds ``parameter_change_log`` table for spec 004 (parameter traceability
and history-based revert). Stores per-stat delta history per
``(session_id, history_id)``.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012_add_parameter_change_log"
down_revision: Union[str, None] = "011_add_user_novelai_text_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "parameter_change_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("history_id", sa.String(), nullable=False),
        sa.Column("stat_name", sa.String(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("prev_value", sa.Integer(), nullable=False),
        sa.Column("new_value", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["history_id"], ["history.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_pcl_history_id",
        "parameter_change_log",
        ["history_id"],
        unique=False,
    )
    op.create_index(
        "idx_pcl_session_id",
        "parameter_change_log",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_pcl_session_id", table_name="parameter_change_log")
    op.drop_index("idx_pcl_history_id", table_name="parameter_change_log")
    op.drop_table("parameter_change_log")
