#!/usr/bin/env python3
"""
Verification command and status report for WatchMan database & ML flow.

Displays live row counts and diagnostics for:
  - contents
  - content_embeddings (total coverage, popular embedded, interacted embedded)
  - users & user_embeddings
  - watch_history, saved_content, ratings, reviews
  - interaction_events, watchman_decisions
  - als_user_factors & als_item_factors
  - recommendations
  - Embedding policy configuration
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, text

# Add backend directory to sys.path so app modules import cleanly
root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings

REPORT_TABLES = [
    ("contents", "Catalog Content Items (Movies & TV Series)"),
    ("content_embeddings", "Dense 384-D Content Vectors"),
    ("users", "Registered Real Users"),
    ("user_embeddings", "Dense 384-D User Taste Vectors"),
    ("watch_history", "Playback & Progress Records"),
    ("saved_content", "Watchlist & Favorites"),
    ("ratings", "User Star Ratings"),
    ("reviews", "User Reviews"),
    ("interaction_events", "Behavioral Telemetry Events"),
    ("watchman_decisions", "WatchMan User Decisions (Must Watch/Time Pass/Skip)"),
    ("als_user_factors", "Collaborative Filtering User Latent Factors"),
    ("als_item_factors", "Collaborative Filtering Item Latent Factors"),
    ("recommendations", "Persisted Ranked Recommendations"),
]


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url and url.strip():
        return url.strip()

    for candidate in [root_dir / ".env", root_dir / "backend" / ".env"]:
        if candidate.exists():
            values = dotenv_values(candidate)
            if "DATABASE_URL" in values and values["DATABASE_URL"]:
                return values["DATABASE_URL"].strip()

    return settings.DATABASE_URL


def generate_report() -> dict[str, int]:
    raw_url = get_database_url()
    db_url = raw_url
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine = create_engine(db_url)
    counts: dict[str, int] = {}

    print("=" * 72)
    print("       WATCHMAN ML & RECOMMENDATION DATA FLOW VERIFICATION REPORT")
    print("=" * 72)
    print(f"Database: {raw_url.split('@')[-1] if '@' in raw_url else 'local/sqlite'}")
    print("-" * 72)
    print(f"{'Table Name':<24} | {'Count':>8} | {'Description'}")
    print("-" * 72)

    with engine.connect() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())

        for tbl, desc in REPORT_TABLES:
            if tbl in existing_tables:
                cnt = conn.execute(text(f'SELECT COUNT(*) FROM "{tbl}"')).scalar() or 0
                counts[tbl] = int(cnt)
                status_str = f"{cnt:>8}"
            else:
                counts[tbl] = 0
                status_str = f"{'N/A':>8}"
            print(f"{tbl:<24} | {status_str} | {desc}")

        # Selective embedding metrics
        popular_movie_limit = settings.INITIAL_POPULAR_MOVIE_EMBED_LIMIT
        popular_tv_limit = settings.INITIAL_POPULAR_TV_EMBED_LIMIT
        popular_target = popular_movie_limit + popular_tv_limit

        # Query embedded popular movies
        embedded_pop_movies = 0
        if "contents" in existing_tables and "content_embeddings" in existing_tables:
            query_pop_movies = text(
                """
                WITH top_movies AS (
                    SELECT id FROM contents
                    WHERE content_type = 'movie'
                    ORDER BY popularity DESC NULLS LAST, id ASC
                    LIMIT :limit
                )
                SELECT COUNT(*)
                FROM top_movies tm
                JOIN content_embeddings ce ON tm.id = ce.content_id
                WHERE ce.embedding IS NOT NULL
                """
            )
            embedded_pop_movies = int(
                conn.execute(query_pop_movies, {"limit": popular_movie_limit}).scalar() or 0
            )

            query_pop_tv = text(
                """
                WITH top_tv AS (
                    SELECT id FROM contents
                    WHERE content_type = 'tv'
                    ORDER BY popularity DESC NULLS LAST, id ASC
                    LIMIT :limit
                )
                SELECT COUNT(*)
                FROM top_tv tt
                JOIN content_embeddings ce ON tt.id = ce.content_id
                WHERE ce.embedding IS NOT NULL
                """
            )
            embedded_pop_tv = int(
                conn.execute(query_pop_tv, {"limit": popular_tv_limit}).scalar() or 0
            )
            popular_embedded_count = embedded_pop_movies + embedded_pop_tv

            # Interaction-driven embedded count:
            # Real distinct content referenced by user interactions
            interacted_subqueries = []
            if "watch_history" in existing_tables:
                interacted_subqueries.append("SELECT content_id FROM watch_history WHERE content_id IS NOT NULL")
            if "saved_content" in existing_tables:
                interacted_subqueries.append("SELECT content_id FROM saved_content WHERE content_id IS NOT NULL")
            if "ratings" in existing_tables:
                interacted_subqueries.append("SELECT content_id FROM ratings WHERE content_id IS NOT NULL")
            if "reviews" in existing_tables:
                interacted_subqueries.append("SELECT content_id FROM reviews WHERE content_id IS NOT NULL")
            if "interaction_events" in existing_tables:
                interacted_subqueries.append("SELECT content_id FROM interaction_events WHERE content_id IS NOT NULL")
            if "watchman_decisions" in existing_tables:
                interacted_subqueries.append("SELECT content_id FROM watchman_decisions WHERE content_id IS NOT NULL")

            if interacted_subqueries:
                union_sql = " UNION ".join(interacted_subqueries)
                query_interacted = text(
                    f"""
                    WITH distinct_interacted AS (
                        {union_sql}
                    )
                    SELECT
                        COUNT(di.content_id) AS total_interacted,
                        COUNT(ce.content_id) AS embedded_interacted
                    FROM distinct_interacted di
                    LEFT JOIN content_embeddings ce ON di.content_id = ce.content_id AND ce.embedding IS NOT NULL
                    """
                )
                row = conn.execute(query_interacted).first()
                total_interacted = int(row[0] or 0) if row else 0
                embedded_interacted = int(row[1] or 0) if row else 0
            else:
                total_interacted = 0
                embedded_interacted = 0
        else:
            popular_embedded_count = 0
            embedded_pop_movies = 0
            embedded_pop_tv = 0
            total_interacted = 0
            embedded_interacted = 0

    print("=" * 72)

    # Health / State diagnostics
    print("\nML & Recommendation Diagnostics:")
    content_cnt = counts.get("contents", 0)
    emb_cnt = counts.get("content_embeddings", 0)
    user_cnt = counts.get("users", 0)
    user_emb_cnt = counts.get("user_embeddings", 0)
    als_user_cnt = counts.get("als_user_factors", 0)
    als_item_cnt = counts.get("als_item_factors", 0)
    rec_cnt = counts.get("recommendations", 0)

    if content_cnt > 0:
        emb_pct = (emb_cnt / content_cnt) * 100.0
        print(f"  * Content Embedding Coverage : {emb_pct:.1f}% ({emb_cnt}/{content_cnt})")
    else:
        print("  * Content Catalog             : Empty (catalog sync required)")

    print(
        f"  * Popular Content Embedded   : {popular_embedded_count}/{popular_target} "
        f"({embedded_pop_movies}/{popular_movie_limit} movies, {embedded_pop_tv}/{popular_tv_limit} TV)"
    )
    if total_interacted > 0:
        pct_int = (embedded_interacted / total_interacted) * 100.0
        print(f"  * Interacted Content Embedded: {embedded_interacted}/{total_interacted} ({pct_int:.1f}%)")
    else:
        print(f"  * Interacted Content Embedded: 0/0 (No user interaction history)")

    if user_cnt == 0:
        print("  * User State                  : Zero users (fresh/reset state)")
    else:
        print(f"  * Active Users with Embeddings: {user_emb_cnt}/{user_cnt}")

    if als_user_cnt > 0 and als_item_cnt > 0:
        print(f"  * ALS Collaborative Model    : Active ({als_user_cnt} user factors, {als_item_cnt} item factors)")
    else:
        print("  * ALS Collaborative Model    : Inactive/Skipped (insufficient users/interactions)")

    print(f"  * Persisted Recommendations   : {rec_cnt} active recommendations across all users")

    print("\nEmbedding Policy:")
    print(f"  * Initial Popular Target     : {popular_target} ({popular_movie_limit} movies, {popular_tv_limit} TV)")
    print(f"  * Interaction-Driven Embed   : {'enabled' if settings.ENABLE_INTERACTION_EMBEDDING else 'disabled'}")
    print(f"  * Search-Driven Embed        : {'enabled' if settings.ENABLE_SEARCH_EMBEDDING else 'disabled'}")
    print("=" * 72)

    return counts


if __name__ == "__main__":
    generate_report()
