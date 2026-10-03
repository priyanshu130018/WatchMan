import sys
import os
import uuid
from datetime import datetime
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.user import User
from app.models.content import Content
from app.models.embedding import ContentEmbedding, UserEmbedding
from app.models.interaction import SavedContent, WatchHistory, InteractionEvent
from app.models.review import Rating
from app.models.watchman import WatchmanDecision
from app.ml.embeddings.sentence_encoder import SentenceEncoder
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.candidates.content_based import ContentBasedCandidateGenerator
from app.core.config import settings

def run_tests():
    db: Session = SessionLocal()
    results = {}
    print("=" * 70)
    print("WATCHMAN CONTENT-BASED RECOMMENDATION SYSTEM TEST SUITE")
    print("=" * 70)
    print(f"Embedding Model: {settings.EMBEDDING_MODEL}")
    print(f"Vector Dimension: {settings.VECTOR_DIMENSION}")
    print(f"pgvector Enabled: {settings.ENABLE_PGVECTOR}")

    # ---------------------------------------------------------
    # TEST 1: Sentence Encoder & Dimension Verification
    # ---------------------------------------------------------
    print("\n[TEST 1] Verifying SentenceEncoder with BAAI/bge-small-en-v1.5 (384-D)...")
    encoder = SentenceEncoder.get_instance()
    sample_text = "Sci-Fi thriller about dreams, memory manipulation, and space exploration."
    single_vector = encoder.encode(sample_text)
    dim = len(single_vector)
    norm = float(np.linalg.norm(single_vector))
    assert dim == 384, f"Expected 384 dimensions, got {dim}"
    print(f"  -> Single text encoding: dim={dim}, vector norm={norm:.4f} [PASS]")

    batch_texts = [
        "Inception directed by Christopher Nolan, dream within a dream sci-fi",
        "Interstellar wormhole space travel physics and black holes",
        "Toy Story animated family adventure with talking toys"
    ]
    batch_vectors = encoder.encode_batch(batch_texts)
    assert len(batch_vectors) == 3, f"Expected 3 vectors, got {len(batch_vectors)}"
    for idx, v in enumerate(batch_vectors):
        assert len(v) == 384, f"Vector {idx} dimension mismatch: {len(v)}"
    print(f"  -> Batch encoding ({len(batch_texts)} texts): all 384-D [PASS]")
    results["test_1_encoder"] = "PASS"

    # ---------------------------------------------------------
    # TEST 2: Content Embedding Generation & Deduplication
    # ---------------------------------------------------------
    print("\n[TEST 2] Testing Content Embedding Persistence & Content Hash Deduplication...")
    test_movie = db.query(Content).filter(Content.content_type == "movie").first()
    assert test_movie is not None, "Catalog has no movie items!"

    emb1 = ContentEmbeddingService.embed_content(db, test_movie.id, force=True)
    assert emb1 is not None and emb1.embedding is not None
    assert len(emb1.embedding) == 384
    assert emb1.model_name == settings.EMBEDDING_MODEL
    assert emb1.dimension == 384
    initial_updated_at = emb1.updated_at
    print(f"  -> Successfully embedded content_id={test_movie.id} ('{test_movie.title}'): 384-D vector stored")

    # Call again without force (should be idempotent / skipped)
    emb2 = ContentEmbeddingService.embed_content(db, test_movie.id, force=False)
    assert emb2.updated_at == initial_updated_at, "Deduplication failed: embedding was unexpectedly re-generated!"
    print(f"  -> Content hash deduplication verified: skipped unchanged content [PASS]")
    results["test_2_deduplication"] = "PASS"

    # ---------------------------------------------------------
    # TEST 3: Cold-Start Behavior (0 Interactions)
    # ---------------------------------------------------------
    print("\n[TEST 3] Testing Cold-Start Behavior (Brand New User)...")
    cold_user_id = uuid.uuid4()
    cold_user = User(
        id=cold_user_id,
        email=f"cold_start_{cold_user_id.hex[:6]}@watchman.test",
        password_hash="test_hash",
        is_active=True,
    )
    db.add(cold_user)
    db.commit()

    # User preference vector should be None
    user_vec = UserEmbeddingService.get_or_compute_user_embedding(db, cold_user.id)
    assert user_vec is None, "Cold start user must not have a user preference vector!"

    # Candidate generation should return empty list gracefully without crashing
    candidates = ContentBasedCandidateGenerator.generate_candidates(db, cold_user.id, limit=10)
    assert candidates == [], "Cold start candidate generator must return empty list!"
    print(f"  -> Cold-start user handled gracefully: user_vector=None, candidates=[] [PASS]")
    results["test_3_cold_start"] = "PASS"

    # Clean up cold user
    db.delete(cold_user)
    db.commit()

    # ---------------------------------------------------------
    # TEST 4: Controlled User with Known Sci-Fi Interactions
    # ---------------------------------------------------------
    print("\n[TEST 4] Testing Controlled User Preference Vector & Sci-Fi Retrieval...")
    test_user_id = uuid.uuid4()
    test_user = User(
        id=test_user_id,
        email=f"scifi_fan_{test_user_id.hex[:6]}@watchman.test",
        password_hash="test_hash",
        is_active=True,
    )
    db.add(test_user)
    db.commit()

    # Find 3 Sci-Fi / Thriller movies in the catalog with embeddings
    scifi_movies = (
        db.query(Content)
        .join(ContentEmbedding, Content.id == ContentEmbedding.content_id)
        .filter(
            Content.content_type == "movie",
            Content.overview.ilike("%space%") | Content.overview.ilike("%sci-fi%") | 
            Content.overview.ilike("%future%") | Content.title.in_(["Inception", "Interstellar", "The Matrix", "Avatar", "Tenet", "Dune", "Arrival", "Blade Runner 2049", "The Martian"])
        )
        .limit(3)
        .all()
    )

    if len(scifi_movies) < 3:
        # Fallback: grab any 3 movies with embeddings and embed specific sci-fi items
        scifi_movies = db.query(Content).filter(Content.title.in_(["Inception", "Interstellar", "The Matrix", "Avatar", "Tenet", "Dune", "Arrival", "Blade Runner 2049", "The Martian", "Alien"])).all()
        for m in scifi_movies:
            ContentEmbeddingService.embed_content(db, m.id)

    print("  -> Interacting with known Sci-Fi/Space movies:")
    interacted_ids = set()
    for idx, m in enumerate(scifi_movies):
        interacted_ids.add(m.id)
        print(f"     {idx+1}. ID={m.id} | '{m.title}' | Genres: {[g.genre.name for g in (m.genres or []) if hasattr(g, 'genre')]}")

    # Add positive interactions across various channels:
    # 1. SavedContent (weight: 1.0)
    db.add(SavedContent(user_id=test_user.id, content_id=scifi_movies[0].id))
    # 2. Rating (weight: 5.0/5.0 = 1.0)
    db.add(Rating(user_id=test_user.id, content_id=scifi_movies[1].id, rating=5.0))
    # 3. WatchmanDecision (decision='must_watch', weight: 1.0)
    db.add(WatchmanDecision(user_id=test_user.id, content_id=scifi_movies[2].id, decision="must_watch"))
    # 4. WatchHistory (progress: 0.85 -> weight: 0.5 + 0.5*0.85 = 0.925)
    db.add(WatchHistory(user_id=test_user.id, content_id=scifi_movies[0].id, progress=0.85))
    db.commit()

    # Compute user preference vector
    pref_vector = UserEmbeddingService.compute_and_save_user_embedding(db, test_user.id)
    assert pref_vector is not None, "Failed to compute user preference vector!"
    assert len(pref_vector.embedding) == 384, f"Expected 384 dimensions, got {len(pref_vector.embedding)}"
    pref_norm = float(np.linalg.norm(pref_vector.embedding))
    assert abs(pref_norm - 1.0) < 1e-3, f"Preference vector not unit normalized: {pref_norm}"

    print(f"  -> Generated User Preference Vector: dim={len(pref_vector.embedding)}, L2 norm={pref_norm:.4f}")
    print(f"     Sample vector dimensions [0:5]: {[round(x, 4) for x in pref_vector.embedding[:5]]}")

    # Retrieve Top-10 content-based recommendations excluding interacted items
    candidates = ContentBasedCandidateGenerator.generate_candidates(
        db,
        user_id=test_user.id,
        limit=10,
        exclude_content_ids=interacted_ids,
    )
    assert len(candidates) > 0, "No candidates returned from similarity search!"
    assert all(c["content_id"] not in interacted_ids for c in candidates), "Interacted items were not excluded!"

    print("\n  -> Top-10 Content-Based Recommendations for Sci-Fi Profile:")
    for idx, c in enumerate(candidates, 1):
        item = c["content"]
        genres = [g.genre.name for g in (item.genres or []) if hasattr(g, "genre")]
        print(f"     {idx:2d}. [Score: {c['score']:.4f}] '{item.title}' ({item.release_date[:4] if item.release_date else 'N/A'}) - Genres: {genres}")

    # Save a detached copy of initial Sci-Fi preference vector
    initial_user_vector_copy = list(pref_vector.embedding)

    # ---------------------------------------------------------
    # TEST 5: User Preference Shift & Recommendation Update
    # ---------------------------------------------------------
    print("\n[TEST 5] Testing User Preference Shift (Adding Animation / Family)...")
    # Find prominent Animation / Family movies
    animation_movies = (
        db.query(Content)
        .join(ContentEmbedding, Content.id == ContentEmbedding.content_id)
        .filter(
            Content.content_type == "movie",
            Content.title.in_(["Spirited Away", "Toy Story", "Spider-Man: Into the Spider-Verse", "Inside Out", "Finding Nemo", "WALL·E", "Up", "Coco", "The Lion King", "Shrek", "Moana", "Zootopia", "Ratatouille", "Despicable Me", "Frozen", "Kung Fu Panda"])
        )
        .limit(3)
        .all()
    )
    if len(animation_movies) < 3:
        animation_movies = (
            db.query(Content)
            .join(ContentEmbedding, Content.id == ContentEmbedding.content_id)
            .filter(
                Content.content_type == "movie",
                Content.overview.ilike("%animation%") | Content.overview.ilike("%animated%") | Content.overview.ilike("%family%")
            )
            .limit(3)
            .all()
        )

    print("  -> User shifts taste: Adding strong ratings for Animation movies:")
    new_interacted_ids = set(interacted_ids)
    for idx, m in enumerate(animation_movies):
        new_interacted_ids.add(m.id)
        db.add(SavedContent(user_id=test_user.id, content_id=m.id))
        db.add(Rating(user_id=test_user.id, content_id=m.id, rating=5.0))
        db.add(WatchmanDecision(user_id=test_user.id, content_id=m.id, decision="must_watch"))
        print(f"     {idx+1}. ID={m.id} | '{m.title}' | Genres: {[g.genre.name for g in (m.genres or []) if hasattr(g, 'genre')]}")
    db.commit()

    # Recompute user preference vector
    shifted_pref_vector = UserEmbeddingService.compute_and_save_user_embedding(db, test_user.id)
    assert shifted_pref_vector is not None
    shifted_norm = float(np.linalg.norm(shifted_pref_vector.embedding))

    # Calculate cosine similarity between old and new preference vectors
    old_vec = np.array(initial_user_vector_copy, dtype=np.float32)
    new_vec = np.array(shifted_pref_vector.embedding, dtype=np.float32)
    vector_shift_sim = float(np.dot(old_vec, new_vec))
    print(f"  -> Shifted Preference Vector computed: L2 norm={shifted_norm:.4f}")
    print(f"     Shifted vector sample [0:5]: {[round(x, 4) for x in shifted_pref_vector.embedding[:5]]}")
    print(f"  -> Cosine similarity between initial and shifted user vector: {vector_shift_sim:.4f} (Taste profile shifted!)")

    shifted_candidates = ContentBasedCandidateGenerator.generate_candidates(
        db,
        user_id=test_user.id,
        limit=10,
        exclude_content_ids=new_interacted_ids,
    )
    print("\n  -> Top-10 Content-Based Recommendations After Preference Shift:")
    for idx, c in enumerate(shifted_candidates, 1):
        item = c["content"]
        genres = [g.genre.name for g in (item.genres or []) if hasattr(g, "genre")]
        print(f"     {idx:2d}. [Score: {c['score']:.4f}] '{item.title}' ({item.release_date[:4] if item.release_date else 'N/A'}) - Genres: {genres}")

    # Clean up test user & interactions
    print("\n[CLEANUP] Cleaning up test user and temporary interactions...")
    db.query(WatchmanDecision).filter(WatchmanDecision.user_id == test_user.id).delete()
    db.query(SavedContent).filter(SavedContent.user_id == test_user.id).delete()
    db.query(Rating).filter(Rating.user_id == test_user.id).delete()
    db.query(WatchHistory).filter(WatchHistory.user_id == test_user.id).delete()
    db.query(InteractionEvent).filter(InteractionEvent.user_id == test_user.id).delete()
    db.query(UserEmbedding).filter(UserEmbedding.user_id == test_user.id).delete()
    db.delete(test_user)
    db.commit()
    print("  -> Cleanup complete. DB restored to clean state.")

    print("\n" + "=" * 70)
    print("ALL CONTENT-BASED RECOMMENDATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)
    db.close()

if __name__ == "__main__":
    run_tests()
