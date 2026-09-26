"""add_character_look_state

Revision ID: 024_add_character_look_state
Revises: 023_add_character_cast_fields
Create Date: 2026-09-26

Separate a cast member's user-authored look (the session_character fields) from
the look actually drawn each turn. The drawn look is stored per history row,
keyed by character id, and carried over to the next turn; appearance_spec_rev
tells whether the user changed the setting after that history was written.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "024_add_character_look_state"
down_revision: str | None = "023_add_character_cast_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("history") as batch_op:
        batch_op.add_column(
            sa.Column("character_states_json", sa.Text(), nullable=True)
        )
    with op.batch_alter_table("session_character") as batch_op:
        batch_op.add_column(
            sa.Column(
                "appearance_spec_rev",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("session_character") as batch_op:
        batch_op.drop_column("appearance_spec_rev")
    with op.batch_alter_table("history") as batch_op:
        batch_op.drop_column("character_states_json")
