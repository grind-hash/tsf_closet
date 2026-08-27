"""add_user_tts_engine_port

Revision ID: 017_add_user_tts_engine_port
Revises: 015_add_prompt_expander_reference
Create Date: 2026-08-27

Adds a per-user override for the speech synthesis engine port. NULL keeps the
port taken from AIVIS_ENGINE_BASE_URL (10101 by default).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "017_add_user_tts_engine_port"
down_revision: Union[str, None] = "015_add_prompt_expander_reference"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tts_engine_port", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "tts_engine_port")
