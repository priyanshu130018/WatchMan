"""Unit tests for partitioned TMDB catalogue importer.

Tests:
- DatePartition subdivision logic and edge cases.
- Dynamic partition subdivision when total_pages > 500 (TMDB limit).
- AsyncRateLimiter and exponential backoff retry on 429/5xx.
- Resumable checkpoint persistence.
- Safe, idempotent bulk upsert (deduplication, insert vs update counts).
- Large catalogue pagination calculation (10,000 items -> 556 pages of 18; popular capped at 100 items / 6 pages).
"""

from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.constants import CONTENT_PAGE_SIZE, POPULAR_COLLECTION_MAX
from app.core.exceptions import TMDBRateLimitedException, TMDBUnavailableException
from app.models.content import Content, ContentType
from app.services.catalog import ContentCatalogService
from app.services.tmdb.importer import (
    AsyncRateLimiter,
    BatchStats,
    CheckpointManager,
    DatePartition,
    PlannedPartition,
    TMDB_MAX_DISCOVER_PAGE,
    bulk_upsert_items,
    fetch_page_with_retry,
    get_initial_movie_partitions,
    get_initial_tv_partitions,
    plan_partition,
    sync_taxonomy_genres,
)
from app.services.tmdb.service import TMDBService


def test_date_partition_subdivision():
    """Verify DatePartition bisects date spans into contiguous, non-overlapping slices."""
    p = DatePartition("movie", "2020-01-01", "2020-12-31", "2020")
    assert p.can_subdivide() is True

    left, right = p.subdivide()
    assert left.start_date == "2020-01-01"
    assert left.end_date == "2020-07-01"
    assert right.start_date == "2020-07-02"
    assert right.end_date == "2020-12-31"

    # Single-day partition cannot subdivide
    p_single = DatePartition("movie", "2020-05-01", "2020-05-01", "Single Day")
    assert p_single.can_subdivide() is False
    with pytest.raises(ValueError):
        p_single.subdivide()


def test_initial_partitions_coverage():
    """Verify default initial partitions cover historical and upcoming movie/tv eras."""
    movie_parts = get_initial_movie_partitions()
    tv_parts = get_initial_tv_partitions()

    assert len(movie_parts) >= 15
    assert len(tv_parts) >= 12

    # Check movie boundaries
    assert movie_parts[0].start_date == "1890-01-01"
    assert movie_parts[-1].end_date == "2028-12-31"

    # Check tv boundaries
    assert tv_parts[0].start_date == "1950-01-01"
    assert tv_parts[-1].end_date == "2028-12-31"


@pytest.mark.asyncio
async def test_partition_subdivision_when_pages_exceed_500():
    """Verify that when TMDB returns total_pages > 500, plan_partition subdivides recursively."""
    tmdb_mock = MagicMock(spec=TMDBService)
    rate_limiter = AsyncRateLimiter(requests_per_second=0)

    # First call (full 2020): total_pages = 800 (> 500)
    # Next calls (subdivided halves): total_pages = 400 (<= 500)
    async def mock_request(endpoint, params, use_cache=False):
        gte = params.get("primary_release_date.gte")
        if gte == "2020-01-01" and params.get("primary_release_date.lte") == "2020-12-31":
            return {"page": 1, "total_pages": 800, "total_results": 16000, "results": []}
        return {"page": 1, "total_pages": 400, "total_results": 8000, "results": []}

    tmdb_mock._request = AsyncMock(side_effect=mock_request)

    parent_part = DatePartition("movie", "2020-01-01", "2020-12-31", "2020 Full")
    planned = await plan_partition(parent_part, tmdb_mock, rate_limiter)

    # Should have split into 2 child partitions
    assert len(planned) == 2
    for child in planned:
        assert child.total_pages <= TMDB_MAX_DISCOVER_PAGE
        assert child.total_pages == 400
        assert child.total_results == 8000


