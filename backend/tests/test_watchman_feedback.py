"""Unit and integration tests for the WatchMan scoring and decision system."""

from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user, get_current_user_optional
from app.models.content import Content, ContentType
from app.models.user import User
from app.models.watchman import WatchmanDecision
from app.services.watchman_service import (
    WatchmanService,
    get_watchman_label,
    get_watchman_display,
)
from app.main import app


# -----------------------------------------------------------------------------
# 1. Classification & Threshold Unit Tests
# -----------------------------------------------------------------------------

def test_watchman_label_thresholds():
    """Verify exact boundary behavior for WatchMan classification."""
    # MUST WATCH: 75.0 to 100.0
    assert get_watchman_label(100.0) == "must_watch"
    assert get_watchman_label(85.5) == "must_watch"
    assert get_watchman_label(75.0) == "must_watch"

    # TIME PASS: 45.0 to 74.9
    assert get_watchman_label(74.9) == "time_pass"
    assert get_watchman_label(60.0) == "time_pass"
    assert get_watchman_label(45.0) == "time_pass"

    # SKIP: 0.0 to 44.9
    assert get_watchman_label(44.9) == "skip"
    assert get_watchman_label(20.0) == "skip"
    assert get_watchman_label(0.0) == "skip"


def test_watchman_display_strings():
    """Verify uppercase user-facing labels."""
    assert get_watchman_display("must_watch") == "MUST WATCH"
    assert get_watchman_display("time_pass") == "TIME PASS"
    assert get_watchman_display("skip") == "SKIP"


# -----------------------------------------------------------------------------
# 2. Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_user_1():
    return User(
        id=uuid.uuid4(),
        email="watchman_user1@example.com",
        password_hash="fakehash",
        is_active=True,
    )


@pytest.fixture
def mock_user_2():
    return User(
        id=uuid.uuid4(),
        email="watchman_user2@example.com",
        password_hash="fakehash",
        is_active=True,
    )


@pytest.fixture
def sample_movie(db_session):
    movie = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=9901,
        title="Inception WatchMan Test",
        original_title="Inception WatchMan Test",
        overview="Mind-bending dream world.",
        release_date="2010-07-16",
        runtime=148,
        popularity=90.0,
        vote_average=8.2,
        vote_count=35000,
    )
    db_session.add(movie)
    db_session.commit()
    db_session.refresh(movie)
    return movie


@pytest.fixture
def sample_tv(db_session):
    tv = Content(
        content_type=ContentType.TV.value,
        tmdb_id=9902,
        title="Breaking Bad WatchMan Test",
        original_title="Breaking Bad WatchMan Test",
        overview="Chemistry teacher turns kingpin.",
        release_date="2008-01-20",
        number_of_seasons=5,
        number_of_episodes=62,
        popularity=95.0,
        vote_average=8.9,
        vote_count=14000,
    )
    db_session.add(tv)
    db_session.commit()
    db_session.refresh(tv)
    return tv


# -----------------------------------------------------------------------------
# 3. API & Service Integration Tests
# -----------------------------------------------------------------------------

def test_get_watchman_score_unauthenticated(sample_movie):
    """Anonymous visitors can read the score and community breakdown."""
    with TestClient(app) as client:
        resp = client.get(f"/api/content/{sample_movie.id}/watchman")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["content_id"] == sample_movie.id
        assert data["final_score"] >= 75.0
        assert data["watchman_label"] == "must_watch"
        assert data["label_display"] == "MUST WATCH"
        assert data["user_decision"] is None
        assert data["community_counts"]["total"] == 0


def test_put_watchman_score_unauthenticated_fails(sample_movie):
    """Anonymous attempts to submit a decision must be rejected with 401."""
    with TestClient(app) as client:
        resp = client.put(
            f"/api/content/{sample_movie.id}/watchman",
            json={"decision": "must_watch", "content_type": "movie"},
        )
        assert resp.status_code == 401


