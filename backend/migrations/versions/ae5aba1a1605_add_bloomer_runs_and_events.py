"""add_bloomer_runs_and_events

Revision ID: ae5aba1a1605
Revises: h8c2d3e4f5g6
Create Date: 2026-08-04 19:28:30.217993

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ae5aba1a1605"
down_revision: Union[str, None] = "h8c2d3e4f5g6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bloomer_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("source_session_id", sa.String(), nullable=True),
        sa.Column("character_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("max_days", sa.Integer(), nullable=False),
        sa.Column("actions_left", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("nsfw_stage", sa.Integer(), nullable=False),
        sa.Column("mood", sa.Integer(), nullable=False),
        sa.Column("stamina", sa.Integer(), nullable=False),
        sa.Column("trust", sa.Integer(), nullable=False),
        sa.Column("axes_json", sa.Text(), nullable=False),
        sa.Column("growth_json", sa.Text(), nullable=False),
        sa.Column("wardrobe_json", sa.Text(), nullable=False),
        sa.Column("equipped_outfit", sa.String(), nullable=True),
        sa.Column("decisions_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("ending_key", sa.String(), nullable=True),
        sa.Column("initial_image_path", sa.Text(), nullable=True),
        sa.Column("current_image_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["character_id"], ["character_preset.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_session_id"], ["sessions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("bloomer_runs", schema=None) as batch_op:
        batch_op.create_index(
            "idx_bloomer_runs_user_status", ["user_id", "status"], unique=False
        )
        batch_op.create_index(
            "idx_bloomer_runs_user_updated", ["user_id", "updated_at"], unique=False
        )

    op.create_table(
        "bloomer_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("action_key", sa.String(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column("image_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["bloomer_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("bloomer_events", schema=None) as batch_op:
        batch_op.create_index(
            "idx_bloomer_events_run_created", ["run_id", "created_at"], unique=False
        )
        batch_op.create_index(
            "idx_bloomer_events_run_day", ["run_id", "day"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("bloomer_events", schema=None) as batch_op:
        batch_op.drop_index("idx_bloomer_events_run_day")
        batch_op.drop_index("idx_bloomer_events_run_created")

    op.drop_table("bloomer_events")

    with op.batch_alter_table("bloomer_runs", schema=None) as batch_op:
        batch_op.drop_index("idx_bloomer_runs_user_updated")
        batch_op.drop_index("idx_bloomer_runs_user_status")

    op.drop_table("bloomer_runs")
