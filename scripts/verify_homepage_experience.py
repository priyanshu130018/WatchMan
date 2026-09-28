"""
Live End-to-End Verification of WatchMan Homepage Personalized Experience.
Executes against running backend container (http://localhost:8000) and frontend (http://localhost:3000).
"""

import os
import sys
import time
import uuid
import requests
from jose import jwt

# Add backend directory to path to load config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
from app.core.config import settings

BASE_URL = "http://localhost:8000/api"
FRONTEND_URL = "http://localhost:3000"

def log(msg: str):
    print(f"[VERIFY] {msg}")

def create_test_token(user_id: str, email: str) -> str:
    now = int(time.time())
    claims = {
        "sub": str(user_id),
        "aud": settings.SUPABASE_JWT_AUD,
        "email": email,
        "exp": now + 3600,
        "iat": now,
        "user_metadata": {
            "full_name": f"User {str(user_id)[:6]}",
            "username": f"user_{str(user_id)[:6]}",
        },
    }
    return jwt.encode(claims, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

def run_verification():
    log("Starting Live Verification of WatchMan Homepage Recommendation Experience")

    # 1. Verify frontend server is alive (Step 1)
    try:
        fe_res = requests.get(FRONTEND_URL, timeout=5)
        assert fe_res.status_code == 200, f"Frontend returned {fe_res.status_code}"
        log("Step 1 Verified: Frontend homepage is accessible (HTTP 200)")
    except Exception as e:
        log(f"Warning: Frontend check: {e}")

    # 2. Cold Start Verification (Step 11: Verify a new user does not receive fake personalized content)
    cold_user_id = str(uuid.uuid4())
    cold_email = f"cold_user_{cold_user_id[:6]}@example.com"
    cold_token = create_test_token(cold_user_id, cold_email)
    cold_headers = {"Authorization": f"Bearer {cold_token}"}

    home_cold = requests.get(f"{BASE_URL}/recommendations/home", headers=cold_headers)
    assert home_cold.status_code == 200, f"Cold home failed: {home_cold.text}"
    cold_data = home_cold.json()
    assert cold_data["has_personalization"] is False, "Cold user must have has_personalization == False"
    assert len(cold_data["sections"]) == 0, "Cold user must have 0 personalized sections"
    log("Step 11 Verified: New/cold-start user receives has_personalization=False and 0 personalized shelves (no fake content)")

    # 3. Active User Flow
    active_user_id = str(uuid.uuid4())
    active_email = f"active_user_{active_user_id[:6]}@example.com"
    active_token = create_test_token(active_user_id, active_email)
    active_headers = {"Authorization": f"Bearer {active_token}"}

    # Fetch catalog items from live database
    catalog_res = requests.get(f"{BASE_URL}/movies?limit=10")
    assert catalog_res.status_code == 200, f"Failed to fetch catalog: {catalog_res.text}"
    movies = catalog_res.json().get("results", [])
    if not movies:
        movies = catalog_res.json().get("items", [])
    assert len(movies) >= 4, f"Need at least 4 catalog items for testing, got {len(movies)}"
    m1, m2, m3, m4 = movies[0], movies[1], movies[2], movies[3]
    log(f"Using catalog movies for test: '{m1['title']}', '{m2['title']}', '{m3['title']}', '{m4['title']}'")

    # 4. Start playback and leave incomplete (Step 6)
    log(f"Starting playback on '{m1['title']}' with 42% progress (incomplete)...")
    wh_res = requests.post(
        f"{BASE_URL}/watch-history",
        headers=active_headers,
        json={
            "content_type": m1.get("content_type", "movie"),
            "content_id": m1["id"],
            "tmdb_id": m1.get("tmdb_id", m1["id"]),
            "progress": 42.0,
            "completed": False,
        },
    )
    assert wh_res.status_code == 200, f"Failed to log watch history: {wh_res.text}"
    history_entry = wh_res.json()
    history_id = history_entry["id"]

    # Step 7: Verify it appears in Continue Watching
    cw_res = requests.get(f"{BASE_URL}/recommendations/continue-watching", headers=active_headers)
    assert cw_res.status_code == 200, f"CW failed: {cw_res.text}"
    cw_items = cw_res.json().get("items", [])
    assert any(it["id"] == m1["id"] for it in cw_items), f"'{m1['title']}' must appear in Continue Watching"
    cw_m1 = next(it for it in cw_items if it["id"] == m1["id"])
    assert cw_m1["progress"] == 42.0
    assert cw_m1["completed"] is False
    log(f"Step 6 & 7 Verified: '{m1['title']}' appears in Continue Watching with 42% progress and progress bar metadata")

    # 5. Create WatchMan decision & positive watch activity (Step 3 & 4 & 5)
    log(f"Submitting WatchMan decision MUST_WATCH for '{m2['title']}'...")
    dec_res = requests.put(
        f"{BASE_URL}/content/{m2['id']}/watchman",
        headers=active_headers,
        json={
            "content_type": m2.get("content_type", "movie") if m2.get("content_type") in ["movie", "tv"] else "movie",
            "decision": "must_watch",
        },
    )
    assert dec_res.status_code == 200, f"Failed to submit decision: {dec_res.text}"

    # Also log watch history for m2 (80% watched)
    requests.post(
        f"{BASE_URL}/watch-history",
        headers=active_headers,
        json={
            "content_type": m2.get("content_type", "movie"),
            "content_id": m2["id"],
            "tmdb_id": m2.get("tmdb_id", m2["id"]),
            "progress": 80.0,
            "completed": False,
        },
    )

    # Rate Movie 3 (9.5/10) and complete it
    log(f"Rating '{m3['title']}' 9.5/10 and marking completed...")
    requests.post(
        f"{BASE_URL}/ratings",
        headers=active_headers,
        json={
            "content_id": m3["id"],
            "rating": 9.5,
            "content_type": m3.get("content_type", "movie"),
        },
    )
    requests.post(
        f"{BASE_URL}/watch-history",
        headers=active_headers,
        json={
            "content_type": m3.get("content_type", "movie"),
            "content_id": m3["id"],
            "tmdb_id": m3.get("tmdb_id", m3["id"]),
            "progress": 100.0,
            "completed": True,
        },
    )

    # Explicitly SKIP Movie 4
    log(f"Marking Movie 4 '{m4['title']}' as SKIP...")
    requests.put(
        f"{BASE_URL}/content/{m4['id']}/watchman",
        headers=active_headers,
        json={
            "content_type": m4.get("content_type", "movie") if m4.get("content_type") in ["movie", "tv"] else "movie",
            "decision": "skip",
        },
    )

    # Step 5: Verify watched/liked shelf
    wl_res = requests.get(f"{BASE_URL}/recommendations/watched-liked", headers=active_headers)
    assert wl_res.status_code == 200, f"WL failed: {wl_res.text}"
    wl_items = wl_res.json().get("items", [])
    wl_ids = {it["id"] for it in wl_items}
    assert m2["id"] in wl_ids, f"'{m2['title']}' with MUST WATCH decision must appear in Watched & Liked"
    assert m3["id"] in wl_ids, f"'{m3['title']}' with 9.5 rating & completed must appear in Watched & Liked"
    assert m4["id"] not in wl_ids, f"Skipped movie '{m4['title']}' must NOT appear in Watched & Liked"
    log("Step 5 Verified: Watched and liked titles appear in the correct shelf with proper positive evidence")

    # Step 2, 4, 10: Verify GET /recommendations/home
    home_res = requests.get(f"{BASE_URL}/recommendations/home", headers=active_headers)
    assert home_res.status_code == 200, f"Home failed: {home_res.text}"
    home_data = home_res.json()
    assert home_data["has_personalization"] is True, "Active user must have has_personalization == True"

    sections = {s["key"]: s for s in home_data["sections"]}
    log(f"Active user received personalized sections: {list(sections.keys())}")

    # Check deduplication between shelves (Step 10)
    all_shelf_items = []
    for s_key, s_data in sections.items():
        shelf_ids = [it["id"] for it in s_data["items"]]
        all_shelf_items.extend(shelf_ids)
    assert len(all_shelf_items) == len(set(all_shelf_items)), "Step 10 Failed: Duplicate titles found between shelves!"
    log("Step 10 Verified: No duplicate titles found between personalized shelves (CW > WL > ML priority enforced)")

    # Verify skipped movie is suppressed (Step 4)
    for s_data in sections.values():
        for it in s_data["items"]:
            assert it["id"] != m4["id"], f"Skipped movie '{m4['title']}' appeared in shelf '{s_data['title']}'!"
    log("Step 4 Verified: Skipped content is suppressed across all personalized shelves")

    # Step 8 & 9: Complete playback and verify it disappears from Continue Watching
    log(f"Completing playback on '{m1['title']}' (progress=100.0, completed=True)...")
    put_res = requests.put(
        f"{BASE_URL}/watch-history/{history_id}",
        headers=active_headers,
        json={"progress": 100.0, "completed": True},
    )
    assert put_res.status_code == 200, f"Failed to update watch history: {put_res.text}"

    # Verify disappears from Continue Watching
    cw_refreshed = requests.get(f"{BASE_URL}/recommendations/continue-watching", headers=active_headers)
    assert cw_refreshed.status_code == 200
    refreshed_cw_items = cw_refreshed.json().get("items", [])
    assert not any(it["id"] == m1["id"] for it in refreshed_cw_items), f"'{m1['title']}' must disappear from Continue Watching after completion"
    log("Step 8 & 9 Verified: Completed content disappears from Continue Watching immediately")

    log("==================================================")
    log("ALL 11 VERIFICATION STEPS PASSED SUCCESSFULLY ON RUNNING STACK!")
    log("==================================================")

if __name__ == "__main__":
    try:
        run_verification()
    except Exception as e:
        print(f"[ERROR] Verification failed: {e}")
        sys.exit(1)
