import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.models.user import User, UserPreference
from app.models.content import Content
from app.models.taxonomy import Genre, ContentGenre
from app.models.interaction import SavedContent, WatchHistory, InteractionEvent
from app.models.review import Rating
from app.models.watchman import WatchmanDecision
from app.models.recommendation import Recommendation
from app.core.security import create_access_token
from app.api.auth.router import hash_password
from app.services.recommendation.service import UnifiedRecommendationService

# SQLite in-memory test database
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
def test_movies(db_session):
    g1 = Genre(id=1, tmdb_id=878, name="Sci-Fi")
    g2 = Genre(id=2, tmdb_id=28, name="Action")
    db_session.add_all([g1, g2])
    db_session.commit()

    movies = []
    for i in range(1, 11):
        c = Content(
            tmdb_id=1000 + i,
            content_type="movie",
            title=f"Movie {i}",
            overview=f"Overview of Movie {i}",
            runtime=120,
            vote_average=7.5 + (i * 0.1),
            vote_count=1000,
            popularity=100.0 - i,
            release_date="2024-01-01",
        )
        db_session.add(c)
        movies.append(c)
    db_session.commit()
    for m in movies:
        db_session.refresh(m)
        db_session.add(ContentGenre(content_id=m.id, genre_id=1))
    db_session.commit()
    return movies


def create_user(db_session, email_prefix: str) -> tuple[User, str]:
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


# 1. Cold-start user returns no personalized shelves
def test_cold_start_user_returns_no_personalized_shelves(client, db_session, test_movies):
    user, token = create_user(db_session, "cold_user")
    headers = {"Authorization": f"Bearer {token}"}

    # Unified home endpoint
    res = client.get("/api/recommendations/home", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["has_personalization"] is False
    assert len(data["sections"]) == 0

    # Individual shelf endpoints
    res_ml = client.get("/api/recommendations/must-like", headers=headers)
    assert res_ml.status_code == 200
    assert len(res_ml.json()["items"]) == 0

    res_wl = client.get("/api/recommendations/watched-liked", headers=headers)
    assert res_wl.status_code == 200
    assert len(res_wl.json()["items"]) == 0

    res_cw = client.get("/api/recommendations/continue-watching", headers=headers)
    assert res_cw.status_code == 200
    assert len(res_cw.json()["items"]) == 0


# 2. Must Like uses recommendation engine (persisted / hybrid)
def test_must_like_uses_recommendation_engine(client, db_session, test_movies):
    user, token = create_user(db_session, "active_user")
    headers = {"Authorization": f"Bearer {token}"}

    # Add genuine activity for user: Rating on Movie 1
    db_session.add(Rating(user_id=user.id, content_id=test_movies[0].id, rating=9.0))
    # Persist recommendation for Movie 2 & Movie 3
    db_session.add(Recommendation(user_id=user.id, content_id=test_movies[1].id, score=0.92, rank=1, explanation="Top hybrid match"))
    db_session.add(Recommendation(user_id=user.id, content_id=test_movies[2].id, score=0.88, rank=2, explanation="Strong collaborative signal"))
    db_session.commit()

    res = client.get("/api/recommendations/must-like", headers=headers)
    assert res.status_code == 200
    data = res.json()
    items = data["items"]
    assert len(items) >= 2
    ids = [it["id"] for it in items]
    assert test_movies[1].id in ids
    assert test_movies[2].id in ids


# 3. Watched & Liked only contains actually watched and positively rated/decided content
def test_watched_and_liked_only_contains_actually_watched_positive_content(client, db_session, test_movies):
    user, token = create_user(db_session, "wl_user")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Saved only (Movie 1) -> NOT watched, must NOT appear
    db_session.add(SavedContent(user_id=user.id, content_id=test_movies[0].id))

    # 2. Watched only 2% (Movie 2) -> Below meaningful threshold, must NOT appear
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[1].id, progress=2.0, completed=False))

    # 3. Completed watch (Movie 3, completed=True) -> MUST appear
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[2].id, progress=100.0, completed=True))

    # 4. Watched 70% with positive rating 9.0 (Movie 4) -> MUST appear
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[3].id, progress=70.0, completed=False))
    db_session.add(Rating(user_id=user.id, content_id=test_movies[3].id, rating=9.0))

    # 5. Watched 80% with WatchMan decision must_watch (Movie 5) -> MUST appear
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[4].id, progress=80.0, completed=False))
    db_session.add(WatchmanDecision(user_id=user.id, content_id=test_movies[4].id, decision="must_watch"))

    # 6. Watched 80% with negative rating 3.0 (Movie 6) -> Disqualified, must NOT appear
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[5].id, progress=80.0, completed=False))
    db_session.add(Rating(user_id=user.id, content_id=test_movies[5].id, rating=3.0))

    # 7. Completed 100% but marked skip (Movie 7) -> Disqualified, must NOT appear
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[6].id, progress=100.0, completed=True))
    db_session.add(WatchmanDecision(user_id=user.id, content_id=test_movies[6].id, decision="skip"))

    db_session.commit()

    res = client.get("/api/recommendations/watched-liked", headers=headers)
    assert res.status_code == 200
    items = res.json()["items"]
    item_ids = {it["id"] for it in items}

    assert test_movies[0].id not in item_ids, "Saved-only must NOT appear in Watched & Liked"
    assert test_movies[1].id not in item_ids, "2% watch must NOT appear in Watched & Liked"
    assert test_movies[2].id in item_ids, "Completed watch MUST appear in Watched & Liked"
    assert test_movies[3].id in item_ids, "Watched with rating 9.0 MUST appear in Watched & Liked"
    assert test_movies[4].id in item_ids, "Watched with must_watch decision MUST appear in Watched & Liked"
    assert test_movies[5].id not in item_ids, "Negative rating must NOT appear in Watched & Liked"
    assert test_movies[6].id not in item_ids, "Skipped title must NOT appear in Watched & Liked"


