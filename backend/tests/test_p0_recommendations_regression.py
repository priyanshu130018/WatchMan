"""
Regression test suite specifically verifying fixes for all confirmed P0 issues
in the WatchMan recommendation system audit:

P0-1: Rating normalization (10-point scale consistency)
P0-2: Negative / weak interaction signal contamination prevention
P0-3: Disliked genre handling in HybridRanker
P0-4: Cold-start behavior consistency
P0-5: Recommendation persistence error propagation and logging
"""

import uuid
import pytest
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.models.content import Content
from app.models.taxonomy import Genre, ContentGenre
from app.models.user import User, UserPreference
from app.models.interaction import SavedContent, WatchHistory, InteractionEvent
from app.models.review import Rating
from app.models.watchman import WatchmanDecision
from app.models.recommendation import Recommendation

from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.collaborative.training import ALSTrainingService
from app.ml.ranking.hybrid import HybridRanker, RankedRecommendation
from app.ml.candidates.pipeline import CandidateItem
from app.ml.recommendations.generator import RecommendationGenerator
from app.services.recommendation.service import UnifiedRecommendationService


# =========================================================================== #
# P0-1: Rating Normalization Tests (10.0 scale)
# =========================================================================== #

def test_p0_1_rating_normalization_values(db_session: Session):
    """
    Verify exact required normalization values:
    10.0 -> 1.0
    9.0  -> 0.9
    5.0  -> 0.5
    1.0  -> 0.1
    0.5  -> 0.05
    """
    user_als = User(
        id=uuid.uuid4(),
        email="p0_1_als@example.com",
        username="p0_1_als",
        password_hash="x",
        is_active=True,
    )
    db_session.add(user_als)

    test_ratings = [
        (1001, 10.0, 1.0),
        (1002, 9.0, 0.9),
        (1003, 5.0, 0.5),
        (1004, 1.0, 0.1),
        (1005, 0.5, 0.05),
    ]

    for cid, val, _ in test_ratings:
        c = Content(
            id=cid,
            tmdb_id=cid,
            title=f"Movie {cid}",
            content_type="movie",
            popularity=10.0,
        )
        db_session.add(c)
        db_session.add(Rating(user_id=user_als.id, content_id=cid, rating=val))

    db_session.commit()

    # ALS training matrix verification
    matrix, _, _ = ALSTrainingService.build_interactions(db_session)
    user_matrix = matrix[user_als.id]

    for cid, _, expected_norm in test_ratings:
        assert user_matrix[cid] == pytest.approx(expected_norm, abs=1e-4), (
            f"Content {cid} with rating should normalize to {expected_norm}, got {user_matrix[cid]}"
        )


def test_p0_1_user_embedding_weights_rating_scale(db_session: Session):
    """
    Verify UserEmbeddingService converts positive ratings using rating / 10.0:
    10.0 -> 1.0
    9.0  -> 0.9
    6.0  -> 0.6
    """
    user = User(
        id=uuid.uuid4(),
        email="p0_1_emb@example.com",
        username="p0_1_emb",
        password_hash="x",
        is_active=True,
    )
    db_session.add(user)

    c1 = Content(id=2001, tmdb_id=2001, title="Movie High 10", content_type="movie")
    c2 = Content(id=2002, tmdb_id=2002, title="Movie High 9", content_type="movie")
    c3 = Content(id=2003, tmdb_id=2003, title="Movie Med 6", content_type="movie")
    db_session.add_all([c1, c2, c3])
    db_session.commit()

    db_session.add(Rating(user_id=user.id, content_id=c1.id, rating=10.0))
    db_session.add(Rating(user_id=user.id, content_id=c2.id, rating=9.0))
    db_session.add(Rating(user_id=user.id, content_id=c3.id, rating=6.0))
    db_session.commit()

    weights = UserEmbeddingService.get_user_interaction_weights(db_session, user.id)
    assert weights[c1.id] == pytest.approx(1.0)
    assert weights[c2.id] == pytest.approx(0.9)
    assert weights[c3.id] == pytest.approx(0.6)


# =========================================================================== #
# P0-2: Negative / Weak Interaction Signal Contamination Tests
# =========================================================================== #

