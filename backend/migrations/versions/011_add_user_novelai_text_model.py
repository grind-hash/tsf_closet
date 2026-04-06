"""add_user_novelai_text_model

Revision ID: 011_add_user_novelai_text_model
Revises: 010_add_play_summaries
Create Date: 2026-04-02

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "011_add_user_novelai_text_model"
down_revision: Union[str, None] = "010_add_play_summaries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "novelai_text_model",
            sa.String(),
            nullable=False,
            server_default="glm-4-6",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "novelai_text_model")
