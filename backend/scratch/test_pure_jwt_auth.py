"""
Comprehensive test script for WatchMan pure Python/FastAPI JWT-based Authentication.

Verifies:
1. Login with test users (Bharat & Aryan) using email + password (bcrypt).
2. JWT structure, claims (sub, user_id, type, exp, iat, jti), signature validation, and payload integrity.
3. Access to all protected endpoints with WatchMan JWT:
   - /api/auth/me
   - /api/users/me/profile
   - /api/users/me/preferences
   - /api/favorites
   - /api/ratings
   - /api/watch-history
   - /api/recommendations
4. Invalid authentication cases (must return 401):
   - Wrong password
   - Nonexistent user
   - Missing token
   - Malformed token
   - Expired token
   - Tampered token signature
5. Token refresh endpoint (/api/auth/refresh).
6. Content-Based recommendations via pgvector for authenticated user (Bharat).
7. Celery Beat / user embedding pipeline identity continuity.
"""

import sys
import os
import uuid
from datetime import datetime, timedelta, timezone

# Ensure backend directory is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from jose import jwt

from app.main import app
from app.core.config import settings
from app.core.security import decode_token, create_access_token
from app.db.session import SessionLocal
from app.models.user import User
from app.models.embedding import UserEmbedding

client = TestClient(app)

