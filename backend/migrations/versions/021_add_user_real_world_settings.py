"""add_user_real_world_settings

Revision ID: 021_add_user_real_world_settings
Revises: 020_add_avatar_character_variant
Create Date: 2026-09-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021_add_user_real_world_settings"
down_revision: str | None = "020_add_avatar_character_variant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "real_world_weather_enabled",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "real_world_search_enabled",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "real_world_search_enabled")
    op.drop_column("users", "real_world_weather_enabled")
