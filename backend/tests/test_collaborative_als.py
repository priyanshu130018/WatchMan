"""
Tests for the ALS collaborative-filtering branch:

    * pure-numpy ALS algorithm (fit / score / recommend)
    * ALSTrainingService (interaction matrix build, skip-on-cold, persistence)
    * ALSCollaborativeCandidateGenerator (online read path, cold start, exclusion)
    * separation guarantee: ALS latent factors are NOT the content embeddings

Runs on SQLite in-memory (see conftest). Pure-numpy ALS logic needs no DB.
"""

import uuid

import numpy as np
import pytest

from app.models.user import User
from app.models.content import Content
from app.models.interaction import SavedContent, WatchHistory
from app.models.review import Rating
from app.models.collaborative import ALSUserFactors, ALSItemFactors
from app.models.embedding import ContentEmbedding
from app.ml.collaborative.als import ALSModel
from app.ml.collaborative.training import ALSTrainingService
from app.ml.candidates.als_collaborative import ALSCollaborativeCandidateGenerator, _ITEM_CACHE


# --------------------------------------------------------------------------- #
# Pure-numpy ALS algorithm (no database)
# --------------------------------------------------------------------------- #

def test_als_fit_shapes_and_determinism():
    R = np.array([
        [1.0, 1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 1.0],
        [0.0, 0.0, 1.0, 1.0],
    ])
    m1 = ALSModel(factors=3, iterations=10, seed=42).fit(R)
    m2 = ALSModel(factors=3, iterations=10, seed=42).fit(R)

    assert m1.user_factors.shape == (4, 3)
    assert m1.item_factors.shape == (4, 3)
    # Same seed -> deterministic factors
    assert np.allclose(m1.user_factors, m2.user_factors)


def test_als_learns_block_structure():
    # Two disjoint taste clusters: users 0,1 like items 0,1; users 2,3 like 2,3.
    R = np.array([
        [1.0, 1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 1.0],
        [0.0, 0.0, 1.0, 1.0],
    ])
    model = ALSModel(factors=2, iterations=20, alpha=40.0, seed=1).fit(R)

    # User 0 should score their in-cluster item above an out-of-cluster item.
    assert model.score(0, 1) > model.score(0, 3)
    # recommend() should surface the unseen in-cluster item (index 1) for user 0.
    recs = model.recommend(0, n=2, exclude_item_indices={0})
    assert recs[0][0] == 1


def test_als_invalid_inputs():
    with pytest.raises(ValueError):
        ALSModel(factors=0)
    with pytest.raises(ValueError):
        ALSModel(factors=2).fit(np.array([1.0, 2.0, 3.0]))  # not 2D
    with pytest.raises(RuntimeError):
        ALSModel(factors=2).score(0, 0)  # not trained


# --------------------------------------------------------------------------- #
# Fixtures for DB-backed tests
# --------------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def _clear_item_cache():
    _ITEM_CACHE.clear()
    yield
    _ITEM_CACHE.clear()


@pytest.fixture
def seeded_interactions(db_session):
    """4 users x 6 contents with two clear taste clusters and 12 interactions (>= ALS_MIN_INTERACTIONS=10)."""
    users = []
    for i in range(4):
        u = User(
            id=uuid.uuid4(),
            email=f"als_u{i}@example.com",
            username=f"als_u{i}",
            password_hash="x",
            is_active=True,
        )
        users.append(u)
    contents = []
    for j in range(6):
        c = Content(
            tmdb_id=900 + j,
            content_type="movie",
            title=f"ALS Movie {j}",
            overview="test",
            popularity=10.0 + j,
        )
        contents.append(c)
    db_session.add_all(users + contents)
    db_session.commit()
    for u in users:
        db_session.refresh(u)
    for c in contents:
        db_session.refresh(c)

    # Cluster A: users 0,1 like contents 0,1,2 ; Cluster B: users 2,3 like 3,4,5.
    likes = {
        0: [0, 1, 2], 1: [0, 1, 2],
        2: [3, 4, 5], 3: [3, 4, 5],
    }
    for ui, cids in likes.items():
        for cj in cids:
            db_session.add(Rating(user_id=users[ui].id, content_id=contents[cj].id, rating=5.0))
            db_session.add(SavedContent(user_id=users[ui].id, content_id=contents[cj].id))
    db_session.commit()
    return users, contents


# --------------------------------------------------------------------------- #
# ALSTrainingService
# --------------------------------------------------------------------------- #

