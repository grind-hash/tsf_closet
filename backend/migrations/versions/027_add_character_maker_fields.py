"""add_character_maker_fields

Revision ID: 027_add_character_maker_fields
Revises: 026_add_user_history_lookback_count
Create Date: 2026-10-26

Character maker: a character preset also carries a 3D model (VRM), a voice and
a portrait image, and a character chat thread can be linked to a preset so that
its personality, speech style and knowledge are read live from the preset.
No foreign keys are added (same reason as source_run_id: avoid SQLite table
rebuilds, and keep conversations when a preset or model is deleted).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "027_add_character_maker_fields"
down_revision: str | None = "026_add_user_history_lookback_count"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("character_preset") as batch_op:
        batch_op.add_column(sa.Column("avatar_model_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("voice_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("portrait_path", sa.Text(), nullable=True))
    with op.batch_alter_table("character_chat_threads") as batch_op:
        batch_op.add_column(
            sa.Column("character_preset_id", sa.String(), nullable=True)
        )
        batch_op.create_index(
            "idx_character_chat_threads_character_preset",
            ["character_preset_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("character_chat_threads") as batch_op:
        batch_op.drop_index("idx_character_chat_threads_character_preset")
        batch_op.drop_column("character_preset_id")
    with op.batch_alter_table("character_preset") as batch_op:
        batch_op.drop_column("portrait_path")
        batch_op.drop_column("voice_json")
        batch_op.drop_column("avatar_model_id")
