"""add_avatar_character_variant

Revision ID: 020_add_avatar_character_variant
Revises: 019_add_avatar_models
Create Date: 2026-08-30

Group VRM avatars that depict the same character (costume / hairstyle variants)
so the Adventure companion mode can switch between them. ``character_name`` is
the user-editable group key (NULL = ungrouped) and ``variant_label`` describes
the variant within the group.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "020_add_avatar_character_variant"
down_revision: Union[str, None] = "019_add_avatar_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("avatar_models") as batch_op:
        batch_op.add_column(
            sa.Column("character_name", sa.String(length=80), nullable=True)
        )
        batch_op.add_column(
            sa.Column("variant_label", sa.String(length=80), nullable=True)
        )
        batch_op.create_index(
            "idx_avatar_models_character", ["character_name"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("avatar_models") as batch_op:
        batch_op.drop_index("idx_avatar_models_character")
        batch_op.drop_column("variant_label")
        batch_op.drop_column("character_name")