# 4. Continue Watching only contains incomplete playback (5% < progress < 90%)
def test_continue_watching_only_contains_incomplete_playback(client, db_session, test_movies):
    user, token = create_user(db_session, "cw_user")
    headers = {"Authorization": f"Bearer {token}"}

    # Movie 1: 45% progress, incomplete -> MUST qualify
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[0].id, progress=45.0, completed=False))

    # Movie 2: 2% progress (below starting threshold 5%) -> Disqualified
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[1].id, progress=2.0, completed=False))

    # Movie 3: 92% progress (above completion threshold 90%) -> Disqualified
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[2].id, progress=92.0, completed=False))

    # Movie 4: 0.65 ratio (65% progress) -> MUST qualify
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[3].id, progress=0.65, completed=False))

    db_session.commit()

    res = client.get("/api/recommendations/continue-watching", headers=headers)
    assert res.status_code == 200
    items = res.json()["items"]
    item_ids = {it["id"] for it in items}

    assert test_movies[0].id in item_ids
    assert test_movies[1].id not in item_ids
    assert test_movies[2].id not in item_ids
    assert test_movies[3].id in item_ids

    # Verify progress fields on card item
    item_45 = next(it for it in items if it["id"] == test_movies[0].id)
    assert item_45["progress"] == 45.0
    assert item_45["completed"] is False
    assert item_45["duration_seconds"] == test_movies[0].runtime * 60


