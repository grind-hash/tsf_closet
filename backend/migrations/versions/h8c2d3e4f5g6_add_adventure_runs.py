"""アドベンチャーRunとターンを追加する。"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "h8c2d3e4f5g6"
down_revision: Union[str, None] = "g7b1c2d3e4f5"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "adventure_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("source_session_id", sa.String(), nullable=True),
        sa.Column("source_history_id", sa.String(), nullable=True),
        sa.Column("preset", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("constraints_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("current_image_path", sa.Text(), nullable=False),
        sa.Column("initial_image_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_turns", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("ending_title", sa.Text(), nullable=True),
        sa.Column("ending_summary", sa.Text(), nullable=True),
        sa.Column("language", sa.String(), nullable=False, server_default="ja"),
        sa.Column("nsfw_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("text_model", sa.String(), nullable=False),
        sa.Column("image_provider", sa.String(), nullable=False),
        sa.Column("image_model", sa.String(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["source_session_id"], ["sessions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_history_id"], ["history.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_adventure_runs_user_updated",
        "adventure_runs",
        ["user_id", "updated_at"],
    )
    op.create_index(
        "idx_adventure_runs_source_session",
        "adventure_runs",
        ["source_session_id"],
    )

    op.create_table(
        "adventure_turns",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("client_turn_id", sa.String(), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column("input_kind", sa.String(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("choices_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("state_delta_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("image_path", sa.Text(), nullable=True),
        sa.Column(
            "image_status",
            sa.String(),
            nullable=False,
            server_default="not_requested",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["adventure_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_adventure_turns_run_number",
        "adventure_turns",
        ["run_id", "turn_number"],
        unique=True,
    )
    op.create_index(
        "idx_adventure_turns_client",
        "adventure_turns",
        ["run_id", "client_turn_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_adventure_turns_client", table_name="adventure_turns")
    op.drop_index("idx_adventure_turns_run_number", table_name="adventure_turns")
    op.drop_table("adventure_turns")
    op.drop_index("idx_adventure_runs_source_session", table_name="adventure_runs")
    op.drop_index("idx_adventure_runs_user_updated", table_name="adventure_runs")
    op.drop_table("adventure_runs")
