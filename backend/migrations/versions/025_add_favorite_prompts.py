"""add_favorite_prompts

Revision ID: 025_add_favorite_prompts
Revises: 024_add_character_look_state
Create Date: 2026-10-14

Add tables for favorite prompts: reusable tag/text snippets the user saves and
inserts into prompt fields. They are stored only in TSF Closet and are not
synced with NovelAI prompt chunks.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "025_add_favorite_prompts"
down_revision: str | None = "024_add_character_look_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "favorite_prompt_categories",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_favorite_prompt_categories_user",
        "favorite_prompt_categories",
        ["user_id", "sort_order"],
        unique=False,
    )
    op.create_table(
        "favorite_prompts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("category_id", sa.String(), nullable=True),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["favorite_prompt_categories.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_favorite_prompts_user",
        "favorite_prompts",
        ["user_id", "sort_order"],
        unique=False,
    )
    op.create_index(
        "idx_favorite_prompts_category",
        "favorite_prompts",
        ["category_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_favorite_prompts_category", table_name="favorite_prompts")
    op.drop_index("idx_favorite_prompts_user", table_name="favorite_prompts")
    op.drop_table("favorite_prompts")
    op.drop_index(
        "idx_favorite_prompt_categories_user",
        table_name="favorite_prompt_categories",
    )
    op.drop_table("favorite_prompt_categories")