def test_p0_2_low_rating_does_not_become_positive_taste_signal(db_session: Session):
    """
    1/10 rating (0.1) accompanied by generic 'rate' InteractionEvent
    must NOT become a positive 0.5 taste signal.
    """
    user = User(
        id=uuid.uuid4(),
        email="p0_2_rate@example.com",
        username="p0_2_rate",
        password_hash="x",
        is_active=True,
    )
    content = Content(id=3001, tmdb_id=3001, title="Awful Movie", content_type="movie")
    db_session.add_all([user, content])
    db_session.commit()

    # User rates 1/10
    db_session.add(Rating(user_id=user.id, content_id=content.id, rating=1.0))
    # Generic telemetry event logged
    db_session.add(
        InteractionEvent(
            user_id=user.id,
            content_id=content.id,
            event_type="rate",
            event_value=1.0,
        )
    )
    db_session.commit()

    weights = UserEmbeddingService.get_user_interaction_weights(db_session, user.id)
    assert weights.get(content.id, 0.0) == 0.0, (
        f"1/10 rating must NOT become a positive taste signal (got weight {weights.get(content.id)})"
    )
    assert content.id not in weights


def test_p0_2_zero_watch_does_not_become_positive_taste_signal(db_session: Session):
    """
    0% watch accompanied by generic 'watch' InteractionEvent
    must NOT become a positive 0.5 taste signal.
    """
    user = User(
        id=uuid.uuid4(),
        email="p0_2_watch0@example.com",
        username="p0_2_watch0",
        password_hash="x",
        is_active=True,
    )
    content = Content(id=3002, tmdb_id=3002, title="Unwatched Movie", content_type="movie")
    db_session.add_all([user, content])
    db_session.commit()

    # User watched 0%
    db_session.add(WatchHistory(user_id=user.id, content_id=content.id, progress=0.0, completed=False))
    # Generic telemetry event logged
    db_session.add(
        InteractionEvent(
            user_id=user.id,
            content_id=content.id,
            event_type="watch",
            event_value=0.0,
        )
    )
    db_session.commit()

    weights = UserEmbeddingService.get_user_interaction_weights(db_session, user.id)
    assert weights.get(content.id, 0.0) == 0.0, (
        f"0% watch must NOT become a positive taste signal (got weight {weights.get(content.id)})"
    )
    assert content.id not in weights


def test_p0_2_partial_and_completed_watch_produce_positive_signals(db_session: Session):
    """
    50% watch produces an appropriate positive signal.
    Completed watch produces a strong positive signal (1.0).
    """
    user = User(
        id=uuid.uuid4(),
        email="p0_2_watch_pos@example.com",
        username="p0_2_watch_pos",
        password_hash="x",
        is_active=True,
    )
    c_half = Content(id=3003, tmdb_id=3003, title="Half Watched", content_type="movie")
    c_full = Content(id=3004, tmdb_id=3004, title="Completed Movie", content_type="movie")
    db_session.add_all([user, c_half, c_full])
    db_session.commit()

    # 50% watch
    db_session.add(WatchHistory(user_id=user.id, content_id=c_half.id, progress=0.5, completed=False))
    # Completed watch
    db_session.add(WatchHistory(user_id=user.id, content_id=c_full.id, progress=1.0, completed=True))
    db_session.commit()

    weights = UserEmbeddingService.get_user_interaction_weights(db_session, user.id)
    # 50% watch -> 0.5 + 0.5 * 0.5 = 0.75
    assert weights[c_half.id] == pytest.approx(0.75)
    # completed watch -> 1.0
    assert weights[c_full.id] == pytest.approx(1.0)


def test_p0_2_must_watch_remains_positive_and_skip_excluded(db_session: Session):
    """
    must_watch decision gives strong positive signal (1.0).
    skip decision removes/excludes the item even if previously saved.
    """
    user = User(
        id=uuid.uuid4(),
        email="p0_2_wm@example.com",
        username="p0_2_wm",
        password_hash="x",
        is_active=True,
    )
    c_must = Content(id=3005, tmdb_id=3005, title="Must Watch Movie", content_type="movie")
    c_skip = Content(id=3006, tmdb_id=3006, title="Skipped Movie", content_type="movie")
    db_session.add_all([user, c_must, c_skip])
    db_session.commit()

    # User saved c_skip previously
    db_session.add(SavedContent(user_id=user.id, content_id=c_skip.id))
    # Decisions
    db_session.add(WatchmanDecision(user_id=user.id, content_id=c_must.id, decision="must_watch"))
    db_session.add(WatchmanDecision(user_id=user.id, content_id=c_skip.id, decision="skip"))
    db_session.commit()

    weights = UserEmbeddingService.get_user_interaction_weights(db_session, user.id)
    assert weights[c_must.id] == pytest.approx(1.0)
    assert c_skip.id not in weights


