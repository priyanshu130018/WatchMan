"""Section-specific pagination tests.

Verifies the ``CONTENT_PAGE_SIZE=18`` window for the movies and web-series
catalogues, the finite "popular" collection (top ``POPULAR_COLLECTION_MAX=100``,
i.e. 6 pages of 18 with a 10-item last page), and the trending showcase
(exactly ``TRENDING_ITEMS=18`` movies + series combined on a single,
never-paginated page).

Ordering is always the backend's own popularity / trending order — the tests
assert we neither fabricate items nor re-sort in a second layer.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.constants import CONTENT_PAGE_SIZE, POPULAR_COLLECTION_MAX, TRENDING_ITEMS
from app.models.content import Content, ContentType
from app.services.catalog import ContentCatalogService
from app.main import app


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _seed(db, content_type: str, n: int, start_tmdb: int = 10_000) -> None:
    """Insert ``n`` rows with strictly increasing popularity.

    ``popularity = i`` and ``vote_average = n - i`` are deliberately inverse so a
    test can prove the "popular" collection is ordered by popularity and not by
    some other sort key that might be passed in. ``tmdb_id`` increases with
    popularity, so popularity-descending order == tmdb_id-descending order.
    """
    for i in range(n):
        db.add(
            Content(
                content_type=content_type,
                tmdb_id=start_tmdb + i,
                title=f"{content_type}-{i:04d}",
                release_date=f"{2000 + (i % 20)}-01-01",
                popularity=float(i),
                vote_average=float(n - i),
                vote_count=100 + i,
            )
        )
    db.commit()


def _ids(dtos) -> list[int]:
    return [d.tmdb_id for d in dtos]


# ---------------------------------------------------------------------------
# Movies / web-series catalogue: 18 per page, real totals, correct windows.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("content_type", [ContentType.MOVIE.value, ContentType.TV.value])
def test_catalogue_pages_are_18_wide_with_correct_windows(db_session, content_type):
    service = ContentCatalogService()
    _seed(db_session, content_type, 40)

    # Ground-truth ordering (single wide page) to compare 18-wide slices against.
    full, total, _ = service.list_content(
        db_session, content_type=content_type, page=1, limit=100
    )
    assert total == 40
    order = _ids(full)

    page1, total1, total_pages1 = service.list_content(
        db_session, content_type=content_type, page=1, limit=CONTENT_PAGE_SIZE
    )
    assert total1 == 40
    assert total_pages1 == 3  # ceil(40 / 18)
    assert len(page1) == CONTENT_PAGE_SIZE
    assert _ids(page1) == order[:18]

    page2, _, _ = service.list_content(
        db_session, content_type=content_type, page=2, limit=CONTENT_PAGE_SIZE
    )
    # Page 2 begins at the 19th item overall.
    assert page2[0].tmdb_id == order[18]
    assert _ids(page2) == order[18:36]

    # Last page holds the remainder (40 - 36 = 4), not a padded full page.
    page3, _, _ = service.list_content(
        db_session, content_type=content_type, page=3, limit=CONTENT_PAGE_SIZE
    )
    assert len(page3) == 4
    assert _ids(page3) == order[36:40]

    # A page beyond the total is empty, but the total is unchanged.
    page4, total4, _ = service.list_content(
        db_session, content_type=content_type, page=4, limit=CONTENT_PAGE_SIZE
    )
    assert page4 == []
    assert total4 == 40


def test_filter_narrows_total_and_repaginates(db_session):
    """Applying a filter changes the real total / total_pages.

    (Resetting to page 1 on a filter change is a frontend concern; the backend's
    job is to report the *filtered* totals honestly rather than fake them.)
    """
    service = ContentCatalogService()
    _seed(db_session, ContentType.MOVIE.value, 30)

    _, total_all, _ = service.list_content(db_session, content_type=ContentType.MOVIE.value)
    assert total_all == 30

    # release_date year 2001 -> (i % 20) == 1 -> i in {1, 21} -> exactly 2 items.
    y_items, y_total, y_pages = service.list_content(
        db_session, content_type=ContentType.MOVIE.value, year=2001
    )
    assert y_total == 2
    assert y_pages == 1
    assert all(item.release_date.startswith("2001") for item in y_items)


# ---------------------------------------------------------------------------
# Popular collection: finite top-100, 6 pages of 18 (last = 10), no fabrication.
# ---------------------------------------------------------------------------


def test_popular_collection_caps_at_100_across_six_pages(db_session):
    service = ContentCatalogService()
    _seed(db_session, ContentType.MOVIE.value, 120)  # more titles than the cap

    collected: list[int] = []
    for page in range(1, 7):
        items, total, total_pages = service.list_content(
            db_session,
            content_type=ContentType.MOVIE.value,
            page=page,
            limit=CONTENT_PAGE_SIZE,
            max_items=POPULAR_COLLECTION_MAX,
        )
        assert total == POPULAR_COLLECTION_MAX  # clamped to 100, not 120
        assert total_pages == 6  # ceil(100 / 18)
        assert len(items) == (CONTENT_PAGE_SIZE if page < 6 else 10)
        collected.extend(_ids(items))

    assert len(collected) == POPULAR_COLLECTION_MAX  # 18*5 + 10 == 100
    assert len(set(collected)) == POPULAR_COLLECTION_MAX  # no duplicate cards

    # Page 7 is a valid empty page; the total stays clamped (no fabrication).
    page7, total7, total_pages7 = service.list_content(
        db_session,
        content_type=ContentType.MOVIE.value,
        page=7,
        limit=CONTENT_PAGE_SIZE,
        max_items=POPULAR_COLLECTION_MAX,
    )
    assert page7 == []
    assert total7 == POPULAR_COLLECTION_MAX
    assert total_pages7 == 6


def test_popular_collection_preserves_backend_popularity_order(db_session):
    service = ContentCatalogService()
    _seed(db_session, ContentType.MOVIE.value, 120)

    # Ground-truth top-100 by popularity (single capped page).
    full, total, _ = service.list_content(
        db_session,
        content_type=ContentType.MOVIE.value,
        page=1,
        limit=POPULAR_COLLECTION_MAX,
        max_items=POPULAR_COLLECTION_MAX,
    )
    assert total == POPULAR_COLLECTION_MAX
    top_100 = _ids(full)
    # Highest popularity first; strictly descending; exactly the real top 100.
    assert top_100[0] == 10_000 + 119
    assert top_100 == sorted(top_100, reverse=True)

    # Concatenating the six 18-wide pages reproduces that exact order.
    paged: list[int] = []
    for page in range(1, 7):
        items, _, _ = service.list_content(
            db_session,
            content_type=ContentType.MOVIE.value,
            page=page,
            limit=CONTENT_PAGE_SIZE,
            max_items=POPULAR_COLLECTION_MAX,
        )
        paged.extend(_ids(items))
    assert paged == top_100


def test_popular_collection_uses_real_total_when_below_cap(db_session):
    service = ContentCatalogService()
    _seed(db_session, ContentType.TV.value, 50)  # fewer than the 100 cap

    items_p1, total, total_pages = service.list_content(
        db_session,
        content_type=ContentType.TV.value,
        page=1,
        limit=CONTENT_PAGE_SIZE,
        max_items=POPULAR_COLLECTION_MAX,
    )
    assert total == 50  # the real total, not the 100 cap
    assert total_pages == 3  # ceil(50 / 18)
    assert len(items_p1) == CONTENT_PAGE_SIZE

    last_page, _, _ = service.list_content(
        db_session,
        content_type=ContentType.TV.value,
        page=3,
        limit=CONTENT_PAGE_SIZE,
        max_items=POPULAR_COLLECTION_MAX,
    )
    assert len(last_page) == 50 - 2 * CONTENT_PAGE_SIZE  # 50 - 36 == 14


# ---------------------------------------------------------------------------
# API contract: /api/movies & /api/web-series honor 18/page with real totals.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, content_type",
    [
        ("/api/movies", ContentType.MOVIE.value),
        ("/api/web-series", ContentType.TV.value),
    ],
)
def test_api_listing_default_page_size_is_18(client, db_session, path, content_type):
    _seed(db_session, content_type, 40, start_tmdb=20_000)

    # Ground-truth ordering via one wide page (limit<=100 is allowed by the route).
    full = client.get(f"{path}?page=1&limit=100")
    assert full.status_code == 200
    order = [r["tmdb_id"] for r in full.json()["results"]]
    assert len(order) == 40

    body1 = client.get(f"{path}?page=1").json()
    assert body1["limit"] == CONTENT_PAGE_SIZE
    assert body1["total"] == 40
    assert body1["total_pages"] == 3
    assert len(body1["results"]) == CONTENT_PAGE_SIZE
    assert [r["tmdb_id"] for r in body1["results"]] == order[:18]

    body2 = client.get(f"{path}?page=2").json()
    assert [r["tmdb_id"] for r in body2["results"]] == order[18:36]  # starts at #19

    body3 = client.get(f"{path}?page=3").json()
    assert len(body3["results"]) == 4  # remainder page
    assert [r["tmdb_id"] for r in body3["results"]] == order[36:40]

    body4 = client.get(f"{path}?page=4").json()
    assert body4["results"] == []
    assert body4["total"] == 40


def test_api_movies_popular_collection_is_finite_six_pages(client, db_session):
    _seed(db_session, ContentType.MOVIE.value, 120, start_tmdb=30_000)

    body = client.get("/api/movies?collection=popular&page=6").json()
    assert body["total"] == POPULAR_COLLECTION_MAX
    assert body["total_pages"] == 6
    assert len(body["results"]) == 10  # 100 - 18*5

    # Page 7 is a valid, empty page — never fabricated.
    page7 = client.get("/api/movies?collection=popular&page=7")
    assert page7.status_code == 200
    assert page7.json()["results"] == []


def test_api_popular_collection_forces_popularity_order(client, db_session):
    """``collection=popular`` must ignore an incoming sort and keep popularity order.

    vote_average is seeded inverse to popularity, so a vote_average sort would
    reverse the order; the response must still be popularity-descending.
    """
    _seed(db_session, ContentType.MOVIE.value, 30, start_tmdb=40_000)

    resp = client.get("/api/movies?collection=popular&sort=vote_average_desc&limit=100")
    assert resp.status_code == 200
    ids = [r["tmdb_id"] for r in resp.json()["results"]]
    # popularity desc == tmdb_id desc here; a vote_average sort would be ascending.
    assert ids == sorted(ids, reverse=True)
    assert ids[0] == 40_000 + 29


# ---------------------------------------------------------------------------
# Trending: exactly TRENDING_ITEMS combined, single page, never paginated.
# ---------------------------------------------------------------------------


def _trending_payload() -> dict:
    """Interleaved movie/tv entries with people mixed in at known positions."""
    entries: list[dict] = []
    for i in range(25):
        entries.append({"id": 1_000 + i, "media_type": "movie", "title": f"M{i}"})
        entries.append({"id": 2_000 + i, "media_type": "tv", "name": f"T{i}"})
    # People must be filtered out no matter where they appear in the feed.
    entries.insert(2, {"id": 9_001, "media_type": "person", "name": "Person A"})
    entries.insert(9, {"id": 9_002, "media_type": "person", "name": "Person B"})
    entries.append({"id": 9_003, "media_type": "person", "name": "Person C"})
    return {"page": 1, "results": entries}


def test_api_trending_returns_exactly_18_combined(client):
    with patch("app.services.tmdb.service.TMDBService.trending_all") as mock_trending:
        mock_trending.return_value = _trending_payload()
        body = client.get("/api/trending?time_window=week").json()

    assert body["page"] == 1
    assert body["total_pages"] == 1  # a single fixed page
    assert body["page_size"] == TRENDING_ITEMS
    assert body["total_results"] == TRENDING_ITEMS
    assert len(body["results"]) == TRENDING_ITEMS  # never more than 18


def test_api_trending_filters_people_and_preserves_order(client):
    payload = _trending_payload()
    with patch("app.services.tmdb.service.TMDBService.trending_all") as mock_trending:
        mock_trending.return_value = payload
        results = client.get("/api/trending").json()["results"]

    assert all(item["media_type"] in ("movie", "tv") for item in results)  # no people
    expected = [e for e in payload["results"] if e["media_type"] in ("movie", "tv")][
        :TRENDING_ITEMS
    ]
    assert [r["id"] for r in results] == [e["id"] for e in expected]  # order unchanged


def test_api_trending_not_padded_when_upstream_has_fewer(client):
    small = {
        "page": 1,
        "results": [
            {"id": 1, "media_type": "movie", "title": "Only 1"},
            {"id": 2, "media_type": "tv", "name": "Only 2"},
            {"id": 3, "media_type": "person", "name": "Ignored"},
        ],
    }
    with patch("app.services.tmdb.service.TMDBService.trending_all") as mock_trending:
        mock_trending.return_value = small
        body = client.get("/api/trending").json()

    assert body["total_pages"] == 1
    assert body["total_results"] == 2  # two real titles, nothing padded
    assert len(body["results"]) == 2


def test_api_trending_ignores_page_parameter(client):
    """Trending exposes no page param; a stray ``?page=2`` must change nothing."""
    with patch("app.services.tmdb.service.TMDBService.trending_all") as mock_trending:
        mock_trending.return_value = _trending_payload()
        page1 = client.get("/api/trending").json()
        page2 = client.get("/api/trending?page=2").json()

    assert page1 == page2
    assert page2["total_pages"] == 1
    assert len(page2["results"]) == TRENDING_ITEMS


def test_api_movies_popular_page1_vs_page2_different_records(client, db_session):
    """Popular mode page 1 and page 2 must return completely disjoint sets of records."""
    _seed(db_session, ContentType.MOVIE.value, 50, start_tmdb=50_000)

    p1 = client.get("/api/movies?collection=popular&page=1").json()
    p2 = client.get("/api/movies?collection=popular&page=2").json()

    assert p1["page"] == 1
    assert p2["page"] == 2
    assert len(p1["results"]) == CONTENT_PAGE_SIZE
    assert len(p2["results"]) == CONTENT_PAGE_SIZE

    ids_p1 = [r["tmdb_id"] for r in p1["results"]]
    ids_p2 = [r["tmdb_id"] for r in p2["results"]]
    assert set(ids_p1).isdisjoint(set(ids_p2))


def test_api_popular_and_full_catalogue_differ_in_query_and_totals(client, db_session):
    """Full Catalogue and Popular mode must return different totals when dataset exceeds 100."""
    _seed(db_session, ContentType.MOVIE.value, 120, start_tmdb=60_000)

    # Full Catalogue: real database total (120), 7 pages of 18
    full = client.get("/api/movies?page=1&page_size=18").json()
    assert full["total"] == 120
    assert full["total_results"] == 120
    assert full["total_pages"] == 7
    assert full["page_size"] == 18
    assert len(full["results"]) == 18

    # Popular mode: capped at 100, exactly 6 pages
    popular = client.get("/api/movies?collection=popular&page=1&page_size=18").json()
    assert popular["total"] == POPULAR_COLLECTION_MAX
    assert popular["total_results"] == POPULAR_COLLECTION_MAX
    assert popular["total_pages"] == 6
    assert popular["page_size"] == 18
    assert len(popular["results"]) == 18


def test_api_page_size_query_param_supported(client, db_session):
    """Verify page_size is accepted as alias for limit and reflected in response envelope."""
    _seed(db_session, ContentType.MOVIE.value, 25, start_tmdb=70_000)

    resp = client.get("/api/movies?page=1&page_size=10").json()
    assert resp["limit"] == 10
    assert resp["page_size"] == 10
    assert resp["total"] == 25
    assert resp["total_results"] == 25
    assert resp["total_pages"] == 3
    assert len(resp["results"]) == 10
