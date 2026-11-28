"""add_prompt_expander_entry_instruction_source

Revision ID: 042_add_prompt_expander_entry_instruction_source
Revises: 041_add_prompt_expander_entry_synopsis
Create Date: 2026-11-28

Records which field the instruction of a Prompt Expander entry was written in
(instruction = the instruction / synopsis field, script = the comic storyboard
field). A storyboard written by hand with an empty synopsis can then be
restored into the storyboard field. Existing entries keep NULL and are told
apart by the synopsis as before.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "042_add_prompt_expander_entry_instruction_source"
down_revision: str | None = "041_add_prompt_expander_entry_synopsis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.add_column(sa.Column("instruction_source", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.drop_column("instruction_source")