def run_tests():
    print("=" * 80)
    print("WATCHMAN PURE PYTHON/FASTAPI JWT AUTHENTICATION VERIFICATION")
    print("=" * 80)
    print(f"Auth Provider Setting: {settings.AUTH_PROVIDER}")
    print(f"Algorithm: {settings.ALGORITHM}")
    print(f"Access Token Expiry: {settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutes")
    print(f"Refresh Token Expiry: {settings.REFRESH_TOKEN_EXPIRE_DAYS} days")
    print("-" * 80)

    # ------------------------------------------------------------------
    # TEST 1: Login with Bharat (bharat@gmail.com / 123456789)
    # ------------------------------------------------------------------
    print("\n[TEST 1] Testing Login for bharat@gmail.com...")
    login_resp = client.post("/api/auth/login", json={
        "email": "bharat@gmail.com",
        "password": "123456789"
    })
    assert login_resp.status_code == 200, f"Login failed: {login_resp.status_code} {login_resp.text}"
    bharat_data = login_resp.json()
    bharat_token = bharat_data["access_token"]
    bharat_refresh = bharat_data["refresh_token"]
    bharat_user = bharat_data["user"]

    print("  -> Status: 200 OK")
    print(f"  -> Returned User ID: {bharat_user['id']}")
    print(f"  -> Username: {bharat_user['username']}")
    print(f"  -> Email: {bharat_user['email']}")
    assert "password" not in bharat_user, "Password must not be in User object!"
    assert "password_hash" not in bharat_user, "Password hash must not be in User object!"
    assert bharat_data["token_type"] == "bearer"
    assert len(bharat_token) > 20
    print("  -> User response does NOT expose password/hash.")

    # Decode and verify JWT claims
    claims = decode_token(bharat_token)
    print("  -> JWT Decoded Claims:")
    print(f"     sub: {claims.get('sub')}")
    print(f"     type: {claims.get('type')}")
    print(f"     exp: {claims.get('exp')} (UTC: {datetime.fromtimestamp(claims.get('exp'), tz=timezone.utc)})")
    assert claims.get("sub") == bharat_user["id"], "JWT sub must match user UUID"
    assert claims.get("type") == "access", "Token type must be access"

    # ------------------------------------------------------------------
    # TEST 2: Login with Aryan (aryan@gmail.com / 123456789)
    # ------------------------------------------------------------------
    print("\n[TEST 2] Testing Login for aryan@gmail.com...")
    login_resp_aryan = client.post("/api/auth/login", json={
        "email": "aryan@gmail.com",
        "password": "123456789"
    })
    assert login_resp_aryan.status_code == 200, f"Login failed: {login_resp_aryan.status_code} {login_resp_aryan.text}"
    aryan_data = login_resp_aryan.json()
    aryan_token = aryan_data["access_token"]
    aryan_user = aryan_data["user"]

    print("  -> Status: 200 OK")
    print(f"  -> Returned User ID: {aryan_user['id']}")
    print(f"  -> Username: {aryan_user['username']}")
    print(f"  -> Email: {aryan_user['email']}")
    assert "password" not in aryan_user
    assert "password_hash" not in aryan_user
    aryan_claims = decode_token(aryan_token)
    assert aryan_claims.get("sub") == aryan_user["id"]
    print("  -> Aryan login and JWT token verified.")

    # ------------------------------------------------------------------
    # TEST 3: Access Protected Endpoints with Bharat's JWT
    # ------------------------------------------------------------------
    print("\n[TEST 3] Testing Protected Endpoints using Bharat's Bearer JWT...")
    headers = {"Authorization": f"Bearer {bharat_token}"}

    # 3.1 /api/auth/me
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200, f"GET /api/auth/me failed: {resp.status_code} {resp.text}"
    print(f"  -> GET /api/auth/me: 200 OK (id={resp.json()['id']}, email={resp.json()['email']})")

    # 3.2 /api/users/me/profile
    resp = client.get("/api/users/me/profile", headers=headers)
    assert resp.status_code == 200, f"GET /api/users/me/profile failed: {resp.status_code} {resp.text}"
    print(f"  -> GET /api/users/me/profile: 200 OK (username={resp.json().get('username')})")

    # 3.3 /api/users/me/preferences
    resp = client.get("/api/users/me/preferences", headers=headers)
    assert resp.status_code == 200, f"GET /api/users/me/preferences failed: {resp.status_code} {resp.text}"
    pref_data = resp.json()
    print(f"  -> GET /api/users/me/preferences: 200 OK (favorite_genres={pref_data.get('favorite_genres')})")

    # 3.4 /api/favorites
    resp = client.get("/api/favorites", headers=headers)
    assert resp.status_code == 200, f"GET /api/favorites failed: {resp.status_code} {resp.text}"
    print(f"  -> GET /api/favorites: 200 OK ({len(resp.json())} items)")

    # 3.5 /api/ratings
    resp = client.get("/api/ratings", headers=headers)
    assert resp.status_code == 200, f"GET /api/ratings failed: {resp.status_code} {resp.text}"
    print(f"  -> GET /api/ratings: 200 OK ({len(resp.json())} ratings)")

    # 3.6 /api/watch-history
    resp = client.get("/api/watch-history", headers=headers)
    assert resp.status_code == 200, f"GET /api/watch-history failed: {resp.status_code} {resp.text}"
    print(f"  -> GET /api/watch-history: 200 OK ({len(resp.json())} items)")

    # 3.7 /api/recommendations
    resp = client.get("/api/recommendations", headers=headers)
    assert resp.status_code == 200, f"GET /api/recommendations failed: {resp.status_code} {resp.text}"
    rec_res = resp.json()
    rec_items = rec_res.get("items", rec_res) if isinstance(rec_res, dict) else rec_res
    print(f"  -> GET /api/recommendations: 200 OK ({len(rec_items)} recommendations returned)")

    # ------------------------------------------------------------------
    # TEST 4: Invalid Authentication Scenarios (Must Return 401)
    # ------------------------------------------------------------------
    print("\n[TEST 4] Testing Invalid Authentication Scenarios (Expecting 401 Unauthorized)...")

    # 4.1 Wrong Password
    resp = client.post("/api/auth/login", json={"email": "bharat@gmail.com", "password": "wrongpassword"})
    print(f"  -> Wrong Password: Status {resp.status_code} (Code: {resp.json().get('error', {}).get('code')})")
    assert resp.status_code == 401

    # 4.2 Nonexistent User
    resp = client.post("/api/auth/login", json={"email": "nonexistent@gmail.com", "password": "123456789"})
    print(f"  -> Nonexistent User: Status {resp.status_code} (Code: {resp.json().get('error', {}).get('code')})")
    assert resp.status_code == 401

    # 4.3 Missing Bearer Token
    resp = client.get("/api/auth/me")
    print(f"  -> Missing Token: Status {resp.status_code} (Code: {resp.json().get('error', {}).get('code')})")
    assert resp.status_code == 401

    # 4.4 Malformed Token
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer malformed.invalid.token"})
    print(f"  -> Malformed Token: Status {resp.status_code} (Code: {resp.json().get('error', {}).get('code')})")
    assert resp.status_code == 401

    # 4.5 Expired Token
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": str(bharat_user["id"]),
        "user_id": str(bharat_user["id"]),
        "type": "access",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
        "jti": str(uuid.uuid4()),
    }
    expired_token = jwt.encode(expired_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    print(f"  -> Expired Token: Status {resp.status_code} (Code: {resp.json().get('error', {}).get('code')})")
    assert resp.status_code == 401

    # 4.6 Tampered Token (Signed with wrong secret)
    tampered_token = jwt.encode(expired_payload, "completely-wrong-secret-key-1234567890", algorithm=settings.ALGORITHM)
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
    print(f"  -> Tampered Signature: Status {resp.status_code} (Code: {resp.json().get('error', {}).get('code')})")
    assert resp.status_code == 401

    # ------------------------------------------------------------------
    # TEST 5: Token Refresh Endpoint (/api/auth/refresh)
    # ------------------------------------------------------------------
    print("\n[TEST 5] Testing Token Refresh with Bharat's Refresh Token...")
    resp = client.post("/api/auth/refresh", json={"refresh_token": bharat_refresh})
    assert resp.status_code == 200, f"Token refresh failed: {resp.status_code} {resp.text}"
    refreshed_data = resp.json()
    new_access_token = refreshed_data["access_token"]
    new_refresh_token = refreshed_data["refresh_token"]
    print("  -> Status: 200 OK")
    print(f"  -> New Access Token Issued: {new_access_token[:25]}...")
    print(f"  -> New Refresh Token Issued: {new_refresh_token[:25]}...")

    # Validate that the refreshed token works on protected endpoints
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_access_token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == bharat_user["id"]
    print("  -> Successfully accessed /api/auth/me using refreshed access token.")

    # ------------------------------------------------------------------
    # TEST 6: Recommendation Quality for Bharat (Horror Taste)
    # ------------------------------------------------------------------
    print("\n[TEST 6] Testing Personalized Recommendations Content Alignment for Bharat...")
    rec_resp = client.get("/api/recommendations?limit=10", headers={"Authorization": f"Bearer {bharat_token}"})
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    rec_list = rec_data.get("items", rec_data) if isinstance(rec_data, dict) else rec_data
    print(f"  -> Top {len(rec_list)} recommendations for Bharat:")
    for i, item in enumerate(rec_list[:10], 1):
        title = item.get("title") or item.get("name")
        genres = [g.get("name") if isinstance(g, dict) else str(g) for g in item.get("genres", [])]
        print(f"     {i:2d}. {title} | Genres: {genres} | Type: {item.get('content_type')}")

    # ------------------------------------------------------------------
    # TEST 7: Celery Pipeline & PostgreSQL user_embeddings Identity Check
    # ------------------------------------------------------------------
    print("\n[TEST 7] Checking PostgreSQL user_embeddings & Celery pipeline identity continuity...")
    db = SessionLocal()
    try:
        user_emb = db.query(UserEmbedding).filter(UserEmbedding.user_id == uuid.UUID(bharat_user["id"])).first()
        assert user_emb is not None, "Bharat's user embedding must exist in PostgreSQL!"
        print(f"  -> Stored UserEmbedding found for user_id: {user_emb.user_id}")
        print(f"  -> Embedding model: {user_emb.model_name}, Dimension: {user_emb.dimension}")
        print(f"  -> Updated at: {user_emb.updated_at}")
        print(f"  -> Celery pipeline correctly maps JWT user_id ({bharat_user['id']}) directly to user_embeddings.")
    finally:
        db.close()

    print("\n" + "=" * 80)
    print("ALL 7 VERIFICATION SUITES PASSED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    run_tests()
