"""Comprehensive unit and integration tests for the Unified Content Domain and Database Foundation."""

import uuid
from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient

from app.db.base import Base
from app.models.content import Content, ContentType, ContentExternalId, ContentVideo
from app.models.taxonomy import Genre, ContentGenre, Language, ContentLanguage
from app.models.people import Person, ContentCast, ContentCrew
from app.models.user import User
from app.models.interaction import SavedContent, WatchHistory, InteractionEvent, SearchHistory
from app.models.review import Rating, Review
from app.models.embedding import ContentEmbedding, UserEmbedding
from app.repositories.content_repository import ContentRepository
from app.services.catalog import ContentCatalogService
from app.services.tmdb.service import TMDBService
from app.main import app


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# =============================================================================
# 1. Content Identity Tests (Composite Uniqueness)
# =============================================================================

def test_same_tmdb_id_different_content_types_allowed(db_session):
    """Movie and TV show with identical numeric TMDB ID must coexist without conflict."""
    movie = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=550,
        title="Fight Club",
        release_date="1999-10-15",
        runtime=139,
    )
    tv_show = Content(
        content_type=ContentType.TV.value,
        tmdb_id=550,
        title="Fight Club The Series",
        release_date="2020-01-01",
        number_of_seasons=2,
        number_of_episodes=20,
    )
    db_session.add_all([movie, tv_show])
    db_session.commit()

    assert movie.id != tv_show.id
    assert movie.tmdb_id == tv_show.tmdb_id == 550
    assert movie.content_type == "movie"
    assert tv_show.content_type == "tv"


def test_duplicate_movie_tmdb_id_fails(db_session):
    """Two movie records with the same TMDB ID must violate uniqueness constraint."""
    movie1 = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=550,
        title="Fight Club",
    )
    movie2 = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=550,
        title="Fight Club Duplicate",
    )
    db_session.add(movie1)
    db_session.commit()

    db_session.add(movie2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_tv_tmdb_id_fails(db_session):
    """Two TV records with the same TMDB ID must violate uniqueness constraint."""
    tv1 = Content(
        content_type=ContentType.TV.value,
        tmdb_id=1399,
        title="Game of Thrones",
    )
    tv2 = Content(
        content_type=ContentType.TV.value,
        tmdb_id=1399,
        title="Game of Thrones Duplicate",
    )
    db_session.add(tv1)
    db_session.commit()

    db_session.add(tv2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# =============================================================================
# 2. Normalized Relational Architecture Tests
# =============================================================================

def test_content_genres_and_languages_relationships(db_session):
    """Verify content relates to normalized genres and languages with uniqueness."""
    content = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=100,
        title="Inception",
    )
    db_session.add(content)
    db_session.commit()

    genre1 = ContentRepository.get_or_create_genre(db_session, tmdb_id=28, name="Action")
    genre2 = ContentRepository.get_or_create_genre(db_session, tmdb_id=878, name="Science Fiction")
    lang_en = ContentRepository.get_or_create_language(db_session, code="en", name="English", english_name="English")

    db_session.add(ContentGenre(content_id=content.id, genre_id=genre1.id))
    db_session.add(ContentGenre(content_id=content.id, genre_id=genre2.id))
    db_session.add(ContentLanguage(content_id=content.id, language_code=lang_en.code))
    db_session.commit()

    reloaded = ContentRepository.get_by_id(db_session, content.id)
    assert len(reloaded.genres) == 2
    assert {g.genre.name for g in reloaded.genres} == {"Action", "Science Fiction"}
    assert len(reloaded.languages) == 1
    assert reloaded.languages[0].language.code == "en"


def test_content_cast_crew_external_ids_videos(db_session):
    """Verify cast, crew, external IDs, and videos link to content properly."""
    content = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=603,
        title="The Matrix",
    )
    db_session.add(content)
    db_session.commit()

    # People
    keanu = ContentRepository.get_or_create_person(
        db_session, tmdb_id=6384, name="Keanu Reeves", known_for_department="Acting"
    )
    lana = ContentRepository.get_or_create_person(
        db_session, tmdb_id=9339, name="Lana Wachowski", known_for_department="Directing"
    )

    db_session.add(
        ContentCast(
            content_id=content.id,
            person_id=keanu.id,
            character="Neo",
            cast_order=0,
        )
    )
    db_session.add(
        ContentCrew(
            content_id=content.id,
            person_id=lana.id,
            department="Directing",
            job="Director",
        )
    )
    db_session.add(
        ContentExternalId(
            content_id=content.id,
            provider="imdb",
            external_id="tt0133093",
        )
    )
    db_session.add(
        ContentVideo(
            content_id=content.id,
            key="vKQi3bBA1y8",
            site="YouTube",
            name="Official Trailer",
            type="Trailer",
            official=True,
        )
    )
    db_session.commit()

    reloaded = ContentRepository.get_by_id(db_session, content.id)
    assert len(reloaded.cast) == 1
    assert reloaded.cast[0].person.name == "Keanu Reeves"
    assert reloaded.cast[0].character == "Neo"

    assert len(reloaded.crew) == 1
    assert reloaded.crew[0].person.name == "Lana Wachowski"
    assert reloaded.crew[0].job == "Director"

    assert len(reloaded.external_ids) == 1
    assert reloaded.external_ids[0].provider == "imdb"
    assert reloaded.external_ids[0].external_id == "tt0133093"

    assert len(reloaded.videos) == 1
    assert reloaded.videos[0].key == "vKQi3bBA1y8"


