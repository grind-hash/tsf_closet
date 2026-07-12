"""add_user_tts_settings

Revision ID: f3a1b2c4d5e6
Revises: e8fdcc4c3a8e
Create Date: 2026-07-12

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3a1b2c4d5e6"
down_revision: Union[str, None] = "e8fdcc4c3a8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("tts_enabled", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("tts_use_gpu", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("tts_engine_dir", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("tts_model_dir", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("tts_speaker_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("tts_style_id", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "tts_output_format", sa.String(), nullable=False, server_default="wav"
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "tts_output_format")
    op.drop_column("users", "tts_style_id")
    op.drop_column("users", "tts_speaker_id")
    op.drop_column("users", "tts_model_dir")
    op.drop_column("users", "tts_engine_dir")
    op.drop_column("users", "tts_use_gpu")
    op.drop_column("users", "tts_enabled")
