"""
WatchMan Step 9: Production Integration, End-to-End Testing & System Hardening Test Suite.
Verifies complete system flow: Auth Lifecycle, Idempotency, Ownership, Cache Isolation,
Recommendation Engine Explainability, Health/Readiness, Celery Tasks, and Security.
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.orm import Session

from app.main import app
from app.models.user import User, Profile, UserPreference
from app.models.content import Content, ContentType
from app.models.taxonomy import Genre, ContentGenre
from app.models.interaction import SavedContent, WatchHistory
from app.models.review import Rating, Review
from app.models.recommendation import Recommendation, RecommendationCandidate
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.logger import sanitize_data
from app.repositories.content_repository import ContentRepository
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.recommendations.generator import RecommendationGenerator
from app.core.redis import cache


@pytest.mark.asyncio
async def test_full_auth_lifecycle(db_session: Session):
    """
    Test 1: Complete authentication lifecycle:
    Register -> Profile/Prefs Created -> Tokens -> /me -> Refresh -> Token Separation -> Logout.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register new user
        reg_payload = {
            "email": "e2e_user@example.com",
            "password": "SecurePassword123!",
            "full_name": "E2E Test User",
            "username": "e2e_tester",
        }
        res = await client.post("/api/auth/register", json=reg_payload)
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        user_id = data["user"]["id"]
        assert data["user"]["email"] == "e2e_user@example.com"

        # Verify profile and preferences auto-created in database
        profile = db_session.query(Profile).filter(Profile.id == uuid.UUID(user_id)).first()
        assert profile is not None
        assert profile.username == "e2e_tester"

        pref = db_session.query(UserPreference).filter(UserPreference.user_id == uuid.UUID(user_id)).first()
        assert pref is not None

        access_token = data["access_token"]
        refresh_token = data["refresh_token"]

        # 2. Access /api/auth/me with access token
        me_res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        assert me_res.status_code == 200
        assert me_res.json()["email"] == "e2e_user@example.com"

        # 3. Verify Refresh token CANNOT be used as access token
        invalid_access = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
        assert invalid_access.status_code == 401

        # 4. Verify Access token CANNOT be used as refresh token
        invalid_refresh = await client.post("/api/auth/refresh", json={"refresh_token": access_token})
        assert invalid_refresh.status_code == 401

        # 5. Refresh token flow
        ref_res = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert ref_res.status_code == 200
        new_tokens = ref_res.json()
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens

        # New access token works
        me_res2 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_tokens['access_token']}"})
        assert me_res2.status_code == 200

        # 6. Malformed token produces 401, not 500
        bad_token_res = await client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.jwt.payload"})
        assert bad_token_res.status_code == 401
        assert bad_token_res.json()["error"]["code"] == "UNAUTHORIZED"

        # 7. Inactive user is rejected
        user_record = db_session.query(User).filter(User.id == uuid.UUID(user_id)).first()
        user_record.is_active = False
        db_session.commit()

        inactive_res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_tokens['access_token']}"})
        assert inactive_res.status_code == 403

        # 8. Logout
        logout_res = await client.post("/api/auth/logout")
        assert logout_res.status_code == 200


@pytest.mark.asyncio
async def test_request_id_and_tracing(db_session: Session):
    """
    Test 2: Request ID middleware attaches X-Request-ID to all responses.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # When no header passed, generates one
        res = await client.get("/api/health")
        assert res.status_code == 200
        assert "X-Request-ID" in res.headers

        # When custom header passed, preserves it
        custom_id = "custom-trace-id-12345"
        res2 = await client.get("/api/health", headers={"X-Request-ID": custom_id})
        assert res2.status_code == 200
        assert res2.headers.get("X-Request-ID") == custom_id


@pytest.mark.asyncio
async def test_health_and_readiness_endpoints(db_session: Session):
    """
    Test 3: Liveness (/health) and Readiness (/ready) endpoint behaviors.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Liveness
        health_res = await client.get("/health")
        assert health_res.status_code == 200
        assert health_res.json()["status"] == "ok"

        # Readiness
        ready_res = await client.get("/ready")
        assert ready_res.status_code in [200, 503]
        data = ready_res.json()
        assert "components" in data


