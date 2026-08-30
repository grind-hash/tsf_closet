"""add_prompt_expander_inpaint

Revision ID: 018_add_prompt_expander_inpaint
Revises: 017_add_user_tts_engine_port
Create Date: 2026-08-28

Adds inpaint (partial redraw) bookkeeping to Prompt Expander entries. The mask
itself is stored next to the generated image as ``{entry_id}_mask.png`` so a
past entry can be regenerated with the same masked region.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "018_add_prompt_expander_inpaint"
down_revision: Union[str, None] = "017_add_user_tts_engine_port"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.add_column(
            sa.Column("inpaint", sa.Boolean(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("inpaint_mask_path", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.drop_column("inpaint_mask_path")
        batch_op.drop_column("inpaint")
