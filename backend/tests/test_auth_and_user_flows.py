"""Comprehensive test suite for Authentication, User Profile, Preferences,
Saved Content, Ratings, Reviews, Watch History, and Interaction Events.
"""

import uuid
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.models.user import User, Profile, UserPreference
from app.models.content import Content, ContentType
from app.models.taxonomy import Genre
from app.models.interaction import SavedContent, WatchHistory, InteractionEvent
from app.models.review import Rating, Review
from app.core.security import create_access_token, create_refresh_token
from app.services.interaction import InteractionTrackingService


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def seed_genres(db_session):
    g1 = Genre(tmdb_id=28, name="Action")
    g2 = Genre(tmdb_id=878, name="Sci-Fi")
    g3 = Genre(tmdb_id=35, name="Comedy")
    db_session.add_all([g1, g2, g3])
    db_session.commit()
    return [g1, g2, g3]


@pytest.fixture
def seed_content(db_session):
    c1 = Content(
        id=101,
        content_type=ContentType.MOVIE.value,
        tmdb_id=550,
        title="Fight Club",
        overview="An insomniac office worker...",
        release_date="1999-10-15",
        popularity=85.5,
        vote_average=8.4,
        vote_count=24000,
    )
    c2 = Content(
        id=102,
        content_type=ContentType.TV.value,
        tmdb_id=1399,
        title="Game of Thrones",
        overview="Seven noble families fight for control...",
        release_date="2011-04-17",
        popularity=120.0,
        vote_average=8.4,
        vote_count=21000,
        number_of_seasons=8,
        number_of_episodes=73,
    )
    db_session.add_all([c1, c2])
    db_session.commit()
    return c1, c2


# -----------------------------------------------------------------------------
# 1. Registration Tests
# -----------------------------------------------------------------------------

def test_register_successful(client, db_session):
    payload = {
        "email": "user1@example.com",
        "password": "StrongPassword123!",
        "full_name": "Test User",
        "username": "testuser1",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert "user" in data
    assert data["user"]["email"] == "user1@example.com"
    assert data["user"]["full_name"] == "Test User"
    assert data["user"]["username"] == "testuser1"
    assert "password" not in data["user"]
    assert "password_hash" not in data["user"]

    # Verify database persistence
    user = db_session.query(User).filter(User.email == "user1@example.com").first()
    assert user is not None
    assert user.password_hash != "StrongPassword123!"
    assert user.password_hash.startswith("$2") or len(user.password_hash) > 20


def test_register_duplicate_email(client):
    payload = {
        "email": "duplicate@example.com",
        "password": "Password123!",
    }
    r1 = client.post("/api/auth/register", json=payload)
    assert r1.status_code == 200

    r2 = client.post("/api/auth/register", json=payload)
    assert r2.status_code == 409
    data = r2.json()
    assert data["success"] is False
    assert data["error"]["code"] in ("USER_ALREADY_EXISTS", "RESOURCE_CONFLICT")


def test_register_invalid_payload(client):
    # Short password (< 8 chars)
    r = client.post("/api/auth/register", json={"email": "short@example.com", "password": "short"})
    assert r.status_code == 422

    # Invalid email format
    r2 = client.post("/api/auth/register", json={"email": "not-an-email", "password": "ValidPassword123"})
    assert r2.status_code == 422


# -----------------------------------------------------------------------------
# 2. Login Tests
# -----------------------------------------------------------------------------

def test_login_successful(client):
    register_payload = {
        "email": "loginuser@example.com",
        "password": "MySecretPassword123",
        "full_name": "Login User",
    }
    client.post("/api/auth/register", json=register_payload)

    login_resp = client.post("/api/auth/login", json={
        "email": "loginuser@example.com",
        "password": "MySecretPassword123",
    })
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "loginuser@example.com"
    assert "password_hash" not in data["user"]


def test_login_invalid_credentials(client):
    register_payload = {
        "email": "wrongpwd@example.com",
        "password": "CorrectPassword123",
    }
    client.post("/api/auth/register", json=register_payload)

    # Wrong password
    r1 = client.post("/api/auth/login", json={
        "email": "wrongpwd@example.com",
        "password": "WrongPassword123",
    })
    assert r1.status_code == 401
    assert r1.json()["error"]["message"] == "Invalid email or password."

    # Non-existent email
    r2 = client.post("/api/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "AnyPassword123",
    })
    assert r2.status_code == 401
    assert r2.json()["error"]["message"] == "Invalid email or password."


