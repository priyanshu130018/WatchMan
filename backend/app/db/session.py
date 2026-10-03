from sqlalchemy import create_engine, event, Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import time

from app.core.config import settings
from app.core.timing import get_current_timing_ctx


@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info["_query_start_time"] = time.perf_counter()


@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    start = conn.info.get("_query_start_time")
    if start:
        elapsed_ms = (time.perf_counter() - start) * 1000
        ctx = get_current_timing_ctx()
        if ctx:
            ctx.sql_query_count += 1
            ctx.db_ms += elapsed_ms
            ctx.sql_queries.append({
                "statement": str(statement)[:200],
                "duration_ms": round(elapsed_ms, 2),
            })


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

