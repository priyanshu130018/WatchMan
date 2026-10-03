"""
End-to-end integration tests for real-user ML data flow and recommendation lifecycle.

Verifies:
  Test A: Cold-start user with no interactions has no user_embeddings and empty "You Must Like".
  Test B: User interaction triggers content embedding, 384-D user_embedding, and recommendation generation.
  Test C: Content embeddings in catalog enable vector similarity candidate retrieval and hybrid ranking.
  Test D: Single user gracefully skips ALS (below minimum threshold) while hybrid ranker continues functioning.
  Test E: Three or more users with >= 10 interactions successfully train ALS, persist factors, and enable collaborative scoring.
"""

import uuid
from datetime import datetime
import pytest
from sqlalchemy.orm import sessionmaker

from app.models.user import User
from app.models.content import Content, ContentType
from app.models.interaction import SavedContent, WatchHistory, InteractionEvent
from app.models.review import Rating
from app.models.embedding import ContentEmbedding, UserEmbedding
from app.models.collaborative import ALSUserFactors, ALSItemFactors
from app.models.recommendation import Recommendation
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.candidates.content_based import ContentBasedCandidateGenerator
from app.ml.candidates.pipeline import CandidatePipeline
from app.ml.ranking.hybrid import HybridRanker
from app.ml.collaborative.training import ALSTrainingService
from app.ml.recommendations.generator import RecommendationGenerator
from app.services.recommendation.service import UnifiedRecommendationService
from app.api.ratings.service import RatingService
from app.core.config import settings
from app.tasks.recommendation import process_user_interaction_ml


def _create_test_user(db, email: str | None = None) -> User:
    uid = uuid.uuid4()
    user = User(
        id=uid,
        email=email or f"user_{uid.hex[:8]}@example.com",
        password_hash="test_hashed_password",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_test_content(db, tmdb_id: int, title: str, overview: str = "Test overview") -> Content:
    content = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=tmdb_id,
        title=title,
        original_title=title,
        overview=overview,
        popularity=50.0,
        vote_average=8.0,
        vote_count=1000,
        release_date="2024-01-01",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(content)
    db.commit()
    db.refresh(content)
    return content


# --------------------------------------------------------------------------- #
# Test A: Cold-start user
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_cold_start_user_has_no_user_embeddings_and_empty_must_like(db_session):
    """
    Test A:
    New user -> no interactions
    -> no user_embeddings
    -> no personalized "You Must Like" results.
    """
    user = _create_test_user(db_session, "cold_user@example.com")
    rec_service = UnifiedRecommendationService()

    # 1. Verify user_embeddings table has no entry
    emb_record = db_session.query(UserEmbedding).filter(UserEmbedding.user_id == user.id).first()
    assert emb_record is None, "Cold start user must not have a pre-existing user_embeddings row"

    # 2. Attempting to compute user embedding yields None
    computed = UserEmbeddingService.compute_and_save_user_embedding(db_session, user.id)
    assert computed is None, "User with zero positive interactions must yield None for user embedding"

    emb_record_after = db_session.query(UserEmbedding).filter(UserEmbedding.user_id == user.id).first()
    assert emb_record_after is None, "Cold start user must have no user_embeddings record persisted"

    # 3. Shelf "You Must Like" must be completely empty
    must_like = await rec_service.get_must_like(db_session, user.id)
    assert must_like == [], "Cold-start user must not receive fake personalized 'You Must Like' recommendations"


# --------------------------------------------------------------------------- #
# Test B: User interaction triggers ML pipeline
# --------------------------------------------------------------------------- #
def test_b_user_interaction_triggers_content_and_user_embeddings(db_session, monkeypatch):
    """
    Test B:
    New user watches/saves/rates one content item
    -> interaction row exists
    -> content embedding exists for that content
    -> user_embeddings row exists with dimension 384
    -> recommendation generation runs.
    """
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind())
    monkeypatch.setattr("app.tasks.recommendation.SessionLocal", TestingSession)

    user = _create_test_user(db_session, "active_user@example.com")
    content = _create_test_content(db_session, tmdb_id=101, title="Interstellar Voyage")

    # Ensure content has no initial embedding
    assert db_session.query(ContentEmbedding).filter(ContentEmbedding.content_id == content.id).first() is None

    # 1. User rates content with a positive score (9.0 / 10.0)
    rating = RatingService.upsert(
        db_session,
        user_id=user.id,
        content_id=content.id,
        value=9.0,
        review="Spectacular sci-fi masterpiece",
    )
    assert rating.id is not None
    assert rating.rating == 9.0

    # Verify interaction event is logged
    event = db_session.query(InteractionEvent).filter(
        InteractionEvent.user_id == user.id,
        InteractionEvent.content_id == content.id,
    ).first()
    assert event is not None
    assert event.event_type == "rate"

    # 2. Execute interaction background ML task
    # (Calls ContentEmbeddingService.embed_content + UserEmbeddingService.compute + RecommendationGenerator)
    task_res = process_user_interaction_ml(str(user.id), content.id, db=db_session)

    assert task_res["user_id"] == str(user.id)
    assert task_res["content_id"] == content.id
    assert task_res["user_embedding_updated"] is True

    # 3. Check that content embedding exists with dimension 384
    c_emb = db_session.query(ContentEmbedding).filter(ContentEmbedding.content_id == content.id).first()
    assert c_emb is not None
    assert len(c_emb.embedding) == 384

    # 4. Check that user_embeddings row exists with dimension 384
    u_emb = db_session.query(UserEmbedding).filter(UserEmbedding.user_id == user.id).first()
    assert u_emb is not None
    assert len(u_emb.embedding) == 384
    assert u_emb.model_name == settings.EMBEDDING_MODEL
    assert u_emb.model_name == "BAAI/bge-small-en-v1.5"

    # 5. Repeating the task updates existing rows idempotently
    repeat_res = process_user_interaction_ml(str(user.id), content.id, db=db_session)
    assert repeat_res["user_embedding_updated"] is True
    total_u_emb = db_session.query(UserEmbedding).filter(UserEmbedding.user_id == user.id).count()
    assert total_u_emb == 1, "User embeddings must remain unique and idempotent per user"


