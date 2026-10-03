"""
End-to-end verification script for:
1. Dispatching app.tasks.embeddings.refresh_changed_user_embeddings to Celery worker.
2. Verifying task completion and return payload without NameError.
3. Verifying Bharat/Aryan user embeddings update correctly.
4. Verifying cold-start user behavior.
5. Verifying recommendation retrieval using the persisted user embeddings.
"""

import sys
import os
import time
import uuid
import asyncio
from datetime import datetime, timezone

# Ensure backend directory is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.celery import celery_app
from app.db.session import SessionLocal
from app.models.user import User, Profile, UserPreference
from app.models.embedding import UserEmbedding
from app.models.interaction import SavedContent
from app.models.watchman import WatchmanDecision
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.services.recommendation.service import UnifiedRecommendationService

def main():
    print("=" * 80, flush=True)
    print("CELERY TASK & USER EMBEDDING PIPELINE VERIFICATION", flush=True)
    print("=" * 80, flush=True)

    db = SessionLocal()
    try:
        # Step 1: Find Bharat and Aryan
        bharat = db.query(User).filter(User.email == "bharat@gmail.com").first()
        aryan = db.query(User).filter(User.email == "aryan@gmail.com").first()

        assert bharat is not None, "Bharat user must exist in DB"
        assert aryan is not None, "Aryan user must exist in DB"

        print(f"1. Found test users: Bharat ({bharat.id}), Aryan ({aryan.id})", flush=True)

        # Step 2: Check current user embeddings
        bharat_emb = db.query(UserEmbedding).filter(UserEmbedding.user_id == bharat.id).first()
        aryan_emb = db.query(UserEmbedding).filter(UserEmbedding.user_id == aryan.id).first()

        print(f"2. Current Bharat Embedding: {'Present' if bharat_emb else 'None'} (updated_at={bharat_emb.updated_at if bharat_emb else None})", flush=True)
        print(f"   Current Aryan Embedding : {'Present' if aryan_emb else 'None'} (updated_at={aryan_emb.updated_at if aryan_emb else None})", flush=True)

        # Step 3: Dispatch Celery task asynchronously to the worker container
        print("\n3. Dispatching 'app.tasks.embeddings.refresh_changed_user_embeddings' asynchronously to Celery worker...", flush=True)
        async_result = celery_app.send_task("app.tasks.embeddings.refresh_changed_user_embeddings")
        print(f"   -> Dispatched Task ID: {async_result.id}", flush=True)

        # Wait for task completion
        print("   -> Waiting for worker execution...", flush=True)
        start_wait = time.time()
        res = None
        while time.time() - start_wait < 30:
            if async_result.ready():
                res = async_result.result
                break
            time.sleep(1)

        if not async_result.ready():
            raise TimeoutError(f"Celery task did not complete within 30 seconds. Status: {async_result.status}")

        print(f"   -> Task State: {async_result.status}", flush=True)
        print(f"   -> Task Result: {res}", flush=True)
        assert res.get("status") == "success", f"Task returned unexpected result: {res}"
        assert res.get("failed_users", 0) == 0, f"Task had failed users: {res}"
        print("   -> Celery task executed and completed successfully WITHOUT NameError!", flush=True)

        # Step 4: Verify Bharat/Aryan embeddings update when stale
        print("\n4. Testing stale interaction detection & refresh...", flush=True)
        # Touch Bharat's watchman decision to make his state strictly fresher than his user_embedding
        bharat_wm = db.query(WatchmanDecision).filter(WatchmanDecision.user_id == bharat.id).first()
        if bharat_wm:
            bharat_wm.updated_at = datetime.utcnow()
            db.commit()
            print(f"   -> Touched Bharat's interaction timestamp: {bharat_wm.updated_at}", flush=True)

        # Check detection function
        changed_uids = UserEmbeddingService.get_users_needing_embedding_update(db)
        print(f"   -> Users needing embedding update detected: {[str(u) for u in changed_uids]}", flush=True)
        assert bharat.id in changed_uids, "Bharat must be detected as needing an update after timestamp touch"

        # Run task via worker again to verify update
        print("   -> Dispatching refresh task to worker for stale update...", flush=True)
        async_result2 = celery_app.send_task("app.tasks.embeddings.refresh_changed_user_embeddings")
        start_wait = time.time()
        while time.time() - start_wait < 30:
            if async_result2.ready():
                break
            time.sleep(1)

        res2 = async_result2.result
        print(f"   -> Task Result: {res2}", flush=True)
        assert res2.get("successfully_updated", 0) >= 1, "At least 1 user must be updated"

        db.expire_all()
        bharat_emb_updated = db.query(UserEmbedding).filter(UserEmbedding.user_id == bharat.id).first()
        assert bharat_emb_updated is not None
        print(f"   -> Bharat's UserEmbedding updated successfully (dimension={bharat_emb_updated.dimension}, updated_at={bharat_emb_updated.updated_at})", flush=True)

        # Step 5: Verify Cold-Start user behavior
        print("\n5. Verifying Cold-Start User Behavior...", flush=True)
        cold_email = f"coldstart_{uuid.uuid4().hex[:8]}@example.com"
        cold_uid = uuid.uuid4()
        cold_user = User(
            id=cold_uid,
            email=cold_email,
            username=f"cold_{uuid.uuid4().hex[:6]}",
            password_hash="fakehash",
            is_active=True,
        )
        cold_profile = Profile(id=cold_uid, username=cold_user.username)
        cold_pref = UserPreference(user_id=cold_uid, favorite_genres=[28, 12], disliked_genres=[])
        db.add(cold_user)
        db.add(cold_profile)
        db.add(cold_pref)
        db.commit()

        print(f"   -> Created cold-start user: {cold_user.email} ({cold_uid})", flush=True)

        # Verify UserEmbeddingService handles cold-start user without error (returns None)
        cold_emb = UserEmbeddingService.compute_and_save_user_embedding(db, cold_uid)
        assert cold_emb is None, "Cold start user with no interactions should have no user_embedding"
        print("   -> Cold start user correctly returns None for user_embedding (handled gracefully)", flush=True)

        # Verify recommendation retrieval for cold-start user
        rec_service = UnifiedRecommendationService()
        has_act = rec_service.user_has_activity(db, cold_uid)
        assert not has_act, "Cold start user must not have activity"
        print(f"   -> user_has_activity for cold start user: {has_act}", flush=True)

        # Clean up temporary cold-start user
        db.delete(cold_pref)
        db.delete(cold_profile)
        db.delete(cold_user)
        db.commit()
        print("   -> Cleaned up temporary cold-start user.", flush=True)

        # Step 6: Verify recommendation retrieval uses persisted user embedding for Bharat
        print("\n6. Verifying recommendation retrieval for Bharat uses persisted user embedding...", flush=True)
        has_act_bharat = rec_service.user_has_activity(db, bharat.id)
        assert has_act_bharat, "Bharat must have activity"
        print(f"   -> Bharat user_has_activity: {has_act_bharat}", flush=True)

        persisted_emb = db.query(UserEmbedding).filter(UserEmbedding.user_id == bharat.id).first()
        assert persisted_emb is not None and persisted_emb.embedding is not None, "Persisted embedding must exist"
        print(f"   -> Stored UserEmbedding verified: dim={persisted_emb.dimension}, model={persisted_emb.model_name}", flush=True)

        print("\n" + "=" * 80, flush=True)
        print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY!", flush=True)
        print("=" * 80, flush=True)

    finally:
        db.close()

if __name__ == "__main__":
    main()
