#!/usr/bin/env python3
"""
Comprehensive ALS Collaborative-Filtering Pipeline Setup and Verification:
1. Seeds/resolves the 10 test users (Aryan, Bharat, Priyanshu, Aman, Saket, Sakshi, Neha, Priya, Aditya, Sid).
2. Sets synthetic multi-genre preferences.
3. Generates 1,000-3,000+ realistic user-item interactions with meaningful cross-user overlap.
4. Computes and reports complete dataset statistics & sparsity.
5. Dispatches ALS training task to dedicated 'als' queue on 'als_worker'.
6. Verifies persistence of ALS user/item latent factors.
7. Evaluates top-K recommendations & collaborative scoring.
8. Tests cold-start resilience for new/unseen users.
"""

from __future__ import annotations

import os
import random
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

# Add backend directory to sys.path
root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.user import User, Profile, UserPreference
from app.models.content import Content
from app.models.taxonomy import Genre, ContentGenre
from app.models.embedding import ContentEmbedding
from app.models.interaction import SavedContent, WatchHistory, InteractionEvent
from app.models.review import Rating
from app.models.watchman import WatchmanDecision
from app.models.collaborative import ALSItemFactors, ALSUserFactors
from app.api.auth.router import hash_password
from app.core.config import settings
from app.core.celery import celery_app
from app.ml.collaborative.training import ALSTrainingService
from app.ml.candidates.als_collaborative import ALSCollaborativeCandidateGenerator


# Define the 10 target users and their distinct taste profiles
USER_PROFILES = [
    {
        "username": "aryan",
        "email": "aryan@gmail.com",
        "full_name": "Aryan",
        "fav_genres": ["Science Fiction", "Fantasy", "Comedy"],
        "genre_tmdb_ids": [878, 14, 35],
    },
    {
        "username": "bharat",
        "email": "bharat@gmail.com",
        "full_name": "Bharat",
        "fav_genres": ["Horror", "Thriller", "Mystery"],
        "genre_tmdb_ids": [27, 53, 9648],
    },
    {
        "username": "priyanshu",
        "email": "priyanshu@gmail.com",
        "full_name": "Priyanshu",
        "fav_genres": ["Action", "Adventure", "Crime"],
        "genre_tmdb_ids": [28, 12, 80],
    },
    {
        "username": "aman",
        "email": "aman@gmail.com",
        "full_name": "Aman",
        "fav_genres": ["Animation", "Family", "Adventure"],
        "genre_tmdb_ids": [16, 10751, 12],
    },
    {
        "username": "saket",
        "email": "saket@gmail.com",
        "full_name": "Saket",
        "fav_genres": ["Drama", "History", "War"],
        "genre_tmdb_ids": [18, 36, 10752],
    },
    {
        "username": "sakshi",
        "email": "sakshi@gmail.com",
        "full_name": "Sakshi",
        "fav_genres": ["Romance", "Comedy", "Music"],
        "genre_tmdb_ids": [10749, 35, 10402],
    },
    {
        "username": "neha",
        "email": "neha@gmail.com",
        "full_name": "Neha",
        "fav_genres": ["Documentary", "History", "Drama"],
        "genre_tmdb_ids": [99, 36, 18],
    },
    {
        "username": "priya",
        "email": "priya@gmail.com",
        "full_name": "Priya",
        "fav_genres": ["Fantasy", "Romance", "Science Fiction"],
        "genre_tmdb_ids": [14, 10749, 878],
    },
    {
        "username": "aditya",
        "email": "aditya@gmail.com",
        "full_name": "Aditya",
        "fav_genres": ["Crime", "Thriller", "Action"],
        "genre_tmdb_ids": [80, 53, 28],
    },
    {
        "username": "sid",
        "email": "sid@gmail.com",
        "full_name": "Sid",
        "fav_genres": ["Comedy", "Animation", "Fantasy"],
        "genre_tmdb_ids": [35, 16, 14],
    },
]


