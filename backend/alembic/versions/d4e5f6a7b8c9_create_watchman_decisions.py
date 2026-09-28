"""create watchman_decisions table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-28 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    uuid_col = postgresql.UUID(as_uuid=True) if is_postgres else sa.String(36)

    op.create_table(
        "watchman_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", uuid_col, nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=20), server_default="movie", nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "content_id", name="uq_user_content_watchman_decision"),
    )
    op.create_index("ix_watchman_decisions_user_id", "watchman_decisions", ["user_id"])
    op.create_index("ix_watchman_decisions_content_id", "watchman_decisions", ["content_id"])


def downgrade() -> None:
    op.drop_index("ix_watchman_decisions_content_id", table_name="watchman_decisions")
    op.drop_index("ix_watchman_decisions_user_id", table_name="watchman_decisions")
    op.drop_table("watchman_decisions")
