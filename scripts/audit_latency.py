import json
import time
import uuid
from datetime import datetime, timezone, timedelta
import httpx
from jose import jwt

BASE_URL = "http://localhost:8000"
SECRET_KEY = "To7GVQXCXThEnMqRNepeJgub4olEywRPkiYPlNPW-1PAkEZ9c5LY8B1UlFhGWDuU"

def create_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=7)
    payload = {
        "sub": user_id,
        "user_id": user_id,
        "type": "access",
        "iat": now,
        "jti": str(uuid.uuid4()),
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

USERS = {
    "aryan": {
        "id": "5fa008ee-0848-4293-a1e5-a49fce22dea6",
        "token": create_token("5fa008ee-0848-4293-a1e5-a49fce22dea6"),
    },
    "bharat": {
        "id": "0b5c7ab5-f62c-46b9-8de0-9645f992991d",
        "token": create_token("0b5c7ab5-f62c-46b9-8de0-9645f992991d"),
    }
}


def run_request(client, name, method, path, headers=None, params=None):
    t0 = time.perf_counter()
    resp = client.request(method, f"{BASE_URL}{path}", headers=headers, params=params, timeout=30.0)
    client_elapsed = (time.perf_counter() - t0) * 1000
    server_proc_time = resp.headers.get("X-Process-Time-Ms", "N/A")
    print(f"\n========================================================")
    print(f"REQUEST: {name}")
    print(f"URL: {method} {path} | Status: {resp.status_code}")
    print(f"Client measured: {client_elapsed:.2f} ms | Server X-Process-Time-Ms: {server_proc_time} ms")
    if resp.status_code >= 400:
        print(f"ERROR: {resp.text[:300]}")
    return resp


def main():
    with httpx.Client() as client:
        print("Starting Latency Audit Benchmark...")

        # 1. Warm up health
        run_request(client, "Health Check", "GET", "/health")

        # 2. Movie listing: page 1
        run_request(client, "Movies List (page=1, limit=20)", "GET", "/api/movies", params={"page": 1, "limit": 20})

        # 3. Movie listing: page 2
        run_request(client, "Movies List (page=2, limit=20)", "GET", "/api/movies", params={"page": 2, "limit": 20})

        # 4. Movie listing with collection=popular
        run_request(client, "Movies Popular Collection (limit=18)", "GET", "/api/movies", params={"collection": "popular", "page": 1, "limit": 18})

        # 5. Movie detail (local movie e.g. 550)
        run_request(client, "Movie Details tmdb_id=550", "GET", "/api/movies/550")

        # 6. Movie detail second call (OMDb cached in Redis)
        run_request(client, "Movie Details tmdb_id=550 (2nd call)", "GET", "/api/movies/550")

        # 7. Recommendations for bharat (with stored user embedding / persisted recs)
        headers = {"Authorization": f"Bearer {USERS['bharat']['token']}"}
        run_request(client, "Recommendations Bharat (1st call)", "GET", "/api/recommendations", headers=headers, params={"limit": 20})

        # 8. Recommendations for bharat (2nd call - Redis Cache hit)
        run_request(client, "Recommendations Bharat (2nd call - Redis hit)", "GET", "/api/recommendations", headers=headers, params={"limit": 20})

        # 9. Recommendations for bharat (force_refresh=true - full pipeline execution)
        run_request(client, "Recommendations Bharat (force_refresh=true)", "GET", "/api/recommendations", headers=headers, params={"force_refresh": "true", "limit": 20})

        # 10. Recommendations Home Shelves for bharat
        run_request(client, "Homepage Shelves Bharat", "GET", "/api/recommendations/home", headers=headers)

        # 11. Recommendations Must Like for bharat
        run_request(client, "Must Like Shelf Bharat", "GET", "/api/recommendations/must-like", headers=headers)

        # 12. Recommendations Watched & Liked for bharat
        run_request(client, "Watched & Liked Shelf Bharat", "GET", "/api/recommendations/watched-liked", headers=headers)

        # 13. Recommendations Continue Watching for bharat
        run_request(client, "Continue Watching Shelf Bharat", "GET", "/api/recommendations/continue-watching", headers=headers)


if __name__ == "__main__":
    main()
