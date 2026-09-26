"""add_character_cast_fields

Revision ID: 023_add_character_cast_fields
Revises: 022_add_character_chat_source_run
Create Date: 2026-09-26

Per-character negative tags, personality profile, on-stage flag and source
thumbnail for the multi-character cast, the same fields on one-person presets,
and a table for named cast combinations (group presets).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "023_add_character_cast_fields"
down_revision: str | None = "022_add_character_chat_source_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("session_character") as batch_op:
        batch_op.add_column(
            sa.Column("negative_tags", sa.Text(), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("profile_json", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("on_stage", sa.Boolean(), nullable=False, server_default="1")
        )
        batch_op.add_column(sa.Column("thumbnail_url", sa.String(), nullable=True))

    with op.batch_alter_table("character_preset") as batch_op:
        batch_op.add_column(
            sa.Column("negative_tags", sa.Text(), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("profile_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("thumbnail_url", sa.String(), nullable=True))

    op.create_table(
        "character_group_preset",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("members_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_character_group_preset_name",
        "character_group_preset",
        ["name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_character_group_preset_name", table_name="character_group_preset"
    )
    op.drop_table("character_group_preset")

    with op.batch_alter_table("character_preset") as batch_op:
        batch_op.drop_column("thumbnail_url")
        batch_op.drop_column("profile_json")
        batch_op.drop_column("negative_tags")

    with op.batch_alter_table("session_character") as batch_op:
        batch_op.drop_column("thumbnail_url")
        batch_op.drop_column("on_stage")
        batch_op.drop_column("profile_json")
        batch_op.drop_column("negative_tags")
