"""add_adventure_portrait_background_fields

Revision ID: 15605ab968c2
Revises: h8c2d3e4f5g6
Create Date: 2026-08-10 11:18:04.477007

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "15605ab968c2"
down_revision: Union[str, None] = "h8c2d3e4f5g6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("adventure_runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("background_image_path", sa.Text(), nullable=True)
        )
        batch_op.add_column(sa.Column("portrait_image_path", sa.Text(), nullable=True))

    with op.batch_alter_table("adventure_turns", schema=None) as batch_op:
        batch_op.add_column(sa.Column("portrait_image_path", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "portrait_status",
                sa.String(),
                nullable=False,
                server_default="not_requested",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("adventure_turns", schema=None) as batch_op:
        batch_op.drop_column("portrait_status")
        batch_op.drop_column("portrait_image_path")

    with op.batch_alter_table("adventure_runs", schema=None) as batch_op:
        batch_op.drop_column("portrait_image_path")
        batch_op.drop_column("background_image_path")