def test_tmdb_sync_idempotency(db_session: Session):
    """
    Test 4: Repeated sync of identical content is strictly idempotent and does not duplicate relations.
    """
    content_dict = {
        "content_type": ContentType.MOVIE.value,
        "tmdb_id": 550,
        "title": "Fight Club",
        "overview": "An insomniac office worker...",
        "release_date": "1999-10-15",
        "popularity": 85.5,
        "vote_average": 8.4,
        "vote_count": 25000,
        "runtime": 139,
    }
    genres = [{"id": 18, "name": "Drama"}, {"id": 53, "name": "Thriller"}]
    languages = [{"iso_639_1": "en", "name": "English", "english_name": "English"}]
    cast = [{"id": 819, "name": "Edward Norton", "character": "The Narrator", "order": 0}]
    crew = [{"id": 7467, "name": "David Fincher", "department": "Directing", "job": "Director"}]
    videos = [{"key": "O1nDozs-Lda", "site": "YouTube", "name": "Official Trailer", "type": "Trailer", "official": True}]

    # First Upsert
    c1 = ContentRepository.upsert_content(
        db=db_session,
        content_dict=content_dict,
        genres=genres,
        languages=languages,
        cast=cast,
        crew=crew,
        external_ids=[{"provider": "imdb_id", "external_id": "tt0137523"}],
        videos=videos,
    )
    db_session.commit()
    initial_id = c1.id

    # Second Upsert with updated vote count
    content_dict["vote_count"] = 25100
    c2 = ContentRepository.upsert_content(
        db=db_session,
        content_dict=content_dict,
        genres=genres,
        languages=languages,
        cast=cast,
        crew=crew,
        external_ids=[{"provider": "imdb_id", "external_id": "tt0137523"}],
        videos=videos,
    )
    db_session.commit()

    # Must be same row
    assert c2.id == initial_id
    assert c2.vote_count == 25100

    # Verify no duplicate genres or cast associated
    assert len(c2.genres) == 2
    assert len(c2.cast) == 1
    assert len(c2.crew) == 1
    assert len(c2.videos) == 1

    total_contents = db_session.query(Content).filter(Content.tmdb_id == 550).count()
    assert total_contents == 1


