"""add_user_novelai_image_models

Revision ID: 012_add_user_novelai_image_models
Revises: 49557c43d0d7
Create Date: 2026-08-21

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "012_add_user_novelai_image_models"
down_revision: Union[str, None] = "49557c43d0d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "novelai_image_model",
            sa.String(),
            nullable=False,
            server_default="nai-diffusion-4-5-full",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "novelai_curated_image_model",
            sa.String(),
            nullable=False,
            server_default="nai-diffusion-4-5-curated",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "novelai_curated_image_model")
    op.drop_column("users", "novelai_image_model")