# =============================================================================
# 3. User Interactions & Relationship Integrity
# =============================================================================

def test_saved_content_duplicate_prevention(db_session):
    """User cannot save the exact same content item twice."""
    user = User(
        id=uuid.uuid4(),
        email="testuser@example.com",
        password_hash="hash123",
    )
    content = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=1234,
        title="Test Movie",
    )
    db_session.add_all([user, content])
    db_session.commit()

    save1 = SavedContent(user_id=user.id, content_id=content.id)
    db_session.add(save1)
    db_session.commit()

    save2 = SavedContent(user_id=user.id, content_id=content.id)
    db_session.add(save2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_rating_uniqueness_and_review(db_session):
    """User can rate a content item once and post reviews."""
    user = User(
        id=uuid.uuid4(),
        email="rater@example.com",
        password_hash="hash123",
    )
    content = Content(
        content_type=ContentType.TV.value,
        tmdb_id=5678,
        title="Test TV Show",
    )
    db_session.add_all([user, content])
    db_session.commit()

    rating1 = Rating(user_id=user.id, content_id=content.id, rating=4.5, review="Great show!")
    db_session.add(rating1)
    db_session.commit()

    # Duplicate rating must fail
    rating2 = Rating(user_id=user.id, content_id=content.id, rating=5.0)
    db_session.add(rating2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Review creation
    review = Review(
        user_id=user.id,
        content_id=content.id,
        rating=4.5,
        title="Masterpiece",
        content="Detailed long review text here.",
    )
    db_session.add(review)
    db_session.commit()
    assert review.id is not None


def test_watch_history_and_interaction_events(db_session):
    """Verify watch history progress and interaction events logging."""
    user = User(
        id=uuid.uuid4(),
        email="watcher@example.com",
        password_hash="hash123",
    )
    content = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=789,
        title="Interstellar",
    )
    db_session.add_all([user, content])
    db_session.commit()

    history = WatchHistory(
        user_id=user.id,
        content_id=content.id,
        progress=0.75,
        completed=False,
    )
    event = InteractionEvent(
        user_id=user.id,
        content_id=content.id,
        event_type="watch_progress",
        event_value=0.75,
        event_data={"device": "desktop"},
    )
    db_session.add_all([history, event])
    db_session.commit()

    assert history.id is not None
    assert event.id is not None
    assert history.movie_id == content.id  # backward compatibility property


# =============================================================================
# 4. Content Repository Layer Tests
# =============================================================================

def test_repository_list_filter_and_pagination(db_session):
    """Test pagination defaults to 16 and supports filtering by content_type, year, and sorting."""
    # Create 25 movie and TV items
    for i in range(1, 26):
        c_type = ContentType.MOVIE.value if i % 2 == 0 else ContentType.TV.value
        year = 2020 + (i % 5)
        content = Content(
            content_type=c_type,
            tmdb_id=1000 + i,
            title=f"Title {i:02d}",
            release_date=f"{year}-01-01",
            popularity=float(i * 10),
            vote_average=7.0 + (i * 0.1),
        )
        db_session.add(content)
    db_session.commit()

    # Default pagination: limit=16
    items, total = ContentRepository.list(db_session, limit=16)
    assert total == 25
    assert len(items) == 16
    # Default sort is popularity descending
    assert items[0].popularity > items[1].popularity

    # Filter by content_type = "movie"
    movies, total_movies = ContentRepository.list(
        db_session, content_type=ContentType.MOVIE.value, limit=16
    )
    assert total_movies == 12
    assert len(movies) == 12
    assert all(m.content_type == "movie" for m in movies)

    # Filter by year = 2022
    year_2022_items, total_2022 = ContentRepository.list(db_session, year=2022)
    assert total_2022 == 5
    assert all(item.release_date.startswith("2022") for item in year_2022_items)


def test_repository_search(db_session):
    """Test repository search across titles and overviews."""
    c1 = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=2001,
        title="Spider-Man No Way Home",
        overview="Peter Parker faces multiversal villains.",
    )
    c2 = Content(
        content_type=ContentType.TV.value,
        tmdb_id=2002,
        title="Spider-Man Animated Series",
        overview="Classic 90s animated adventure.",
    )
    c3 = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=2003,
        title="Batman Begins",
        overview="Bruce Wayne travels to the Himalayas.",
    )
    db_session.add_all([c1, c2, c3])
    db_session.commit()

    results, total = ContentRepository.search(db_session, query_str="Spider-Man")
    assert total == 2
    assert len(results) == 2

    # Filter search by content_type
    movie_results, m_total = ContentRepository.search(
        db_session, query_str="Spider-Man", content_type=ContentType.MOVIE.value
    )
    assert m_total == 1
    assert movie_results[0].title == "Spider-Man No Way Home"


