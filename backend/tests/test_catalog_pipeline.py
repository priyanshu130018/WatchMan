"""Comprehensive unit and integration test suite for TMDB Catalog Ingestion, Synchronization, Search, Filtering, and Content APIs (Step 5)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    MovieNotFoundException,
    TVShowNotFoundException,
    ContentNotFoundException,
    TMDBAuthenticationException,
    TMDBRateLimitedException,
    TMDBUnavailableException,
    TMDBTimeoutException,
    TMDBInvalidResponseException,
)
from app.core.redis import RedisCache
from app.core.security import get_current_user
from app.models.content import Content, ContentType
from app.models.user import User
from app.repositories.content_repository import ContentRepository
from app.schemas.content import (
    ContentPaginationResponse,
    ContentSummaryDTO,
    ContentDetailResponse,
)
from app.services.catalog import ContentCatalogService
from app.services.tmdb.service import TMDBService
from app.main import app


@pytest.fixture
def mock_user():
    import uuid
    return User(
        id=uuid.uuid4(),
        email="test_curator@example.com",
        password_hash="mockhash123",
        is_active=True,
    )


@pytest.fixture
def client(mock_user):
    """Test client with authenticated user override."""
    def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


# =============================================================================
# 1. TMDB Client Error Mapping & Exception Handling
# =============================================================================

@pytest.mark.asyncio
async def test_tmdb_401_authentication_exception():
    tmdb = TMDBService()
    mock_resp = MagicMock(status_code=401)
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with pytest.raises(TMDBAuthenticationException) as exc_info:
            await tmdb._request("movie/550", use_cache=False)
        assert exc_info.value.code == "TMDB_AUTHENTICATION_ERROR"
        assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_tmdb_404_movie_and_tv_not_found():
    tmdb = TMDBService()
    mock_resp = MagicMock(status_code=404)
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        # Movie 404
        with pytest.raises(MovieNotFoundException) as exc_m:
            await tmdb._request("movie/999999", use_cache=False)
        assert exc_m.value.code == "MOVIE_NOT_FOUND"
        assert exc_m.value.status_code == 404

        # TV 404
        with pytest.raises(TVShowNotFoundException) as exc_tv:
            await tmdb._request("tv/888888", use_cache=False)
        assert exc_tv.value.code == "TV_SHOW_NOT_FOUND"
        assert exc_tv.value.status_code == 404


@pytest.mark.asyncio
async def test_tmdb_429_rate_limited():
    tmdb = TMDBService()
    mock_resp = MagicMock(status_code=429)
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with pytest.raises(TMDBRateLimitedException) as exc_info:
            await tmdb._request("trending/movie/week", use_cache=False)
        assert exc_info.value.code == "TMDB_RATE_LIMITED"
        assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_tmdb_500_unavailable():
    tmdb = TMDBService()
    mock_resp = MagicMock(status_code=500)
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with pytest.raises(TMDBUnavailableException) as exc_info:
            await tmdb._request("movie/popular", use_cache=False)
        assert exc_info.value.code == "TMDB_UNAVAILABLE"
        assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_tmdb_timeout_and_network_errors():
    tmdb = TMDBService()
    with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Timeout")):
        with pytest.raises(TMDBTimeoutException) as exc_timeout:
            await tmdb._request("movie/550", use_cache=False)
        assert exc_timeout.value.code == "TMDB_TIMEOUT"

    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Network Error")):
        with pytest.raises(TMDBUnavailableException) as exc_conn:
            await tmdb._request("movie/550", use_cache=False)
        assert exc_conn.value.code == "TMDB_UNAVAILABLE"


@pytest.mark.asyncio
async def test_tmdb_invalid_json():
    tmdb = TMDBService()
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.side_effect = json.JSONDecodeError("Invalid JSON", "doc", 0)
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with pytest.raises(TMDBInvalidResponseException) as exc_info:
            await tmdb._request("movie/550", use_cache=False)
        assert exc_info.value.code == "TMDB_INVALID_RESPONSE"


# =============================================================================
# 2. Redis Caching & Non-blocking Graceful Degradation
# =============================================================================

@pytest.mark.asyncio
async def test_redis_cache_hit_and_graceful_degradation():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps({"id": 550, "title": "Cached Fight Club"})

    cache = RedisCache(redis_url="redis://localhost:6379/0")
    cache._client = mock_redis

    tmdb = TMDBService(redis_cache=cache)
    result = await tmdb.movie_details(550)
    assert result["title"] == "Cached Fight Club"
    mock_redis.get.assert_awaited()

    # Simulate Redis connection failure
    mock_redis.get.side_effect = ConnectionError("Redis server unreachable")
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": 550, "title": "Live Fight Club"}

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        live_result = await tmdb.movie_details(550)
        # Should gracefully fall back to live API call without crashing
        assert live_result["title"] == "Live Fight Club"


# =============================================================================
# 3. Pydantic Schemas & DTO Serialization
# =============================================================================

def test_pydantic_schema_pagination_and_summary():
    card = ContentSummaryDTO(
        id=1,
        tmdb_id=550,
        content_type="movie",
        title="Fight Club",
        popularity=85.5,
        vote_average=8.4,
        vote_count=25000,
    )
    page_resp = ContentPaginationResponse[ContentSummaryDTO](
        page=1,
        limit=16,
        total=1,
        total_pages=1,
        results=[card],
    )
    dumped = page_resp.model_dump()
    assert dumped["page"] == 1
    assert dumped["limit"] == 16
    assert dumped["total"] == 1
    assert dumped["total_pages"] == 1
    assert len(dumped["results"]) == 1
    assert dumped["results"][0]["title"] == "Fight Club"


# =============================================================================
# 4. Catalog Ingestion, Idempotency & Relationship Reconciliation
# =============================================================================

@pytest.mark.asyncio
async def test_idempotent_ingestion_and_reconciliation(db_session):
    service = ContentCatalogService()

    initial_movie = {
        "id": 550,
        "title": "Fight Club",
        "original_title": "Fight Club",
        "overview": "First overview version.",
        "release_date": "1999-10-15",
        "runtime": 139,
        "popularity": 80.0,
        "vote_average": 8.4,
        "vote_count": 24000,
        "genres": [{"id": 18, "name": "Drama"}],
        "spoken_languages": [{"iso_639_1": "en", "name": "English"}],
    }
    credits_v1 = {
        "cast": [{"id": 287, "name": "Brad Pitt", "character": "Tyler Durden", "order": 0}],
        "crew": [{"id": 7467, "name": "David Fincher", "department": "Directing", "job": "Director"}],
    }
    videos_v1 = {"results": [{"key": "trailer1", "name": "Trailer 1", "site": "YouTube"}]}
    ext_v1 = {"imdb_id": "tt0137523"}

    with patch.object(service.tmdb, "content_details", return_value=initial_movie), \
         patch.object(service.tmdb, "content_credits", return_value=credits_v1), \
         patch.object(service.tmdb, "content_videos", return_value=videos_v1), \
         patch.object(service.tmdb, "content_external_ids", return_value=ext_v1):

        movie_v1 = await service.sync_content(db_session, "movie", 550)
        assert movie_v1.overview == "First overview version."
        assert len(movie_v1.cast) == 1
        assert movie_v1.cast[0].person.name == "Brad Pitt"
        assert len(movie_v1.crew) == 1
        assert len(movie_v1.videos) == 1
        assert len(movie_v1.external_ids) == 1

    # Second sync with updated data (reconciliation)
    updated_movie = {
        "id": 550,
        "title": "Fight Club (Remastered)",
        "original_title": "Fight Club",
        "overview": "Updated overview version.",
        "release_date": "1999-10-15",
        "runtime": 139,
        "popularity": 95.0,
        "vote_average": 8.5,
        "vote_count": 26000,
        "genres": [{"id": 18, "name": "Drama"}, {"id": 53, "name": "Thriller"}],
        "spoken_languages": [{"iso_639_1": "en", "name": "English"}],
    }
    credits_v2 = {
        "cast": [
            {"id": 287, "name": "Brad Pitt", "character": "Tyler Durden", "order": 0},
            {"id": 819, "name": "Edward Norton", "character": "Narrator", "order": 1},
        ],
        "crew": [{"id": 7467, "name": "David Fincher", "department": "Directing", "job": "Director"}],
    }
    videos_v2 = {"results": [{"key": "trailer2", "name": "Official 4K Trailer", "site": "YouTube"}]}
    ext_v2 = {"imdb_id": "tt0137523", "wikidata_id": "Q190050"}

    with patch.object(service.tmdb, "content_details", return_value=updated_movie), \
         patch.object(service.tmdb, "content_credits", return_value=credits_v2), \
         patch.object(service.tmdb, "content_videos", return_value=videos_v2), \
         patch.object(service.tmdb, "content_external_ids", return_value=ext_v2):

        movie_v2 = await service.sync_content(db_session, "movie", 550)
        assert movie_v2.id == movie_v1.id  # Same primary key
        assert movie_v2.title == "Fight Club (Remastered)"
        assert movie_v2.overview == "Updated overview version."
        assert len(movie_v2.genres) == 2
        assert len(movie_v2.cast) == 2
        assert len(movie_v2.videos) == 1
        assert movie_v2.videos[0].key == "trailer2"
        assert len(movie_v2.external_ids) == 2


# =============================================================================
# 5. Catalog Search, Filtering, and Pagination
# =============================================================================

def test_catalog_filtering_sorting_and_empty_search(db_session):
    service = ContentCatalogService()

    # Seed 30 content items across 2021-2023 with varying ratings
    for i in range(1, 31):
        c_type = "movie" if i <= 15 else "tv"
        year = 2021 + (i % 3)
        c = Content(
            content_type=c_type,
            tmdb_id=3000 + i,
            title=f"Sample Content {i:02d}",
            release_date=f"{year}-06-15",
            popularity=float(i * 5),
            vote_average=5.0 + (i * 0.1),
        )
        db_session.add(c)
    db_session.commit()

    # Default pagination: page=1, limit=16
    results, total, total_pages = service.list_content(db_session, page=1, limit=16)
    assert total == 30
    assert total_pages == 2
    assert len(results) == 16
    assert results[0].popularity > results[1].popularity  # default popularity_desc

    # Filter by TV content
    tv_results, tv_total, tv_pages = service.list_content(
        db_session, content_type="tv", page=1, limit=16
    )
    assert tv_total == 15
    assert tv_pages == 1
    assert len(tv_results) == 15

    # Filter by year = 2022
    y_results, y_total, _ = service.list_content(db_session, year=2022)
    assert y_total == 10
    assert all(item.release_date.startswith("2022") for item in y_results)

    # Empty search query returns ([], 0, 0)
    empty_res, empty_total, empty_pages = service.search_content(db_session, query_str="")
    assert empty_res == []
    assert empty_total == 0
    assert empty_pages == 0

    # Search with keyword
    search_res, s_total, _ = service.search_content(db_session, query_str="Sample Content 05")
    assert s_total == 1
    assert search_res[0].title == "Sample Content 05"


# =============================================================================
# 6. API Route Contracts & Fallbacks
# =============================================================================

def test_api_movies_and_web_series_endpoints(client, db_session):
    # Test GET /api/movies (listing)
    res_list = client.get("/api/movies?page=1&limit=16")
    assert res_list.status_code == 200
    data = res_list.json()
    assert "results" in data
    assert "page" in data
    assert data["limit"] == 16

    # Test POST /api/movies/sync
    with patch("app.services.catalog.ContentCatalogService.sync_movie") as mock_sync:
        mock_sync.return_value = Content(
            id=10,
            tmdb_id=550,
            content_type="movie",
            title="Synced Fight Club",
            release_date="1999-10-15",
            runtime=139,
        )
        res_sync = client.post("/api/movies/sync", json={"movie_id": 550})
        assert res_sync.status_code == 200
        assert res_sync.json()["status"] == "success"
        assert res_sync.json()["movie"]["title"] == "Synced Fight Club"

    # Test POST /api/web-series/sync
    with patch("app.services.catalog.ContentCatalogService.sync_tv") as mock_tv_sync:
        mock_tv_sync.return_value = Content(
            id=11,
            tmdb_id=1399,
            content_type="tv",
            title="Synced GOT",
            release_date="2011-04-17",
            number_of_seasons=8,
            number_of_episodes=73,
        )
        res_tv_sync = client.post("/api/web-series/sync", json={"tv_id": 1399})
        assert res_tv_sync.status_code == 200
        assert res_tv_sync.json()["status"] == "success"
        assert res_tv_sync.json()["web_series"]["title"] == "Synced GOT"


def test_api_search_endpoint_blank_query_and_fallback(client, db_session):
    # Blank query must return 200 OK with empty results (never 404)
    res_blank = client.get("/api/search")
    assert res_blank.status_code == 200
    assert res_blank.json()["results"] == []
    assert res_blank.json()["total"] == 0

    res_empty_q = client.get("/api/search?q=")
    assert res_empty_q.status_code == 200
    assert res_empty_q.json()["results"] == []

    # Query with external TMDB fallback
    with patch("app.services.tmdb.service.TMDBService.search_multi") as mock_multi:
        mock_multi.return_value = {
            "page": 1,
            "total_results": 1,
            "total_pages": 1,
            "results": [
                {
                    "id": 999,
                    "media_type": "movie",
                    "title": "Fallback Matrix",
                    "overview": "Neo enters matrix",
                    "popularity": 50.0,
                    "vote_average": 8.0,
                }
            ],
        }
        res_search = client.get("/api/search?q=Matrix")
        assert res_search.status_code == 200
        data = res_search.json()
        assert data["total"] == 1
        assert data["results"][0]["title"] == "Fallback Matrix"


def test_api_trending_endpoint(client):
    with patch("app.services.tmdb.service.TMDBService.trending_all") as mock_trend:
        mock_trend.return_value = {
            "page": 1,
            "results": [{"id": 100, "title": "Trending Hit", "media_type": "movie"}],
        }
        res = client.get("/api/trending?time_window=week")
        assert res.status_code == 200
        assert res.json()["results"][0]["title"] == "Trending Hit"