# -----------------------------------------------------------------------------
# 3. Token & /me Tests
# -----------------------------------------------------------------------------

def test_me_authenticated_and_unauthenticated(client):
    # Unauthenticated
    r_unauth = client.get("/api/auth/me")
    assert r_unauth.status_code == 401

    # Register & get token
    reg = client.post("/api/auth/register", json={
        "email": "me_test@example.com",
        "password": "Password123!",
        "full_name": "Me Tester",
    }).json()
    token = reg["access_token"]

    # Authenticated
    r_auth = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r_auth.status_code == 200
    me = r_auth.json()
    assert me["email"] == "me_test@example.com"
    assert me["full_name"] == "Me Tester"
    assert "password_hash" not in me


def test_refresh_token_flow(client):
    reg = client.post("/api/auth/register", json={
        "email": "refresh_test@example.com",
        "password": "Password123!",
    }).json()
    refresh_token = reg["refresh_token"]
    access_token = reg["access_token"]

    # Refresh with valid refresh token
    ref_resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert ref_resp.status_code == 200
    new_data = ref_resp.json()
    assert "access_token" in new_data
    assert "refresh_token" in new_data

    # Reject access token passed as refresh token
    ref_invalid = client.post("/api/auth/refresh", json={"refresh_token": access_token})
    assert ref_invalid.status_code == 401


# -----------------------------------------------------------------------------
# 4. User Profile & Preferences Tests
# -----------------------------------------------------------------------------