@pytest.mark.asyncio
async def test_partition_no_subdivision_when_under_500():
    """Verify that partitions with total_pages <= 500 are not subdivided."""
    tmdb_mock = MagicMock(spec=TMDBService)
    rate_limiter = AsyncRateLimiter(requests_per_second=0)
    tmdb_mock._request = AsyncMock(
        return_value={"page": 1, "total_pages": 150, "total_results": 3000, "results": []}
    )

    p = DatePartition("tv", "1970-01-01", "1979-12-31", "1970s TV")
    planned = await plan_partition(p, tmdb_mock, rate_limiter)

    assert len(planned) == 1
    assert planned[0].total_pages == 150
    assert planned[0].total_results == 3000


@pytest.mark.asyncio
async def test_rate_limiter_pacing():
    """Verify AsyncRateLimiter paces requests to respect rate limits."""
    limiter = AsyncRateLimiter(requests_per_second=20.0)
    start = asyncio.get_running_loop().time()

    for _ in range(3):
        await limiter.acquire()

    elapsed = asyncio.get_running_loop().time() - start
    # 3 calls at 20/s means 2 intervals of 0.05s = ~0.10s
    assert elapsed >= 0.08


@pytest.mark.asyncio
async def test_fetch_with_retry_on_rate_limit():
    """Verify retry logic recovers from transient 429 rate limit exceptions."""
    tmdb_mock = MagicMock(spec=TMDBService)
    rate_limiter = AsyncRateLimiter(requests_per_second=0)

    attempts = 0

    async def flaky_request(endpoint, params, use_cache=False):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TMDBRateLimitedException("Rate limit hit")
        return {"page": 1, "results": [{"id": 1234, "title": "Test Movie"}]}

    tmdb_mock._request = AsyncMock(side_effect=flaky_request)

    res = await fetch_page_with_retry(
        tmdb_mock,
        "discover/movie",
        {},
        rate_limiter,
        max_retries=4,
        base_delay=0.01,
    )
    assert attempts == 3
    assert res["results"][0]["id"] == 1234


@pytest.mark.asyncio
async def test_fetch_with_retry_exhaustion():
    """Verify fetch_page_with_retry raises when retries are exhausted."""
    tmdb_mock = MagicMock(spec=TMDBService)
    rate_limiter = AsyncRateLimiter(requests_per_second=0)
    tmdb_mock._request = AsyncMock(side_effect=TMDBUnavailableException("TMDB down"))

    with pytest.raises(TMDBUnavailableException):
        await fetch_page_with_retry(
            tmdb_mock,
            "discover/movie",
            {},
            rate_limiter,
            max_retries=2,
            base_delay=0.01,
        )


def test_checkpoint_manager(tmp_path):
    """Verify CheckpointManager records, persists, and resumes progress."""
    chk_file = str(tmp_path / "test_checkpoint.json")
    mgr = CheckpointManager(chk_file)

    assert mgr.is_partition_done("movie:1990:1999") is False
    assert mgr.get_last_page("movie:1990:1999") == 0

    asyncio.run(mgr.record_progress("movie:1990:1999", page=5, inserted=100, updated=5))
    assert mgr.get_last_page("movie:1990:1999") == 5

    asyncio.run(mgr.mark_partition_done("movie:1990:1999"))
    assert mgr.is_partition_done("movie:1990:1999") is True

    # Reload from disk into a fresh instance
    mgr2 = CheckpointManager(chk_file)
    assert mgr2.is_partition_done("movie:1990:1999") is True
    assert mgr2.get_last_page("movie:1990:1999") == 5
    assert mgr2.get_stats()["inserted"] == 100
    assert mgr2.get_stats()["updated"] == 5