# =========================================================================== #
# P0-3: Disliked Genre Handling Tests
# =========================================================================== #

def test_p0_3_favorite_and_disliked_genres_preference_scoring():
    """
    Unit tests for HybridRanker._compute_preference_score:
    - favorite genre -> positive preference effect
    - disliked genre -> negative preference effect
    - favorite + disliked conflict -> deterministic behavior
    - no preferences -> existing behavior preserved (0.0)
    """
    # Create mock content items with genres
    g_action = MagicMock()
    g_action.genre.name = "Action"

    g_horror = MagicMock()
    g_horror.genre.name = "Horror"

    g_comedy = MagicMock()
    g_comedy.genre.name = "Comedy"

    item_action = Content(id=4001, title="Action Hero", content_type="movie")
    item_action.genres = [g_action]

    item_horror = Content(id=4002, title="Haunted House", content_type="movie")
    item_horror.genres = [g_horror]

    item_action_horror = Content(id=4003, title="Zombie Action", content_type="movie")
    item_action_horror.genres = [g_action, g_horror]

    item_comedy = Content(id=4004, title="Funny Times", content_type="movie")
    item_comedy.genres = [g_comedy]

    pref_genres = {"action"}
    disliked_genres = {"horror"}
    pref_langs = set()

    # 1. Favorite genre -> positive preference score
    score_fav = HybridRanker._compute_preference_score(
        item_action, pref_genres=pref_genres, pref_langs=pref_langs, disliked_genres=disliked_genres
    )
    assert score_fav > 0.0, f"Favorite genre should have positive score, got {score_fav}"
    assert score_fav == pytest.approx(1.0)

    # 2. Disliked genre -> negative preference score (clear penalty)
    score_disliked = HybridRanker._compute_preference_score(
        item_horror, pref_genres=pref_genres, pref_langs=pref_langs, disliked_genres=disliked_genres
    )
    assert score_disliked < 0.0, f"Disliked genre should have negative score, got {score_disliked}"
    assert score_disliked == pytest.approx(-1.0)

    # 3. Favorite + disliked conflict -> deterministic balance
    score_conflict = HybridRanker._compute_preference_score(
        item_action_horror, pref_genres=pref_genres, pref_langs=pref_langs, disliked_genres=disliked_genres
    )
    # 1 favorite out of 2 genres -> 0.5 base; 1 disliked out of 2 -> 0.5 penalty; net = 0.0
    assert score_conflict == pytest.approx(0.0)

    # 4. Neutral genre (neither favorite nor disliked) -> 0.0
    score_neutral = HybridRanker._compute_preference_score(
        item_comedy, pref_genres=pref_genres, pref_langs=pref_langs, disliked_genres=disliked_genres
    )
    assert score_neutral == pytest.approx(0.0)

    # 5. No preferences -> 0.0 preserved
    score_no_prefs = HybridRanker._compute_preference_score(
        item_action, pref_genres=set(), pref_langs=set(), disliked_genres=set()
    )
    assert score_no_prefs == pytest.approx(0.0)


def test_p0_3_ranking_penalizes_disliked_genre_in_candidate_list(db_session: Session):
    """
    End-to-end rank_candidates test verifying an item with a disliked genre
    is penalized in composite score compared to an identical neutral item.
    """
    user = User(
        id=uuid.uuid4(),
        email="p0_3_rank@example.com",
        username="p0_3_rank",
        password_hash="x",
        is_active=True,
    )
    db_session.add(user)

    # Genres
    g_sci_fi = Genre(id=10, tmdb_id=878, name="Science Fiction")
    g_horror = Genre(id=11, tmdb_id=27, name="Horror")
    db_session.add_all([g_sci_fi, g_horror])
    db_session.commit()

    # User dislikes Horror
    pref = UserPreference(
        user_id=user.id,
        favorite_genres=["Science Fiction"],
        disliked_genres=["Horror"],
    )
    db_session.add(pref)

    # Two items with equal baseline candidate scores
    c_neutral = Content(id=4010, tmdb_id=4010, title="Neutral Sci-Fi", content_type="movie", popularity=50.0)
    c_disliked = Content(id=4011, tmdb_id=4011, title="Horror Movie", content_type="movie", popularity=50.0)
    db_session.add_all([c_neutral, c_disliked])
    db_session.commit()

    db_session.add(ContentGenre(content_id=c_neutral.id, genre_id=g_sci_fi.id))
    db_session.add(ContentGenre(content_id=c_disliked.id, genre_id=g_horror.id))
    db_session.commit()

    cand_neutral = CandidateItem(
        content_id=c_neutral.id,
        content=c_neutral,
        popularity_score=0.8,
        freshness_score=0.5,
    )
    cand_disliked = CandidateItem(
        content_id=c_disliked.id,
        content=c_disliked,
        popularity_score=0.8,
        freshness_score=0.5,
    )

    ranked = HybridRanker.rank_candidates(
        db=db_session,
        user_id=user.id,
        candidates=[cand_neutral, cand_disliked],
        apply_diversity=False,
    )

    ranked_map = {r.content_id: r for r in ranked}
    assert ranked_map[c_neutral.id].score > ranked_map[c_disliked.id].score
    assert ranked_map[c_disliked.id].preference_score < 0.0