# 5. Completed content excluded from Continue Watching
def test_completed_content_excluded_from_continue_watching(client, db_session, test_movies):
    user, token = create_user(db_session, "cw_comp_user")
    headers = {"Authorization": f"Bearer {token}"}

    # Movie 1: completed=True with 100% progress
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[0].id, progress=100.0, completed=True))
    # Movie 2: completed=True with 50% progress (e.g. user manually marked as completed)
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[1].id, progress=50.0, completed=True))
    db_session.commit()

    res = client.get("/api/recommendations/continue-watching", headers=headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 0


# 6. Skipped content suppressed appropriately
def test_skipped_content_suppressed_appropriately(client, db_session, test_movies):
    user, token = create_user(db_session, "skip_user")
    headers = {"Authorization": f"Bearer {token}"}

    # Give user general activity so cold start passes
    db_session.add(Rating(user_id=user.id, content_id=test_movies[0].id, rating=8.0))

    # Mark Movie 2 as skip in WatchmanDecision
    db_session.add(WatchmanDecision(user_id=user.id, content_id=test_movies[1].id, decision="skip"))

    # Also simulate Recommendation existing for Movie 2 & Movie 3
    db_session.add(Recommendation(user_id=user.id, content_id=test_movies[1].id, score=0.95, rank=1))
    db_session.add(Recommendation(user_id=user.id, content_id=test_movies[2].id, score=0.85, rank=2))
    db_session.commit()

    res = client.get("/api/recommendations/must-like", headers=headers)
    assert res.status_code == 200
    items = res.json()["items"]
    ids = [it["id"] for it in items]

    assert test_movies[1].id not in ids, "Explicitly skipped content must NOT appear in Must Like"
    assert test_movies[2].id in ids, "Non-skipped candidate should appear"


# 7. Duplicate titles removed between shelves in priority order (CW > WL > ML)
def test_duplicate_titles_removed_between_shelves(client, db_session, test_movies):
    user, token = create_user(db_session, "dedupe_user")
    headers = {"Authorization": f"Bearer {token}"}

    # Movie 1 is in Continue Watching (40% progress)
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[0].id, progress=40.0, completed=False))

    # Movie 2 is completed & rated 10/10 -> Watched & Liked
    db_session.add(WatchHistory(user_id=user.id, content_id=test_movies[1].id, progress=100.0, completed=True))
    db_session.add(Rating(user_id=user.id, content_id=test_movies[1].id, rating=10.0))

    # Recommendation table recommends Movie 1 (in CW), Movie 2 (in WL), and Movie 3 (new)
    db_session.add(Recommendation(user_id=user.id, content_id=test_movies[0].id, score=0.99, rank=1))
    db_session.add(Recommendation(user_id=user.id, content_id=test_movies[1].id, score=0.95, rank=2))
    db_session.add(Recommendation(user_id=user.id, content_id=test_movies[2].id, score=0.90, rank=3))
    db_session.commit()

    res = client.get("/api/recommendations/home", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["has_personalization"] is True

    sections = {s["key"]: s["items"] for s in data["sections"]}

    cw_items = sections.get("continue_watching", [])
    wl_items = sections.get("watched_liked", [])
    ml_items = sections.get("must_like", [])

    cw_ids = {it["id"] for it in cw_items}
    wl_ids = {it["id"] for it in wl_items}
    ml_ids = {it["id"] for it in ml_items}

    # Movie 1 is in Continue Watching
    assert test_movies[0].id in cw_ids
    # Movie 1 must NOT appear in Watched & Liked or Must Like
    assert test_movies[0].id not in wl_ids
    assert test_movies[0].id not in ml_ids

    # Movie 2 is in Watched & Liked
    assert test_movies[1].id in wl_ids
    # Movie 2 must NOT appear in Continue Watching or Must Like
    assert test_movies[1].id not in cw_ids
    assert test_movies[1].id not in ml_ids

    # Movie 3 is in Must Like
    assert test_movies[2].id in ml_ids
    assert test_movies[2].id not in cw_ids
    assert test_movies[2].id not in wl_ids


# 8. User A cannot receive User B's personalized data (isolation)
def test_user_a_cannot_receive_user_b_personalized_data(client, db_session, test_movies):
    user_a, token_a = create_user(db_session, "user_alpha")
    user_b, token_b = create_user(db_session, "user_beta")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A watches Movie 1 with 50% progress
    db_session.add(WatchHistory(user_id=user_a.id, content_id=test_movies[0].id, progress=50.0, completed=False))
    db_session.commit()

    # User A sees Movie 1 in continue watching
    res_a = client.get("/api/recommendations/home", headers=headers_a)
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["has_personalization"] is True
    cw_a = next(s for s in data_a["sections"] if s["key"] == "continue_watching")
    assert any(it["id"] == test_movies[0].id for it in cw_a["items"])

    # User B has no activity -> cold start, completely isolated from User A
    res_b = client.get("/api/recommendations/home", headers=headers_b)
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["has_personalization"] is False
    assert len(data_b["sections"]) == 0
