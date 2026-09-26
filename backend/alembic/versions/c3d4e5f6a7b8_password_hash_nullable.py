"""make users.password_hash nullable (Supabase Auth path stores no password)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-24 22:35:00.000000

Production authentication is owned by Supabase Auth, so users authenticated
that way have NO local password. ``users.password_hash`` therefore becomes
nullable. Local-development accounts (AUTH_PROVIDER=local) continue to store a
bcrypt hash here; this only relaxes the NOT NULL constraint.

No data is migrated or dropped. On non-PostgreSQL backends (SQLite tests) the
column is already effectively nullable via the ORM, so this is a no-op there.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # Backfill any NULLs before restoring NOT NULL so the constraint can apply.
    op.execute("UPDATE users SET password_hash = '' WHERE password_hash IS NULL;")
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=False,
    )