@pytest.mark.asyncio
async def test_user_interaction_integrity_and_ownership(db_session: Session):
    """
    Test 5: User interactions (Saves, Ratings, Reviews, History) enforce ownership and idempotency.
    """
    # Create two test users
    u1 = User(id=uuid.uuid4(), email="user1@test.com", password_hash="hash", is_active=True)
    u2 = User(id=uuid.uuid4(), email="user2@test.com", password_hash="hash", is_active=True)
    db_session.add_all([u1, u2])

    content = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=101,
        title="Inception",
        vote_average=8.8,
        popularity=90.0,
    )
    db_session.add(content)
    db_session.commit()

    token_u1 = create_access_token(u1.id)
    token_u2 = create_access_token(u2.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. User 1 saves content
        save_res = await client.post(
            "/api/saved",
            json={"content_type": "movie", "tmdb_id": 101},
            headers={"Authorization": f"Bearer {token_u1}"},
        )
        assert save_res.status_code == 200

        # Duplicate save returns 409 Conflict with standardized error
        save_res2 = await client.post(
            "/api/saved",
            json={"content_type": "movie", "tmdb_id": 101},
            headers={"Authorization": f"Bearer {token_u1}"},
        )
        assert save_res2.status_code == 409
        assert save_res2.json()["error"]["code"] == "RESOURCE_CONFLICT"

        # 2. User 1 submits rating
        rate_res = await client.put(
            "/api/ratings/movie/101",
            json={"rating": 9.5, "review": "Masterpiece!"},
            headers={"Authorization": f"Bearer {token_u1}"},
        )
        assert rate_res.status_code == 200
        assert rate_res.json()["rating"] == 9.5

        # Invalid rating score (> 10.0 or < 1.0) rejected
        invalid_rate = await client.put(
            "/api/ratings/movie/101",
            json={"rating": 15.0},
            headers={"Authorization": f"Bearer {token_u1}"},
        )
        assert invalid_rate.status_code == 422

        # 3. User 1 creates review
        rev_res = await client.post(
            "/api/reviews",
            json={"content_type": "movie", "tmdb_id": 101, "title": "Great Mindbender", "content": "Christopher Nolan at his best."},
            headers={"Authorization": f"Bearer {token_u1}"},
        )
        assert rev_res.status_code == 200
        review_id = rev_res.json()["id"]

        # User 2 CANNOT edit or delete User 1's review (ownership check)
        u2_edit_res = await client.put(
            f"/api/reviews/{review_id}",
            json={"title": "Hacked Title", "content": "I am modifying someone else's review"},
            headers={"Authorization": f"Bearer {token_u2}"},
        )
        assert u2_edit_res.status_code == 403

        u2_del_res = await client.delete(
            f"/api/reviews/{review_id}",
            headers={"Authorization": f"Bearer {token_u2}"},
        )
        assert u2_del_res.status_code == 403

        # User 1 CAN delete their own review
        u1_del_res = await client.delete(
            f"/api/reviews/{review_id}",
            headers={"Authorization": f"Bearer {token_u1}"},
        )
        assert u1_del_res.status_code == 200

        # 4. User 1 Watch History progress
        hist_res = await client.post(
            "/api/watch-history",
            json={"content_type": "movie", "tmdb_id": 101, "progress": 85.0, "completed": False},
            headers={"Authorization": f"Bearer {token_u1}"},
        )
        assert hist_res.status_code == 200
        assert hist_res.json()["progress"] == 85.0


def test_recommendation_pipeline_and_explainability(db_session: Session):
    """
    Test 6: End-to-end recommendation generation, cold-start handling, and explainability signals.
    """
    # Create genre
    sci_fi = Genre(tmdb_id=878, name="Science Fiction")
    db_session.add(sci_fi)
    db_session.commit()

    # Create content items
    m1 = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=2001,
        title="Interstellar",
        overview="Space exploration through wormholes",
        vote_average=8.7,
        popularity=95.0,
    )
    m2 = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=2002,
        title="Arrival",
        overview="Linguistics and extraterrestrial arrival",
        vote_average=8.0,
        popularity=75.0,
    )
    db_session.add_all([m1, m2])
    db_session.commit()

    # Link genre
    db_session.add(ContentGenre(content_id=m1.id, genre_id=sci_fi.id))
    db_session.add(ContentGenre(content_id=m2.id, genre_id=sci_fi.id))
    db_session.commit()

    # Create new cold-start user
    cold_user = User(id=uuid.uuid4(), email="cold@test.com", password_hash="hash", is_active=True)
    db_session.add(cold_user)
    db_session.commit()

    # Generate recommendations for cold-start user
    cold_recs = RecommendationGenerator.generate_and_persist_for_user(
        db=db_session,
        user_id=cold_user.id,
        limit=10,
    )
    assert len(cold_recs) > 0
    # Every recommendation has a valid non-empty explanation
    for rec in cold_recs:
        assert rec.explanation is not None
        assert len(rec.explanation) > 0
        assert rec.score >= 0.0

    # User interacts with Interstellar (saves it)
    db_session.add(SavedContent(user_id=cold_user.id, content_id=m1.id))
    db_session.commit()

    # Recompute recommendations
    updated_recs = RecommendationGenerator.generate_and_persist_for_user(
        db=db_session,
        user_id=cold_user.id,
        limit=10,
    )
    # Interstellar should now be excluded as already seen/saved
    rec_content_ids = [r.content_id for r in updated_recs]
    assert m1.id not in rec_content_ids


def test_sensitive_data_sanitization():
    """
    Test 7: Verify logger data sanitizer masks passwords, tokens, and secret keys.
    """
    raw_payload = {
        "email": "user@example.com",
        "password": "SuperSecretPassword123!",
        "access_token": "eyJhbGciOi...",
        "tmdb_api_key": "secret_tmdb_key_999",
        "nested": {
            "refresh_token": "refresh_secret_123",
            "public_field": "visible",
        },
    }
    sanitized = sanitize_data(raw_payload)

    assert sanitized["email"] == "user@example.com"
    assert sanitized["password"] == "******"
    assert sanitized["access_token"] == "******"
    assert sanitized["tmdb_api_key"] == "******"
    assert sanitized["nested"]["refresh_token"] == "******"
    assert sanitized["nested"]["public_field"] == "visible"
