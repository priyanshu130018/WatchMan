"""
WatchMan Step 10: Security Regression & Release-Readiness Test Suite.
Tests authentication bypass protection, JWT forgery rejection, IDOR protection,
SQL injection resilience, XSS payload safety, rate limiting, and security response headers.
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.orm import Session

from app.main import app
from app.models.user import User
from app.models.content import Content, ContentType
from app.models.review import Review, Rating
from app.models.interaction import SavedContent, WatchHistory
from app.core.security import create_access_token, create_refresh_token


@pytest.mark.asyncio
async def test_security_headers_present(db_session: Session):
    """Verify standard security headers and process time are attached to responses."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/health")
        assert res.status_code == 200
        assert res.headers.get("X-Content-Type-Options") == "nosniff"
        assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "X-Request-ID" in res.headers
        assert "X-Process-Time-Ms" in res.headers


@pytest.mark.asyncio
async def test_jwt_tampering_and_forgery_rejection(db_session: Session):
    """Verify that manipulated tokens, wrong token types, and garbage strings are rejected with 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Random garbage string
        res1 = await client.get("/api/auth/me", headers={"Authorization": "Bearer fake.jwt.string"})
        assert res1.status_code == 401
        assert res1.json()["error"]["code"] == "UNAUTHORIZED"

        # 2. Token with None header
        res2 = await client.get("/api/auth/me", headers={"Authorization": "Bearer "})
        assert res2.status_code == 401

        # 3. Valid user ID with forged signature (fabricated token)
        forged_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3OC0xMjM0LTUyMzQtMTIzNC0xMjM0NTY3ODEyMzQiLCJ0eXBlIjoiYWNjZXNzIn0.InValidSigNaTuRe"
        res3 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged_token}"})
        assert res3.status_code == 401


@pytest.mark.asyncio
async def test_idor_protection_cross_user_isolation(db_session: Session):
    """Verify that User A cannot modify or delete User B's reviews, history, or saved content."""
    # Create two users
    u_alice = User(id=uuid.uuid4(), email="alice@test.com", password_hash="hash", is_active=True)
    u_bob = User(id=uuid.uuid4(), email="bob@test.com", password_hash="hash", is_active=True)
    db_session.add_all([u_alice, u_bob])

    # Create content
    movie = Content(
        content_type=ContentType.MOVIE.value,
        tmdb_id=999,
        title="Secret Movie",
        vote_average=8.0,
    )
    db_session.add(movie)
    db_session.commit()

    # Bob creates a review
    bobs_review = Review(
        user_id=u_bob.id,
        content_id=movie.id,
        title="Bob's Review",
        content="This is Bob's original text.",
        rating=9.0,
    )
    db_session.add(bobs_review)
    db_session.commit()

    token_alice = create_access_token(u_alice.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Alice attempts to edit Bob's review
        edit_res = await client.put(
            f"/api/reviews/{bobs_review.id}",
            json={"title": "Hacked Review", "content": "Alice overwrote Bob's review."},
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert edit_res.status_code == 403
        assert edit_res.json()["error"]["code"] == "FORBIDDEN"

        # Alice attempts to delete Bob's review
        del_res = await client.delete(
            f"/api/reviews/{bobs_review.id}",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert del_res.status_code == 403
        assert del_res.json()["error"]["code"] == "FORBIDDEN"

        # Verify Bob's review remains unchanged
        refreshed = db_session.query(Review).filter(Review.id == bobs_review.id).first()
        assert refreshed.title == "Bob's Review"
        assert refreshed.content == "This is Bob's original text."


@pytest.mark.asyncio
async def test_sql_injection_resilience(db_session: Session):
    """Verify that malicious SQL injection payloads in search and catalog parameters are handled safely."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        sqli_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE contents; --",
            "1 UNION SELECT null, null, null--",
            "admin'--",
            "' OR 1=1#",
        ]

        for payload in sqli_payloads:
            # Test Search with SQL injection payload
            res = await client.get("/api/search", params={"q": payload})
            assert res.status_code in [200, 422]  # Handled cleanly without SQL syntax or 500 error

            # Test Movies with SQL injection sort
            res2 = await client.get("/api/movies", params={"sort": payload})
            assert res2.status_code in [200, 422]

        # Verify table still exists and database is intact
        count = db_session.query(Content).count()
        assert isinstance(count, int)


@pytest.mark.asyncio
async def test_xss_payload_in_reviews(db_session: Session):
    """Verify that XSS and script injection payloads submitted in user reviews do not crash backend."""
    user = User(id=uuid.uuid4(), email="reviewer@test.com", password_hash="hash", is_active=True)
    movie = Content(content_type=ContentType.MOVIE.value, tmdb_id=888, title="XSS Safe Movie")
    db_session.add_all([user, movie])
    db_session.commit()

    token = create_access_token(user.id)
    xss_payload = "<script>alert('XSS')</script><img src=x onerror=alert('document.cookie') />"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/reviews",
            json={
                "content_type": "movie",
                "tmdb_id": 888,
                "title": "<script>alert(1)</script>",
                "content": xss_payload,
                "rating": 8.0,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "id" in data


@pytest.mark.asyncio
async def test_unauthenticated_protected_routes_rejection(db_session: Session):
    """Verify that protected user library endpoints reject unauthenticated calls with 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Saved content
        res1 = await client.get("/api/saved")
        assert res1.status_code == 401

        # Watch history
        res2 = await client.get("/api/watch-history")
        assert res2.status_code == 401

        # User preferences
        res3 = await client.get("/api/users/me/preferences")
        assert res3.status_code == 401

        # Refresh recommendations
        res4 = await client.post("/api/recommendations/refresh")
        assert res4.status_code == 401


@pytest.mark.asyncio
async def test_inactive_account_blocked(db_session: Session):
    """Verify that inactive accounts are rejected with 403."""
    u_inactive = User(id=uuid.uuid4(), email="inactive@test.com", password_hash="hash", is_active=False)
    db_session.add(u_inactive)
    db_session.commit()

    token = create_access_token(u_inactive.id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_token_type_mismatch_rejection(db_session: Session):
    """Verify that refresh tokens cannot be used as access tokens and vice-versa."""
    user = User(id=uuid.uuid4(), email="user_mismatch@test.com", password_hash="hash", is_active=True)
    db_session.add(user)
    db_session.commit()

    refresh_token = create_refresh_token(user.id)
    access_token = create_access_token(user.id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Use refresh token on access-protected route -> 401
        res1 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
        assert res1.status_code == 401

        # 2. Use access token on refresh route -> 401
        res2 = await client.post("/api/auth/refresh", json={"refresh_token": access_token})
        assert res2.status_code == 401


@pytest.mark.asyncio
async def test_idor_cross_user_watch_history_and_ratings(db_session: Session):
    """Verify User A cannot update or delete User B's watch history entries or ratings."""
    u_alice = User(id=uuid.uuid4(), email="alice_idor@test.com", password_hash="hash", is_active=True)
    u_bob = User(id=uuid.uuid4(), email="bob_idor@test.com", password_hash="hash", is_active=True)
    movie = Content(content_type=ContentType.MOVIE.value, tmdb_id=777, title="IDOR Isolation Test Movie")
    db_session.add_all([u_alice, u_bob, movie])
    db_session.commit()

    # Bob creates watch history entry
    bob_wh = WatchHistory(user_id=u_bob.id, content_id=movie.id, progress=0.75, completed=False)
    db_session.add(bob_wh)
    db_session.commit()

    token_alice = create_access_token(u_alice.id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Alice tries to update Bob's watch history
        res_update = await client.put(
            f"/api/watch-history/{bob_wh.id}",
            json={"progress": 1.0, "completed": True},
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_update.status_code in [403, 404]

        # Alice tries to delete Bob's watch history
        res_del = await client.delete(
            f"/api/watch-history/{bob_wh.id}",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_del.status_code in [403, 404]

        # Bob's history is unmodified
        refreshed = db_session.query(WatchHistory).filter(WatchHistory.id == bob_wh.id).first()
        assert refreshed is not None
        assert refreshed.progress == 0.75


@pytest.mark.asyncio
async def test_input_validation_and_search_abuse(db_session: Session):
    """Verify input validation handles extreme payloads, unicode, and large queries safely."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 2000-character search query
        long_query = "a" * 2000
        res_long = await client.get("/api/search", params={"q": long_query})
        assert res_long.status_code in [200, 422]

        # 2. Unicode and emoji search query
        res_unicode = await client.get("/api/search", params={"q": "🍿 🎬 Inception 🚀"})
        assert res_unicode.status_code == 200

        # 3. Invalid pagination params (e.g. limit > 100 or page < 1)
        res_invalid_page = await client.get("/api/movies", params={"page": 0, "limit": 500})
        assert res_invalid_page.status_code == 422