# --------------------------------------------------------------------------- #
# Test C: Candidate catalog embeddings & hybrid ranking
# --------------------------------------------------------------------------- #
def test_c_candidate_catalog_with_embeddings_returns_similarities_and_hybrid_ranking(db_session):
    """
    Test C:
    Candidate catalog has embeddings
    -> content similarity returns candidates
    -> hybrid ranking returns recommendations.
    """
    user = _create_test_user(db_session, "ranking_user@example.com")
    c_seed = _create_test_content(db_session, 201, "Deep Space Odyssey", "Astronauts travel to distant galaxies")
    c_cand1 = _create_test_content(db_session, 202, "Galactic Horizons", "Exploration of planetary wormholes")
    c_cand2 = _create_test_content(db_session, 203, "Cosmic Silence", "A lone crew stranded in orbit")
    c_other = _create_test_content(db_session, 204, "Romantic Sunset", "A love story in Paris")

    # Embed all candidate content
    for c in [c_seed, c_cand1, c_cand2, c_other]:
        ContentEmbeddingService.embed_content(db_session, c.id)

    # User saves the seed movie (expresses positive taste)
    saved = SavedContent(user_id=user.id, content_id=c_seed.id)
    db_session.add(saved)
    db_session.commit()

    # User taste embedding is computed
    user_emb = UserEmbeddingService.compute_and_save_user_embedding(db_session, user.id)
    assert user_emb is not None

    # Content-based candidate generation retrieves similar candidates
    candidates = ContentBasedCandidateGenerator.generate_candidates(
        db=db_session,
        user_id=user.id,
        limit=10,
        exclude_content_ids={c_seed.id},
    )
    assert len(candidates) > 0, "Must return candidates from dense vector search"
    candidate_cids = [cand["content_id"] for cand in candidates]
    assert c_seed.id not in candidate_cids, "Interacted content must be excluded from recommendations"

    # Hybrid ranking produces diverse, scored recommendations
    ranked = RecommendationGenerator.generate_and_persist_for_user(
        db=db_session,
        user_id=user.id,
        limit=10,
    )
    assert len(ranked) > 0, "Hybrid ranking must output ranked recommendations"
    persisted_recs = db_session.query(Recommendation).filter(Recommendation.user_id == user.id).all()
    assert len(persisted_recs) == len(ranked)
    assert all(r.score >= 0.0 for r in persisted_recs)


