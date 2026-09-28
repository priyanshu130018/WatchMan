"""Partitioned TMDB catalogue importer for large-scale movie and TV ingestion.

Provides:
- DatePartition with recursive midpoint subdivision when total_pages > 500.
- Async rate limiting and bounded concurrency.
- Exponential backoff retry on transient TMDB failures (429, 5xx, connection resets).
- Resumable checkpointing via CheckpointManager.
- Dialect-aware bulk upsert (PostgreSQL xmax=0 / SQLite fallback) for contents,
  genres, and languages without duplicating records.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import json
import logging
import os
import random
from typing import Any, Callable

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.exceptions import (
    TMDBException,
    TMDBRateLimitedException,
    TMDBTimeoutException,
    TMDBUnavailableException,
)
from app.db.session import SessionLocal
from app.models.content import ContentType
from app.services.tmdb.service import TMDBService

logger = logging.getLogger(__name__)

# TMDB hard cap for /3/discover endpoints: page > 500 returns HTTP 400.
TMDB_MAX_DISCOVER_PAGE = 500


@dataclass(frozen=True)
class DatePartition:
    """A bounded date slice for TMDB Discover queries."""

    content_type: str  # "movie" or "tv"
    start_date: str    # "YYYY-MM-DD"
    end_date: str      # "YYYY-MM-DD"
    label: str = ""

    @property
    def partition_id(self) -> str:
        return f"{self.content_type}:{self.start_date}:{self.end_date}"

    def can_subdivide(self) -> bool:
        """True if the date range covers at least 2 distinct days."""
        d_start = datetime.strptime(self.start_date, "%Y-%m-%d").date()
        d_end = datetime.strptime(self.end_date, "%Y-%m-%d").date()
        return d_start < d_end

    def subdivide(self) -> tuple[DatePartition, DatePartition]:
        """Bisects the partition into two equal or near-equal halves."""
        d_start = datetime.strptime(self.start_date, "%Y-%m-%d").date()
        d_end = datetime.strptime(self.end_date, "%Y-%m-%d").date()
        if d_start >= d_end:
            raise ValueError(f"Cannot subdivide single-day partition: {self.partition_id}")

        delta_days = (d_end - d_start).days
        mid_offset = delta_days // 2
        d_mid = d_start + timedelta(days=mid_offset)
        d_mid_next = d_mid + timedelta(days=1)

        left = DatePartition(
            content_type=self.content_type,
            start_date=d_start.strftime("%Y-%m-%d"),
            end_date=d_mid.strftime("%Y-%m-%d"),
            label=f"{self.label or self.partition_id} [pt1]",
        )
        right = DatePartition(
            content_type=self.content_type,
            start_date=d_mid_next.strftime("%Y-%m-%d"),
            end_date=d_end.strftime("%Y-%m-%d"),
            label=f"{self.label or self.partition_id} [pt2]",
        )
        return left, right


def get_initial_movie_partitions() -> list[DatePartition]:
    """Generates standard chronological partitions covering TMDB movie history."""
    definitions = [
        ("1890-01-01", "1949-12-31", "Pre-1950 Movies"),
        ("1950-01-01", "1959-12-31", "1950s Movies"),
        ("1960-01-01", "1969-12-31", "1960s Movies"),
        ("1970-01-01", "1979-12-31", "1970s Movies"),
        ("1980-01-01", "1989-12-31", "1980s Movies"),
        ("1990-01-01", "1999-12-31", "1990s Movies"),
        ("2000-01-01", "2004-12-31", "2000-2004 Movies"),
        ("2005-01-01", "2009-12-31", "2005-2009 Movies"),
        ("2010-01-01", "2014-12-31", "2010-2014 Movies"),
        ("2015-01-01", "2019-12-31", "2015-2019 Movies"),
        ("2020-01-01", "2020-12-31", "2020 Movies"),
        ("2021-01-01", "2021-12-31", "2021 Movies"),
        ("2022-01-01", "2022-12-31", "2022 Movies"),
        ("2023-01-01", "2023-12-31", "2023 Movies"),
        ("2024-01-01", "2024-12-31", "2024 Movies"),
        ("2025-01-01", "2025-12-31", "2025 Movies"),
        ("2026-01-01", "2026-12-31", "2026 Movies"),
        ("2027-01-01", "2028-12-31", "Upcoming Movies 2027-2028"),
    ]
    return [
        DatePartition(content_type=ContentType.MOVIE.value, start_date=s, end_date=e, label=lbl)
        for s, e, lbl in definitions
    ]


def get_initial_tv_partitions() -> list[DatePartition]:
    """Generates standard chronological partitions covering TMDB TV series history."""
    definitions = [
        ("1950-01-01", "1969-12-31", "Classic TV (Pre-1970)"),
        ("1970-01-01", "1979-12-31", "1970s TV"),
        ("1980-01-01", "1989-12-31", "1980s TV"),
        ("1990-01-01", "1999-12-31", "1990s TV"),
        ("2000-01-01", "2009-12-31", "2000s TV"),
        ("2010-01-01", "2014-12-31", "2010-2014 TV"),
        ("2015-01-01", "2019-12-31", "2015-2019 TV"),
        ("2020-01-01", "2020-12-31", "2020 TV"),
        ("2021-01-01", "2021-12-31", "2021 TV"),
        ("2022-01-01", "2022-12-31", "2022 TV"),
        ("2023-01-01", "2023-12-31", "2023 TV"),
        ("2024-01-01", "2024-12-31", "2024 TV"),
        ("2025-01-01", "2025-12-31", "2025 TV"),
        ("2026-01-01", "2026-12-31", "2026 TV"),
        ("2027-01-01", "2028-12-31", "Upcoming TV 2027-2028"),
    ]
    return [
        DatePartition(content_type=ContentType.TV.value, start_date=s, end_date=e, label=lbl)
        for s, e, lbl in definitions
    ]


class AsyncRateLimiter:
    """Async token bucket / leaky bucket rate limiter to adhere to TMDB limits."""

    def __init__(self, requests_per_second: float = 4.0):
        self.requests_per_second = requests_per_second
        self.interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def acquire(self) -> None:
        if self.interval <= 0:
            return
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            elapsed = now - self._last_call
            wait = self.interval - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = loop.time()


class CheckpointManager:
    """Tracks ingestion progress across partitions and pages in a persistent JSON file."""

    def __init__(self, filepath: str = ".ingest_checkpoint.json"):
        self.filepath = filepath
        self._lock = asyncio.Lock()
        self.data: dict[str, Any] = {
            "completed_partitions": [],
            "partition_progress": {},  # partition_id -> last_completed_page
            "stats": {
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "partitions_completed": 0,
            },
        }
        self.load()

    def load(self) -> None:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self.data["completed_partitions"] = loaded.get("completed_partitions", [])
                        self.data["partition_progress"] = loaded.get("partition_progress", {})
                        self.data["stats"] = loaded.get("stats", self.data["stats"])
            except Exception as e:
                logger.warning("Could not read checkpoint file %s: %s", self.filepath, e)

    def save(self) -> None:
        try:
            tmp_path = f"{self.filepath}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp_path, self.filepath)
        except Exception as e:
            logger.warning("Could not write checkpoint file %s: %s", self.filepath, e)

    def is_partition_done(self, partition_id: str) -> bool:
        return partition_id in self.data["completed_partitions"]

    def get_last_page(self, partition_id: str) -> int:
        return self.data["partition_progress"].get(partition_id, 0)

    async def record_progress(
        self,
        partition_id: str,
        page: int,
        inserted: int = 0,
        updated: int = 0,
        skipped: int = 0,
    ) -> None:
        async with self._lock:
            self.data["partition_progress"][partition_id] = page
            self.data["stats"]["inserted"] += inserted
            self.data["stats"]["updated"] += updated
            self.data["stats"]["skipped"] += skipped
            self.save()

    async def mark_partition_done(self, partition_id: str) -> None:
        async with self._lock:
            if partition_id not in self.data["completed_partitions"]:
                self.data["completed_partitions"].append(partition_id)
                self.data["stats"]["partitions_completed"] = len(self.data["completed_partitions"])
            self.save()

    def get_stats(self) -> dict[str, int]:
        return dict(self.data["stats"])


@dataclass
class BatchStats:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0


@dataclass
class PlannedPartition:
    partition: DatePartition
    total_results: int
    total_pages: int
    initial_results: list[dict[str, Any]] = field(default_factory=list)


def build_discover_params(partition: DatePartition, page: int = 1) -> tuple[str, dict[str, Any]]:
    """Builds the TMDB discover endpoint and query parameters for a date partition."""
    is_movie = partition.content_type == ContentType.MOVIE.value
    endpoint = "discover/movie" if is_movie else "discover/tv"
    date_gte_key = "primary_release_date.gte" if is_movie else "first_air_date.gte"
    date_lte_key = "primary_release_date.lte" if is_movie else "first_air_date.lte"

    params = {
        date_gte_key: partition.start_date,
        date_lte_key: partition.end_date,
        "sort_by": "popularity.desc",
        "include_adult": "false",
        "page": page,
    }
    return endpoint, params


async def fetch_page_with_retry(
    tmdb_service: TMDBService,
    endpoint: str,
    params: dict[str, Any],
    rate_limiter: AsyncRateLimiter,
    max_retries: int = 5,
    base_delay: float = 1.0,
) -> dict[str, Any]:
    """Fetches a TMDB endpoint with rate limiting and exponential backoff retry."""
    for attempt in range(1, max_retries + 1):
        await rate_limiter.acquire()
        try:
            return await tmdb_service._request(endpoint, params, use_cache=False)
        except (
            TMDBRateLimitedException,
            TMDBUnavailableException,
            TMDBTimeoutException,
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.HTTPError,
        ) as e:
            if attempt == max_retries:
                logger.error(
                    "Request failed to %s with %s after %d attempts: %s",
                    endpoint,
                    params,
                    attempt,
                    e,
                )
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 0.4)
            logger.warning(
                "Attempt %d/%d failed for %s (%s). Retrying in %.2fs...",
                attempt,
                max_retries,
                endpoint,
                e,
                delay,
            )
            await asyncio.sleep(delay)
    raise TMDBUnavailableException("Exhausted retries.")


async def plan_partition(
    partition: DatePartition,
    tmdb_service: TMDBService,
    rate_limiter: AsyncRateLimiter,
    max_depth: int = 8,
) -> list[PlannedPartition]:
    """Recursively checks and subdivides a partition if TMDB total_pages > 500.

    TMDB hard-caps Discover endpoints at 500 pages (page 501 returns HTTP 400).
    When total_pages > 500 and the date range can be divided, it splits recursively
    into smaller date ranges until each leaf partition has <= 500 pages.
    """
    endpoint, params = build_discover_params(partition, page=1)
    data = await fetch_page_with_retry(tmdb_service, endpoint, params, rate_limiter)
    total_pages = int(data.get("total_pages", 1) or 1)
    total_results = int(data.get("total_results", 0) or 0)
    page_1_results = data.get("results") or []

    if total_pages > TMDB_MAX_DISCOVER_PAGE and partition.can_subdivide() and max_depth > 0:
        left, right = partition.subdivide()
        planned_left = await plan_partition(left, tmdb_service, rate_limiter, max_depth - 1)
        planned_right = await plan_partition(right, tmdb_service, rate_limiter, max_depth - 1)
        return planned_left + planned_right
    else:
        capped_pages = min(total_pages, TMDB_MAX_DISCOVER_PAGE)
        return [
            PlannedPartition(
                partition=partition,
                total_results=total_results,
                total_pages=capped_pages,
                initial_results=page_1_results,
            )
        ]


def sync_taxonomy_genres(db: Session, tmdb_genres: list[dict[str, Any]]) -> dict[int, int]:
    """Ensures all TMDB genres exist in the genres table. Returns tmdb_id -> internal id map."""
    rows = db.execute(text("SELECT id, tmdb_id FROM genres")).fetchall()
    genre_map = {row[1]: row[0] for row in rows}

    for g in tmdb_genres:
        tid = g.get("id")
        name = g.get("name")
        if not tid or not name:
            continue
        if tid not in genre_map:
            # Check by name first to honor unique constraint on name
            res = db.execute(
                text("SELECT id FROM genres WHERE name = :name"),
                {"name": name},
            ).fetchone()
            if res:
                genre_map[tid] = res[0]
            else:
                try:
                    new_row = db.execute(
                        text("INSERT INTO genres (tmdb_id, name) VALUES (:tid, :name) RETURNING id"),
                        {"tid": tid, "name": name},
                    ).fetchone()
                    if new_row:
                        genre_map[tid] = new_row[0]
                except Exception:
                    db.rollback()
                    # Re-query in case of race condition
                    res = db.execute(
                        text("SELECT id FROM genres WHERE tmdb_id = :tid"),
                        {"tid": tid},
                    ).fetchone()
                    if res:
                        genre_map[tid] = res[0]
    db.commit()
    return genre_map


def ensure_genre(db: Session, genre_map: dict[int, int], tmdb_genre_id: int) -> int | None:
    """Gets internal genre ID for a tmdb_genre_id, inserting placeholder if unseen."""
    if tmdb_genre_id in genre_map:
        return genre_map[tmdb_genre_id]

    row = db.execute(
        text("SELECT id FROM genres WHERE tmdb_id = :tid"),
        {"tid": tmdb_genre_id},
    ).fetchone()
    if row:
        genre_map[tmdb_genre_id] = row[0]
        return row[0]

    placeholder_name = f"Genre {tmdb_genre_id}"
    try:
        new_row = db.execute(
            text("INSERT INTO genres (tmdb_id, name) VALUES (:tid, :name) RETURNING id"),
            {"tid": tmdb_genre_id, "name": placeholder_name},
        ).fetchone()
        db.commit()
        if new_row:
            genre_map[tmdb_genre_id] = new_row[0]
            return new_row[0]
    except Exception:
        db.rollback()
        row = db.execute(
            text("SELECT id FROM genres WHERE tmdb_id = :tid"),
            {"tid": tmdb_genre_id},
        ).fetchone()
        if row:
            genre_map[tmdb_genre_id] = row[0]
            return row[0]
    return None


def ensure_sequences_healthy(db: Session) -> None:
    """Guarantees PostgreSQL sequence counters match or exceed max(id) across core tables."""
    if db.bind and getattr(db.bind.dialect, "name", "") == "postgresql":
        for tbl in ["contents", "genres", "content_genres", "content_languages"]:
            try:
                seq = db.execute(
                    text("SELECT pg_get_serial_sequence(:tbl, 'id')"), {"tbl": tbl}
                ).scalar()
                if seq:
                    max_id = db.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {tbl}")).scalar()
                    new_val = max(max_id, 1) + 1
                    db.execute(
                        text("SELECT setval(:seq, :val, false)"),
                        {"seq": seq, "val": new_val},
                    )
                    db.commit()
            except Exception:
                db.rollback()


def bulk_upsert_items(
    db: Session,
    items: list[dict[str, Any]],
    content_type: str,
    genre_map: dict[int, int],
) -> BatchStats:
    """Bulk upserts a list of raw TMDB items into contents, languages, and genres.

    Uses PostgreSQL's native (xmax = 0) AS is_inserted when running on PostgreSQL,
    and falls back to pre-querying existing tmdb_ids in SQLite/test environments.
    """
    if not items:
        return BatchStats()

    stats = BatchStats()

    # 1. Upsert languages dynamically
    lang_codes = {
        item.get("original_language")
        for item in items
        if item.get("original_language") and len(item.get("original_language", "")) <= 10
    }
    for code in lang_codes:
        db.execute(
            text(
                """
                INSERT INTO languages (code, name, english_name)
                VALUES (:code, :name, :name)
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {"code": code, "name": code},
        )

    # 2. Prepare content rows
    content_params = []
    seen_ids = set()
    for item in items:
        tmdb_id = item.get("id")
        if not tmdb_id or tmdb_id in seen_ids:
            continue
        seen_ids.add(tmdb_id)

        title = item.get("title") or item.get("name") or "Untitled"
        original_title = item.get("original_title") or item.get("original_name")
        overview = item.get("overview")
        release_date = item.get("release_date") or item.get("first_air_date") or None
        poster_path = item.get("poster_path")
        backdrop_path = item.get("backdrop_path")
        original_language = item.get("original_language")
        popularity = float(item.get("popularity") or 0.0)
        vote_average = float(item.get("vote_average") or 0.0)
        vote_count = int(item.get("vote_count") or 0)
        adult = bool(item.get("adult", False))

        content_params.append(
            {
                "content_type": content_type,
                "tmdb_id": tmdb_id,
                "title": title[:500],
                "original_title": original_title[:500] if original_title else None,
                "overview": overview,
                "release_date": release_date[:50] if release_date else None,
                "poster_path": poster_path[:500] if poster_path else None,
                "backdrop_path": backdrop_path[:500] if backdrop_path else None,
                "original_language": original_language[:20] if original_language else None,
                "popularity": popularity,
                "vote_average": vote_average,
                "vote_count": vote_count,
                "adult": adult,
            }
        )

    if not content_params:
        return stats

    dialect_name = db.bind.dialect.name if db.bind else ""
    is_postgres = dialect_name == "postgresql"

    id_map: dict[int, int] = {}

    if is_postgres:
        values_clauses = []
        bound_params = {}
        for idx, p in enumerate(content_params):
            pfx = f"p{idx}_"
            values_clauses.append(
                f"(:{pfx}ct, :{pfx}tid, :{pfx}t, :{pfx}ot, :{pfx}o, :{pfx}rd, "
                f":{pfx}pp, :{pfx}bp, :{pfx}ol, :{pfx}pop, :{pfx}va, :{pfx}vc, :{pfx}ad, NOW(), NOW())"
            )
            bound_params[f"{pfx}ct"] = p["content_type"]
            bound_params[f"{pfx}tid"] = p["tmdb_id"]
            bound_params[f"{pfx}t"] = p["title"]
            bound_params[f"{pfx}ot"] = p["original_title"]
            bound_params[f"{pfx}o"] = p["overview"]
            bound_params[f"{pfx}rd"] = p["release_date"]
            bound_params[f"{pfx}pp"] = p["poster_path"]
            bound_params[f"{pfx}bp"] = p["backdrop_path"]
            bound_params[f"{pfx}ol"] = p["original_language"]
            bound_params[f"{pfx}pop"] = p["popularity"]
            bound_params[f"{pfx}va"] = p["vote_average"]
            bound_params[f"{pfx}vc"] = p["vote_count"]
            bound_params[f"{pfx}ad"] = p["adult"]

        upsert_sql = text(
            f"""
            INSERT INTO contents (
                content_type, tmdb_id, title, original_title, overview, release_date,
                poster_path, backdrop_path, original_language, popularity, vote_average,
                vote_count, adult, created_at, updated_at
            ) VALUES {', '.join(values_clauses)}
            ON CONFLICT (content_type, tmdb_id) DO UPDATE SET
                title = EXCLUDED.title,
                original_title = EXCLUDED.original_title,
                overview = EXCLUDED.overview,
                release_date = EXCLUDED.release_date,
                poster_path = EXCLUDED.poster_path,
                backdrop_path = EXCLUDED.backdrop_path,
                original_language = EXCLUDED.original_language,
                popularity = EXCLUDED.popularity,
                vote_average = EXCLUDED.vote_average,
                vote_count = EXCLUDED.vote_count,
                adult = EXCLUDED.adult,
                updated_at = NOW()
            RETURNING id, tmdb_id, (xmax = 0) AS is_inserted;
            """
        )
        rows = db.execute(upsert_sql, bound_params).fetchall()
        for row in rows:
            cid, tid, is_ins = row[0], row[1], row[2]
            id_map[tid] = cid
            if is_ins:
                stats.inserted += 1
            else:
                stats.updated += 1
    else:
        # SQLite / standard SQL fallback for unit tests
        batch_tmdb_ids = [p["tmdb_id"] for p in content_params]
        existing_rows = db.execute(
            text(
                f"SELECT tmdb_id FROM contents WHERE content_type = :ct AND tmdb_id IN ({','.join(str(i) for i in batch_tmdb_ids)})"
            ),
            {"ct": content_type},
        ).fetchall()
        existing_ids = {r[0] for r in existing_rows}

        upsert_sqlite = text(
            """
            INSERT INTO contents (
                content_type, tmdb_id, title, original_title, overview, release_date,
                poster_path, backdrop_path, original_language, popularity, vote_average,
                vote_count, adult, created_at, updated_at
            ) VALUES (
                :content_type, :tmdb_id, :title, :original_title, :overview, :release_date,
                :poster_path, :backdrop_path, :original_language, :popularity, :vote_average,
                :vote_count, :adult, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (content_type, tmdb_id) DO UPDATE SET
                title = excluded.title,
                original_title = excluded.original_title,
                overview = excluded.overview,
                release_date = excluded.release_date,
                poster_path = excluded.poster_path,
                backdrop_path = excluded.backdrop_path,
                original_language = excluded.original_language,
                popularity = excluded.popularity,
                vote_average = excluded.vote_average,
                vote_count = excluded.vote_count,
                adult = excluded.adult,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id, tmdb_id;
            """
        )
        for param in content_params:
            row = db.execute(upsert_sqlite, param).fetchone()
            if row:
                cid, tid = row[0], row[1]
                id_map[tid] = cid
                if tid in existing_ids:
                    stats.updated += 1
                else:
                    stats.inserted += 1

    # 3. Associate content_genres and content_languages using batched inserts
    cg_pairs = set()
    cl_pairs = set()
    for item in items:
        tmdb_id = item.get("id")
        content_id = id_map.get(tmdb_id)
        if not content_id:
            continue

        for gid in item.get("genre_ids") or []:
            internal_gid = ensure_genre(db, genre_map, gid)
            if internal_gid:
                cg_pairs.add((content_id, internal_gid))

        orig_lang = item.get("original_language")
        if orig_lang and len(orig_lang) <= 10:
            cl_pairs.add((content_id, orig_lang))

    if cg_pairs:
        cg_values = []
        cg_params = {}
        for idx, (cid, gid) in enumerate(cg_pairs):
            cg_values.append(f"(:cid_{idx}, :gid_{idx})")
            cg_params[f"cid_{idx}"] = cid
            cg_params[f"gid_{idx}"] = gid
        db.execute(
            text(
                f"INSERT INTO content_genres (content_id, genre_id) VALUES {', '.join(cg_values)} ON CONFLICT (content_id, genre_id) DO NOTHING"
            ),
            cg_params,
        )

    if cl_pairs:
        cl_values = []
        cl_params = {}
        for idx, (cid, code) in enumerate(cl_pairs):
            cl_values.append(f"(:cid_{idx}, :code_{idx})")
            cl_params[f"cid_{idx}"] = cid
            cl_params[f"code_{idx}"] = code
        db.execute(
            text(
                f"INSERT INTO content_languages (content_id, language_code) VALUES {', '.join(cl_values)} ON CONFLICT (content_id, language_code) DO NOTHING"
            ),
            cl_params,
        )

    db.commit()
    return stats


