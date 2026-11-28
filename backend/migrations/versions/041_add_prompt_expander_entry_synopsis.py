"""add_prompt_expander_entry_synopsis

Revision ID: 041_add_prompt_expander_entry_synopsis
Revises: 040_add_prompt_expander_references_json
Create Date: 2026-11-28

Keeps the synopsis a comic storyboard was drafted from on a Prompt Expander
entry, so restoring the entry brings back the synopsis, the storyboard
(instruction) and the final prompt into their own fields. Entries made without
a storyboard keep NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "041_add_prompt_expander_entry_synopsis"
down_revision: str | None = "040_add_prompt_expander_references_json"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.add_column(sa.Column("synopsis", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.drop_column("synopsis")
