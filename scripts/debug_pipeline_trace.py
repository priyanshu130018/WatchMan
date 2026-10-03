import sys
import time
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.user import User
from app.models.content import Content, ContentType
from app.services.catalog import ContentCatalogService
from app.services.tmdb.service import TMDBService
from app.ml.recommendations.generator import RecommendationGenerator
from app.ml.candidates.pipeline import CandidatePipeline
from app.ml.candidates.content_based import ContentBasedCandidateGenerator
from app.ml.candidates.als_collaborative import ALSCollaborativeCandidateGenerator
from app.ml.candidates.collaborative import CollaborativeCandidateGenerator
from app.ml.candidates.popularity import PopularityCandidateGenerator
from app.ml.candidates.freshness import FreshnessCandidateGenerator
from app.ml.ranking.hybrid import HybridRanker
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.core.timing import start_timing_ctx, get_current_timing_ctx


def debug_movie_listing():
    print("\n" + "=" * 60)
    print("DEBUGGING: Movie Listing (catalog.list_content)")
    print("=" * 60)
    db = SessionLocal()
    ctx = start_timing_ctx("/api/movies")
    t0 = time.perf_counter()
    tmdb = TMDBService()
    catalog = ContentCatalogService(tmdb)
    results, total, total_pages = catalog.list_content(
        db=db,
        content_type=ContentType.MOVIE.value,
        sort_by="popularity_desc",
        page=1,
        limit=20,
    )
    total_time = (time.perf_counter() - t0) * 1000
    print(f"Total list_content time: {total_time:.2f} ms")
    print(f"Total SQL queries executed: {ctx.sql_query_count}")
    print(f"Total DB execution time: {ctx.db_ms:.2f} ms")
    print(f"Results returned: {len(results)}, Total in DB: {total}")
    for idx, q in enumerate(ctx.sql_queries, 1):
        print(f"  Query {idx} ({q['duration_ms']} ms): {q['statement']}")
    db.close()


def debug_movie_details():
    print("\n" + "=" * 60)
    print("DEBUGGING: Movie Details tmdb_id=550")
    print("=" * 60)
    db = SessionLocal()
    ctx = start_timing_ctx("/api/movies/550")
    t0 = time.perf_counter()
    tmdb = TMDBService()
    catalog = ContentCatalogService(tmdb)
    details = catalog.get_local_or_external_details(db, ContentType.MOVIE.value, 550)
    total_time = (time.perf_counter() - t0) * 1000
    print(f"Total get_local_or_external_details time: {total_time:.2f} ms")
    print(f"Total SQL queries executed: {ctx.sql_query_count}")
    print(f"Total DB execution time: {ctx.db_ms:.2f} ms")
    for idx, q in enumerate(ctx.sql_queries, 1):
        print(f"  Query {idx} ({q['duration_ms']} ms): {q['statement']}")
    db.close()


def debug_recommendation_pipeline(user_id_str: str):
    print("\n" + "=" * 60)
    print(f"DEBUGGING: Full Recommendation Pipeline for user {user_id_str}")
    print("=" * 60)
    db = SessionLocal()
    user_id = UUID(user_id_str)
    ctx = start_timing_ctx("/api/recommendations")

    # Step 1: User embedding check
    t0 = time.perf_counter()
    user_vec = UserEmbeddingService.get_stored_user_embedding(db, user_id)
    t_emb = (time.perf_counter() - t0) * 1000
    print(f"1. Stored user embedding lookup: {t_emb:.2f} ms (Vector found: {user_vec is not None})")

    # Step 2: Seen content IDs
    t0 = time.perf_counter()
    seen_ids = CandidatePipeline.get_user_seen_content_ids(db, user_id)
    t_seen = (time.perf_counter() - t0) * 1000
    print(f"2. User seen content IDs: {t_seen:.2f} ms (Seen count: {len(seen_ids)})")

    # Step 3: Content-based candidates
    t0 = time.perf_counter()
    cb_cands = ContentBasedCandidateGenerator.generate_candidates(db, user_id, limit=50, exclude_content_ids=seen_ids)
    t_cb = (time.perf_counter() - t0) * 1000
    print(f"3. Content-based candidate generation: {t_cb:.2f} ms (Found: {len(cb_cands)})")

    # Step 4: ALS collaborative candidates
    t0 = time.perf_counter()
    als_cands = ALSCollaborativeCandidateGenerator.generate_candidates(db, user_id, limit=50, exclude_content_ids=seen_ids)
    t_als = (time.perf_counter() - t0) * 1000
    print(f"4. ALS collaborative candidate generation: {t_als:.2f} ms (Found: {len(als_cands)})")

    # Step 5: Fallback collaborative candidates (if ALS empty)
    if not als_cands:
        print("   ALS returned 0 candidates, testing fallback memory KNN...")
        t0 = time.perf_counter()
        knn_cands = CollaborativeCandidateGenerator.generate_candidates(db, user_id, limit=50, exclude_content_ids=seen_ids)
        t_knn = (time.perf_counter() - t0) * 1000
        print(f"   Memory KNN collaborative candidate generation: {t_knn:.2f} ms (Found: {len(knn_cands)})")

    # Step 6: Popularity candidates
    t0 = time.perf_counter()
    pop_cands = PopularityCandidateGenerator.generate_candidates(db, limit=50, exclude_content_ids=seen_ids)
    t_pop = (time.perf_counter() - t0) * 1000
    print(f"6. Popularity candidate generation: {t_pop:.2f} ms (Found: {len(pop_cands)})")

    # Step 7: Freshness candidates
    t0 = time.perf_counter()
    fresh_cands = FreshnessCandidateGenerator.generate_candidates(db, limit=50, exclude_content_ids=seen_ids)
    t_fresh = (time.perf_counter() - t0) * 1000
    print(f"7. Freshness candidate generation: {t_fresh:.2f} ms (Found: {len(fresh_cands)})")

    # Step 8: Ranking
    all_cands = CandidatePipeline.generate_all_candidates(db, user_id, limit_per_channel=50)
    t0 = time.perf_counter()
    ranked = HybridRanker.rank_candidates(db, user_id, all_cands, limit=20)
    t_rank = (time.perf_counter() - t0) * 1000
    print(f"8. Hybrid ranking: {t_rank:.2f} ms (Ranked count: {len(ranked)})")

    # Summary
    print(f"\n--- Total Pipeline Metrics ---")
    print(f"Total SQL queries executed: {ctx.sql_query_count}")
    print(f"Total DB time: {ctx.db_ms:.2f} ms")
    for idx, q in enumerate(ctx.sql_queries, 1):
        print(f"  Query {idx} ({q['duration_ms']} ms): {q['statement']}")
    db.close()


if __name__ == "__main__":
    debug_movie_listing()
    debug_movie_details()
    debug_recommendation_pipeline("0b5c7ab5-f62c-46b9-8de0-9645f992991d")
