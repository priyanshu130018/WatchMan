"""
Unit and integration tests for authentication-aware recommendations and cold-start behavior.

Verifies:
1. Unauthenticated requests to /api/recommendations return 401.
2. Cold-start user (no interactions/ratings/watch history) returns empty list and is_cold_start=True.
3. No fake/fixed popular recommendations are persisted for cold-start users.
4. Active user with genuine interaction signals receives real dynamic recommendations from the hybrid pipeline.
5. Cold-start user calling /api/recommendations/personalized returns empty list, not a hardcoded movie.
"""

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.models.user import User
from app.models.content import Content, ContentType
from app.models.taxonomy import Genre, ContentGenre
from app.models.interaction import SavedContent, WatchHistory, InteractionEvent
from app.models.review import Rating
from app.models.recommendation import Recommendation
from app.models.embedding import ContentEmbedding, UserEmbedding
from app.core.security import create_access_token
from app.api.auth.router import hash_password
from app.services.recommendation.service import UnifiedRecommendationService
from app.ml.recommendations.generator import RecommendationGenerator

# In-memory SQLite for fast, hermetic test runs
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seed_catalog(db_session):
    g1 = Genre(id=1, tmdb_id=878, name="Sci-Fi")
    g2 = Genre(id=2, tmdb_id=28, name="Action")
    db_session.add_all([g1, g2])
    db_session.commit()

    items = []
    # Seed 5 movies with embeddings and varying popularity
    for i in range(1, 6):
        c = Content(
            tmdb_id=2000 + i,
            content_type="movie",
            title=f"Catalog Movie {i}",
            overview=f"Overview of Movie {i}",
            runtime=110,
            vote_average=8.0,
            vote_count=500,
            popularity=100.0 - i,
            release_date="2024-01-01",
        )
        db_session.add(c)
        items.append(c)
    db_session.commit()

    for item in items:
        db_session.refresh(item)
        db_session.add(ContentGenre(content_id=item.id, genre_id=1))
        # Provide dummy 384-D vector so vector search works
        dummy_vec = [0.05 * (item.id % 10)] * 384
        db_session.add(
            ContentEmbedding(
                content_id=item.id,
                embedding=dummy_vec,
                model_version="1.0.0",
            )
        )
    db_session.commit()
    return items


def create_test_user(db_session, email_prefix: str) -> tuple[User, str]:
    user = User(
        id=uuid.uuid4(),
        email=f"{email_prefix}_{uuid.uuid4().hex[:6]}@example.com",
        username=f"{email_prefix}_{uuid.uuid4().hex[:6]}",
        password_hash=hash_password("Pass123!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(user.id)
    return user, token


def test_unauthenticated_recommendations_endpoint_returns_401(client):
    """Unauthenticated requests to /api/recommendations must be rejected."""
    res = client.get("/api/recommendations")
    assert res.status_code == 401


def test_cold_start_user_receives_empty_list_and_cold_start_flag(client, db_session, seed_catalog):
    """
    Cold-start user with no interactions must receive an empty list and is_cold_start=True.
    No fake popular recommendations should be returned or persisted.
    """
    user, token = create_test_user(db_session, "brand_new_cold")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/recommendations", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["is_cold_start"] is True

    # Verify no fake recommendations were persisted into recommendations table
    persisted = db_session.query(Recommendation).filter(Recommendation.user_id == user.id).all()
    assert len(persisted) == 0, "No recommendations should be persisted for a cold-start user"


def test_cold_start_user_personalized_route_returns_empty_results(client, db_session, seed_catalog):
    """The /personalized route must not return a hardcoded/fixed movie for cold users."""
    user, token = create_test_user(db_session, "cold_pers")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/recommendations/personalized", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["results"] == []


def test_page_view_events_alone_do_not_defeat_cold_start(client, db_session, seed_catalog):
    """Browsing/viewing a card (page_view event) without saving/rating must remain cold-start."""
    user, token = create_test_user(db_session, "browser_only")
    headers = {"Authorization": f"Bearer {token}"}

    # Simulate 3 page_view telemetry events
    for item in seed_catalog[:3]:
        db_session.add(
            InteractionEvent(
                user_id=user.id,
                content_id=item.id,
                event_type="page_view",
                event_value=1.0,
            )
        )
    db_session.commit()

    rec_service = UnifiedRecommendationService()
    assert rec_service.user_has_activity(db_session, user.id) is False

    res = client.get("/api/recommendations", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["is_cold_start"] is True


def test_active_user_with_interaction_receives_real_recommendations(client, db_session, seed_catalog):
    """
    User with genuine activity (saved item + positive rating) receives real
    recommendations from the hybrid pipeline, which are persisted.
    """
    user, token = create_test_user(db_session, "active_taste")
    headers = {"Authorization": f"Bearer {token}"}

    # User saves Movie 1 and rates Movie 2 positively
    db_session.add(SavedContent(user_id=user.id, content_id=seed_catalog[0].id))
    db_session.add(Rating(user_id=user.id, content_id=seed_catalog[1].id, rating=9.0))
    # Give user a taste vector
    user_vec = [0.05 * (seed_catalog[0].id % 10)] * 384
    db_session.add(UserEmbedding(user_id=user.id, embedding=user_vec, model_version="1.0.0"))
    db_session.commit()

    rec_service = UnifiedRecommendationService()
    assert rec_service.user_has_activity(db_session, user.id) is True

    res = client.get("/api/recommendations", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["is_cold_start"] is False
    assert len(data["items"]) > 0

    # Ensure recommendations exclude already seen items (Movie 1 and Movie 2)
    rec_ids = [it["id"] for it in data["items"]]
    assert seed_catalog[0].id not in rec_ids
    assert seed_catalog[1].id not in rec_ids

    # Verify recommendations are persisted in the database for this user
    persisted = db_session.query(Recommendation).filter(Recommendation.user_id == user.id).all()
    assert len(persisted) > 0
    persisted_ids = [r.content_id for r in persisted]
    assert seed_catalog[0].id not in persisted_ids


def test_stale_recommendations_pruned_if_user_loses_activity(client, db_session, seed_catalog):
    """If a user has no remaining activity, any stale recommendation rows are pruned."""
    user, token = create_test_user(db_session, "stale_cleanup")
    headers = {"Authorization": f"Bearer {token}"}

    # Artificially insert a stale recommendation row for this inactive user
    db_session.add(
        Recommendation(
            user_id=user.id,
            content_id=seed_catalog[0].id,
            score=0.99,
            rank=1,
            explanation="Old stale fake rec",
        )
    )
    db_session.commit()

    # Calling /api/recommendations should detect zero activity and prune it
    res = client.get("/api/recommendations", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["is_cold_start"] is True

    # Verify pruned from database
    rem = db_session.query(Recommendation).filter(Recommendation.user_id == user.id).count()
    assert rem == 0