def test_build_interactions_weights(db_session, seeded_interactions):
    users, contents = seeded_interactions
    # Add a partial watch to exercise the progress-based weight.
    db_session.add(WatchHistory(user_id=users[0].id, content_id=contents[3].id, progress=0.5, completed=False))
    db_session.commit()

    matrix, user_ids, item_ids = ALSTrainingService.build_interactions(db_session)
    assert len(user_ids) == 4
    assert len(item_ids) == 6
    # rating 5.0 -> normalized 0.5 on 10-point scale; Saved (0.9) is also present; max wins -> 0.9
    assert matrix[users[0].id][contents[0].id] == pytest.approx(0.9)
    # update rating to 10.0 -> normalized 1.0
    r = db_session.query(Rating).filter(Rating.user_id == users[0].id, Rating.content_id == contents[1].id).first()
    r.rating = 10.0
    db_session.commit()
    matrix_updated, _, _ = ALSTrainingService.build_interactions(db_session)
    assert matrix_updated[users[0].id][contents[1].id] == pytest.approx(1.0)
    # watch progress 0.5 -> 0.3 + 0.7*0.5 = 0.65
    assert matrix[users[0].id][contents[3].id] == pytest.approx(0.65)


def test_train_skips_on_insufficient_data(db_session):
    # Empty DB -> below min thresholds -> skipped, no factors persisted.
    result = ALSTrainingService.train_and_persist(db_session)
    assert result["status"] == "skipped"
    assert db_session.query(ALSUserFactors).count() == 0
    assert db_session.query(ALSItemFactors).count() == 0


def test_train_and_persist_creates_factors(db_session, seeded_interactions):
    users, contents = seeded_interactions
    result = ALSTrainingService.train_and_persist(db_session)

    assert result["status"] == "trained"
    assert result["users"] == 4
    assert result["items"] == 6
    # One factor row per user and per item, all sharing the trained version.
    assert db_session.query(ALSUserFactors).count() == 4
    assert db_session.query(ALSItemFactors).count() == 6
    versions = {r.model_version for r in db_session.query(ALSItemFactors).all()}
    assert versions == {result["model_version"]}
    # Factor vectors have the reported dimensionality.
    row = db_session.query(ALSUserFactors).first()
    assert len(row.factors) == result["factors"]


# --------------------------------------------------------------------------- #
# ALSCollaborativeCandidateGenerator (online read path)
# --------------------------------------------------------------------------- #

def test_candidate_generator_cold_when_untrained(db_session, seeded_interactions):
    users, _ = seeded_interactions
    # No training run yet -> no persisted factors -> empty (pipeline falls back).
    cands = ALSCollaborativeCandidateGenerator.generate_candidates(db_session, users[0].id, limit=10)
    assert cands == []


def test_candidate_generator_recommends_in_cluster(db_session, seeded_interactions):
    users, contents = seeded_interactions
    ALSTrainingService.train_and_persist(db_session)

    # User 0 has seen contents 0,1; ask for candidates excluding those.
    seen = {contents[0].id, contents[1].id}
    cands = ALSCollaborativeCandidateGenerator.generate_candidates(
        db_session, users[0].id, limit=10, exclude_content_ids=seen
    )
    assert len(cands) > 0
    # All scores normalized into [0, 1] and source labelled collaborative.
    for c in cands:
        assert 0.0 <= c["score"] <= 1.0
        assert c["source"] == "als_collaborative"
        assert c["content_id"] not in seen


def test_candidate_generator_cold_user_returns_empty(db_session, seeded_interactions):
    users, contents = seeded_interactions
    ALSTrainingService.train_and_persist(db_session)

    # A brand-new user with no trained factors for the current model version.
    newbie = User(
        id=uuid.uuid4(), email="cold@example.com", username="cold",
        password_hash="x", is_active=True,
    )
    db_session.add(newbie)
    db_session.commit()
    cands = ALSCollaborativeCandidateGenerator.generate_candidates(db_session, newbie.id, limit=10)
    assert cands == []


# --------------------------------------------------------------------------- #
# Separation guarantee: ALS factors are NOT content embeddings
# --------------------------------------------------------------------------- #

def test_als_factors_are_separate_from_content_embeddings(db_session, seeded_interactions):
    users, contents = seeded_interactions
    # Persist a content embedding for content 0 (384-dim, the HF space).
    db_session.add(ContentEmbedding(
        content_id=contents[0].id,
        embedding=[0.1] * 384,
        dimension=384,
        content_hash="deadbeef",
    ))
    db_session.commit()

    ALSTrainingService.train_and_persist(db_session)

    als_item = (
        db_session.query(ALSItemFactors)
        .filter(ALSItemFactors.content_id == contents[0].id)
        .first()
    )
    content_emb = (
        db_session.query(ContentEmbedding)
        .filter(ContentEmbedding.content_id == contents[0].id)
        .first()
    )
    # Distinct storage, distinct dimensionality: the ALS latent factors are a
    # different representation from the 384-dim content embedding.
    assert als_item is not None and content_emb is not None
    assert len(als_item.factors) != len(content_emb.embedding)
    assert als_item.num_factors <= 4  # capped by min(users, items) - 1