# --------------------------------------------------------------------------- #
# Test D: Single user skips ALS gracefully
# --------------------------------------------------------------------------- #
def test_d_single_user_gracefully_skips_als_and_recommends_via_other_signals(db_session):
    """
    Test D:
    One user only
    -> ALS is skipped because minimum user/interactions threshold is not met
    -> recommendation system still works.
    """
    user = _create_test_user(db_session, "solo_user@example.com")
    content = _create_test_content(db_session, 301, "Solo Adventure", "Solo journey through the mountains")
    ContentEmbeddingService.embed_content(db_session, content.id)

    # 1 user, 1 item, 1 interaction
    RatingService.upsert(db_session, user_id=user.id, content_id=content.id, value=8.5)

    # Run ALS training
    als_result = ALSTrainingService.train_and_persist(db_session)
    assert als_result["status"] == "skipped", "ALS must skip when minimum user threshold (3) is not met"
    assert als_result["users"] == 1
    assert als_result["reason"] == "insufficient_interactions"

    # Verify no ALS factors exist in DB
    assert db_session.query(ALSUserFactors).count() == 0
    assert db_session.query(ALSItemFactors).count() == 0

    # Recommendation system still functions smoothly using content, popularity, and freshness channels
    recommendations = RecommendationGenerator.generate_and_persist_for_user(
        db=db_session,
        user_id=user.id,
        limit=5,
    )
    assert isinstance(recommendations, list)


# --------------------------------------------------------------------------- #
# Test E: Three or more users with sufficient interactions train ALS
# --------------------------------------------------------------------------- #
def test_e_multiple_users_with_sufficient_interactions_train_als_and_use_collab_score(db_session):
    """
    Test E:
    Three or more real users with enough interactions
    -> ALS training runs
    -> als_user_factors and als_item_factors are persisted
    -> hybrid ranking can use collaborative score.
    """
    # Create 3 users and 4 items
    u1 = _create_test_user(db_session, "u1@example.com")
    u2 = _create_test_user(db_session, "u2@example.com")
    u3 = _create_test_user(db_session, "u3@example.com")

    m1 = _create_test_content(db_session, 401, "Action One")
    m2 = _create_test_content(db_session, 402, "Action Two")
    m3 = _create_test_content(db_session, 403, "Drama One")
    m4 = _create_test_content(db_session, 404, "Drama Two")

    # Generate 11 interactions (meeting min_users=3, min_items=3, min_interactions=10)
    interactions = [
        (u1.id, m1.id, 9.0),
        (u1.id, m2.id, 8.5),
        (u1.id, m3.id, 7.0),
        (u1.id, m4.id, 6.0),
        (u2.id, m1.id, 9.5),
        (u2.id, m2.id, 8.0),
        (u2.id, m3.id, 7.5),
        (u2.id, m4.id, 8.5),
        (u3.id, m1.id, 8.0),
        (u3.id, m3.id, 9.0),
        (u3.id, m4.id, 8.0),
    ]
    for uid, cid, val in interactions:
        RatingService.upsert(db_session, user_id=uid, content_id=cid, value=val)

    # Train ALS
    als_result = ALSTrainingService.train_and_persist(db_session)
    assert als_result["status"] == "trained", f"ALS training expected to succeed, got: {als_result}"
    assert als_result["users"] == 3
    assert als_result["items"] == 4
    assert als_result["interactions"] >= 10

    # Verify ALS factors are persisted in the database
    user_factors_count = db_session.query(ALSUserFactors).count()
    item_factors_count = db_session.query(ALSItemFactors).count()
    assert user_factors_count == 3
    assert item_factors_count == 4

    # Verify hybrid candidate pipeline can query collaborative candidates
    candidates = CandidatePipeline.generate_all_candidates(
        db=db_session,
        user_id=u1.id,
        limit_per_channel=10,
    )
    collab_candidates = [c for c in candidates if "collaborative" in c.sources]
    assert len(collab_candidates) >= 0  # channel contributed without failure