# =============================================================================
# 5. TMDB Normalization & ContentCatalogService Ingestion
# =============================================================================

@pytest.mark.asyncio
async def test_catalog_service_normalizes_movies_and_tv(db_session):
    """Test ContentCatalogService correctly handles differences between Movie and TV payloads."""
    service = ContentCatalogService()

    movie_payload = {
        "id": 550,
        "title": "Fight Club",
        "original_title": "Fight Club",
        "overview": "An insomniac office worker...",
        "release_date": "1999-10-15",
        "runtime": 139,
        "popularity": 75.5,
        "vote_average": 8.4,
        "vote_count": 25000,
        "genres": [{"id": 18, "name": "Drama"}],
        "spoken_languages": [{"iso_639_1": "en", "name": "English", "english_name": "English"}],
    }

    tv_payload = {
        "id": 1399,
        "name": "Game of Thrones",
        "original_name": "Game of Thrones",
        "overview": "Seven noble families fight for control...",
        "first_air_date": "2011-04-17",
        "episode_run_time": [60],
        "number_of_seasons": 8,
        "number_of_episodes": 73,
        "popularity": 150.2,
        "vote_average": 8.4,
        "vote_count": 22000,
        "genres": [{"id": 10765, "name": "Sci-Fi & Fantasy"}],
        "spoken_languages": [{"iso_639_1": "en", "name": "English", "english_name": "English"}],
    }

    with patch.object(service.tmdb, "content_details", side_effect=lambda c_type, item_id: movie_payload if c_type == "movie" else tv_payload), \
         patch.object(service.tmdb, "content_credits", return_value={"cast": [{"id": 1, "name": "Actor A", "character": "Char A"}], "crew": []}), \
         patch.object(service.tmdb, "content_videos", return_value={"results": []}), \
         patch.object(service.tmdb, "content_external_ids", return_value={"imdb_id": "tt123456"}):

        # Sync Movie
        synced_movie = await service.sync_content(db_session, "movie", 550)
        assert synced_movie.content_type == "movie"
        assert synced_movie.title == "Fight Club"
        assert synced_movie.release_date == "1999-10-15"
        assert synced_movie.runtime == 139
        assert synced_movie.number_of_seasons is None

        # Sync TV
        synced_tv = await service.sync_content(db_session, "tv", 1399)
        assert synced_tv.content_type == "tv"
        assert synced_tv.title == "Game of Thrones"
        assert synced_tv.release_date == "2011-04-17"
        assert synced_tv.runtime == 60
        assert synced_tv.number_of_seasons == 8
        assert synced_tv.number_of_episodes == 73


# =============================================================================
# 6. API Route Contracts (Movies, Web Series, Trending)
# =============================================================================

def test_api_movie_and_web_series_and_trending_routes(client):
    """Ensure /api/movies, /api/web-series, /api/trending endpoints function according to contract."""
    with patch("app.services.tmdb.service.TMDBService.trending_movies") as mock_trend_m, \
         patch("app.services.tmdb.service.TMDBService.trending_tv") as mock_trend_tv, \
         patch("app.services.tmdb.service.TMDBService.trending_all") as mock_trend_all, \
         patch("app.services.tmdb.service.TMDBService.movie_details") as mock_movie_det, \
         patch("app.services.tmdb.service.TMDBService.tv_details") as mock_tv_det:

        mock_trend_m.return_value = {"page": 1, "results": [{"id": 1, "title": "Movie 1"}]}
        mock_trend_tv.return_value = {"page": 1, "results": [{"id": 2, "name": "Series 1"}]}
        mock_trend_all.return_value = {"page": 1, "results": [{"id": 1, "media_type": "movie"}]}
        mock_movie_det.return_value = {"id": 101, "title": "Movie Detail"}
        mock_tv_det.return_value = {"id": 202, "name": "TV Detail"}

        # Movies endpoints
        resp_m = client.get("/api/movies/trending")
        assert resp_m.status_code == 200
        assert resp_m.json()["results"][0]["title"] == "Movie 1"

        resp_md = client.get("/api/movies/101")
        assert resp_md.status_code == 200
        assert resp_md.json()["title"] == "Movie Detail"

        # Web-Series endpoints
        resp_tv = client.get("/api/web-series/trending")
        assert resp_tv.status_code == 200
        assert resp_tv.json()["results"][0]["name"] == "Series 1"

        resp_tvd = client.get("/api/web-series/202")
        assert resp_tvd.status_code == 200
        assert resp_tvd.json()["name"] == "TV Detail"

        # Trending unified endpoints
        resp_trend = client.get("/api/trending")
        assert resp_trend.status_code == 200
        assert resp_trend.json()["results"][0]["media_type"] == "movie"

        resp_trend_det = client.get("/api/trending/movie/101")
        assert resp_trend_det.status_code == 200
        assert resp_trend_det.json()["title"] == "Movie Detail"