def test_bulk_upsert_deduplication(db_session: Session):
    """Verify bulk_upsert_items is idempotent, counts inserts vs updates, and prevents duplicates."""
    # Ensure taxonomy genres
    genre_map = sync_taxonomy_genres(
        db_session,
        [{"id": 28, "name": "Action"}, {"id": 12, "name": "Adventure"}],
    )

    items = [
        {
            "id": 9001,
            "title": "Cosmic Voyager",
            "overview": "First run overview",
            "release_date": "2024-05-10",
            "original_language": "en",
            "popularity": 85.5,
            "vote_average": 7.8,
            "vote_count": 500,
            "genre_ids": [28, 12],
        },
        {
            "id": 9002,
            "title": "Silent Echoes",
            "overview": "A quiet drama",
            "release_date": "2023-11-20",
            "original_language": "fr",
            "popularity": 42.0,
            "vote_average": 8.1,
            "vote_count": 250,
            "genre_ids": [28],
        },
    ]

    # Initial upsert: 2 inserted
    stats1 = bulk_upsert_items(db_session, items, ContentType.MOVIE.value, genre_map)
    assert stats1.inserted == 2
    assert stats1.updated == 0

    count = db_session.execute(
        text("SELECT count(*) FROM contents WHERE content_type = 'movie'")
    ).scalar()
    assert count == 2

    # Second upsert with updated popularity: 0 inserted, 2 updated
    items[0]["popularity"] = 99.0
    stats2 = bulk_upsert_items(db_session, items, ContentType.MOVIE.value, genre_map)
    assert stats2.inserted == 0
    assert stats2.updated == 2

    # Count must remain 2 (no duplicates!)
    count_after = db_session.execute(
        text("SELECT count(*) FROM contents WHERE content_type = 'movie'")
    ).scalar()
    assert count_after == 2

    # Verify updated field was committed
    row = db_session.execute(
        text("SELECT popularity FROM contents WHERE tmdb_id = 9001")
    ).fetchone()
    assert row[0] == 99.0


def test_large_catalogue_pagination_scale(db_session: Session):
    """Verify that a large catalogue (10,000 items) produces 556 pages at 18/page.

    Also proves that collection='popular' strictly caps at 100 items (6 pages).
    """
    total_records = 10_000
    # Seed bulk rows directly
    contents = [
        Content(
            content_type=ContentType.MOVIE.value,
            tmdb_id=100_000 + i,
            title=f"Movie {i}",
            release_date=f"{1980 + (i % 45)}-06-15",
            popularity=float(i),
            vote_average=7.0,
            vote_count=100 + i,
        )
        for i in range(total_records)
    ]
    db_session.bulk_save_objects(contents)
    db_session.commit()

    service = ContentCatalogService(MagicMock(spec=TMDBService))

    # 1. Full Catalogue (collection=None)
    results, total, total_pages = service.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        page=1,
        limit=CONTENT_PAGE_SIZE,  # 18
        max_items=None,
    )
    assert total == 10_000
    assert len(results) == 18
    # 10,000 / 18 = 555.55... -> 556 pages
    assert total_pages == 556

    # Verify mid-catalogue page 300
    results_p300, total_p300, total_pages_p300 = service.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        page=300,
        limit=CONTENT_PAGE_SIZE,
        max_items=None,
    )
    assert len(results_p300) == 18
    assert total_p300 == 10_000
    assert total_pages_p300 == 556

    # 2. Popular Collection (collection='popular' -> max_items=100)
    pop_results, pop_total, pop_pages = service.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        page=1,
        limit=CONTENT_PAGE_SIZE,
        max_items=POPULAR_COLLECTION_MAX,  # 100
    )
    assert pop_total == 100
    assert len(pop_results) == 18
    # 100 / 18 = 5.55... -> 6 pages
    assert pop_pages == 6

    # Page 6 of popular should have remaining 10 items (18*5 = 90, 100 - 90 = 10)
    p6_results, p6_total, p6_pages = service.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        page=6,
        limit=CONTENT_PAGE_SIZE,
        max_items=POPULAR_COLLECTION_MAX,
    )
    assert len(p6_results) == 10
    assert p6_total == 100
    assert p6_pages == 6
