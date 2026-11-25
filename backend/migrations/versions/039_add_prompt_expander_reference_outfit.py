"""add_prompt_expander_reference_outfit

Revision ID: 039_add_prompt_expander_reference_outfit
Revises: 038_add_hakoniwa_worlds
Create Date: 2026-11-25

Records whether a Prompt Expander entry's precise reference also referenced the
outfit (the "include outfit" toggle of NAI Diffusion V5 precise references).
Only V5 references have a value; V4.5 references and entries without a
reference keep NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "039_add_prompt_expander_reference_outfit"
down_revision: str | None = "038_add_hakoniwa_worlds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.add_column(
            sa.Column("reference_include_outfit", sa.Boolean(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.drop_column("reference_include_outfit")
