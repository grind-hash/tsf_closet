"""add_prompt_expander_references_json

Revision ID: 040_add_prompt_expander_references_json
Revises: 039_add_prompt_expander_reference_outfit
Create Date: 2026-11-27

Stores every precise reference used by a Prompt Expander entry as JSON, so an
entry can record several references (each with its own type, strength, outfit
flag and an optional character name). Entries created before this keep NULL
and are read from the single reference_* columns.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "040_add_prompt_expander_references_json"
down_revision: str | None = "039_add_prompt_expander_reference_outfit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.add_column(sa.Column("references_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.drop_column("references_json")