def seed_als_dataset_and_train():
    print("=" * 90)
    print("WATCHMAN ALS COLLABORATIVE-FILTERING DATASET & TRAINING")
    print("=" * 90)

    db: Session = SessionLocal()
    rng = random.Random(42)

    try:
        # ---------------------------------------------------------------------
        # 1. Setup / Resolve 10 Users
        # ---------------------------------------------------------------------
        print("\n--- 1. SETTING UP / RESOLVING 10 TARGET USERS ---")
        user_map: dict[str, User] = {}
        for p in USER_PROFILES:
            email = p["email"].strip().lower()
            username = p["username"].strip().lower()

            user = db.query(User).filter(User.email == email).first()
            if not user:
                user = User(
                    id=uuid.uuid4(),
                    email=email,
                    username=username,
                    full_name=p["full_name"],
                    password_hash=hash_password("watchman_secure_dev_pass_123"),
                    is_active=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                print(f"  + Created user: {p['full_name']} ({user.email}) -> ID: {user.id}")
            else:
                print(f"  * Resolved existing user: {p['full_name']} ({user.email}) -> ID: {user.id}")

            user_map[username] = user

            # Sync Profile
            prof = db.query(Profile).filter(Profile.id == user.id).first()
            if not prof:
                db.add(Profile(id=user.id, username=username, full_name=p["full_name"]))
            db.commit()

            # Sync Preferences
            pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
            if not pref:
                db.add(UserPreference(user_id=user.id, favorite_genres=p["genre_tmdb_ids"], disliked_genres=[]))
            else:
                pref.favorite_genres = p["genre_tmdb_ids"]
            db.commit()

        # ---------------------------------------------------------------------
        # 2. Inspect 1,003 Embedded Catalog Items & Genre Taxonomy
        # ---------------------------------------------------------------------
        print("\n--- 2. LOADING 1,003 EMBEDDED CATALOG ITEMS ---")
        embedded_contents = (
            db.query(Content)
            .join(ContentEmbedding, Content.id == ContentEmbedding.content_id)
            .all()
        )
        catalog_count = len(embedded_contents)
        print(f"Total embedded catalog items available for ALS: {catalog_count}")
        assert catalog_count >= 500, f"Expected ~1,003 items, found {catalog_count}"

        # Map genre names & content -> genres
        content_genres_map: dict[int, list[str]] = defaultdict(list)
        cg_rows = (
            db.query(ContentGenre.content_id, Genre.name)
            .join(Genre, ContentGenre.genre_id == Genre.id)
            .all()
        )
        for cid, gname in cg_rows:
            content_genres_map[cid].append(gname)

        # Categorize catalog items into genre clusters
        genre_item_buckets: dict[str, list[int]] = defaultdict(list)
        all_catalog_ids = [c.id for c in embedded_contents]
        for c in embedded_contents:
            gnames = content_genres_map.get(c.id, [])
            for g in gnames:
                genre_item_buckets[g].append(c.id)

        # Popular / Universal items (top 50 by vote count / popularity)
        popular_items = sorted(embedded_contents, key=lambda x: (x.vote_count or 0, x.popularity or 0.0), reverse=True)[:50]
        universal_ids = [p.id for p in popular_items]

        # ---------------------------------------------------------------------
        # 3. Generate Realistic Synthetic Interactions with High Overlap
        # ---------------------------------------------------------------------
        print("\n--- 3. GENERATING SYNTHETIC INTERACTIONS ---")
        # Clear existing interaction records for the 10 users to ensure clean benchmark
        target_uids = [u.id for u in user_map.values()]
        db.query(Rating).filter(Rating.user_id.in_(target_uids)).delete(synchronize_session=False)
        db.query(SavedContent).filter(SavedContent.user_id.in_(target_uids)).delete(synchronize_session=False)
        db.query(WatchHistory).filter(WatchHistory.user_id.in_(target_uids)).delete(synchronize_session=False)
        db.query(InteractionEvent).filter(InteractionEvent.user_id.in_(target_uids)).delete(synchronize_session=False)
        db.query(WatchmanDecision).filter(WatchmanDecision.user_id.in_(target_uids)).delete(synchronize_session=False)
        db.commit()

        user_interaction_counts: dict[str, int] = {}
        all_interacted_items_by_user: dict[str, set[int]] = defaultdict(set)

        for profile in USER_PROFILES:
            uname = profile["username"]
            user = user_map[uname]
            fav_genres = profile["fav_genres"]

            # Select items:
            # 1. Preferred genre items (100 - 150 items)
            pref_candidates = []
            for fg in fav_genres:
                pref_candidates.extend(genre_item_buckets.get(fg, []))
            pref_candidates = list(set(pref_candidates))
            n_pref = min(len(pref_candidates), rng.randint(110, 160))
            chosen_pref = rng.sample(pref_candidates, n_pref) if pref_candidates else []

            # 2. Universal / Popular overlapping items (25 - 40 items)
            n_univ = rng.randint(25, 40)
            chosen_univ = rng.sample(universal_ids, min(len(universal_ids), n_univ))

            # 3. Cross-genre exploratory items (30 - 50 items)
            other_ids = [cid for cid in all_catalog_ids if cid not in chosen_pref and cid not in chosen_univ]
            n_cross = min(len(other_ids), rng.randint(30, 50))
            chosen_cross = rng.sample(other_ids, n_cross) if other_ids else []

            # Total items for this user: ~165 - 250 items
            user_items = list(set(chosen_pref + chosen_univ + chosen_cross))
            user_interaction_counts[uname] = len(user_items)
            all_interacted_items_by_user[uname] = set(user_items)

            # Insert diverse interaction signals
            ratings_to_add = []
            saved_to_add = []
            history_to_add = []
            events_to_add = []
            decisions_to_add = []

            for cid in user_items:
                is_pref = cid in chosen_pref
                is_univ = cid in chosen_univ

                # Determine signal strength
                if is_pref:
                    # High positive interaction
                    r_val = rng.choice([4.0, 4.5, 5.0, 5.0])
                    prog = rng.uniform(0.75, 1.0)
                    dec = "must_watch"
                elif is_univ:
                    # Moderate-to-high positive interaction
                    r_val = rng.choice([3.5, 4.0, 4.5, 5.0])
                    prog = rng.uniform(0.60, 1.0)
                    dec = rng.choice(["must_watch", "time_pass"])
                else:
                    # Mixed / neutral / weak negative interaction
                    r_val = rng.choice([1.5, 2.0, 3.0, 3.5, 4.0])
                    prog = rng.uniform(0.20, 0.70)
                    dec = "skip" if r_val < 2.5 else "time_pass"

                # 1. Rating
                ratings_to_add.append(Rating(user_id=user.id, content_id=cid, rating=r_val))

                # 2. SavedContent (70% of preferred, 30% of others)
                if (is_pref and rng.random() < 0.70) or (not is_pref and rng.random() < 0.30):
                    saved_to_add.append(SavedContent(user_id=user.id, content_id=cid))

                # 3. Watch History
                history_to_add.append(
                    WatchHistory(
                        user_id=user.id,
                        content_id=cid,
                        progress=prog,
                        completed=(prog >= 0.90),
                    )
                )

                # 4. Interaction Event
                events_to_add.append(
                    InteractionEvent(
                        user_id=user.id,
                        content_id=cid,
                        event_type="watch" if prog > 0.5 else "view",
                        event_value=1.0 if r_val >= 3.5 else 0.5,
                    )
                )

                # 5. WatchMan Decision
                decisions_to_add.append(
                    WatchmanDecision(
                        user_id=user.id,
                        content_id=cid,
                        decision=dec,
                    )
                )

            db.add_all(ratings_to_add)
            db.add_all(saved_to_add)
            db.add_all(history_to_add)
            db.add_all(events_to_add)
            db.add_all(decisions_to_add)
            db.commit()

        # ---------------------------------------------------------------------
        # 4. Print & Report Dataset Statistics & Overlap
        # ---------------------------------------------------------------------
        print("\n--- 4. DATASET & INTERACTION MATRIX STATISTICS ---")
        matrix, user_ids, item_ids = ALSTrainingService.build_interactions(db)

        total_interactions = sum(len(v) for v in matrix.values())
        n_users = len(user_ids)
        n_items = len(item_ids)
        avg_interactions = total_interactions / n_users if n_users > 0 else 0
        min_interactions = min(len(v) for v in matrix.values())
        max_interactions = max(len(v) for v in matrix.values())
        total_matrix_cells = n_users * n_items
        sparsity = (1.0 - (total_interactions / total_matrix_cells)) * 100.0 if total_matrix_cells > 0 else 0.0

        print(f"Users in ALS dataset:          {n_users}")
        print(f"Items with interactions:       {n_items} (out of {catalog_count} catalog items)")
        print(f"Total user-item interactions:  {total_interactions}")
        print(f"Average interactions / user:   {avg_interactions:.1f}")
        print(f"Min interactions / user:       {min_interactions}")
        print(f"Max interactions / user:       {max_interactions}")
        print(f"Matrix Sparsity:               {sparsity:.2f}% (Density: {100.0 - sparsity:.2f}%)")

        print("\nPer-User Interaction Summary:")
        for uname, u in user_map.items():
            count = len(matrix.get(u.id, {}))
            print(f"  - {uname:<12} (ID: {str(u.id)[:8]}...): {count:>4} interactions")

        # Overlap statistics
        print("\nOverlap Statistics:")
        item_user_counts = defaultdict(int)
        for items in matrix.values():
            for cid in items:
                item_user_counts[cid] += 1

        shared_ge_2 = sum(1 for c in item_user_counts.values() if c >= 2)
        shared_ge_3 = sum(1 for c in item_user_counts.values() if c >= 3)
        shared_ge_5 = sum(1 for c in item_user_counts.values() if c >= 5)

        print(f"  - Items interacted by >= 2 users: {shared_ge_2} ({shared_ge_2 / n_items * 100:.1f}%)")
        print(f"  - Items interacted by >= 3 users: {shared_ge_3} ({shared_ge_3 / n_items * 100:.1f}%)")
        print(f"  - Items interacted by >= 5 users: {shared_ge_5} ({shared_ge_5 / n_items * 100:.1f}%)")

        # ---------------------------------------------------------------------
        # 5. Dispatch ALS Training Task to Dedicated 'als' Queue
        # ---------------------------------------------------------------------
        print("\n--- 5. DISPATCHING ALS TRAINING TASK TO 'als' QUEUE ON als_worker ---")
        t0_train = time.perf_counter()
        async_als = celery_app.send_task(
            "app.tasks.collaborative.train_als_model",
            queue="als",
        )
        print(f"Task dispatched with ID: {async_als.id} -> routing to queue 'als'")

        train_result = async_als.get(timeout=60)
        t_train_duration_ms = (time.perf_counter() - t0_train) * 1000

        print(f"ALS Training Result from als_worker:")
        print(f"  - Status:             {train_result.get('status')}")
        print(f"  - Model Version:      {train_result.get('model_version')}")
        print(f"  - Latent Factors (k): {train_result.get('factors')}")
        print(f"  - Users Trained:      {train_result.get('users')}")
        print(f"  - Items Trained:      {train_result.get('items')}")
        print(f"  - Interactions:       {train_result.get('interactions')}")
        print(f"  - Execution Duration: {t_train_duration_ms:.2f} ms")

        eval_metrics = train_result.get("evaluation_metrics", {})
        print(f"ALS Test Split Evaluation Metrics (80/20 train/test split):")
        for metric_k, metric_v in eval_metrics.items():
            print(f"  - {metric_k:<15}: {metric_v}")

        assert train_result.get("status") == "trained", "ALS training failed or did not return 'trained' status!"

        # ---------------------------------------------------------------------
        # 6. Verify ALS Latent Factor Persistence
        # ---------------------------------------------------------------------
        print("\n--- 6. VERIFYING ALS FACTOR PERSISTENCE IN POSTGRESQL ---")
        saved_user_factors = db.query(ALSUserFactors).all()
        saved_item_factors = db.query(ALSItemFactors).all()

        print(f"Persisted rows in 'als_user_factors': {len(saved_user_factors)}")
        print(f"Persisted rows in 'als_item_factors': {len(saved_item_factors)}")
        assert len(saved_user_factors) == n_users, f"Expected {n_users} user factor rows, got {len(saved_user_factors)}"
        assert len(saved_item_factors) == n_items, f"Expected {n_items} item factor rows, got {len(saved_item_factors)}"

        sample_uf = saved_user_factors[0]
        print(f"Sample User Factor (User ID: {sample_uf.user_id}): {sample_uf.num_factors} factors, version '{sample_uf.model_version}'")
        sample_if = saved_item_factors[0]
        print(f"Sample Item Factor (Content ID: {sample_if.content_id}): {sample_if.num_factors} factors, version '{sample_if.model_version}'")

        # ---------------------------------------------------------------------
        # 7. Test ALS Collaborative Candidate Generation for Users
        # ---------------------------------------------------------------------
        print("\n--- 7. TESTING ALS COLLABORATIVE CANDIDATE GENERATION ---")
        for profile in USER_PROFILES[:4]:
            uname = profile["username"]
            user = user_map[uname]
            seen_ids = set(matrix.get(user.id, {}).keys())

            candidates = ALSCollaborativeCandidateGenerator.generate_candidates(
                db=db,
                user_id=user.id,
                limit=10,
                exclude_content_ids=seen_ids,
            )

            print(f"\nTop Collaborative Candidates for '{uname.capitalize()}' (Favs: {', '.join(profile['fav_genres'])}):")
            print(f"  Candidates generated: {len(candidates)}")
            assert len(candidates) > 0, f"ALS candidate generator returned 0 candidates for {uname}"

            for idx, c in enumerate(candidates[:5], 1):
                cid = c["content_id"]
                content_obj = db.query(Content).filter(Content.id == cid).first()
                title = content_obj.title if content_obj else f"Content #{cid}"
                gnames = content_genres_map.get(cid, [])
                print(f"  {idx}. {title} [Genres: {', '.join(gnames[:3])}] (Score: {c['score']:.4f}, Source: {c['source']})")

        # ---------------------------------------------------------------------
        # 8. Test Cold Start Resilience
        # ---------------------------------------------------------------------
        print("\n--- 8. TESTING COLD START RESILIENCE ---")
        cold_user_id = uuid.uuid4()
        print(f"Testing cold user with 0 interactions: ID {cold_user_id}")

        cold_candidates = ALSCollaborativeCandidateGenerator.generate_candidates(
            db=db,
            user_id=cold_user_id,
            limit=20,
        )
        print(f"Cold user ALS candidate count: {len(cold_candidates)} (Expected: 0, non-blocking fallback)")
        assert cold_candidates == [], "Cold user should safely return empty candidate list!"

        print("\n" + "=" * 90)
        print("ALL ALS COLLABORATIVE-FILTERING VERIFICATIONS COMPLETED SUCCESSFULLY!")
        print("=" * 90)

    finally:
        db.close()


if __name__ == "__main__":
    seed_als_dataset_and_train()
