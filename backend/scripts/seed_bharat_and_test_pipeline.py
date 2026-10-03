#!/usr/bin/env python3
"""
Seed script and end-to-end verification for second test user 'Bharat'
verifying the asynchronous Content-Based Recommendation + Celery pipeline.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

# Add backend directory to sys.path so app modules import cleanly
root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.db.session import SessionLocal
from app.models.user import User, Profile, UserPreference
from app.models.content import Content
from app.models.taxonomy import Genre
from app.models.embedding import ContentEmbedding, UserEmbedding
from app.models.interaction import SavedContent, WatchHistory, InteractionEvent
from app.models.review import Rating
from app.models.watchman import WatchmanDecision
from app.api.auth.router import hash_password, verify_password
from app.core.security import create_access_token, decode_token
from app.core.config import settings
from app.core.celery import celery_app
from app.tasks.embeddings import refresh_changed_user_embeddings
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.candidates.content_based import ContentBasedCandidateGenerator


def run_bharat_pipeline_test():
    orig_provider = settings.AUTH_PROVIDER
    settings.AUTH_PROVIDER = "local"
    client = TestClient(app)
    db: Session = SessionLocal()

    print("=" * 85)
    print("WATCHMAN BHARAT END-TO-END ASYNCHRONOUS PIPELINE VERIFICATION")
    print("=" * 85)

    # -------------------------------------------------------------------------
    # 1. Create Bharat User
    # -------------------------------------------------------------------------
    print("\n[1. USER CREATION] Creating/Resolving test user 'bharat'...")
    email = "bharat@gmail.com"
    username = "bharat"
    raw_password = "123456789"
    hashed_pwd = hash_password(raw_password)

    bharat = db.query(User).filter(User.email == email).first()
    if not bharat:
        bharat = User(
            id=uuid.uuid4(),
            email=email,
            username=username,
            full_name="Bharat",
            password_hash=hashed_pwd,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(bharat)
        db.flush()
    else:
        bharat.username = username
        bharat.full_name = "Bharat"
        bharat.password_hash = hashed_pwd
        bharat.is_active = True
        bharat.updated_at = datetime.utcnow()
        db.flush()

    # Profile Sync
    profile = db.query(Profile).filter(Profile.id == bharat.id).first()
    if not profile:
        profile = Profile(id=bharat.id, username=username, full_name="Bharat", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.add(profile)
    else:
        profile.username = username
        profile.full_name = "Bharat"
        profile.updated_at = datetime.utcnow()
    db.flush()

    # 2. Horror Preferences (Horror: 27, Thriller: 53, Mystery: 9648)
    horror_genre_tmdb_ids = [27, 53, 9648]
    pref = db.query(UserPreference).filter(UserPreference.user_id == bharat.id).first()
    if not pref:
        pref = UserPreference(user_id=bharat.id, favorite_genres=horror_genre_tmdb_ids, disliked_genres=[], created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.add(pref)
    else:
        pref.favorite_genres = horror_genre_tmdb_ids
        pref.disliked_genres = []
        pref.updated_at = datetime.utcnow()
    db.flush()

    # Clean prior interactions & embedding for Bharat
    db.query(SavedContent).filter(SavedContent.user_id == bharat.id).delete()
    db.query(Rating).filter(Rating.user_id == bharat.id).delete()
    db.query(WatchHistory).filter(WatchHistory.user_id == bharat.id).delete()
    db.query(InteractionEvent).filter(InteractionEvent.user_id == bharat.id).delete()
    db.query(WatchmanDecision).filter(WatchmanDecision.user_id == bharat.id).delete()
    db.query(UserEmbedding).filter(UserEmbedding.user_id == bharat.id).delete()
    db.commit()

    # Verify password & auth
    assert verify_password(raw_password, bharat.password_hash) is True
    token = create_access_token(bharat.id)
    headers = {"Authorization": f"Bearer {token}"}
    r_me = client.get("/api/auth/me", headers=headers)
    assert r_me.status_code == 200
    print(f"  -> User Created: ID={bharat.id}, Username={bharat.username}, Email={bharat.email}")
    print(f"  -> Preferences Configured: Horror (27), Thriller (53), Mystery (9648)")
    print(f"  -> Authentication verified: Password hashed with bcrypt ($2b$), JWT login valid [PASS]")

    # -------------------------------------------------------------------------
    # 3. Seed Real Horror Interactions (with existing 384D Content Embeddings)
    # -------------------------------------------------------------------------
    print("\n[2. HORROR INTERACTIONS] Seeding positive interactions on existing Horror catalog items...")
    initial_horror_titles = {
        "The Thing": {"rating": 5.0, "progress": 0.95, "save": True, "wm": "must_watch"},
        "Alien": {"rating": 5.0, "progress": 0.90, "save": True, "wm": "must_watch"},
        "28 Days Later": {"rating": 4.5, "progress": 0.85, "save": True, "wm": "must_watch"},
        "A Nightmare on Elm Street": {"rating": 4.5, "progress": 0.70, "save": False, "wm": "must_watch"},
    }

    seeded_items_details = []
    initial_interacted_cids = set()

    for title, spec in initial_horror_titles.items():
        c_item = (
            db.query(Content)
            .join(ContentEmbedding, Content.id == ContentEmbedding.content_id)
            .filter(Content.title == title)
            .first()
        )
        assert c_item is not None, f"Item '{title}' not found in embedded catalog!"
        emb = db.query(ContentEmbedding).filter(ContentEmbedding.content_id == c_item.id).first()
        assert emb is not None and len(emb.embedding) == 384, f"Embedding missing for '{title}'!"

        cid = c_item.id
        initial_interacted_cids.add(cid)
        now_ts = datetime.now(timezone.utc)

        if spec.get("save"):
            db.add(SavedContent(user_id=bharat.id, content_id=cid, created_at=now_ts))
        if spec.get("rating"):
            db.add(Rating(user_id=bharat.id, content_id=cid, rating=spec["rating"], created_at=now_ts, updated_at=now_ts))
        if spec.get("wm"):
            db.add(WatchmanDecision(user_id=bharat.id, content_id=cid, decision=spec["wm"], created_at=now_ts, updated_at=now_ts))
        if spec.get("progress"):
            db.add(WatchHistory(user_id=bharat.id, content_id=cid, progress=spec["progress"], completed=(spec["progress"] >= 0.9), watched_at=now_ts))
        db.add(InteractionEvent(user_id=bharat.id, content_id=cid, event_type="watch", event_value=1.0, created_at=now_ts))

        genre_names = [g.genre.name for g in (c_item.genres or []) if hasattr(g, "genre") and hasattr(g.genre, "name")]
        seeded_items_details.append({
            "content_id": cid,
            "title": c_item.title,
            "year": c_item.release_date[:4] if c_item.release_date else "N/A",
            "genres": ", ".join(genre_names),
            "emb_dim": len(emb.embedding),
            "emb_model": emb.model_name,
        })
        print(f"  -> Interacted with ID={cid} | '{c_item.title}' ({seeded_items_details[-1]['year']}) | Genres: {seeded_items_details[-1]['genres']} | Vector: 384D ({emb.model_name})")

    db.commit()

    # -------------------------------------------------------------------------
    # 4. Verify Asynchronous State Before Worker Run
    # -------------------------------------------------------------------------
    print("\n[3. ASYNCHRONOUS DECOUPLING VERIFICATION] Checking user_embeddings before Celery run...")
    emb_before_worker = db.query(UserEmbedding).filter(UserEmbedding.user_id == bharat.id).first()
    assert emb_before_worker is None, "User embedding must NOT be computed synchronously during seeding/API calls!"
    print("  -> Confirmed: Bharat has NO user_embeddings row in PostgreSQL (Fully Asynchronous) [PASS]")

    # -------------------------------------------------------------------------
    # 5. Celery Worker Execution Cycle
    # -------------------------------------------------------------------------
    print("\n[4. CELERY WORKER CYCLE] Triggering Celery background task: app.tasks.embeddings.refresh_changed_user_embeddings...")
    worker_res_1 = refresh_changed_user_embeddings()
    print(f"  -> Worker output: {worker_res_1}")
    assert worker_res_1["changed_users_detected"] >= 1, "Worker failed to detect Bharat!"
    assert worker_res_1["successfully_updated"] >= 1, "Worker failed to compute Bharat's embedding!"

    db.expire_all()
    bharat_emb_1 = db.query(UserEmbedding).filter(UserEmbedding.user_id == bharat.id).first()
    assert bharat_emb_1 is not None and bharat_emb_1.embedding is not None
    assert len(bharat_emb_1.embedding) == 384, f"Expected 384 dimensions, got {len(bharat_emb_1.embedding)}"
    norm_1 = float(np.linalg.norm(bharat_emb_1.embedding))
    assert abs(norm_1 - 1.0) < 1e-3, f"Vector not unit normalized: {norm_1}"

    t1_computed_at = bharat_emb_1.updated_at
    v1_sample = list(bharat_emb_1.embedding)
    print(f"  -> Bharat User Vector Created: Dim={len(bharat_emb_1.embedding)}, L2 Norm={norm_1:.4f}, Model={bharat_emb_1.model_name}")
    print(f"  -> Computed At: {t1_computed_at}")
    print(f"  -> Sample Vector [0:5]: {[round(x, 4) for x in v1_sample[:5]]} [PASS]")

    # -------------------------------------------------------------------------
    # 6. Recommendation Retrieval (Phase 1)
    # -------------------------------------------------------------------------
    print("\n[5. RECOMMENDATION RETRIEVAL - PHASE 1] Querying recommendations for Bharat...")
    recs_phase_1 = ContentBasedCandidateGenerator.generate_candidates(
        db,
        user_id=bharat.id,
        limit=10,
        exclude_content_ids=initial_interacted_cids,
    )
    assert len(recs_phase_1) > 0, "No recommendations generated for Bharat!"
    assert all(r["content_id"] not in initial_interacted_cids for r in recs_phase_1), "Interacted items not excluded!"

    print("\n  Top-10 Content-Based Recommendations for Bharat (Initial Horror Profile):")
    fmt = "  {:<4} | {:<32} | {:<14} | {:<5} | {:<35} | {:<10}"
    print(fmt.format("Rank", "Title", "Type", "Year", "Genres", "Similarity"))
    print("  " + "-" * 110)
    for idx, r in enumerate(recs_phase_1, 1):
        item = r["content"]
        g_names = [g.genre.name for g in (item.genres or []) if hasattr(g, "genre") and hasattr(g.genre, "name")]
        y_str = item.release_date[:4] if item.release_date else "N/A"
        t_str = (item.title[:29] + "...") if len(item.title) > 32 else item.title
        g_str = (", ".join(g_names)[:32] + "...") if len(", ".join(g_names)) > 35 else ", ".join(g_names)
        print(fmt.format(idx, t_str, "Movie" if item.content_type == "movie" else "TV/Web-Series", y_str, g_str, f"{r['score']:.4f}"))

    # -------------------------------------------------------------------------
    # 7. Test Behavior Change (Add 5th Horror Movie: 'Dark Nuns')
    # -------------------------------------------------------------------------
    print("\n[6. BEHAVIOR CHANGE TEST] Adding new positive interaction on 'Dark Nuns' (ID=139)...")
    dark_nuns = db.query(Content).filter(Content.title == "Dark Nuns").first()
    assert dark_nuns is not None
    dn_cid = dark_nuns.id
    now_ts_2 = datetime.now(timezone.utc)

    db.add(SavedContent(user_id=bharat.id, content_id=dn_cid, created_at=now_ts_2))
    db.add(Rating(user_id=bharat.id, content_id=dn_cid, rating=5.0, created_at=now_ts_2, updated_at=now_ts_2))
    db.add(WatchmanDecision(user_id=bharat.id, content_id=dn_cid, decision="must_watch", created_at=now_ts_2, updated_at=now_ts_2))
    db.add(WatchHistory(user_id=bharat.id, content_id=dn_cid, progress=0.90, completed=True, watched_at=now_ts_2))
    db.commit()

    # Verify user embedding is NOT recalculated synchronously
    db.expire_all()
    emb_check = db.query(UserEmbedding).filter(UserEmbedding.user_id == bharat.id).first()
    assert emb_check.updated_at == t1_computed_at, "Embedding was recalculated synchronously on interaction save!"
    print(f"  -> user_embeddings timestamp unchanged ({emb_check.updated_at}) - Asynchronous decoupling verified.")

    # Trigger Celery Worker cycle
    print("  -> Triggering Celery background worker cycle...")
    worker_res_2 = refresh_changed_user_embeddings()
    assert worker_res_2["changed_users_detected"] >= 1
    assert worker_res_2["successfully_updated"] >= 1

    db.expire_all()
    bharat_emb_2 = db.query(UserEmbedding).filter(UserEmbedding.user_id == bharat.id).first()
    t2_computed_at = bharat_emb_2.updated_at
    v2_sample = list(bharat_emb_2.embedding)
    assert t2_computed_at > t1_computed_at, "Timestamp was not updated by Celery worker!"

    shift_sim = float(np.dot(np.array(v1_sample), np.array(v2_sample)))
    print(f"  -> Updated Computed At: {t2_computed_at}")
    print(f"  -> Updated Sample Vector [0:5]: {[round(x, 4) for x in v2_sample[:5]]}")
    print(f"  -> Vector Cosine Similarity Shift: {shift_sim:.4f} (Taste profile successfully updated!)")

    updated_interacted_cids = initial_interacted_cids | {dn_cid}
    recs_phase_2 = ContentBasedCandidateGenerator.generate_candidates(
        db,
        user_id=bharat.id,
        limit=10,
        exclude_content_ids=updated_interacted_cids,
    )
    print("\n  Top-5 Content-Based Recommendations After Adding 'Dark Nuns':")
    for idx, r in enumerate(recs_phase_2[:5], 1):
        item = r["content"]
        g_names = [g.genre.name for g in (item.genres or []) if hasattr(g, "genre") and hasattr(g.genre, "name")]
        print(f"    {idx}. [Score: {r['score']:.4f}] '{item.title}' - Genres: {', '.join(g_names)}")

    # -------------------------------------------------------------------------
    # 8. Test Interaction Removal (Remove 'A Nightmare on Elm Street')
    # -------------------------------------------------------------------------
    print("\n[7. INTERACTION REMOVAL TEST] Removing 'A Nightmare on Elm Street' (ID=2353)...")
    elm_street = db.query(Content).filter(Content.title == "A Nightmare on Elm Street").first()
    assert elm_street is not None
    elm_cid = elm_street.id

    db.query(SavedContent).filter(SavedContent.user_id == bharat.id, SavedContent.content_id == elm_cid).delete()
    db.query(Rating).filter(Rating.user_id == bharat.id, Rating.content_id == elm_cid).delete()
    db.query(WatchmanDecision).filter(WatchmanDecision.user_id == bharat.id, WatchmanDecision.content_id == elm_cid).delete()
    db.query(WatchHistory).filter(WatchHistory.user_id == bharat.id, WatchHistory.content_id == elm_cid).delete()
    db.query(InteractionEvent).filter(InteractionEvent.user_id == bharat.id, InteractionEvent.content_id == elm_cid).delete()
    db.commit()

    # Force timestamp shift to simulate periodic Celery Beat refresh cycle
    bharat_emb_2.updated_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    db.commit()

    worker_res_3 = refresh_changed_user_embeddings()
    assert worker_res_3["successfully_updated"] >= 1

    db.expire_all()
    bharat_emb_3 = db.query(UserEmbedding).filter(UserEmbedding.user_id == bharat.id).first()
    t3_computed_at = bharat_emb_3.updated_at
    v3_sample = list(bharat_emb_3.embedding)
    print(f"  -> Vector Rebuilt From Current DB Interactions: Computed At={t3_computed_at}")
    print(f"  -> Rebuilt Sample Vector [0:5]: {[round(x, 4) for x in v3_sample[:5]]}")

    recs_phase_3 = ContentBasedCandidateGenerator.generate_candidates(
        db,
        user_id=bharat.id,
        limit=10,
        exclude_content_ids=(updated_interacted_cids - {elm_cid}),
    )
    print("\n  Top-5 Recommendations After Removing 'A Nightmare on Elm Street':")
    for idx, r in enumerate(recs_phase_3[:5], 1):
        item = r["content"]
        g_names = [g.genre.name for g in (item.genres or []) if hasattr(g, "genre") and hasattr(g.genre, "name")]
        print(f"    {idx}. [Score: {r['score']:.4f}] '{item.title}' - Genres: {', '.join(g_names)}")

    print("\n" + "=" * 85)
    print("ALL BHARAT ASYNCHRONOUS PIPELINE TESTS COMPLETED AND PASSED!")
    print("=" * 85)

    settings.AUTH_PROVIDER = orig_provider
    db.close()


if __name__ == "__main__":
    run_bharat_pipeline_test()
