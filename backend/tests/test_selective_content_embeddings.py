"""
Tests for selective and on-demand content embedding strategy.

Covers:
  TEST A: Initial popular selection returns configured movies + TV series without embedding unrelated items.
  TEST B: Existing embedding is reused without creating a duplicate row.
  TEST C: Interaction with unembedded content creates exactly one embedding.
  TEST D: Second interaction with the same content does not create another embedding.
  TEST E: Content with stale content_hash or model_version regenerates appropriately.
  TEST F: Recommendation generation works when only a small subset of catalog items have embeddings.
  TEST G: Recommendation generation works with zero content embeddings.
  TEST H: Cold-start user does not receive a user embedding simply because catalog has embeddings.
  TEST I: Initial selective backfill never creates synthetic users, interactions, or content.
"""

import uuid
import pytest
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.content import Content, ContentType
from app.models.embedding import ContentEmbedding, UserEmbedding
from app.models.interaction import InteractionEvent, SavedContent, WatchHistory
from app.models.review import Rating, Review
from app.models.user import User, UserPreference
from app.models.watchman import WatchmanDecision
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.ml.embeddings.eligibility import ContentEmbeddingEligibilityService
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.candidates.pipeline import CandidatePipeline
from app.ml.recommendations.generator import RecommendationGenerator
from app.tasks.recommendation import process_user_interaction_ml


