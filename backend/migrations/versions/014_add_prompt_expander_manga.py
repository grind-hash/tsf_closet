"""add_prompt_expander_manga

Revision ID: 014_add_prompt_expander_manga
Revises: 013_add_prompt_expander
Create Date: 2026-08-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "014_add_prompt_expander_manga"
down_revision: Union[str, None] = "013_add_prompt_expander"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.add_column(
            sa.Column("manga_mode", sa.Boolean(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("manga_panel_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.drop_column("manga_panel_count")
        batch_op.drop_column("manga_mode")
