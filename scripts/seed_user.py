#!/usr/bin/env python3
"""
Seed script to create/update development user 'aryan' with realistic Sci-Fi/Fantasy and Comedy preferences,
interactions, and 384-D taste embeddings for the Content-Based Recommendation System.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add backend directory to sys.path so app modules import cleanly
root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy.orm import Session
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
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.candidates.content_based import ContentBasedCandidateGenerator
from app.core.config import settings


def seed_user(
    db: Session | None = None,
    username: str = "aryan",
    email: str = "aryan@gmail.com",
    password: str = "123456789",
) -> dict:
    """
    Idempotently creates or updates the development test user 'aryan',
    seeds preferences and positive interactions on real catalog items,
    computes the user taste embedding, and retrieves Content-Based recommendations.
    """
    should_close_db = False
    if db is None:
        db = SessionLocal()
        should_close_db = True

    try:
        clean_email = email.strip().lower()
        clean_username = username.strip().lower()

        # 1. Resolve or Create User
        user = db.query(User).filter(User.email == clean_email).first()
        hashed_pwd = hash_password(password)

        if not user:
            user_id = uuid.uuid4()
            user = User(
                id=user_id,
                email=clean_email,
                username=clean_username,
                full_name="Aryan",
                password_hash=hashed_pwd,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(user)
            db.flush()
        else:
            user.username = clean_username
            user.full_name = "Aryan"
            user.password_hash = hashed_pwd
            user.is_active = True
            user.updated_at = datetime.utcnow()
            db.flush()

        # 2. Profile Sync
        profile = db.query(Profile).filter(Profile.id == user.id).first()
        if not profile:
            profile = Profile(
                id=user.id,
                username=user.username,
                full_name=user.full_name,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(profile)
        else:
            profile.username = user.username
            profile.full_name = user.full_name
            profile.updated_at = datetime.utcnow()
        db.flush()

        # 3. Preferences (Sci-Fi & Fantasy, Science Fiction, Fantasy, Comedy)
        # Match TMDB genre IDs: Sci-Fi & Fantasy (10765), Science Fiction (878), Fantasy (14), Comedy (35)
        target_genre_tmdb_ids = [10765, 878, 14, 35]
        pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
        if not pref:
            pref = UserPreference(
                user_id=user.id,
                favorite_genres=target_genre_tmdb_ids,
                disliked_genres=[],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(pref)
        else:
            pref.favorite_genres = target_genre_tmdb_ids
            pref.disliked_genres = []
            pref.updated_at = datetime.utcnow()
        db.flush()

        # 4. Clean prior interactions for this user only to guarantee clean idempotent state
        db.query(SavedContent).filter(SavedContent.user_id == user.id).delete()
        db.query(Rating).filter(Rating.user_id == user.id).delete()
        db.query(WatchHistory).filter(WatchHistory.user_id == user.id).delete()
        db.query(InteractionEvent).filter(InteractionEvent.user_id == user.id).delete()
        db.query(WatchmanDecision).filter(WatchmanDecision.user_id == user.id).delete()
        db.query(UserEmbedding).filter(UserEmbedding.user_id == user.id).delete()
        db.flush()

        # 5. Seed realistic positive interactions on real catalog items matching Sci-Fi/Fantasy and Comedy
        # Let's locate specific catalog items by title
        target_titles = {
            "Interstellar": {"type": "movie", "rating": 5.0, "progress": 0.95, "save": True, "wm": "must_watch"},
            "Inception": {"type": "movie", "rating": 5.0, "progress": 0.90, "save": True, "wm": "must_watch"},
            "Avengers: Endgame": {"type": "movie", "rating": 4.5, "progress": 0.75, "save": False, "wm": "must_watch"},
            "Rick and Morty": {"type": "tv", "rating": 5.0, "progress": 0.80, "save": True, "wm": "must_watch"},
            "The Gentlemen": {"type": "tv", "rating": 4.5, "progress": 0.60, "save": True, "wm": "must_watch"},
            "Brooklyn Nine-Nine": {"type": "tv", "rating": 5.0, "progress": 0.85, "save": True, "wm": "must_watch"},
            "Toy Story 3": {"type": "movie", "rating": 4.0, "progress": 0.50, "save": True, "wm": "time_pass"},
            "South Park": {"type": "tv", "rating": 4.5, "progress": 0.70, "save": False, "wm": "must_watch"},
        }

        seeded_interactions_info = []
        interacted_content_ids = set()

        for title, spec in target_titles.items():
            content_item = (
                db.query(Content)
                .join(ContentEmbedding, Content.id == ContentEmbedding.content_id)
                .filter(Content.title == title, Content.content_type == spec["type"])
                .first()
            )
            if not content_item:
                continue

            cid = content_item.id
            interacted_content_ids.add(cid)
            actions_list = []

            # Save / Watchlist
            if spec.get("save"):
                db.add(SavedContent(user_id=user.id, content_id=cid, created_at=datetime.utcnow()))
                actions_list.append("Saved / Watchlist (weight: 1.0)")

            # Rating
            if spec.get("rating"):
                db.add(Rating(user_id=user.id, content_id=cid, rating=spec["rating"], created_at=datetime.utcnow()))
                actions_list.append(f"Rating: {spec['rating']}/5.0 (normalized weight: {spec['rating']/5.0:.2f})")

            # Watchman Decision
            if spec.get("wm"):
                db.add(WatchmanDecision(user_id=user.id, content_id=cid, decision=spec["wm"], created_at=datetime.utcnow()))
                actions_list.append(f"WatchMan Decision: '{spec['wm']}'")

            # Watch History / Trailer interaction
            if spec.get("progress"):
                db.add(WatchHistory(user_id=user.id, content_id=cid, progress=spec["progress"], completed=(spec["progress"] >= 0.9), watched_at=datetime.utcnow()))
                actions_list.append(f"Watch Progress: {int(spec['progress']*100)}%")

            # Interaction event telemetry
            db.add(InteractionEvent(user_id=user.id, content_id=cid, event_type="watch", event_value=1.0, created_at=datetime.utcnow()))

            genre_names = [g.genre.name for g in (content_item.genres or []) if hasattr(g, "genre") and hasattr(g.genre, "name")]
            seeded_interactions_info.append({
                "content_id": cid,
                "title": content_item.title,
                "content_type": "Movie" if content_item.content_type == "movie" else "TV/Web-Series",
                "genres": ", ".join(genre_names),
                "actions": actions_list,
            })

        db.commit()

        # 6. Compute Aryan's taste preference vector using Content-Based Pipeline
        user_emb_record = UserEmbeddingService.compute_and_save_user_embedding(db, user.id, force=True)
        db.commit()

        # 7. Run Content-Based Recommendation Flow (Excluding interacted items)
        candidates = ContentBasedCandidateGenerator.generate_candidates(
            db,
            user_id=user.id,
            limit=10,
            exclude_content_ids=interacted_content_ids,
        )

        # 8. Authentication & Security Verification
        login_valid = verify_password(password, user.password_hash)
        auth_token = create_access_token(user.id)
        token_payload = decode_token(auth_token)
        token_valid = (token_payload.get("sub") == str(user.id))

        recommendations_info = []
        for idx, c in enumerate(candidates, start=1):
            item = c["content"]
            genre_names = [g.genre.name for g in (item.genres or []) if hasattr(g, "genre") and hasattr(g.genre, "name")]
            rel_date = (item.release_date or "").strip()
            year_str = rel_date[:4] if len(rel_date) >= 4 and rel_date[:4].isdigit() else "N/A"
            recommendations_info.append({
                "rank": idx,
                "content_id": item.id,
                "title": item.title,
                "content_type": "Movie" if item.content_type == "movie" else "TV/Web-Series",
                "release_year": year_str,
                "genres": ", ".join(genre_names) if genre_names else "Unknown",
                "similarity_score": round(float(c["score"]), 4),
            })

        return {
            "status": "success",
            "user": {
                "user_id": str(user.id),
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "is_active": user.is_active,
                "password_hashed": bool(user.password_hash and user.password_hash.startswith("$2b$")),
            },
            "auth_verification": {
                "login_credentials_valid": login_valid,
                "token_generation_valid": token_valid,
                "auth_provider_mode": settings.AUTH_PROVIDER,
            },
            "preferences": {
                "favorite_genres": ["Sci-Fi & Fantasy", "Science Fiction", "Fantasy", "Comedy"],
                "favorite_genre_ids": target_genre_tmdb_ids,
            },
            "seeded_interactions": seeded_interactions_info,
            "user_embedding": {
                "exists": user_emb_record is not None and user_emb_record.embedding is not None,
                "model": user_emb_record.model_name if user_emb_record else None,
                "dimension": len(user_emb_record.embedding) if (user_emb_record and user_emb_record.embedding) else 0,
                "sample_vector_first_5": [round(x, 4) for x in user_emb_record.embedding[:5]] if (user_emb_record and user_emb_record.embedding) else [],
            },
            "recommendations": recommendations_info,
        }
    finally:
        if should_close_db:
            db.close()


def print_report(res: dict):
    u = res["user"]
    p = res["preferences"]
    emb = res["user_embedding"]
    auth = res["auth_verification"]

    print("=" * 80)
    print("WATCHMAN USER SEEDING & CONTENT-BASED RECOMMENDATION REPORT")
    print("=" * 80)
    print(f"User:")
    print(f"  username         : {u['username']}")
    print(f"  email            : {u['email']}")
    print(f"  user_id          : {u['user_id']}")
    print(f"  is_active        : {u['is_active']}")
    print(f"  password_hashed  : {u['password_hashed']} (bcrypt)")

    print(f"\nAuthentication Verification:")
    print(f"  login_credentials_valid : {auth['login_credentials_valid']}")
    print(f"  token_generation_valid  : {auth['token_generation_valid']}")
    print(f"  auth_provider_mode      : {auth['auth_provider_mode']}")

    print(f"\nPreferences:")
    for g in p["favorite_genres"]:
        print(f"  - {g}")

    print(f"\nSeeded Interactions ({len(res['seeded_interactions'])} catalog items):")
    for idx, item in enumerate(res["seeded_interactions"], 1):
        print(f"  {idx}. [{item['content_type']}] '{item['title']}' (Genres: {item['genres']})")
        for act in item["actions"]:
            print(f"     * {act}")

    print(f"\nUser Embedding:")
    print(f"  model      : {emb['model']}")
    print(f"  dimension  : {emb['dimension']}")
    print(f"  exists     : {emb['exists']}")
    print(f"  sample_5D  : {emb['sample_vector_first_5']}")

    print(f"\nTop-10 Content-Based Recommendations:")
    fmt = "{:<4} | {:<32} | {:<14} | {:<5} | {:<36} | {:<10}"
    print(fmt.format("Rank", "Title", "Type", "Year", "Genres", "Similarity"))
    print("-" * 115)
    for r in res["recommendations"]:
        title_str = (r["title"][:29] + "...") if len(r["title"]) > 32 else r["title"]
        genres_str = (r["genres"][:33] + "...") if len(r["genres"]) > 36 else r["genres"]
        print(fmt.format(
            r["rank"],
            title_str,
            r["content_type"],
            r["release_year"],
            genres_str,
            f"{r['similarity_score']:.4f}"
        ))
    print("=" * 80)


if __name__ == "__main__":
    result = seed_user()
    print_report(result)