def _create_content(db: Session, title: str, ctype: str, popularity: float, tmdb_id: int) -> Content:
    item = Content(
        content_type=ctype,
        tmdb_id=tmdb_id,
        title=title,
        overview=f"Overview of {title}",
        popularity=popularity,
        vote_average=8.0,
        vote_count=1000,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _create_user(db: Session, email_prefix: str = "user") -> User:
    uid = uuid.uuid4()
    user = User(
        id=uid,
        email=f"{email_prefix}_{uid.hex[:6]}@example.com",
        username=f"{email_prefix}_{uid.hex[:6]}",
        password_hash="mock_hash",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_a_initial_popular_selection(db_session: Session):
    """
    TEST A: Initial popular selection selects the top popular movies and TV series
    according to popularity rankings without touching unrelated catalog items.
    """
    # Create 10 movies with varying popularity
    movies = [
        _create_content(db_session, f"Movie {i}", ContentType.MOVIE.value, popularity=float(i * 10), tmdb_id=1000 + i)
        for i in range(1, 11)
    ]
    # Create 10 TV shows with varying popularity
    tv_shows = [
        _create_content(db_session, f"TV {i}", ContentType.TV.value, popularity=float(i * 5), tmdb_id=2000 + i)
        for i in range(1, 11)
    ]

    # Request top 3 movies and top 3 TV shows
    candidates = ContentEmbeddingEligibilityService.get_initial_popular_candidates(
        db_session, movie_limit=3, tv_limit=3
    )

    assert len(candidates) == 6
    selected_movie_ids = {c.id for c in candidates if c.content_type == ContentType.MOVIE.value}
    selected_tv_ids = {c.id for c in candidates if c.content_type == ContentType.TV.value}

    # Should be the 3 movies with highest popularity (Movie 10, 9, 8)
    expected_movie_ids = {movies[9].id, movies[8].id, movies[7].id}
    assert selected_movie_ids == expected_movie_ids

    # Should be the 3 TV shows with highest popularity (TV 10, 9, 8)
    expected_tv_ids = {tv_shows[9].id, tv_shows[8].id, tv_shows[7].id}
    assert selected_tv_ids == expected_tv_ids

    # Run batch embed on these candidates
    res = ContentEmbeddingService.batch_embed_items(db_session, candidates)
    assert res["newly_created"] == 6

    # Verify only these 6 items have embeddings, remaining 14 do NOT
    total_embeddings = db_session.query(ContentEmbedding).count()
    assert total_embeddings == 6


def test_b_existing_embedding_reused_no_duplicate(db_session: Session):
    """
    TEST B: If an item already has an embedding matching content_hash and model_version,
    it is reused. No duplicate row or redundant re-generation occurs.
    """
    movie = _create_content(db_session, "Inception", ContentType.MOVIE.value, popularity=95.0, tmdb_id=5001)

    # First embed
    emb1 = ContentEmbeddingService.embed_content(db_session, movie.id)
    assert emb1 is not None
    emb_id = emb1.id
    vec1 = list(emb1.embedding)

    # Second embed (force=False)
    emb2 = ContentEmbeddingService.embed_content(db_session, movie.id, force=False)
    assert emb2.id == emb_id
    assert list(emb2.embedding) == vec1

    # Total row count in content_embeddings must be exactly 1
    count = db_session.query(ContentEmbedding).filter(ContentEmbedding.content_id == movie.id).count()
    assert count == 1


def test_c_interaction_with_unembedded_content_creates_one_embedding(db_session: Session):
    """
    TEST C: Interaction with previously unembedded content creates exactly one embedding.
    """
    movie = _create_content(db_session, "Interstellar", ContentType.MOVIE.value, popularity=88.0, tmdb_id=5002)
    user = _create_user(db_session)

    # Content has no embedding initially
    assert db_session.query(ContentEmbedding).filter(ContentEmbedding.content_id == movie.id).count() == 0

    # User watches content
    watch = WatchHistory(user_id=user.id, content_id=movie.id, progress=1.0, completed=True)
    db_session.add(watch)
    db_session.commit()

    # Celery task executes
    result = process_user_interaction_ml(str(user.id), movie.id, db=db_session)
    assert result["content_id"] == movie.id

    # Exactly one content embedding created
    count = db_session.query(ContentEmbedding).filter(ContentEmbedding.content_id == movie.id).count()
    assert count == 1


def test_d_second_interaction_same_content_no_duplicate(db_session: Session):
    """
    TEST D: Second interaction with the same content reuses the existing vector
    and does not create another content embedding row.
    """
    movie = _create_content(db_session, "Memento", ContentType.MOVIE.value, popularity=75.0, tmdb_id=5003)
    user = _create_user(db_session)

    # First interaction (rate)
    rating = Rating(user_id=user.id, content_id=movie.id, rating=5.0)
    db_session.add(rating)
    db_session.commit()
    process_user_interaction_ml(str(user.id), movie.id, db=db_session)

    assert db_session.query(ContentEmbedding).filter(ContentEmbedding.content_id == movie.id).count() == 1
    emb_initial = db_session.query(ContentEmbedding).filter(ContentEmbedding.content_id == movie.id).first()
    initial_id = emb_initial.id

    # Second interaction (save/favorite)
    saved = SavedContent(user_id=user.id, content_id=movie.id)
    db_session.add(saved)
    db_session.commit()
    process_user_interaction_ml(str(user.id), movie.id, db=db_session)

    # Still exactly one embedding with the same primary key
    assert db_session.query(ContentEmbedding).filter(ContentEmbedding.content_id == movie.id).count() == 1
    emb_after = db_session.query(ContentEmbedding).filter(ContentEmbedding.content_id == movie.id).first()
    assert emb_after.id == initial_id


def test_e_stale_content_hash_or_version_regenerates(db_session: Session):
    """
    TEST E: Content whose content_hash or model_version is stale is regenerated
    appropriately without creating duplicate rows.
    """
    movie = _create_content(db_session, "The Prestige", ContentType.MOVIE.value, popularity=80.0, tmdb_id=5004)

    # Initial embedding
    emb = ContentEmbeddingService.embed_content(db_session, movie.id)
    assert emb.model_version == "1.0.0"

    # Simulate stale model version
    emb.model_version = "0.9.0"
    db_session.commit()

    # Eligibility check should detect staleness
    assert not ContentEmbeddingEligibilityService.is_embedding_current(movie, emb)

    # Re-embed
    updated_emb = ContentEmbeddingService.embed_content(db_session, movie.id)
    assert updated_emb.model_version == "1.0.0"
    assert db_session.query(ContentEmbedding).filter(ContentEmbedding.content_id == movie.id).count() == 1

    # Simulate stale content hash (e.g. title/overview changed)
    updated_emb.content_hash = "stale_hash_value_12345"
    db_session.commit()
    assert not ContentEmbeddingEligibilityService.is_embedding_current(movie, updated_emb)

    re_updated = ContentEmbeddingService.embed_content(db_session, movie.id)
    assert re_updated.content_hash != "stale_hash_value_12345"
    assert db_session.query(ContentEmbedding).filter(ContentEmbedding.content_id == movie.id).count() == 1


def test_f_recommendations_work_with_small_embedded_subset(db_session: Session):
    """
    TEST F: Recommendation generation works seamlessly when only a small subset
    of catalog items have embeddings.
    """
    # 20 catalog items, only 3 have embeddings
    items = [
        _create_content(db_session, f"Catalog Item {i}", ContentType.MOVIE.value, popularity=float(i * 5), tmdb_id=6000 + i)
        for i in range(1, 21)
    ]
    # Embed only the first 3
    for it in items[:3]:
        ContentEmbeddingService.embed_content(db_session, it.id)

    assert db_session.query(ContentEmbedding).count() == 3

    # User with interaction on item 0
    user = _create_user(db_session)
    pref = UserPreference(user_id=user.id, favorite_genres=[], disliked_genres=[])
    db_session.add(pref)
    db_session.add(SavedContent(user_id=user.id, content_id=items[0].id))
    db_session.commit()

    # Generate recommendations
    recs = RecommendationGenerator.generate_and_persist_for_user(db_session, user.id, limit=10)
    assert len(recs) > 0

    # Ensure no automatic mass-embedding occurred on the remaining 17 items
    total_embeddings = db_session.query(ContentEmbedding).count()
    assert total_embeddings == 3


def test_g_recommendations_work_with_zero_content_embeddings(db_session: Session):
    """
    TEST G: Recommendation generation works with zero content embeddings.
    Semantic candidate channel gracefully returns empty candidates while
    popularity/freshness/preferences channels succeed.
    """
    # Create catalog items without any embeddings
    items = [
        _create_content(db_session, f"Pure Catalog Item {i}", ContentType.MOVIE.value, popularity=float(i * 10), tmdb_id=7000 + i)
        for i in range(1, 11)
    ]
    assert db_session.query(ContentEmbedding).count() == 0

    user = _create_user(db_session)
    pref = UserPreference(user_id=user.id, favorite_genres=["Action"], disliked_genres=[])
    db_session.add(pref)
    db_session.commit()

    # Generate candidates directly to inspect sources
    candidates = CandidatePipeline.generate_all_candidates(db_session, user.id, limit_per_channel=10)
    assert len(candidates) > 0

    # None of the candidates should have 'content_based' since 0 embeddings exist
    for c in candidates:
        assert "content_based" not in c.sources

    # Ranked recommendations succeed
    recs = RecommendationGenerator.generate_and_persist_for_user(db_session, user.id, limit=5)
    assert len(recs) > 0


def test_h_cold_start_user_receives_no_user_embedding(db_session: Session):
    """
    TEST H: A cold-start user (zero interactions) does NOT receive a user embedding
    simply because catalog items have embeddings.
    """
    # Embed some catalog items
    for i in range(1, 5):
        it = _create_content(db_session, f"Embedded Item {i}", ContentType.MOVIE.value, popularity=float(i * 15), tmdb_id=8000 + i)
        ContentEmbeddingService.embed_content(db_session, it.id)

    # Cold start user with no interactions
    user = _create_user(db_session)
    pref = UserPreference(user_id=user.id, favorite_genres=["Drama"], disliked_genres=[])
    db_session.add(pref)
    db_session.commit()

    # User embedding computation must return None
    user_emb = UserEmbeddingService.compute_and_save_user_embedding(db_session, user.id)
    assert user_emb is None

    # Recommendations must still work (via popularity / preference fallback)
    recs = RecommendationGenerator.generate_and_persist_for_user(db_session, user.id, limit=5)
    assert len(recs) > 0

    # User still has no user embedding row
    assert db_session.query(UserEmbedding).filter(UserEmbedding.user_id == user.id).count() == 0


def test_i_selective_backfill_creates_no_synthetic_data(db_session: Session):
    """
    TEST I: Initial selective backfill never creates synthetic users,
    interactions, ratings, or content records.
    """
    # Count initial users and interactions
    user_count_before = db_session.query(User).count()
    interaction_count_before = db_session.query(InteractionEvent).count()
    rating_count_before = db_session.query(Rating).count()
    content_count_before = db_session.query(Content).count()

    # Run popular selection and batch embed
    candidates = ContentEmbeddingEligibilityService.get_initial_popular_candidates(
        db_session, movie_limit=5, tv_limit=5
    )
    ContentEmbeddingService.batch_embed_items(db_session, candidates)

    # Verify zero synthetic users, interactions, ratings, or content records created
    assert db_session.query(User).count() == user_count_before
    assert db_session.query(InteractionEvent).count() == interaction_count_before
    assert db_session.query(Rating).count() == rating_count_before
    assert db_session.query(Content).count() == content_count_before