def test_submit_and_update_decision_no_duplicates(db_session, mock_user_1, sample_movie):
    """Authenticated user submits decision, then changes it; no duplicate rows created."""
    db_session.add(mock_user_1)
    db_session.commit()

    def override_user():
        return mock_user_1

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_current_user_optional] = override_user
    try:
        with TestClient(app) as client:
            # 1. Submit MUST WATCH
            resp1 = client.put(
                f"/api/content/{sample_movie.id}/watchman",
                json={"decision": "must_watch", "content_type": "movie"},
            )
            assert resp1.status_code == 200
            data1 = resp1.json()["data"]
            assert data1["user_decision"] == "must_watch"
            assert data1["community_counts"]["must_watch"] == 1
            assert data1["community_counts"]["total"] == 1

            # Verify in DB: exactly 1 row
            decisions = (
                db_session.query(WatchmanDecision)
                .filter(
                    WatchmanDecision.user_id == mock_user_1.id,
                    WatchmanDecision.content_id == sample_movie.id,
                )
                .all()
            )
            assert len(decisions) == 1
            assert decisions[0].decision == "must_watch"

            # 2. Update to SKIP
            resp2 = client.put(
                f"/api/content/{sample_movie.id}/watchman",
                json={"decision": "skip", "content_type": "movie"},
            )
            assert resp2.status_code == 200
            data2 = resp2.json()["data"]
            assert data2["user_decision"] == "skip"
            assert data2["community_counts"]["must_watch"] == 0
            assert data2["community_counts"]["skip"] == 1
            assert data2["community_counts"]["total"] == 1

            # DB should STILL have exactly 1 row (upsert without duplicates)
            db_session.expire_all()
            decisions_after = (
                db_session.query(WatchmanDecision)
                .filter(
                    WatchmanDecision.user_id == mock_user_1.id,
                    WatchmanDecision.content_id == sample_movie.id,
                )
                .all()
            )
            assert len(decisions_after) == 1
            assert decisions_after[0].decision == "skip"

            # 3. GET endpoint reflects updated user decision
            get_resp = client.get(f"/api/content/{sample_movie.id}/watchman")
            assert get_resp.status_code == 200
            assert get_resp.json()["data"]["user_decision"] == "skip"

    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_optional, None)


def test_tv_series_watchman_flow(db_session, mock_user_1, sample_tv):
    """TV / web-series content works seamlessly with WatchMan decisions."""
    db_session.add(mock_user_1)
    db_session.commit()

    def override_user():
        return mock_user_1

    app.dependency_overrides[get_current_user] = override_user
    try:
        with TestClient(app) as client:
            resp = client.put(
                f"/api/content/{sample_tv.id}/watchman",
                json={"decision": "time_pass", "content_type": "tv"},
            )
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["content_type"] == "tv"
            assert data["user_decision"] == "time_pass"
            assert data["community_counts"]["time_pass"] == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_score_clamping_bounds(db_session, mock_user_1):
    """Score must strictly clamp to [0, 100]."""
    db_session.add(mock_user_1)
    # High score content: vote 10.0 + must_watch
    content_high = Content(
        content_type="movie",
        tmdb_id=9903,
        title="Perfect 10 Movie",
        vote_average=10.0,
    )
    # Low score content: vote 0.5 + skip
    content_low = Content(
        content_type="movie",
        tmdb_id=9904,
        title="Terrible Movie",
        vote_average=0.5,
    )
    db_session.add_all([content_high, content_low])
    db_session.commit()

    # High calculation
    WatchmanService.upsert_user_decision(
        db=db_session,
        user_id=mock_user_1.id,
        content=content_high,
        decision="must_watch",
    )
    high_score = WatchmanService.compute_watchman_score(
        db_session, content_high, mock_user_1.id
    )
    assert 0.0 <= high_score.final_score <= 100.0

    # Low calculation
    WatchmanService.upsert_user_decision(
        db=db_session,
        user_id=mock_user_1.id,
        content=content_low,
        decision="skip",
    )
    low_score = WatchmanService.compute_watchman_score(
        db_session, content_low, mock_user_1.id
    )
    assert 0.0 <= low_score.final_score <= 100.0