class TMDBImporter:
    """Orchestrates partitioned ingestion from TMDB Discover into the database."""

    def __init__(
        self,
        db_factory: Callable[[], Session] = SessionLocal,
        tmdb_service: TMDBService | None = None,
        rate_limit_rps: float = 4.0,
        concurrency: int = 4,
        checkpoint_file: str = ".ingest_checkpoint.json",
        max_pages_per_partition: int | None = None,
        batch_size: int = 200,
        progress_callback: Callable[[str], None] | None = None,
    ):
        self.db_factory = db_factory
        self.tmdb = tmdb_service or TMDBService()
        self.rate_limiter = AsyncRateLimiter(rate_limit_rps)
        self.concurrency = concurrency
        self.checkpoint = CheckpointManager(checkpoint_file)
        self.max_pages_per_partition = max_pages_per_partition
        self.batch_size = batch_size
        self.progress_callback = progress_callback or (lambda msg: None)

    def log(self, message: str) -> None:
        logger.info(message)
        self.progress_callback(message)

    async def sync_genres(self) -> dict[int, int]:
        """Fetches movie and TV genre taxonomies from TMDB and updates genres table."""
        self.log("Syncing TMDB genre taxonomies...")
        movie_genres_data = await fetch_page_with_retry(
            self.tmdb, "genre/movie/list", {}, self.rate_limiter
        )
        tv_genres_data = await fetch_page_with_retry(
            self.tmdb, "genre/tv/list", {}, self.rate_limiter
        )
        all_tmdb_genres = (movie_genres_data.get("genres") or []) + (tv_genres_data.get("genres") or [])

        with self.db_factory() as db:
            ensure_sequences_healthy(db)
            genre_map = sync_taxonomy_genres(db, all_tmdb_genres)
        self.log(f"Taxonomy synced: {len(genre_map)} genres available.")
        return genre_map

    async def estimate_partitions(
        self,
        partitions: list[DatePartition],
        use_cache: bool = True,
        cache_path: str = ".planned_partitions_cache.json",
    ) -> list[PlannedPartition]:
        """Plans all partitions by querying page 1 and subdividing if total_pages > 500."""
        if use_cache and os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    all_planned = [
                        PlannedPartition(
                            partition=DatePartition(
                                content_type=p["type"],
                                start_date=p["start"],
                                end_date=p["end"],
                                label=p["label"],
                            ),
                            total_results=p["total_results"],
                            total_pages=p["total_pages"],
                        )
                        for p in cached
                    ]
                    # Verify partition types match requested partitions
                    req_types = {p.content_type for p in partitions}
                    cached_types = {p.partition.content_type for p in all_planned}
                    if req_types == cached_types:
                        self.log(f"Loaded {len(all_planned)} pre-planned leaf partitions from cache.")
                        return all_planned
            except Exception as e:
                logger.warning("Could not load planned partitions cache: %s", e)

        self.log(f"Planning and estimating {len(partitions)} date partitions...")
        all_planned: list[PlannedPartition] = []
        for p in partitions:
            planned = await plan_partition(p, self.tmdb, self.rate_limiter)
            all_planned.extend(planned)

        if use_cache:
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(
                        [
                            {
                                "type": p.partition.content_type,
                                "start": p.partition.start_date,
                                "end": p.partition.end_date,
                                "label": p.partition.label,
                                "total_results": p.total_results,
                                "total_pages": p.total_pages,
                            }
                            for p in all_planned
                        ],
                        f,
                        indent=2,
                    )
            except Exception as e:
                logger.warning("Could not write planned partitions cache: %s", e)

        return all_planned

    async def ingest_partition(
        self,
        planned: PlannedPartition,
        genre_map: dict[int, int],
        resume: bool = True,
    ) -> BatchStats:
        """Ingests all pages of a planned partition with checkpointing and batching."""
        partition = planned.partition
        pid = partition.partition_id

        if resume and self.checkpoint.is_partition_done(pid):
            self.log(f"Skipping already completed partition: {partition.label} ({pid})")
            return BatchStats()

        start_page = 1
        if resume:
            last_page = self.checkpoint.get_last_page(pid)
            if last_page > 0:
                start_page = last_page + 1

        target_pages = planned.total_pages
        if self.max_pages_per_partition is not None:
            target_pages = min(target_pages, self.max_pages_per_partition)

        if start_page > target_pages:
            await self.checkpoint.mark_partition_done(pid)
            return BatchStats()

        self.log(
            f"--> Ingesting partition: {partition.label} ({partition.start_date} to {partition.end_date}) "
            f"[Pages {start_page}..{target_pages}, Total TMDB items: {planned.total_results}]"
        )

        total_stats = BatchStats()
        semaphore = asyncio.Semaphore(self.concurrency)
        endpoint, base_params = build_discover_params(partition)

        page_buffer: list[dict[str, Any]] = []

        # If page 1 was already fetched during planning, use it directly if starting at page 1
        if start_page == 1 and planned.initial_results:
            page_buffer.extend(planned.initial_results)
            start_page = 2

        async def fetch_one_page(page_num: int) -> tuple[int, list[dict[str, Any]]]:
            async with semaphore:
                p_params = dict(base_params)
                p_params["page"] = page_num
                data = await fetch_page_with_retry(
                    self.tmdb, endpoint, p_params, self.rate_limiter
                )
                return page_num, data.get("results") or []

        pages_to_fetch = list(range(start_page, target_pages + 1))
        chunk_size = self.concurrency * 2

        for i in range(0, len(pages_to_fetch), chunk_size):
            chunk = pages_to_fetch[i : i + chunk_size]
            tasks = [fetch_one_page(p) for p in chunk]
            results = await asyncio.gather(*tasks)

            # Sort by page to preserve deterministic progress
            results.sort(key=lambda r: r[0])
            last_fetched = chunk[-1]

            for _, items in results:
                page_buffer.extend(items)

            if len(page_buffer) >= self.batch_size or i + chunk_size >= len(pages_to_fetch):
                with self.db_factory() as db:
                    b_stats = bulk_upsert_items(
                        db, page_buffer, partition.content_type, genre_map
                    )
                total_stats.inserted += b_stats.inserted
                total_stats.updated += b_stats.updated
                total_stats.skipped += b_stats.skipped

                await self.checkpoint.record_progress(
                    pid,
                    last_fetched,
                    inserted=b_stats.inserted,
                    updated=b_stats.updated,
                    skipped=b_stats.skipped,
                )
                page_buffer.clear()

        # Flush any remaining items
        if page_buffer:
            with self.db_factory() as db:
                b_stats = bulk_upsert_items(
                    db, page_buffer, partition.content_type, genre_map
                )
            total_stats.inserted += b_stats.inserted
            total_stats.updated += b_stats.updated
            total_stats.skipped += b_stats.skipped
            await self.checkpoint.record_progress(
                pid,
                target_pages,
                inserted=b_stats.inserted,
                updated=b_stats.updated,
                skipped=b_stats.skipped,
            )
            page_buffer.clear()

        await self.checkpoint.mark_partition_done(pid)
        self.log(
            f"[DONE] Partition complete: {partition.label} "
            f"(+{total_stats.inserted} new, {total_stats.updated} updated)"
        )
        return total_stats

    async def run(
        self,
        partitions: list[DatePartition],
        resume: bool = True,
        dry_run_estimate: bool = False,
    ) -> dict[str, Any]:
        """Runs the complete ingestion pipeline across given partitions."""
        owns_client = False
        client = getattr(self.tmdb, "_client", None)
        if client is None:
            from app.services.tmdb.service import _build_tmdb_client
            client = _build_tmdb_client()
            self.tmdb._client = client
            owns_client = True

        try:
            genre_map = await self.sync_genres()
            planned_partitions = await self.estimate_partitions(partitions, use_cache=resume)

            total_tmdb_items = sum(p.total_results for p in planned_partitions)
            total_pages = sum(p.total_pages for p in planned_partitions)
            self.log(
                f"\nPartitioning Summary: {len(planned_partitions)} leaf partitions planned. "
                f"Total TMDB estimated records: {total_tmdb_items:,} across {total_pages:,} pages."
            )

            if dry_run_estimate:
                return {
                    "dry_run": True,
                    "partitions_count": len(planned_partitions),
                    "estimated_tmdb_records": total_tmdb_items,
                    "estimated_pages": total_pages,
                    "planned_partitions": [
                        {
                            "label": p.partition.label,
                            "type": p.partition.content_type,
                            "start": p.partition.start_date,
                            "end": p.partition.end_date,
                            "total_results": p.total_results,
                            "total_pages": p.total_pages,
                        }
                        for p in planned_partitions
                    ],
                }

            overall_stats = BatchStats()
            for planned in planned_partitions:
                part_stats = await self.ingest_partition(planned, genre_map, resume=resume)
                overall_stats.inserted += part_stats.inserted
                overall_stats.updated += part_stats.updated
                overall_stats.skipped += part_stats.skipped

            # Final counts in DB
            with self.db_factory() as db:
                total_movies = db.execute(
                    text("SELECT count(*) FROM contents WHERE content_type = 'movie'")
                ).scalar()
                total_tv = db.execute(
                    text("SELECT count(*) FROM contents WHERE content_type = 'tv'")
                ).scalar()

            summary = {
                "dry_run": False,
                "partitions_processed": len(planned_partitions),
                "inserted": overall_stats.inserted,
                "updated": overall_stats.updated,
                "skipped": overall_stats.skipped,
                "db_total_movies": total_movies,
                "db_total_tv": total_tv,
            }
            self.log(
                f"\n=== Ingestion Completed Successfully ===\n"
                f"Inserted: {overall_stats.inserted:,} | Updated: {overall_stats.updated:,}\n"
                f"Database Totals: {total_movies:,} Movies | {total_tv:,} TV Shows\n"
            )
            return summary
        finally:
            if owns_client and client:
                await client.aclose()
                self.tmdb._client = None
