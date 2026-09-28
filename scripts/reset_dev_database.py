#!/usr/bin/env python3
"""
Safe database reset script for development and testing.

Clears runtime, user activity, ML embeddings, and recommendation data while
strictly preserving schema, migrations (alembic_version), extensions, and TMDB catalog data.

Modes:
  --runtime-only : Clears users, activity, ratings, reviews, decisions, user_embeddings,
                   ALS factors, recommendations, and cache. Keeps catalog contents and
                   content_embeddings.
  --full-ml-reset: Clears all of the above PLUS content_embeddings. Keeps the TMDB
                   content catalog, taxonomy, and metadata.

Usage:
  python scripts/reset_dev_database.py --runtime-only
  python scripts/reset_dev_database.py --full-ml-reset
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, text


# Tables to clear in runtime-only mode (cleared in dependency-safe order)
RUNTIME_TABLES = [
    "recommendation_cache",
    "recommendations",
    "recommendation_candidates",
    "als_item_factors",
    "als_user_factors",
    "user_embeddings",
    "watchman_decisions",
    "interaction_events",
    "search_history",
    "watch_history",
    "reviews",
    "ratings",
    "saved_content",
    "user_preferences",
    "profiles",
    "users",
    "user_activity",
]

# Additional tables to clear when performing a full ML reset
FULL_ML_ADDITIONAL_TABLES = [
    "content_embeddings",
]

# Tables that must NEVER be dropped or truncated by this script
PROTECTED_TABLES = {
    "alembic_version",
    "contents",
    "genres",
    "content_genres",
    "languages",
    "content_languages",
    "content_external_ids",
    "content_videos",
    "people",
    "content_cast",
    "content_crew",
}


def get_database_url() -> str:
    """Resolve database URL from environment or .env files."""
    url = os.environ.get("DATABASE_URL")
    if url and url.strip():
        return url.strip()

    # Search in root .env or backend/.env
    root_dir = Path(__file__).resolve().parent.parent
    for candidate in [root_dir / ".env", root_dir / "backend" / ".env"]:
        if candidate.exists():
            values = dotenv_values(candidate)
            if "DATABASE_URL" in values and values["DATABASE_URL"]:
                return values["DATABASE_URL"].strip()

    sys.stderr.write(
        "ERROR: DATABASE_URL not found in environment or .env files.\n"
        "Set DATABASE_URL before running the reset script.\n"
    )
    sys.exit(1)


def reset_database(mode: str, dry_run: bool = False) -> None:
    raw_url = get_database_url()
    # Normalize driver prefix for SQLAlchemy if needed
    db_url = raw_url
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    print("=" * 60)
    print("WatchMan Safe Database Reset")
    print("=" * 60)
    print(f"Target Mode: {mode}")
    print(f"Database   : {raw_url.split('@')[-1] if '@' in raw_url else 'local/memory'}")
    if dry_run:
        print("[DRY-RUN MODE] No changes will be committed.")

    tables_to_clear = list(RUNTIME_TABLES)
    if mode == "--full-ml-reset":
        tables_to_clear.extend(FULL_ML_ADDITIONAL_TABLES)

    engine = create_engine(db_url)
    is_sqlite = engine.dialect.name == "sqlite"

    with engine.connect() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())

        # Determine which target tables actually exist in DB
        targets = [t for t in tables_to_clear if t in existing_tables]

        # Verify protected tables are not in targets
        for t in targets:
            if t in PROTECTED_TABLES:
                raise RuntimeError(f"Safety violation: Protected table '{t}' targeted for deletion!")

        print("\nPre-reset table row counts:")
        for t in targets:
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  - {t:<28}: {cnt:>6} rows")

        # Report content catalog count (guaranteed preserved)
        if "contents" in existing_tables:
            content_cnt = conn.execute(text("SELECT COUNT(*) FROM contents")).scalar()
            print(f"  * contents (PRESERVED)     : {content_cnt:>6} rows")
        if "content_embeddings" in existing_tables and mode == "--runtime-only":
            emb_cnt = conn.execute(text("SELECT COUNT(*) FROM content_embeddings")).scalar()
            print(f"  * content_embeddings (KEPT): {emb_cnt:>6} rows")

        if dry_run:
            print("\nDry-run complete. Exiting without modifying database.")
            return

        print(f"\nExecuting reset for {len(targets)} tables...")
        if is_sqlite:
            # SQLite: disable FK constraints temporarily or delete in topological order
            conn.execute(text("PRAGMA foreign_keys = OFF;"))
            for t in targets:
                conn.execute(text(f"DELETE FROM {t};"))
            conn.execute(text("PRAGMA foreign_keys = ON;"))
            conn.commit()
        else:
            # PostgreSQL: TRUNCATE TABLE ... CASCADE
            if targets:
                table_list_sql = ", ".join(f'"{t}"' for t in targets)
                conn.execute(text(f"TRUNCATE TABLE {table_list_sql} CASCADE;"))
                conn.commit()

        print("\nPost-reset table row counts:")
        for t in targets:
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  - {t:<28}: {cnt:>6} rows")

        if "contents" in existing_tables:
            content_cnt_post = conn.execute(text("SELECT COUNT(*) FROM contents")).scalar()
            print(f"  * contents (PRESERVED)     : {content_cnt_post:>6} rows")

        # Invalidate Redis recommendation cache keys if REDIS_URL is configured
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            try:
                import redis
                r = redis.from_url(redis_url)
                rec_keys = r.keys("recommendations:*")
                if rec_keys:
                    r.delete(*rec_keys)
                    print(f"\nFlushed {len(rec_keys)} Redis recommendation cache keys.")
            except Exception as e:
                print(f"\nNotice: Redis cache flush skipped ({e})")

    print("\nDatabase reset completed safely. Schema and catalog preserved.")


def main():
    parser = argparse.ArgumentParser(
        description="Safe development/test database reset script for WatchMan."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--runtime-only",
        action="store_true",
        help="Clear users, interactions, ALS, user embeddings, and recommendations. Keep contents and content embeddings.",
    )
    group.add_argument(
        "--full-ml-reset",
        action="store_true",
        help="Clear all runtime/user data AND content embeddings. Keep TMDB contents catalog and metadata.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Display affected tables and row counts without deleting data.",
    )

    args = parser.parse_args()
    mode = "--runtime-only" if args.runtime_only else "--full-ml-reset"
    reset_database(mode=mode, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
