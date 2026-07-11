"""セッション単位のプレイメモを追加する。"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a0b1c2d3e4"
down_revision: Union[str, None] = "e8fdcc4c3a8e"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "sessions", sa.Column("play_memory_system_text", sa.Text(), nullable=True)
    )
    op.add_column(
        "sessions", sa.Column("play_memory_user_text", sa.Text(), nullable=True)
    )
    op.add_column(
        "sessions",
        sa.Column(
            "play_memory_system_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "play_memory_user_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "sessions",
        sa.Column("play_memory_system_updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sessions", "play_memory_system_updated_at")
    op.drop_column("sessions", "play_memory_user_enabled")
    op.drop_column("sessions", "play_memory_system_enabled")
    op.drop_column("sessions", "play_memory_user_text")
    op.drop_column("sessions", "play_memory_system_text")