# =========================================================================== #
# P0-4: Cold-Start Recommendations Consistency Tests
# =========================================================================== #

@pytest.mark.asyncio
async def test_p0_4_cold_start_user_receives_popularity_and_freshness_recs(db_session: Session):
    """
    A brand new user with zero interactions must NOT receive an empty list [].
    Instead, they must receive initial recommendations driven by popularity/freshness,
    with is_cold_start=True.
    """
    user = User(
        id=uuid.uuid4(),
        email="p0_4_cold@example.com",
        username="p0_4_cold",
        password_hash="x",
        is_active=True,
    )
    db_session.add(user)

    # Seed some popular content in the catalog
    for i in range(5):
        c = Content(
            id=5000 + i,
            tmdb_id=5000 + i,
            title=f"Catalog Hit {i}",
            content_type="movie",
            popularity=100.0 - i * 10,
        )
        db_session.add(c)
    db_session.commit()

    service = UnifiedRecommendationService()
    # Confirm user has no activity
    assert service.user_has_activity(db_session, user.id) is False

    result = await service.get_personalized_recommendations(
        db=db_session,
        user_id=user.id,
        limit=10,
        force_refresh=True,
    )

    assert result["is_cold_start"] is True
    assert len(result["items"]) > 0, "Cold-start user must receive initial recommendations, not []"
    assert result["total"] > 0


@pytest.mark.asyncio
async def test_p0_4_cold_start_with_onboarding_preferences(db_session: Session):
    """
    A new user with onboarding genre preferences receives cold-start recommendations
    boosted by their preferred genre.
    """
    user = User(
        id=uuid.uuid4(),
        email="p0_4_onboard@example.com",
        username="p0_4_onboard",
        password_hash="x",
        is_active=True,
    )
    db_session.add(user)

    g_animation = Genre(id=20, tmdb_id=16, name="Animation")
    g_action = Genre(id=21, tmdb_id=28, name="Action")
    db_session.add_all([g_animation, g_action])
    db_session.commit()

    # User set Animation in onboarding
    pref = UserPreference(user_id=user.id, favorite_genres=["Animation"], disliked_genres=[])
    db_session.add(pref)

    c_anim = Content(id=5020, tmdb_id=5020, title="Animated Hit", content_type="movie", popularity=80.0)
    c_act = Content(id=5021, tmdb_id=5021, title="Action Movie", content_type="movie", popularity=80.0)
    db_session.add_all([c_anim, c_act])
    db_session.commit()

    db_session.add(ContentGenre(content_id=c_anim.id, genre_id=g_animation.id))
    db_session.add(ContentGenre(content_id=c_act.id, genre_id=g_action.id))
    db_session.commit()

    service = UnifiedRecommendationService()
    assert service.user_has_activity(db_session, user.id) is False

    result = await service.get_personalized_recommendations(
        db=db_session,
        user_id=user.id,
        limit=10,
        force_refresh=True,
    )

    assert result["is_cold_start"] is True
    assert len(result["items"]) > 0

    # Animated movie should be ranked higher due to onboarding preference match
    item_ids = [it["id"] for it in result["items"]]
    if c_anim.id in item_ids and c_act.id in item_ids:
        assert item_ids.index(c_anim.id) < item_ids.index(c_act.id)


