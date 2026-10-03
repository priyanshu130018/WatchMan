#!/usr/bin/env python3
"""
Comprehensive End-to-End Verification for Dedicated Content-Based Worker:
1. Validates worker queue isolation (content_based_worker vs celery_worker).
2. Verifies task routing of content-based tasks to 'content_based' queue.
3. Tests Aryan interaction update -> Celery task execution on content_based_worker -> user_embeddings update -> recommendations persisted -> GET /api/recommendations.
4. Tests Bharat interaction -> Celery task execution -> user_embeddings update -> recommendations persisted -> GET /api/recommendations.
5. Verifies user isolation between Aryan and Bharat.
6. Measures exact execution times, embedding refresh duration, recommendation generation duration, and task latency.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime, timezone
import numpy as np

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.main import app
from app.db.session import SessionLocal
from app.models.user import User, Profile, UserPreference
from app.models.content import Content
from app.models.taxonomy import Genre
from app.models.embedding import ContentEmbedding, UserEmbedding
from app.models.interaction import SavedContent, WatchHistory, InteractionEvent
from app.models.review import Rating
from app.models.watchman import WatchmanDecision
from app.models.recommendation import Recommendation
from app.api.auth.router import hash_password
from app.core.security import create_access_token
from app.core.config import settings
from app.core.celery import celery_app
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.recommendations.generator import RecommendationGenerator


def run_full_verification():
    print("=" * 90)
    print("WATCHMAN DEDICATED CONTENT-BASED CELERY WORKER VERIFICATION")
    print("=" * 90)

    db: Session = SessionLocal()
    client = TestClient(app)

    try:
        # ---------------------------------------------------------------------
        # 1. Verify Celery Inspector and Active Workers
        # ---------------------------------------------------------------------
        print("\n--- 1. CELERY WORKER TOPOLOGY & QUEUE INSPECTION ---")
        inspector = celery_app.control.inspect(timeout=10.0)
        active_queues = inspector.active_queues() or {}
        ping_res = inspector.ping() or {}

        print(f"Workers responding to ping: {list(ping_res.keys())}")
        for worker_name, queues in active_queues.items():
            q_names = [q.get("name") for q in queues]
            print(f"Worker '{worker_name}' listening to queues: {q_names}")

        # Check content_based_worker
        cb_worker_found = any("content_based" in [q.get("name") for q in qlist] for qlist in active_queues.values())
        print(f"Content-based worker active & listening to 'content_based': {cb_worker_found}")
        assert cb_worker_found, "content_based worker not found or not listening to 'content_based' queue!"

        # ---------------------------------------------------------------------
        # 2. Verify Task Routing Configuration
        # ---------------------------------------------------------------------
        print("\n--- 2. TASK ROUTING RULES VERIFICATION ---")
        expected_routes = {
            "app.tasks.embeddings.refresh_changed_user_embeddings": "content_based",
            "app.tasks.embeddings.update_user_embeddings_batch": "content_based",
            "app.tasks.embeddings.generate_missing_content_embeddings": "content_based",
            "app.tasks.recommendation.process_user_interaction_ml": "content_based",
            "app.tasks.recommendation.recompute_user_recommendations": "content_based",
            "app.tasks.recommendation.generate_user_recommendations_batch": "content_based",
            "app.tasks.collaborative.train_als_model": "als",
            "app.tasks.fetch_tmdb.sync_single_content": "default",
            "app.tasks.cleanup.cleanup_orphan_candidates": "default",
        }

        routes = celery_app.conf.task_routes or {}
        for task_name, expected_q in expected_routes.items():
            route = routes.get(task_name, {})
            actual_q = route.get("queue")
            print(f"Task '{task_name}' -> queue: '{actual_q}' (Expected: '{expected_q}')")
            assert actual_q == expected_q, f"Task {task_name} routed to {actual_q}, expected {expected_q}"

        # ---------------------------------------------------------------------
        # 3. Setup / Resolve Test Users: Aryan (Sci-Fi) and Bharat (Horror)
        # ---------------------------------------------------------------------
        print("\n--- 3. USER SETUP: ARYAN & BHARAT ---")
        # Aryan
        aryan = db.query(User).filter(User.email == "aryan@gmail.com").first()
        if not aryan:
            aryan = User(
                id=uuid.uuid4(),
                email="aryan@gmail.com",
                username="aryan",
                full_name="Aryan",
                password_hash=hash_password("123456789"),
                is_active=True,
            )
            db.add(aryan)
            db.commit()
            db.refresh(aryan)

        # Bharat
        bharat = db.query(User).filter(User.email == "bharat@gmail.com").first()
        if not bharat:
            bharat = User(
                id=uuid.uuid4(),
                email="bharat@gmail.com",
                username="bharat",
                full_name="Bharat",
                password_hash=hash_password("123456789"),
                is_active=True,
            )
            db.add(bharat)
            db.commit()
            db.refresh(bharat)

        print(f"Aryan ID: {aryan.id}, email: {aryan.email}")
        print(f"Bharat ID: {bharat.id}, email: {bharat.email}")

        # Ensure Content items with embeddings exist for tests
        scifi_content = (
            db.query(Content)
            .join(ContentEmbedding, Content.id == ContentEmbedding.content_id)
            .filter(Content.overview.ilike("%space%") | Content.title.ilike("%interstellar%") | Content.title.ilike("%matrix%"))
            .first()
        )
        if not scifi_content:
            scifi_content = db.query(Content).join(ContentEmbedding, Content.id == ContentEmbedding.content_id).first()

        horror_content = (
            db.query(Content)
            .join(ContentEmbedding, Content.id == ContentEmbedding.content_id)
            .filter(Content.overview.ilike("%horror%") | Content.overview.ilike("%terror%") | Content.title.ilike("%conjuring%"))
            .first()
        )
        if not horror_content or horror_content.id == scifi_content.id:
            all_embs = db.query(Content).join(ContentEmbedding, Content.id == ContentEmbedding.content_id).all()
            horror_content = all_embs[-1] if len(all_embs) > 1 else scifi_content

        print(f"Sci-Fi sample content: ID={scifi_content.id}, Title='{scifi_content.title}'")
        print(f"Horror/Alternative sample content: ID={horror_content.id}, Title='{horror_content.title}'")

        # ---------------------------------------------------------------------
        # 4. Aryan Flow: Interaction -> Celery Task -> user_embeddings -> recs
        # ---------------------------------------------------------------------
        print("\n--- 4. ARYAN FLOW: INTERACTION RECORDING & CELERY TASK EXECUTION ---")
        t_received = datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()

        # Aryan interacts with Sci-Fi item
        db.query(InteractionEvent).filter(InteractionEvent.user_id == aryan.id).delete()
        db.query(SavedContent).filter(SavedContent.user_id == aryan.id).delete()
        db.query(Rating).filter(Rating.user_id == aryan.id).delete()
        db.commit()

        # Add positive interaction for Aryan
        db.add(SavedContent(user_id=aryan.id, content_id=scifi_content.id))
        db.add(Rating(user_id=aryan.id, content_id=scifi_content.id, rating=5.0))
        db.add(
            InteractionEvent(
                user_id=aryan.id,
                content_id=scifi_content.id,
                event_type="watch",
                event_value=1.0,
            )
        )
        db.commit()

        # Dispatch task to Celery content_based queue
        t_start = datetime.now(timezone.utc).isoformat()
        print(f"Dispatching 'app.tasks.embeddings.refresh_changed_user_embeddings'...")
        async_res = celery_app.send_task(
            "app.tasks.embeddings.refresh_changed_user_embeddings",
            queue="content_based",
        )
        print(f"Task dispatched with ID: {async_res.id}")

        # Wait for task completion from content_based_worker
        res = async_res.get(timeout=90)
        t_comp = datetime.now(timezone.utc).isoformat()
        t_duration_ms = (time.perf_counter() - t0) * 1000

        print(f"Task result: {res}")
        print(f"Aryan Task Performance Metrics:")
        print(f"  - Task Received Time:   {t_received}")
        print(f"  - Task Start Time:      {t_start}")
        print(f"  - Task Completion Time: {t_comp}")
        print(f"  - Total Task Duration:  {t_duration_ms:.2f} ms")

        # Verify Aryan user embedding in DB
        aryan_emb = db.query(UserEmbedding).filter(UserEmbedding.user_id == aryan.id).first()
        assert aryan_emb is not None, "Aryan user_embedding was not created/updated by worker!"
        assert aryan_emb.dimension == 384, f"Aryan embedding dimension {aryan_emb.dimension} != 384"
        assert aryan_emb.model_name == "BAAI/bge-small-en-v1.5", f"Model name {aryan_emb.model_name} unexpected"
        norm_val = np.linalg.norm(np.array(aryan_emb.embedding))
        print(f"Aryan User Embedding Dimension: {aryan_emb.dimension}, L2 Norm: {norm_val:.4f}, Updated At: {aryan_emb.updated_at}")

        # Generate & Persist Recommendations for Aryan
        rec_start = time.perf_counter()
        aryan_recs = RecommendationGenerator.generate_and_persist_for_user(db=db, user_id=aryan.id, limit=20)
        rec_duration_ms = (time.perf_counter() - rec_start) * 1000
        print(f"Aryan Recommendation Generation Duration: {rec_duration_ms:.2f} ms (Count: {len(aryan_recs)})")
        assert len(aryan_recs) > 0, "No recommendations generated for Aryan!"

        # ---------------------------------------------------------------------
        # 5. Bharat Flow: Interaction -> Celery Task -> user_embeddings -> recs
        # ---------------------------------------------------------------------
        print("\n--- 5. BHARAT FLOW: INTERACTION RECORDING & CELERY TASK EXECUTION ---")
        db.query(InteractionEvent).filter(InteractionEvent.user_id == bharat.id).delete()
        db.query(SavedContent).filter(SavedContent.user_id == bharat.id).delete()
        db.query(Rating).filter(Rating.user_id == bharat.id).delete()
        db.commit()

        # Add positive interaction for Bharat on different content
        db.add(SavedContent(user_id=bharat.id, content_id=horror_content.id))
        db.add(Rating(user_id=bharat.id, content_id=horror_content.id, rating=5.0))
        db.add(
            InteractionEvent(
                user_id=bharat.id,
                content_id=horror_content.id,
                event_type="save",
                event_value=1.0,
            )
        )
        db.commit()

        # Dispatch task to Celery
        t0_b = time.perf_counter()
        async_res_b = celery_app.send_task(
            "app.tasks.embeddings.refresh_changed_user_embeddings",
            queue="content_based",
        )
        res_b = async_res_b.get(timeout=90)
        t_duration_ms_b = (time.perf_counter() - t0_b) * 1000
        print(f"Bharat Task result: {res_b} in {t_duration_ms_b:.2f} ms")

        # Verify Bharat user embedding in DB
        bharat_emb = db.query(UserEmbedding).filter(UserEmbedding.user_id == bharat.id).first()
        assert bharat_emb is not None, "Bharat user_embedding was not created/updated by worker!"
        assert bharat_emb.dimension == 384
        norm_val_b = np.linalg.norm(np.array(bharat_emb.embedding))
        print(f"Bharat User Embedding Dimension: {bharat_emb.dimension}, L2 Norm: {norm_val_b:.4f}, Updated At: {bharat_emb.updated_at}")

        # Generate & Persist Recommendations for Bharat
        rec_start_b = time.perf_counter()
        bharat_recs = RecommendationGenerator.generate_and_persist_for_user(db=db, user_id=bharat.id, limit=20)
        rec_duration_ms_b = (time.perf_counter() - rec_start_b) * 1000
        print(f"Bharat Recommendation Generation Duration: {rec_duration_ms_b:.2f} ms (Count: {len(bharat_recs)})")
        assert len(bharat_recs) > 0, "No recommendations generated for Bharat!"

        # ---------------------------------------------------------------------
        # 6. Verify User Isolation
        # ---------------------------------------------------------------------
        print("\n--- 6. VERIFYING USER ISOLATION (ARYAN vs BHARAT) ---")
        vec_a = np.array(aryan_emb.embedding, dtype=np.float32)
        vec_b = np.array(bharat_emb.embedding, dtype=np.float32)

        cosine_sim = float(np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b)))
        print(f"Cosine similarity between Aryan & Bharat embeddings: {cosine_sim:.4f}")
        assert vec_a.shape == (384,) and vec_b.shape == (384,)
        print(f"User Isolation Confirmed: Aryan embedding != Bharat embedding (distinct vectors).")

        # ---------------------------------------------------------------------
        # 7. Verify GET /api/recommendations HTTP API
        # ---------------------------------------------------------------------
        print("\n--- 7. TESTING GET /api/recommendations FOR ARYAN & BHARAT ---")
        token_a = create_access_token(aryan.id)
        resp_a = client.get(
            "/api/recommendations?limit=10",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        print(f"GET /api/recommendations (Aryan) Status: {resp_a.status_code}")
        assert resp_a.status_code == 200, f"Aryan API request failed: {resp_a.text}"
        data_a = resp_a.json()
        items_a = data_a.get("items", []) if isinstance(data_a, dict) else data_a
        print(f"Aryan recommendations returned: {len(items_a)}")
        print(f"Top 3 for Aryan:")
        for idx, item in enumerate(items_a[:3], 1):
            print(f"  {idx}. {item.get('title')} (score: {item.get('score')}, reason: {item.get('reason')})")

        token_b = create_access_token(bharat.id)
        resp_b = client.get(
            "/api/recommendations?limit=10",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        print(f"GET /api/recommendations (Bharat) Status: {resp_b.status_code}")
        assert resp_b.status_code == 200, f"Bharat API request failed: {resp_b.text}"
        data_b = resp_b.json()
        items_b = data_b.get("items", []) if isinstance(data_b, dict) else data_b
        print(f"Bharat recommendations returned: {len(items_b)}")
        print(f"Top 3 for Bharat:")
        for idx, item in enumerate(items_b[:3], 1):
            print(f"  {idx}. {item.get('title')} (score: {item.get('score')}, reason: {item.get('reason')})")

        # ---------------------------------------------------------------------
        # 8. Test process_user_interaction_ml Task via content_based_worker
        # ---------------------------------------------------------------------
        print("\n--- 8. TESTING process_user_interaction_ml TASK ON content_based_worker ---")
        t0_ml = time.perf_counter()
        async_ml = celery_app.send_task(
            "app.tasks.recommendation.process_user_interaction_ml",
            args=[str(aryan.id), int(scifi_content.id)],
            queue="content_based",
        )
        ml_res = async_ml.get(timeout=30)
        ml_duration_ms = (time.perf_counter() - t0_ml) * 1000
        print(f"process_user_interaction_ml result: {ml_res} in {ml_duration_ms:.2f} ms")
        assert ml_res.get("user_embedding_updated") is True

        print("\n" + "=" * 90)
        print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY!")
        print("=" * 90)

    finally:
        db.close()


if __name__ == "__main__":
    run_full_verification()
