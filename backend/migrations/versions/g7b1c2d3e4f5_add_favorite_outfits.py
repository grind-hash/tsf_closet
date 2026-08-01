"""お気に入り衣装スナップショット用テーブルを追加する。"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "g7b1c2d3e4f5"
down_revision: Union[str, None] = "016_add_user_feeling_mode"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "favorite_outfits",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("history_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["history_id"], ["history.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_favorite_outfits_user_history",
        "favorite_outfits",
        ["user_id", "history_id"],
        unique=True,
    )
    op.create_index(
        "idx_favorite_outfits_user_created",
        "favorite_outfits",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_favorite_outfits_history_id",
        "favorite_outfits",
        ["history_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_favorite_outfits_history_id", table_name="favorite_outfits")
    op.drop_index("idx_favorite_outfits_user_created", table_name="favorite_outfits")
    op.drop_index("idx_favorite_outfits_user_history", table_name="favorite_outfits")
    op.drop_table("favorite_outfits")
