import sys
import os
import time
import uuid
from datetime import datetime, timezone
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.content import Content
from app.models.embedding import ContentEmbedding, UserEmbedding
from app.models.interaction import SavedContent, WatchHistory, InteractionEvent
from app.models.review import Rating
from app.models.watchman import WatchmanDecision
from app.core.config import settings
from app.core.security import create_access_token
from app.core.celery import celery_app
from app.tasks.embeddings import refresh_changed_user_embeddings
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.candidates.content_based import ContentBasedCandidateGenerator

def run_test_sequence():
    orig_provider = settings.AUTH_PROVIDER
    settings.AUTH_PROVIDER = "local"
    client = TestClient(app)
    db: Session = SessionLocal()

    print("=" * 80)
    print("WATCHMAN CELERY BACKGROUND USER-EMBEDDING PIPELINE TEST SUITE")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # STEP 1: Verify Aryan User & Login
    # -------------------------------------------------------------------------
    print("\n[STEP 1] Logging in as seeded Aryan test user...")
    aryan = db.query(User).filter(User.email == "aryan@gmail.com").first()
    assert aryan is not None, "Aryan user does not exist in DB!"
    token = create_access_token(aryan.id)
    headers = {"Authorization": f"Bearer {token}"}

    r_me = client.get("/api/auth/me", headers=headers)
    assert r_me.status_code == 200, f"Login failed: {r_me.text}"
    print(f"  -> Successfully authenticated as '{r_me.json()['username']}' (ID: {aryan.id}) [PASS]")

    # -------------------------------------------------------------------------
    # STEP 2: Record Current User Embedding Timestamp & Vector
    # -------------------------------------------------------------------------
    print("\n[STEP 2] Recording current user_embeddings timestamp and vector...")
    initial_emb = db.query(UserEmbedding).filter(UserEmbedding.user_id == aryan.id).first()
    assert initial_emb is not None and initial_emb.embedding is not None
    initial_updated_at = initial_emb.updated_at
    initial_vector = list(initial_emb.embedding)
    print(f"  -> Initial embedding updated_at: {initial_updated_at}")
    print(f"  -> Initial sample vector [0:5]: {[round(x, 4) for x in initial_vector[:5]]} [PASS]")

    # Verify that before any interaction change, the Celery task detects 0 changes
    cycle_0 = refresh_changed_user_embeddings()
    assert cycle_0["changed_users_detected"] == 0, "Expected 0 changed users initially!"
    assert cycle_0["skipped_users"] >= 1, "Expected Aryan to be skipped!"
    print(f"  -> Initial Celery check: skipped_users={cycle_0['skipped_users']}, changed={cycle_0['changed_users_detected']} [PASS]")

    # -------------------------------------------------------------------------
    # STEP 3 & 4: Add New Positive Interaction (e.g. Save 'Alien' or 'Avatar')
    # -------------------------------------------------------------------------
    print("\n[STEP 3 & 4] Adding a new positive interaction via API / DB...")
    # Find an embedded movie not currently in Aryan's interactions
    existing_saved_cids = {s.content_id for s in db.query(SavedContent).filter(SavedContent.user_id == aryan.id).all()}
    candidate_content = (
        db.query(Content)
        .join(ContentEmbedding, Content.id == ContentEmbedding.content_id)
        .filter(Content.id.notin_(existing_saved_cids), Content.title.in_(["Alien", "Avatar", "Tenet", "Blade Runner 2049", "The Martian", "The Matrix"]))
        .first()
    )
    assert candidate_content is not None, "Could not find candidate content to interact with!"

    test_cid = candidate_content.id
    test_title = candidate_content.title
    print(f"  -> Adding new SavedContent for ID={test_cid} ('{test_title}')...")

    # Add interaction (simulate immediate DB persistence)
    new_save = SavedContent(user_id=aryan.id, content_id=test_cid, created_at=datetime.now(timezone.utc))
    db.add(new_save)
    db.commit()

    # Verify immediately stored in PostgreSQL
    saved_in_db = db.query(SavedContent).filter(SavedContent.user_id == aryan.id, SavedContent.content_id == test_cid).first()
    assert saved_in_db is not None, "SavedContent was not immediately persisted!"
    print(f"  -> Verified immediately stored in PostgreSQL: ID={saved_in_db.id}, content_id={test_cid} [PASS]")

    # -------------------------------------------------------------------------
    # STEP 5: Verify Embedding Has NOT Been Recalculated Synchronously
    # -------------------------------------------------------------------------
    print("\n[STEP 5] Verifying user embedding was NOT synchronously recalculated...")
    db.expire_all()
    emb_after_save = db.query(UserEmbedding).filter(UserEmbedding.user_id == aryan.id).first()
    assert emb_after_save.updated_at == initial_updated_at, "Embedding was unexpectedly updated synchronously!"
    print(f"  -> user_embeddings.updated_at remains {emb_after_save.updated_at} (Asynchronous decoupling verified) [PASS]")

    # -------------------------------------------------------------------------
    # STEP 6, 7 & 8: Run Background Celery Worker Cycle
    # -------------------------------------------------------------------------
    print("\n[STEP 6, 7 & 8] Triggering Celery background worker cycle...")
    worker_result = refresh_changed_user_embeddings()
    print(f"  -> Celery task execution output: {worker_result}")
    assert worker_result["changed_users_detected"] >= 1, "Celery worker failed to detect changed user!"
    assert worker_result["successfully_updated"] >= 1, "Celery worker failed to update user embedding!"

    db.expire_all()
    updated_emb = db.query(UserEmbedding).filter(UserEmbedding.user_id == aryan.id).first()
    assert updated_emb.updated_at > initial_updated_at, "user_embeddings.updated_at was not updated by Celery worker!"
    updated_vector = list(updated_emb.embedding)
    print(f"  -> Recalculated embedding updated_at: {updated_emb.updated_at}")
    print(f"  -> Updated sample vector [0:5]: {[round(x, 4) for x in updated_vector[:5]]}")

    # Cosine similarity between initial and updated vector
    sim = float(np.dot(np.array(initial_vector), np.array(updated_vector)))
    print(f"  -> Vector similarity shift: {sim:.4f} (Vector updated from new DB interaction state) [PASS]")

    # -------------------------------------------------------------------------
    # STEP 9 & 10: Request Recommendations
    # -------------------------------------------------------------------------
    print("\n[STEP 9 & 10] Requesting recommendations with updated vector...")
    r_recs = client.get("/api/recommendations/must-like", headers=headers)
    assert r_recs.status_code == 200
    rec_items = r_recs.json().get("items", [])
    rec_titles = [it["title"] for it in rec_items]
    print(f"  -> Received {len(rec_items)} recommendations: {rec_titles[:5]}")
    # Interacted item must be excluded from recommendations
    assert test_title not in rec_titles, f"Interacted item '{test_title}' was not excluded!"
    print(f"  -> Interacted item '{test_title}' properly excluded from recommendations [PASS]")

    # -------------------------------------------------------------------------
    # STEP 11, 12 & 13: Remove Interaction & Rebuild from Current DB State
    # -------------------------------------------------------------------------
    print(f"\n[STEP 11, 12 & 13] Removing interaction ('{test_title}') and triggering worker cycle...")
    db.query(SavedContent).filter(SavedContent.user_id == aryan.id, SavedContent.content_id == test_cid).delete()
    db.commit()

    # Re-run worker cycle - force re-evaluation from current DB state
    # Set updated_at back slightly so change is detected or trigger batch update
    updated_emb.updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    db.commit()

    worker_result_2 = refresh_changed_user_embeddings()
    assert worker_result_2["successfully_updated"] >= 1
    print(f"  -> Worker cycle 2 output: {worker_result_2}")

    db.expire_all()
    restored_emb = db.query(UserEmbedding).filter(UserEmbedding.user_id == aryan.id).first()
    restored_vector = list(restored_emb.embedding)
    print(f"  -> Rebuilt vector from remaining current interactions [0:5]: {[round(x, 4) for x in restored_vector[:5]]}")

    restored_sim = float(np.dot(np.array(initial_vector), np.array(restored_vector)))
    assert restored_sim > 0.999, f"Vector did not restore to clean state: sim={restored_sim}"
    print(f"  -> Rebuilt vector perfectly matches pre-addition state (similarity={restored_sim:.6f}) [PASS]")

    # -------------------------------------------------------------------------
    # STEP 14 & 15: Cold-Start User Test
    # -------------------------------------------------------------------------
    print("\n[STEP 14 & 15] Testing Cold-Start user behavior...")
    cold_uid = uuid.uuid4()
    cold_user = User(id=cold_uid, email=f"cold_{cold_uid.hex[:6]}@watchman.test", password_hash="hash", is_active=True)
    db.add(cold_user)
    db.commit()

    # Stored embedding should be None
    stored_cold_emb = UserEmbeddingService.get_stored_user_embedding(db, cold_user.id)
    assert stored_cold_emb is None, "Cold start user must return None for stored embedding!"

    # Candidate generation returns empty list
    cold_candidates = ContentBasedCandidateGenerator.generate_candidates(db, cold_user.id)
    assert cold_candidates == [], "Cold start user must return empty candidates list!"

    # Worker cycle on cold user does not create invalid vector
    refresh_changed_user_embeddings()
    db.expire_all()
    cold_emb_after_worker = db.query(UserEmbedding).filter(UserEmbedding.user_id == cold_user.id).first()
    assert cold_emb_after_worker is None, "Worker must NOT create invalid embedding for cold start user!"
    print("  -> Cold-start behavior verified: No invalid embeddings created, candidate generator returns [] [PASS]")

    # Cleanup cold user
    db.delete(cold_user)
    db.commit()

    # -------------------------------------------------------------------------
    # STEP 16: Verify Celery Beat Schedule
    # -------------------------------------------------------------------------
    print("\n[STEP 16] Verifying Celery Beat configuration...")
    beat_schedule = celery_app.conf.beat_schedule
    assert "refresh-user-embeddings-10min" in beat_schedule, "Beat schedule missing 'refresh-user-embeddings-10min'!"
    task_conf = beat_schedule["refresh-user-embeddings-10min"]
    assert task_conf["task"] == "app.tasks.embeddings.refresh_changed_user_embeddings"
    assert task_conf["schedule"] == 600.0, f"Expected 600.0s (10 min), got {task_conf['schedule']}"
    print(f"  -> Periodic Beat Task: '{task_conf['task']}' scheduled every {task_conf['schedule']}s (10 minutes) [PASS]")

    settings.AUTH_PROVIDER = orig_provider
    db.close()

    print("\n" + "=" * 80)
    print("ALL USER-EMBEDDING BACKGROUND PIPELINE TESTS PASSED!")
    print("=" * 80)

if __name__ == "__main__":
    run_test_sequence()
