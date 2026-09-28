"""Regression tests for the content-detail response contract.

These guard the bug where ``ContentDetailResponse`` had an erroneously merged
pagination block (``page``/``limit``/``total``/``total_pages``/``results``),
which made those four fields REQUIRED on the single-item detail DTO. As a
result ``ContentCatalogService.content_to_detail_dto`` raised
``ValidationError: 4 validation errors for ContentDetailResponse`` and the
``GET /api/movies/{id}`` and ``GET /api/web-series/{id}`` detail endpoints
returned HTTP 500 (surfacing as an Axios "Network Error" in the browser).

The tests also lock in the complementary invariants demanded by the fix:
detail responses must NOT carry pagination metadata, while the separate
paginated list endpoints and ``ContentPaginationResponse`` envelope MUST keep
requiring it.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.exceptions import MovieNotFoundException, TVShowNotFoundException
from app.core.security import get_current_user
from app.models.content import Content, ContentType
from app.models.user import User
from app.repositories.content_repository import ContentRepository
from app.schemas.content import ContentDetailResponse, ContentPaginationResponse
from app.services.catalog import ContentCatalogService
from app.main import app

PAGINATION_FIELDS = {"page", "limit", "total", "total_pages"}


@pytest.fixture
def mock_user():
    import uuid

    return User(
        id=uuid.uuid4(),
        email="detail_contract@example.com",
        password_hash="mockhash123",
        is_active=True,
    )


@pytest.fixture
def client(mock_user):
    """Test client with an authenticated user, mirroring the catalog suite."""

    def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    # raise_server_exceptions=False so a 500 surfaces as an HTTP response we can
    # assert on (this is exactly what the pagination-contract bug produced).
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_current_user, None)


def _seed_movie(db_session, *, tmdb_id: int = 550, title: str = "Fight Club") -> Content:
    movie = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=tmdb_id,
        title=title,
        original_title=title,
        overview="An insomniac forms an underground fight club.",
        release_date="1999-10-15",
        runtime=139,
        popularity=88.0,
        vote_average=8.4,
        vote_count=26000,
    )
    db_session.add(movie)
    db_session.commit()
    return movie


def _seed_web_series(db_session, *, tmdb_id: int = 1399, title: str = "Game of Thrones") -> Content:
    series = Content(
        content_type=ContentType.TV.value,
        tmdb_id=tmdb_id,
        title=title,
        original_title=title,
        overview="Noble families vie for control of the Iron Throne.",
        release_date="2011-04-17",
        popularity=120.0,
        vote_average=8.4,
        vote_count=22000,
        number_of_seasons=8,
        number_of_episodes=73,
    )
    db_session.add(series)
    db_session.commit()
    return series


# =============================================================================
# 1. Schema-level contract: detail DTO must NOT require pagination metadata.
# =============================================================================

def test_content_detail_dto_does_not_declare_pagination_fields():
    """The detail DTO is a single item; it must not carry list pagination fields."""
    leaked = PAGINATION_FIELDS & set(ContentDetailResponse.model_fields)
    assert leaked == set(), f"detail DTO unexpectedly declares pagination fields: {leaked}"
    assert "results" not in ContentDetailResponse.model_fields


def test_content_detail_dto_constructs_without_pagination_metadata():
    """Constructing the detail DTO with only detail fields must succeed.

    Before the fix this raised ``ValidationError`` for the four required
    pagination fields.
    """
    detail = ContentDetailResponse(
        id=1,
        tmdb_id=550,
        content_type="movie",
        title="Fight Club",
    )
    assert detail.tmdb_id == 550
    assert detail.content_type == "movie"
    dumped = detail.model_dump()
    for field in PAGINATION_FIELDS | {"results"}:
        assert field not in dumped


def test_content_to_detail_dto_service_helper_succeeds(db_session):
    """The exact construction site (catalog.content_to_detail_dto) must not raise."""
    _seed_movie(db_session, tmdb_id=777, title="Service DTO Movie")
    content = ContentRepository.get_by_tmdb_id(db_session, ContentType.MOVIE.value, 777)
    assert content is not None

    detail = ContentCatalogService.content_to_detail_dto(content)
    assert isinstance(detail, ContentDetailResponse)
    assert detail.tmdb_id == 777
    assert detail.title == "Service DTO Movie"


# =============================================================================
# 2. Detail endpoints return 200 for locally-stored items (the failing path).
# =============================================================================

def test_movie_detail_endpoint_returns_200_for_local_item(client, db_session):
    _seed_movie(db_session, tmdb_id=550, title="Fight Club")

    res = client.get("/api/movies/550")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tmdb_id"] == 550
    assert body["content_type"] == "movie"
    assert body["title"] == "Fight Club"
    # Detail payload must not leak pagination metadata.
    for field in PAGINATION_FIELDS:
        assert field not in body


def test_web_series_detail_endpoint_returns_200_for_local_item(client, db_session):
    _seed_web_series(db_session, tmdb_id=1399, title="Game of Thrones")

    res = client.get("/api/web-series/1399")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tmdb_id"] == 1399
    assert body["content_type"] == "tv"
    assert body["title"] == "Game of Thrones"
    for field in PAGINATION_FIELDS:
        assert field not in body


# =============================================================================
# 3. Invalid IDs return the intended 404 (not a 500), via TMDB fallback.
# =============================================================================

def test_invalid_movie_id_returns_404(client):
    # Not stored locally -> falls through to TMDB, which 404s for a bad id.
    with patch(
        "app.services.tmdb.service.TMDBService.movie_details",
        side_effect=MovieNotFoundException(),
    ):
        res = client.get("/api/movies/99999999")
    assert res.status_code == 404, res.text
    assert res.json()["error"]["code"] == "MOVIE_NOT_FOUND"


def test_invalid_web_series_id_returns_404(client):
    with patch(
        "app.services.tmdb.service.TMDBService.tv_details",
        side_effect=TVShowNotFoundException(),
    ):
        res = client.get("/api/web-series/99999999")
    assert res.status_code == 404, res.text
    assert res.json()["error"]["code"] == "TV_SHOW_NOT_FOUND"


# =============================================================================
# 4. Paginated list endpoints/envelope MUST retain pagination metadata.
# =============================================================================

def test_paginated_movie_endpoint_still_returns_pagination_metadata(client, db_session):
    for i in range(3):
        _seed_movie(db_session, tmdb_id=6000 + i, title=f"List Movie {i}")

    res = client.get("/api/movies?page=1&limit=16")
    assert res.status_code == 200, res.text
    body = res.json()
    for field in PAGINATION_FIELDS | {"results"}:
        assert field in body, f"list response missing pagination field: {field}"
    assert body["limit"] == 16


def test_paginated_web_series_endpoint_still_returns_pagination_metadata(client, db_session):
    for i in range(3):
        _seed_web_series(db_session, tmdb_id=7000 + i, title=f"List Series {i}")

    res = client.get("/api/web-series?page=1&limit=16")
    assert res.status_code == 200, res.text
    body = res.json()
    for field in PAGINATION_FIELDS | {"results"}:
        assert field in body, f"list response missing pagination field: {field}"
    assert body["limit"] == 16


def test_pagination_envelope_still_requires_metadata():
    """The dedicated paginated model must keep enforcing its contract."""
    for field in PAGINATION_FIELDS:
        assert field in ContentPaginationResponse.model_fields

    with pytest.raises(ValidationError):
        # Missing page/limit/total/total_pages must still fail here.
        ContentPaginationResponse[ContentDetailResponse].model_validate({"results": []})
