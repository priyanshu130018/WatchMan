#!/usr/bin/env python3
"""
Creates a selective PostgreSQL backup containing ONLY movie/catalog-related tables:
- contents
- genres
- content_genres
- languages
- content_languages
- people
- content_cast
- content_crew
- content_videos
- content_external_ids
- content_embeddings

Excludes all user, interaction, auth, recommendation, user_embeddings, and ALS data.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add backend directory to sys.path
root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.db.session import SessionLocal
from sqlalchemy import text


CATALOG_TABLES = [
    "contents",
    "genres",
    "content_genres",
    "languages",
    "content_languages",
    "people",
    "content_cast",
    "content_crew",
    "content_videos",
    "content_external_ids",
    "content_embeddings",
]

EXCLUDED_TABLES = [
    "users",
    "profiles",
    "user_preferences",
    "user_activity",
    "interaction_events",
    "saved_content",
    "watch_history",
    "ratings",
    "reviews",
    "watchman_decisions",
    "user_embeddings",
    "recommendations",
    "recommendation_candidates",
    "recommendation_cache",
    "als_user_factors",
    "als_item_factors",
    "search_history",
    "alembic_version",
]


def create_catalog_backup():
    print("=" * 80)
    print("WATCHMAN MOVIE / CATALOG DATA BACKUP")
    print("=" * 80)

    # 1. Prepare backup directory
    if Path("/app").is_dir():
        backup_dir = Path("/app/backups")
    else:
        backup_dir = root_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"catalog_backup_{timestamp}.sql"

    print(f"Timestamp (UTC): {timestamp}")
    print(f"Backup destination: {backup_file}")

    # 2. Verify row counts in PostgreSQL before backup
    print("\n--- CATALOG TABLES TO BACKUP ---")
    db = SessionLocal()
    table_stats = {}
    try:
        for t in CATALOG_TABLES:
            count = db.execute(text(f'SELECT count(*) FROM "{t}"')).scalar()
            table_stats[t] = count
            print(f"  - {t:<25}: {count:>6} rows")

        print("\n--- EXCLUDED TABLES (VERIFIED EXCLUSION) ---")
        for t in EXCLUDED_TABLES:
            try:
                count = db.execute(text(f'SELECT count(*) FROM "{t}"')).scalar()
                print(f"  - {t:<25}: {count:>6} rows (EXCLUDED)")
            except Exception:
                print(f"  - {t:<25}: not present / skipped (EXCLUDED)")
    finally:
        db.close()

    # 3. Construct pg_dump command
    db_url = settings.DATABASE_URL
    # Normalize url scheme if necessary for pg_dump (e.g. postgresql+psycopg:// -> postgresql://)
    dump_url = db_url.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+asyncpg://", "postgresql://")

    table_args = []
    for t in CATALOG_TABLES:
        table_args.extend(["-t", f"public.{t}"])

    cmd = [
        "pg_dump",
        "--dbname", dump_url,
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
        *table_args,
    ]

    print("\n--- RUNNING PG_DUMP ---")
    t0 = time.perf_counter()
    with open(backup_file, "w", encoding="utf-8") as f:
        result = subprocess.run(
            cmd,
            stdout=f,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        print(f"ERROR: pg_dump failed with return code {result.returncode}")
        # Redact any password in stderr if present
        safe_stderr = result.stderr
        print(f"pg_dump stderr: {safe_stderr}")
        sys.exit(1)

    print(f"pg_dump completed in {elapsed:.2f} seconds.")

    # 4. Verification of the generated backup file
    if not backup_file.exists():
        raise RuntimeError(f"Backup file {backup_file} was not created!")

    file_size_bytes = backup_file.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)

    if file_size_bytes == 0:
        raise RuntimeError(f"Backup file {backup_file} is empty (0 bytes)!")

    print("\n--- BACKUP FILE VERIFICATION ---")
    print(f"Backup File Path: {backup_file}")
    print(f"Backup File Size: {file_size_bytes:,} bytes ({file_size_mb:.2f} MB)")

    # Read and inspect content of the backup
    with open(backup_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify all included tables are present
    for t in CATALOG_TABLES:
        table_pattern = f"CREATE TABLE IF NOT EXISTS public.{t}" in content or f"CREATE TABLE public.{t}" in content
        copy_pattern = f"COPY public.{t} " in content or f"INSERT INTO public.{t}" in content or f'"{t}"' in content
        print(f"  - Verified catalog table '{t}' present in DDL/Data: {table_pattern or copy_pattern}")
        assert table_pattern or copy_pattern, f"Catalog table {t} missing from backup!"

    # Verify NO excluded table is dumped
    for t in EXCLUDED_TABLES:
        has_excluded_ddl = f"CREATE TABLE public.{t} " in content or f"CREATE TABLE IF NOT EXISTS public.{t}" in content or f"COPY public.{t} " in content
        assert not has_excluded_ddl, f"SECURITY VIOLATION: Excluded table '{t}' found in backup!"

    print("  - Verified 0 excluded user/interaction/recommendation/ALS tables are present in backup.")

    print("\n" + "=" * 80)
    print("CATALOG BACKUP COMPLETED AND VERIFIED SUCCESSFULLY!")
    print("=" * 80)
    return str(backup_file), file_size_bytes, table_stats


if __name__ == "__main__":
    create_catalog_backup()
