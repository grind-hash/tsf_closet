"""add_prompt_expander_reference

Revision ID: 015_add_prompt_expander_reference
Revises: 014_add_prompt_expander_manga
Create Date: 2026-08-26

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "015_add_prompt_expander_reference"
down_revision: Union[str, None] = "014_add_prompt_expander_manga"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.add_column(
            sa.Column(
                "transparent_background",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "reference_kind", sa.String(), nullable=False, server_default="none"
            )
        )
        batch_op.add_column(
            sa.Column("reference_history_id", sa.String(), nullable=True)
        )
        batch_op.add_column(sa.Column("reference_entry_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("reference_type", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("reference_strength", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("reference_fidelity", sa.Float(), nullable=True))
        # SQLite の batch モードでは名前付きの制約でないと downgrade で落とせない
        batch_op.create_foreign_key(
            "fk_prompt_expander_entries_reference_history_id",
            "history",
            ["reference_history_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_prompt_expander_entries_reference_entry_id",
            "prompt_expander_entries",
            ["reference_entry_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("prompt_expander_entries") as batch_op:
        batch_op.drop_constraint(
            "fk_prompt_expander_entries_reference_entry_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_prompt_expander_entries_reference_history_id", type_="foreignkey"
        )
        batch_op.drop_column("reference_fidelity")
        batch_op.drop_column("reference_strength")
        batch_op.drop_column("reference_type")
        batch_op.drop_column("reference_entry_id")
        batch_op.drop_column("reference_history_id")
        batch_op.drop_column("reference_kind")
        batch_op.drop_column("transparent_background")
