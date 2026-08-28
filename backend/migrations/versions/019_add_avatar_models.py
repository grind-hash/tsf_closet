"""add_avatar_models

Revision ID: 019_add_avatar_models
Revises: 018_add_prompt_expander_inpaint
Create Date: 2026-08-28

Registry of user-uploaded VRM avatars shown in the Adventure companion mode.
The .vrm file itself lives under AVATAR_MODELS_DIR as ``{id}.vrm``.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "019_add_avatar_models"
down_revision: Union[str, None] = "018_add_prompt_expander_inpaint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "avatar_models",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vrm_spec_version", sa.String(), nullable=False, server_default="0"),
        sa.Column("meta_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_avatar_models_created", "avatar_models", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_avatar_models_created", table_name="avatar_models")
    op.drop_table("avatar_models")
