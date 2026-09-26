"""add ALS latent factor tables (collaborative filtering)

Revision ID: a1b2c3d4e5f6
Revises: 3d8b1c4e5f6a
Create Date: 2026-09-24 18:00:00.000000

Adds persisted ALS / matrix-factorization latent factors for the collaborative
recommendation branch. These are stored as JSON float arrays and are kept
entirely separate from the pgvector content/user embeddings.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "3d8b1c4e5f6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "als_user_factors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("factors", sa.JSON(), nullable=False),
        sa.Column("num_factors", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False, server_default="als-1.0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_als_user_factors_user_id", "als_user_factors", ["user_id"])

    op.create_table(
        "als_item_factors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("factors", sa.JSON(), nullable=False),
        sa.Column("num_factors", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False, server_default="als-1.0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_id"),
    )
    op.create_index("ix_als_item_factors_content_id", "als_item_factors", ["content_id"])


def downgrade() -> None:
    op.drop_index("ix_als_item_factors_content_id", table_name="als_item_factors")
    op.drop_table("als_item_factors")
    op.drop_index("ix_als_user_factors_user_id", table_name="als_user_factors")
    op.drop_table("als_user_factors")
