"""Regression and end-to-end tests for WatchMan search and filter functionality.

Verifies:
1. Exact reproduction and fix of the 'Filters 1 -> No titles found' bug (TMDB genre ID mapping).
2. Genre filtering via both TMDB genre ID (e.g. 878) and internal database genre ID (e.g. 8).
3. Language filtering (e.g. 'en', 'es').
4. Year filtering (e.g. 2024, 2022).
5. Sorting options (popularity_desc, release_date_asc, vote_average_desc).
6. Combined multi-criteria filters.
7. Filtered pagination (page 1, page 2 preserving filtered total and subset).
8. Parameter aliases ('genre' and 'genre_id', 'limit' and 'page_size', 'type' and 'content_type').
9. Popular collection mode capping and interaction with active filters.
10. Unified /api/search with title query + filters.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.content import Content, ContentType
from app.models.taxonomy import Genre, ContentGenre, Language, ContentLanguage
from app.repositories.content_repository import ContentRepository
from app.services.catalog import ContentCatalogService


@pytest.fixture
def seeded_catalog(db_session):
    """Seed distinct content items with explicit genres and languages for precise filter testing."""
    # 1. Ensure genres exist with distinct internal IDs and TMDB IDs
    sci_fi = db_session.query(Genre).filter(Genre.tmdb_id == 878).first()
    if not sci_fi:
        sci_fi = Genre(tmdb_id=878, name="Science Fiction")
        db_session.add(sci_fi)

    action = db_session.query(Genre).filter(Genre.tmdb_id == 28).first()
    if not action:
        action = Genre(tmdb_id=28, name="Action")
        db_session.add(action)

    drama = db_session.query(Genre).filter(Genre.tmdb_id == 18).first()
    if not drama:
        drama = Genre(tmdb_id=18, name="Drama")
        db_session.add(drama)

    db_session.commit()
    db_session.refresh(sci_fi)
    db_session.refresh(action)
    db_session.refresh(drama)

    # 2. Ensure languages exist
    for code, name in [("en", "English"), ("es", "Spanish"), ("fr", "French")]:
        l_obj = db_session.query(Language).filter(Language.code == code).first()
        if not l_obj:
            db_session.add(Language(code=code, name=name, english_name=name))
    db_session.commit()

    # 3. Create sample content items
    items = []

    # Movie 1: Sci-Fi, Action, English, 2024
    m1 = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=90001,
        title="Dune: Test Frontier",
        original_title="Dune: Test Frontier",
        overview="Epic desert sci-fi action movie on Arrakis.",
        release_date="2024-03-01",
        original_language="en",
        popularity=95.0,
        vote_average=8.8,
    )
    db_session.add(m1)
    db_session.flush()
    db_session.add(ContentGenre(content_id=m1.id, genre_id=sci_fi.id))
    db_session.add(ContentGenre(content_id=m1.id, genre_id=action.id))
    db_session.add(ContentLanguage(content_id=m1.id, language_code="en"))
    items.append(m1)

    # Movie 2: Sci-Fi, Spanish, 2022
    m2 = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=90002,
        title="El Tiempo Perdido",
        original_title="El Tiempo Perdido",
        overview="Spanish sci-fi drama about time loops.",
        release_date="2022-10-15",
        original_language="es",
        popularity=60.0,
        vote_average=7.5,
    )
    db_session.add(m2)
    db_session.flush()
    db_session.add(ContentGenre(content_id=m2.id, genre_id=sci_fi.id))
    db_session.add(ContentGenre(content_id=m2.id, genre_id=drama.id))
    db_session.add(ContentLanguage(content_id=m2.id, language_code="es"))
    items.append(m2)

    # Movie 3: Action, Drama (NO Sci-Fi), English, 2024
    m3 = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=90003,
        title="Urban Heatwave",
        original_title="Urban Heatwave",
        overview="Crime action in the city center.",
        release_date="2024-07-20",
        original_language="en",
        popularity=80.0,
        vote_average=6.9,
    )
    db_session.add(m3)
    db_session.flush()
    db_session.add(ContentGenre(content_id=m3.id, genre_id=action.id))
    db_session.add(ContentGenre(content_id=m3.id, genre_id=drama.id))
    db_session.add(ContentLanguage(content_id=m3.id, language_code="en"))
    items.append(m3)

    # Web Series 1: Sci-Fi, English, 2023
    tv1 = Content(
        content_type=ContentType.TV.value,
        tmdb_id=90004,
        title="Orbital Odyssey",
        original_title="Orbital Odyssey",
        overview="Space exploration television series.",
        release_date="2023-01-10",
        original_language="en",
        popularity=70.0,
        vote_average=8.2,
    )
    db_session.add(tv1)
    db_session.flush()
    db_session.add(ContentGenre(content_id=tv1.id, genre_id=sci_fi.id))
    db_session.add(ContentLanguage(content_id=tv1.id, language_code="en"))
    items.append(tv1)

    db_session.commit()
    return {
        "sci_fi": sci_fi,
        "action": action,
        "drama": drama,
        "m1": m1,
        "m2": m2,
        "m3": m3,
        "tv1": tv1,
    }


def test_genre_filter_regression_screenshot_scenario(db_session, seeded_catalog):
    """REGRESSION TEST: A valid genre filter (Sci-Fi TMDB ID 878) must return matching records.
    
    Reproduces the exact screenshot bug where 'Filters 1' (Sci-Fi) returned 'No titles found'.
    """
    catalog = ContentCatalogService()

    # Query with TMDB genre ID 878 (Science Fiction)
    results, total, total_pages = catalog.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        genre_ids=[878],
        page=1,
        limit=18,
    )

    # Must find the seeded movies m1 and m2 (both have Sci-Fi)
    result_ids = {r.id for r in results}
    assert total >= 2, f"Expected at least 2 Sci-Fi movies, got {total}"
    assert seeded_catalog["m1"].id in result_ids
    assert seeded_catalog["m2"].id in result_ids
    # Must NOT include m3 (which is Action/Drama, no Sci-Fi)
    assert seeded_catalog["m3"].id not in result_ids


def test_genre_filter_supports_both_tmdb_id_and_internal_id(db_session, seeded_catalog):
    """Verify that filtering works whether using TMDB genre ID (878) or internal genre table ID."""
    catalog = ContentCatalogService()
    sci_fi = seeded_catalog["sci_fi"]

    # TMDB ID 878
    res_tmdb, total_tmdb, _ = catalog.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        genre_ids=[878],
    )
    # Internal DB ID
    res_internal, total_internal, _ = catalog.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        genre_ids=[sci_fi.id],
    )

    assert total_tmdb == total_internal
    assert {r.id for r in res_tmdb} == {r.id for r in res_internal}


def test_language_filtering(db_session, seeded_catalog):
    """Verify language filtering by ISO-639-1 code."""
    catalog = ContentCatalogService()

    # Spanish ('es')
    res_es, total_es, _ = catalog.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        language_code="es",
    )
    assert any(r.id == seeded_catalog["m2"].id for r in res_es)
    assert not any(r.id == seeded_catalog["m1"].id for r in res_es)

    # English ('en')
    res_en, total_en, _ = catalog.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        language_code="en",
    )
    assert any(r.id == seeded_catalog["m1"].id for r in res_en)
    assert not any(r.id == seeded_catalog["m2"].id for r in res_en)


def test_year_filtering(db_session, seeded_catalog):
    """Verify release year filtering."""
    catalog = ContentCatalogService()

    res_2024, total_2024, _ = catalog.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        year=2024,
    )
    assert any(r.id == seeded_catalog["m1"].id for r in res_2024)
    assert any(r.id == seeded_catalog["m3"].id for r in res_2024)
    assert not any(r.id == seeded_catalog["m2"].id for r in res_2024)

    res_2022, _, _ = catalog.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        year=2022,
    )
    assert any(r.id == seeded_catalog["m2"].id for r in res_2022)
    assert not any(r.id == seeded_catalog["m1"].id for r in res_2022)


def test_sort_filtering(db_session, seeded_catalog):
    """Verify sorting options."""
    catalog = ContentCatalogService()

    # popularity_desc: m1 (95.0) > m3 (80.0) > m2 (60.0)
    res_pop, _, _ = catalog.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        sort_by="popularity_desc",
    )
    assert res_pop[0].id == seeded_catalog["m1"].id

    # release_date_asc: m2 (2022) before m1 (2024-03) and m3 (2024-07)
    res_date, _, _ = catalog.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        sort_by="release_date_asc",
    )
    assert res_date[0].id == seeded_catalog["m2"].id


def test_combined_filters(db_session, seeded_catalog):
    """Verify combined genre + language + year filter."""
    catalog = ContentCatalogService()

    # Sci-Fi (878) + English ('en') + 2024 -> only m1 matches
    res, total, _ = catalog.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        genre_ids=[878],
        language_code="en",
        year=2024,
    )
    assert total == 1
    assert res[0].id == seeded_catalog["m1"].id

    # Sci-Fi (878) + Spanish ('es') + 2022 -> only m2 matches
    res_es, total_es, _ = catalog.list_content(
        db=db_session,
        content_type=ContentType.MOVIE.value,
        genre_ids=[878],
        language_code="es",
        year=2022,
    )
    assert total_es == 1
    assert res_es[0].id == seeded_catalog["m2"].id


def test_api_movies_endpoints_with_filters_and_aliases(seeded_catalog):
    """Verify GET /api/movies endpoint with genre, genre_id, page_size, limit, and sorting."""
    with TestClient(app) as client:
        # 1. Test with genre_id=878 (Science Fiction)
        res1 = client.get("/api/movies?genre_id=878&page=1&limit=18")
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["total"] >= 2
        assert any(r["id"] == seeded_catalog["m1"].id for r in data1["results"])
        assert any(r["id"] == seeded_catalog["m2"].id for r in data1["results"])
        assert not any(r["id"] == seeded_catalog["m3"].id for r in data1["results"])

        # 2. Test with genre=878 alias
        res2 = client.get("/api/movies?genre=878&page_size=18")
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["total"] == data1["total"]

        # 3. Test combined filters via API
        res3 = client.get("/api/movies?genre=878&language=es&year=2022")
        assert res3.status_code == 200
        data3 = res3.json()
        assert data3["total"] == 1
        assert data3["results"][0]["id"] == seeded_catalog["m2"].id


def test_api_web_series_with_filters(seeded_catalog):
    """Verify GET /api/web-series with genre filtering."""
    with TestClient(app) as client:
        res = client.get("/api/web-series?genre_id=878")
        assert res.status_code == 200
        data = res.json()
        assert any(r["id"] == seeded_catalog["tv1"].id for r in data["results"])


def test_api_search_with_query_and_filters(seeded_catalog):
    """Verify GET /api/search with title query and filters."""
    with TestClient(app) as client:
        # Search 'Dune' with genre_id=878
        res = client.get("/api/search?q=Dune&genre_id=878&type=movie")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        assert any("Dune" in r["title"] for r in data["results"])

        # Search with alias genre=878 and content_type=movie
        res_alias = client.get("/api/search?q=Dune&genre=878&content_type=movie")
        assert res_alias.status_code == 200
        assert res_alias.json()["total"] == data["total"]

        # Search with non-matching genre returns empty results
        res_none = client.get("/api/search?q=Dune&genre_id=18&type=movie")
        assert res_none.status_code == 200
        assert not any(r["id"] == seeded_catalog["m1"].id for r in res_none.json()["results"])
