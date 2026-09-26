from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings


def _build_engine():
    """
    Build the SQLAlchemy engine for the configured DATABASE_URL.

    Production points at Supabase PostgreSQL, which is reached through the
    Supabase connection pooler (PgBouncer). NullPool is used deliberately so we
    do not layer a second client-side pool on top of PgBouncer, and
    ``pool_pre_ping`` guards against stale pooled connections. SSL is required
    for any non-local PostgreSQL host.
    """
    url = settings.DATABASE_URL
    connect_args: dict = {}
    is_postgres = url.startswith("postgresql")
    if is_postgres:
        lowered = url.lower()
        has_ssl = "sslmode=" in lowered
        is_local = any(h in lowered for h in ("localhost", "127.0.0.1", "@db:", "//db:"))
        # Require SSL for remote (Supabase) Postgres unless already specified.
        if not has_ssl and not is_local:
            connect_args["sslmode"] = "require"
    return create_engine(
        url,
        poolclass=NullPool,
        pool_pre_ping=True,
        echo=False,
        connect_args=connect_args,
    )


engine = _build_engine()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