@pytest.mark.asyncio
async def test_p0_4_empty_catalog_safely_returns_empty_result(db_session: Session):
    """
    When the catalog is empty, recommendation service must safely return an empty result
    with is_cold_start=True without crashing or raising exceptions.
    """
    user = User(
        id=uuid.uuid4(),
        email="empty_catalog_user@example.com",
        username="empty_catalog_user",
        password_hash="x",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    service = UnifiedRecommendationService()
    result = await service.get_personalized_recommendations(
        db=db_session,
        user_id=user.id,
        limit=10,
        force_refresh=True,
    )

    assert result["items"] == []
    assert result["total"] == 0
    assert result["page"] == 1
    assert result["page_size"] == 10
    assert result["total_pages"] == 1
    assert result["is_cold_start"] is True


def test_p0_4_als_cold_start_does_not_create_fake_collaborative_data(db_session: Session):
    """
    ALS for a brand-new user must not manufacture interactions or fake factors.
    ALSCollaborativeCandidateGenerator naturally returns [] for a cold user.
    """
    from app.models.collaborative import ALSUserFactors, ALSItemFactors
    from app.ml.candidates.als_collaborative import ALSCollaborativeCandidateGenerator

    user_id = uuid.uuid4()
    # Confirm no ALS factors exist for this user
    existing_factors = db_session.query(ALSUserFactors).filter(ALSUserFactors.user_id == user_id).first()
    assert existing_factors is None

    # Generator returns [] without error
    candidates = ALSCollaborativeCandidateGenerator.generate_candidates(
        db=db_session,
        user_id=user_id,
        limit=10,
    )
    assert candidates == []

    # Verify no fake ALS rows were created
    assert db_session.query(ALSUserFactors).filter(ALSUserFactors.user_id == user_id).count() == 0


@pytest.mark.asyncio
async def test_p0_4_api_response_shape_preserved(db_session: Session):
    """
    Cold-start recommendations response preserves the exact expected API shape.
    """
    user = User(
        id=uuid.uuid4(),
        email="p0_4_shape@example.com",
        username="p0_4_shape",
        password_hash="x",
        is_active=True,
    )
    c = Content(
        id=5099,
        tmdb_id=5099,
        title="Shape Test Movie",
        overview="A test movie overview",
        content_type="movie",
        release_date="2024-01-01",
        poster_path="/path.jpg",
        backdrop_path="/backdrop.jpg",
        vote_average=8.5,
        vote_count=1000,
        popularity=99.0,
    )
    db_session.add_all([user, c])
    db_session.commit()

    service = UnifiedRecommendationService()
    result = await service.get_personalized_recommendations(
        db=db_session,
        user_id=user.id,
        limit=5,
        force_refresh=True,
    )

    # Top-level schema keys
    expected_top_keys = {"items", "total", "page", "page_size", "total_pages", "is_cold_start"}
    assert expected_top_keys.issubset(result.keys())

    assert len(result["items"]) > 0
    item = result["items"][0]
    expected_item_keys = {
        "id", "content_id", "tmdb_id", "title", "overview", "content_type",
        "release_date", "poster_path", "backdrop_path", "vote_average",
        "vote_count", "popularity", "genres", "score", "recommendation_score",
        "rank", "explanation", "reason", "sources", "watchman_score", "watchman_label",
    }
    assert expected_item_keys.issubset(item.keys())


# =========================================================================== #
# P0-5: Recommendation Persistence Error Propagation Tests
# =========================================================================== #

def test_p0_5_persistence_failure_rolls_back_logs_and_raises(db_session: Session):
    """
    RecommendationGenerator._persist_ranked() must:
    1. Roll back the DB transaction
    2. Log the exception with user context
    3. Propagate (raise) the exception to the caller rather than silently swallowing it.
    """
    user_id = uuid.uuid4()
    mock_db = MagicMock(spec=Session)
    mock_db.commit.side_effect = RuntimeError("Database disk full / connection dropped")

    mock_rec = MagicMock(spec=RankedRecommendation)
    mock_rec.content_id = 999
    mock_rec.score = 0.95
    mock_rec.rank = 1
    mock_rec.explanation = "Great movie"

    with patch("app.ml.recommendations.generator.logger") as mock_logger:
        with pytest.raises(RuntimeError, match="Database disk full"):
            RecommendationGenerator._persist_ranked(
                db=mock_db,
                user_id=user_id,
                ranked=[mock_rec],
            )

        # 1. Transaction was rolled back
        mock_db.rollback.assert_called_once()
        # 2. Error was logged with context
        mock_logger.exception.assert_called_once()
        log_args = mock_logger.exception.call_args[0]
        assert "Failed to persist recommendations for user %s" in log_args[0]
        assert str(user_id) in str(log_args[1])
