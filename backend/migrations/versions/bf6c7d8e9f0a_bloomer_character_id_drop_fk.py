"""bloomer character_id drop fk

Revision ID: bf6c7d8e9f0a
Revises: ae5aba1a1605
Create Date: 2026-08-04

character_id は images/characters/characters.json の id を格納するため、
character_preset への FK を外す。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "bf6c7d8e9f0a"
down_revision: Union[str, None] = "ae5aba1a1605"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMNS = (
    "id, user_id, origin, source_session_id, character_id, name, day, max_days, "
    "actions_left, stage, nsfw_stage, mood, stamina, trust, axes_json, growth_json, "
    "wardrobe_json, equipped_outfit, decisions_json, status, ending_key, "
    "initial_image_path, current_image_path, created_at, updated_at"
)


def upgrade() -> None:
    # bloomer_events が参照しているため、一時的に FK を無効化して差し替える
    op.execute(sa.text("PRAGMA foreign_keys=OFF"))
    op.create_table(
        "bloomer_runs_new",
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
            ["source_session_id"], ["sessions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        f"INSERT INTO bloomer_runs_new ({_COLUMNS}) SELECT {_COLUMNS} FROM bloomer_runs"
    )
    op.drop_table("bloomer_runs")
    op.rename_table("bloomer_runs_new", "bloomer_runs")
    with op.batch_alter_table("bloomer_runs", schema=None) as batch_op:
        batch_op.create_index(
            "idx_bloomer_runs_user_status", ["user_id", "status"], unique=False
        )
        batch_op.create_index(
            "idx_bloomer_runs_user_updated", ["user_id", "updated_at"], unique=False
        )
    op.execute(sa.text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    op.execute(sa.text("PRAGMA foreign_keys=OFF"))
    op.create_table(
        "bloomer_runs_old",
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
    op.execute(
        f"INSERT INTO bloomer_runs_old ({_COLUMNS}) SELECT {_COLUMNS} FROM bloomer_runs"
    )
    op.drop_table("bloomer_runs")
    op.rename_table("bloomer_runs_old", "bloomer_runs")
    with op.batch_alter_table("bloomer_runs", schema=None) as batch_op:
        batch_op.create_index(
            "idx_bloomer_runs_user_status", ["user_id", "status"], unique=False
        )
        batch_op.create_index(
            "idx_bloomer_runs_user_updated", ["user_id", "updated_at"], unique=False
        )
    op.execute(sa.text("PRAGMA foreign_keys=ON"))