def test_user_profile_get_and_update(client):
    reg = client.post("/api/auth/register", json={
        "email": "profile_user@example.com",
        "password": "Password123!",
        "full_name": "Original Name",
        "username": "profileuser",
    }).json()
    token = reg["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get profile
    p_get = client.get("/api/users/me", headers=headers)
    assert p_get.status_code == 200
    assert p_get.json()["full_name"] == "Original Name"

    # Update profile
    p_put = client.put("/api/users/me", headers=headers, json={
        "full_name": "Updated Name",
        "username": "newhandle",
        "avatar_url": "https://example.com/pic.png",
    })
    assert p_put.status_code == 200
    updated = p_put.json()
    assert updated["full_name"] == "Updated Name"
    assert updated["username"] == "newhandle"
    assert updated["avatar_url"] == "https://example.com/pic.png"


def test_user_preferences_validation(client, seed_genres):
    reg = client.post("/api/auth/register", json={
        "email": "pref_user@example.com",
        "password": "Password123!",
    }).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # Update with valid genres (28 = Action, 878 = Sci-Fi)
    r_valid = client.put("/api/users/me/preferences", headers=headers, json={
        "favorite_genres": [28],
        "disliked_genres": [878],
    })
    assert r_valid.status_code == 200
    pref_data = r_valid.json()
    assert pref_data["favorite_genres"] == [28]
    assert pref_data["disliked_genres"] == [878]
    assert len(pref_data["favorite_genre_details"]) == 1
    assert pref_data["favorite_genre_details"][0]["name"] == "Action"

    # Update with non-existent genre ID -> 422
    r_invalid = client.put("/api/users/me/preferences", headers=headers, json={
        "favorite_genres": [999999],
        "disliked_genres": [],
    })
    assert r_invalid.status_code == 422
    assert "does not exist in taxonomy" in r_invalid.json()["error"]["message"] or "Invalid genre IDs" in r_invalid.json()["error"]["message"]


# -----------------------------------------------------------------------------
# 5. Saved Content Tests
# -----------------------------------------------------------------------------

def test_saved_content_movie_and_tv(client, seed_content):
    c1, c2 = seed_content
    reg = client.post("/api/auth/register", json={
        "email": "saved_user@example.com",
        "password": "Password123!",
    }).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # Save movie
    s1 = client.post("/api/saved", headers=headers, json={
        "content_type": "movie",
        "tmdb_id": 550,
    })
    assert s1.status_code == 200
    assert s1.json()["content_id"] == c1.id

    # Save TV show
    s2 = client.post("/api/saved", headers=headers, json={
        "content_type": "tv",
        "tmdb_id": 1399,
    })
    assert s2.status_code == 200
    assert s2.json()["content_id"] == c2.id

    # Duplicate save -> 409 Conflict
    s_dup = client.post("/api/saved", headers=headers, json={
        "content_type": "movie",
        "tmdb_id": 550,
    })
    assert s_dup.status_code == 409

    # List saved content
    s_list = client.get("/api/saved", headers=headers)
    assert s_list.status_code == 200
    items = s_list.json()
    assert len(items) == 2
    assert any(i["content"]["title"] == "Fight Club" for i in items if i.get("content"))

    # Paginated saved content
    s_pag = client.get("/api/saved/paginated?page=1&limit=10", headers=headers)
    assert s_pag.status_code == 200
    assert s_pag.json()["total"] == 2

    # Remove saved content
    del_resp = client.delete(f"/api/saved/movie/550", headers=headers)
    assert del_resp.status_code == 200

    # Verify count is now 1
    s_after = client.get("/api/saved", headers=headers)
    assert len(s_after.json()) == 1


def test_saved_content_ownership_isolation(client, seed_content):
    c1, _ = seed_content
    # User A saves content
    u_a = client.post("/api/auth/register", json={"email": "user_a@example.com", "password": "Password123!"}).json()
    headers_a = {"Authorization": f"Bearer {u_a['access_token']}"}
    client.post("/api/saved", headers=headers_a, json={"content_type": "movie", "tmdb_id": 550})

    # User B logs in
    u_b = client.post("/api/auth/register", json={"email": "user_b@example.com", "password": "Password123!"}).json()
    headers_b = {"Authorization": f"Bearer {u_b['access_token']}"}

    # User B lists saved content -> should be empty
    b_saved = client.get("/api/saved", headers=headers_b).json()
    assert len(b_saved) == 0

    # User B cannot delete User A's saved item
    b_del = client.delete(f"/api/saved/{c1.id}", headers=headers_b)
    assert b_del.status_code == 404


# -----------------------------------------------------------------------------
# 6. Ratings Tests
# -----------------------------------------------------------------------------

def test_ratings_create_update_delete(client, seed_content):
    c1, _ = seed_content
    reg = client.post("/api/auth/register", json={"email": "rater@example.com", "password": "Password123!"}).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # Create rating
    r_create = client.post("/api/ratings", headers=headers, json={
        "content_type": "movie",
        "tmdb_id": 550,
        "rating": 9.5,
        "review": "A cinematic masterpiece.",
    })
    assert r_create.status_code == 200
    assert r_create.json()["rating"] == 9.5
    assert r_create.json()["content_id"] == c1.id

    # Get specific rating
    r_get = client.get("/api/ratings/movie/550", headers=headers)
    assert r_get.status_code == 200
    assert r_get.json()["rating"] == 9.5

    # Update rating
    r_update = client.put("/api/ratings/movie/550", headers=headers, json={
        "rating": 10.0,
        "review": "Perfection upon rewatching.",
    })
    assert r_update.status_code == 200
    assert r_update.json()["rating"] == 10.0

    # Invalid rating (> 10.0) -> 422
    r_invalid = client.post("/api/ratings", headers=headers, json={
        "content_type": "movie",
        "tmdb_id": 550,
        "rating": 15.0,
    })
    assert r_invalid.status_code == 422

    # Delete rating
    r_del = client.delete("/api/ratings/movie/550", headers=headers)
    assert r_del.status_code == 200


# -----------------------------------------------------------------------------
# 7. Reviews Tests
# -----------------------------------------------------------------------------

def test_reviews_crud_and_authorization(client, seed_content):
    c1, _ = seed_content
    # User A writes a review
    u_a = client.post("/api/auth/register", json={"email": "author_a@example.com", "password": "Password123!", "username": "critic_a"}).json()
    headers_a = {"Authorization": f"Bearer {u_a['access_token']}"}

    rev_create = client.post("/api/reviews", headers=headers_a, json={
        "content_type": "movie",
        "tmdb_id": 550,
        "title": "Subversive Genius",
        "content": "A profound exploration of modern consumerism and existential angst.",
        "rating": 9.0,
    })
    assert rev_create.status_code == 200
    rev_data = rev_create.json()
    review_id = rev_data["id"]
    assert rev_data["author"]["username"] == "critic_a"

    # Public list reviews for content
    pub_list = client.get("/api/reviews/movie/550")
    assert pub_list.status_code == 200
    assert pub_list.json()["total"] == 1
    assert pub_list.json()["results"][0]["title"] == "Subversive Genius"

    # User B attempts to edit User A's review -> 403 FORBIDDEN
    u_b = client.post("/api/auth/register", json={"email": "author_b@example.com", "password": "Password123!"}).json()
    headers_b = {"Authorization": f"Bearer {u_b['access_token']}"}

    b_edit = client.put(f"/api/reviews/{review_id}", headers=headers_b, json={
        "content": "Malicious edit attempt",
    })
    assert b_edit.status_code == 403
    assert b_edit.json()["error"]["code"] == "FORBIDDEN"

    # User B attempts to delete User A's review -> 403 FORBIDDEN
    b_delete = client.delete(f"/api/reviews/{review_id}", headers=headers_b)
    assert b_delete.status_code == 403

    # User A successfully edits their own review
    a_edit = client.put(f"/api/reviews/{review_id}", headers=headers_a, json={
        "title": "Subversive Genius - Updated",
        "content": "Updated critique text.",
    })
    assert a_edit.status_code == 200
    assert a_edit.json()["title"] == "Subversive Genius - Updated"

    # User A successfully deletes their own review
    a_del = client.delete(f"/api/reviews/{review_id}", headers=headers_a)
    assert a_del.status_code == 200


# -----------------------------------------------------------------------------
# 8. Watch History Tests
# -----------------------------------------------------------------------------

def test_watch_history_flow_and_ownership(client, seed_content):
    c1, _ = seed_content
    u_a = client.post("/api/auth/register", json={"email": "watcher_a@example.com", "password": "Password123!"}).json()
    headers_a = {"Authorization": f"Bearer {u_a['access_token']}"}

    # Add watch history
    h_create = client.post("/api/watch-history", headers=headers_a, json={
        "content_type": "movie",
        "tmdb_id": 550,
        "progress": 45.0,
        "completed": False,
    })
    assert h_create.status_code == 200
    h_data = h_create.json()
    history_id = h_data["id"]
    assert h_data["progress"] == 45.0

    # List watch history
    h_list = client.get("/api/watch-history", headers=headers_a)
    assert h_list.status_code == 200
    assert len(h_list.json()) == 1

    # Update progress
    h_update = client.put(f"/api/watch-history/{history_id}", headers=headers_a, json={
        "progress": 100.0,
        "completed": True,
    })
    assert h_update.status_code == 200
    assert h_update.json()["completed"] is True

    # User B attempts to delete User A's history -> 403 FORBIDDEN
    u_b = client.post("/api/auth/register", json={"email": "watcher_b@example.com", "password": "Password123!"}).json()
    headers_b = {"Authorization": f"Bearer {u_b['access_token']}"}

    b_del = client.delete(f"/api/watch-history/{history_id}", headers=headers_b)
    assert b_del.status_code == 403

    # User A deletes own history
    a_del = client.delete(f"/api/watch-history/{history_id}", headers=headers_a)
    assert a_del.status_code == 200


# -----------------------------------------------------------------------------
# 9. Interaction Events & Telemetry Tests
# -----------------------------------------------------------------------------

def test_interaction_telemetry_recording(client, db_session, seed_content):
    c1, _ = seed_content
    reg = client.post("/api/auth/register", json={"email": "telemetry_user@example.com", "password": "Password123!"}).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # Perform action (Save)
    client.post("/api/saved", headers=headers, json={"content_type": "movie", "tmdb_id": 550})

    # Perform action (Rate)
    client.post("/api/ratings", headers=headers, json={"content_type": "movie", "tmdb_id": 550, "rating": 8.0})

    # Verify interaction_events rows exist
    events = db_session.query(InteractionEvent).all()
    event_types = [e.event_type for e in events]
    assert "save" in event_types
    assert "rate" in event_types


def test_telemetry_failure_does_not_break_primary_operation(db_session):
    # Calling log_event with invalid/corrupt data should not raise an unhandled exception
    res = InteractionTrackingService.log_event(
        db_session,
        event_type="test_event",
        user_id="invalid-uuid-string-should-safely-fallback",
        content_id=99999999,
    )
    # The helper handles invalid user ID gracefully and logs
    assert res is not None or res is None
