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
from app.models.embedding import ContentEmbedding, UserEmbedding
from app.models.interaction import SavedContent, WatchHistory, InteractionEvent
from app.models.review import Rating
from app.models.recommendation import Recommendation
from app.core.security import create_access_token
from app.api.auth.router import hash_password
from app.ml.embeddings.sentence_encoder import SentenceEncoder
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.candidates.content_based import ContentBasedCandidateGenerator
from app.ml.candidates.collaborative import CollaborativeCandidateGenerator
from app.ml.candidates.popularity import PopularityCandidateGenerator
from app.ml.candidates.freshness import FreshnessCandidateGenerator
from app.ml.candidates.pipeline import CandidatePipeline
from app.ml.ranking.hybrid import HybridRanker
from app.ml.recommendations.generator import RecommendationGenerator
from app.ml.evaluation.metrics import (
    precision_at_k,
    recall_at_k,
    hit_rate_at_k,
    mean_reciprocal_rank,
    ndcg_at_k,
    catalog_coverage,
    intra_list_diversity,
)

# Test SQLite in-memory DB
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
def sample_user(db_session):
    user = User(
        id=uuid.uuid4(),
        email=f"rec_user_{uuid.uuid4().hex[:8]}@example.com",
        username=f"rec_user_{uuid.uuid4().hex[:8]}",
        password_hash=hash_password("RecTestPass123!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    pref = UserPreference(
        user_id=user.id,
        favorite_genres=["Sci-Fi", "Action"],
        disliked_genres=[],
    )
    db_session.add(pref)
    db_session.commit()
    return user


@pytest.fixture
def sample_contents(db_session):
    genre_scifi = Genre(id=1, tmdb_id=878, name="Sci-Fi")
    genre_action = Genre(id=2, tmdb_id=28, name="Action")
    genre_drama = Genre(id=3, tmdb_id=18, name="Drama")
    db_session.add_all([genre_scifi, genre_action, genre_drama])
    db_session.commit()

    items = [
        Content(
            tmdb_id=101,
            content_type="movie",
            title="Interstellar Odyssey",
            overview="A thrilling journey across galaxies to save humanity.",
            tagline="Beyond the stars",
            release_date="2024-05-01",
            vote_average=8.8,
            vote_count=2500,
            popularity=150.0,
            original_language="en",
        ),
        Content(
            tmdb_id=102,
            content_type="movie",
            title="Cyber Matrix 2099",
            overview="Artificial intelligence takes over the neon underground metropolis.",
            tagline="The code is alive",
            release_date="2024-06-15",
            vote_average=8.2,
            vote_count=1800,
            popularity=120.0,
            original_language="en",
        ),
        Content(
            tmdb_id=103,
            content_type="tv",
            title="Galactic Chronicles",
            overview="An epic series following explorers on alien frontier worlds.",
            tagline="New worlds await",
            release_date="2024-07-20",
            vote_average=8.5,
            vote_count=1200,
            popularity=95.0,
            original_language="en",
        ),
        Content(
            tmdb_id=104,
            content_type="movie",
            title="Midnight Melody",
            overview="An emotional journey of a pianist finding redemption through love and music.",
            tagline="Listen to your heart",
            release_date="2023-01-10",
            vote_average=7.1,
            vote_count=500,
            popularity=40.0,
            original_language="fr",
        ),
    ]
    db_session.add_all(items)
    db_session.commit()
    for item in items:
        db_session.refresh(item)

    # Associate genres
    db_session.add(ContentGenre(content_id=items[0].id, genre_id=genre_scifi.id))
    db_session.add(ContentGenre(content_id=items[0].id, genre_id=genre_action.id))
    db_session.add(ContentGenre(content_id=items[1].id, genre_id=genre_scifi.id))
    db_session.add(ContentGenre(content_id=items[2].id, genre_id=genre_scifi.id))
    db_session.add(ContentGenre(content_id=items[3].id, genre_id=genre_drama.id))
    db_session.commit()

    return items


def test_sentence_encoder_singleton_and_dimensions():
    encoder = SentenceEncoder.get_instance()
    assert encoder is not None
    vec = encoder.encode("Inception thriller dream sci-fi")
    assert len(vec) == 384
    batch_vecs = encoder.encode_batch(["Movie one", "Movie two"])
    assert len(batch_vecs) == 2
    assert len(batch_vecs[0]) == 384


def test_content_embedding_generation_and_idempotency(db_session, sample_contents):
    content_item = sample_contents[0]
    emb = ContentEmbeddingService.embed_content(db_session, content_item.id)
    assert emb is not None
    assert emb.content_id == content_item.id
    assert emb.dimension == 384
    assert emb.content_hash is not None

    # Idempotent re-run should return existing
    emb2 = ContentEmbeddingService.embed_content(db_session, content_item.id, force=False)
    assert emb2.id == emb.id


def test_user_embedding_aggregation(db_session, sample_user, sample_contents):
    content_scifi = sample_contents[0]

    # Add positive signals for user
    db_session.add(SavedContent(user_id=sample_user.id, content_id=content_scifi.id))
    db_session.add(Rating(user_id=sample_user.id, content_id=content_scifi.id, rating=5.0))
    db_session.add(WatchHistory(user_id=sample_user.id, content_id=content_scifi.id, progress=0.9, completed=True))
    db_session.commit()

    user_emb = UserEmbeddingService.compute_and_save_user_embedding(db_session, sample_user.id)
    assert user_emb is not None
    assert user_emb.user_id == sample_user.id
    assert len(user_emb.embedding) == 384


def test_candidate_generators(db_session, sample_user, sample_contents):
    # 1. Content-based candidates
    cb_cands = ContentBasedCandidateGenerator.generate_candidates(db_session, sample_user.id, limit=10)
    assert isinstance(cb_cands, list)

    # 2. Popularity candidates
    pop_cands = PopularityCandidateGenerator.generate_candidates(db_session, limit=10)
    assert len(pop_cands) > 0
    assert pop_cands[0]["score"] >= pop_cands[-1]["score"]

    # 3. Freshness candidates
    fresh_cands = FreshnessCandidateGenerator.generate_candidates(db_session, limit=10)
    assert len(fresh_cands) > 0

    # 4. Multi-channel candidate pipeline
    all_cands = CandidatePipeline.generate_all_candidates(db_session, sample_user.id, limit_per_channel=10)
    assert len(all_cands) > 0


def test_hybrid_ranking_and_diversity(db_session, sample_user, sample_contents):
    candidates = CandidatePipeline.generate_all_candidates(db_session, sample_user.id, limit_per_channel=10)
    ranked = HybridRanker.rank_candidates(db_session, sample_user.id, candidates, limit=10)
    assert len(ranked) > 0
    for r in ranked:
        assert 0.0 <= r.score <= 1.0
        assert r.explanation is not None
        assert len(r.explanation) > 0


def test_recommendation_generator_persistence(db_session, sample_user, sample_contents):
    ranked = RecommendationGenerator.generate_and_persist_for_user(db_session, sample_user.id, limit=10)
    assert len(ranked) > 0

    persisted = db_session.query(Recommendation).filter(Recommendation.user_id == sample_user.id).all()
    assert len(persisted) == len(ranked)


def test_evaluation_metrics():
    recommended = [101, 102, 103, 104, 105]
    relevant = {101, 103, 109}

    assert precision_at_k(recommended, relevant, k=3) == pytest.approx(2 / 3, 0.01)
    assert recall_at_k(recommended, relevant, k=5) == pytest.approx(2 / 3, 0.01)
    assert hit_rate_at_k(recommended, relevant, k=5) == 1.0
    assert hit_rate_at_k([201, 202], relevant, k=2) == 0.0
    assert mean_reciprocal_rank(recommended, relevant) == 1.0  # First item 101 is relevant
    assert ndcg_at_k(recommended, relevant, k=5) > 0.5
    assert catalog_coverage([101, 102], [101, 102, 103, 104]) == 0.5

    genres = [["Action", "Sci-Fi"], ["Drama"], ["Comedy", "Romance"]]
    diversity = intra_list_diversity(genres)
    assert diversity > 0.0


def test_api_recommendations_endpoints(client, sample_user, sample_contents):
    token = create_access_token(str(sample_user.id))
    headers = {"Authorization": f"Bearer {token}"}

    # 1. GET /api/recommendations
    response = client.get("/api/recommendations", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data

    # 2. GET /api/recommendations?content_type=movie
    response_movie = client.get("/api/recommendations?content_type=movie", headers=headers)
    assert response_movie.status_code == 200
    data_movie = response_movie.json()
    for item in data_movie["items"]:
        assert item["content_type"] == "movie"

    # 3. POST /api/recommendations/refresh
    response_refresh = client.post("/api/recommendations/refresh", headers=headers)
    assert response_refresh.status_code == 200
    assert response_refresh.json()["status"] == "success"

    # 4. GET /api/recommendations/{content_type}/{tmdb_id}
    item_tmdb = sample_contents[0].tmdb_id
    response_similar = client.get(f"/api/recommendations/movie/{item_tmdb}")
    assert response_similar.status_code == 200
    assert "results" in response_similar.json()

    # 5. GET /api/recommendations/personalized (backward-compatibility alias)
    response_legacy = client.get("/api/recommendations/personalized", headers=headers)
    assert response_legacy.status_code == 200
    assert "results" in response_legacy.json()
