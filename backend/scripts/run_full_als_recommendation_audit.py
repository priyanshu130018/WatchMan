"""
Full verification and latency audit script for WatchMan ALS collaborative-filtering recommendation integration.
"""

from __future__ import annotations

import time
import uuid
import requests
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User, UserPreference
from app.models.collaborative import ALSUserFactors, ALSItemFactors
from app.models.recommendation import Recommendation
from app.ml.candidates.pipeline import CandidatePipeline
from app.ml.candidates.als_collaborative import ALSCollaborativeCandidateGenerator
from app.ml.candidates.content_based import ContentBasedCandidateGenerator
from app.ml.candidates.popularity import PopularityCandidateGenerator
from app.ml.candidates.freshness import FreshnessCandidateGenerator
from app.ml.ranking.hybrid import HybridRanker
from app.ml.recommendations.generator import RecommendationGenerator
from app.services.recommendation.service import UnifiedRecommendationService
from app.core.security import create_access_token


def run_audit():
    db: Session = SessionLocal()
    rec_service = UnifiedRecommendationService()

    try:
        print("=" * 80)
        print("WATCHMAN ALS COLLABORATIVE-FILTERING RECOMMENDATION PIPELINE AUDIT")
        print("=" * 80)

        # 1. Users
        aryan = db.query(User).filter(User.username == "aryan").first()
        bharat = db.query(User).filter(User.username == "bharat").first()
        assert aryan and bharat, "Aryan and Bharat users must exist"

        print(f"\n[1] User Profiles & ALS Factor Status:")
        for u in [aryan, bharat]:
            uf = db.query(ALSUserFactors).filter(ALSUserFactors.user_id == u.id).first()
            p_genres, p_langs = HybridRanker.get_user_profile_preferences(db, u.id)
            print(f"  * {u.username.title()} (ID: {u.id}):")
            print(f"      ALS Factor: {'Present (64-D, ' + uf.model_version + ')' if uf else 'Missing'}")
            print(f"      Preferred Genres: {p_genres}")

        # 2. Performance & Channel Breakdown for Aryan
        print(f"\n[2] Candidate Channel Retrieval Benchmarks (Aryan):")
        seen_aryan = CandidatePipeline.get_user_seen_content_ids(db, aryan.id)

        # Warm up ALS cache
        ALSCollaborativeCandidateGenerator.generate_candidates(db, aryan.id, limit=30, exclude_content_ids=seen_aryan)

        # Timed candidate runs
        t0 = time.perf_counter()
        cb_cands = ContentBasedCandidateGenerator.generate_candidates(db, aryan.id, limit=30, exclude_content_ids=seen_aryan)
        t_cb = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        als_cands = ALSCollaborativeCandidateGenerator.generate_candidates(db, aryan.id, limit=30, exclude_content_ids=seen_aryan)
        t_als = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        pop_cands = PopularityCandidateGenerator.generate_candidates(db, limit=30, exclude_content_ids=seen_aryan)
        t_pop = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        fresh_cands = FreshnessCandidateGenerator.generate_candidates(db, limit=30, exclude_content_ids=seen_aryan)
        t_fresh = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        all_cands_aryan = CandidatePipeline.generate_all_candidates(db, aryan.id, limit_per_channel=30)
        t_pipeline = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        ranked_aryan = HybridRanker.rank_candidates(db, aryan.id, all_cands_aryan, limit=20)
        t_ranking = (time.perf_counter() - t0) * 1000

        print(f"  * Content-Based Channel:  {len(cb_cands):3d} candidates | {t_cb:6.2f} ms")
        print(f"  * ALS Collaborative Ch:   {len(als_cands):3d} candidates | {t_als:6.2f} ms")
        print(f"  * Popularity Channel:     {len(pop_cands):3d} candidates | {t_pop:6.2f} ms")
        print(f"  * Freshness Channel:      {len(fresh_cands):3d} candidates | {t_fresh:6.2f} ms")
        print(f"  * Merged Candidate Total: {len(all_cands_aryan):3d} candidates | {t_pipeline:6.2f} ms")
        print(f"  * HybridRanker Output:    {len(ranked_aryan):3d} recommendations | {t_ranking:6.2f} ms")

        # 3. Bharat Candidate & Ranking Run
        all_cands_bharat = CandidatePipeline.generate_all_candidates(db, bharat.id, limit_per_channel=30)
        ranked_bharat = HybridRanker.rank_candidates(db, bharat.id, all_cands_bharat, limit=20)

        aryan_ids = [r.content_id for r in ranked_aryan]
        bharat_ids = [r.content_id for r in ranked_bharat]
        overlap_10 = len(set(aryan_ids[:10]).intersection(set(bharat_ids[:10])))
        overlap_20 = len(set(aryan_ids).intersection(set(bharat_ids)))
        print(f"\n[3] Personalization / Distinctness Check:")
        print(f"  * Aryan Top 5 titles:  {[r.content.title for r in ranked_aryan[:5]]}")
        print(f"  * Bharat Top 5 titles: {[r.content.title for r in ranked_bharat[:5]]}")
        print(f"  * Top-10 Overlap: {overlap_10} / 10 items ({(overlap_10/10)*100:.1f}%)")
        print(f"  * Top-20 Overlap: {overlap_20} / 20 items ({(overlap_20/20)*100:.1f}%)")

        # 4. Cold-Start User Verification
        print(f"\n[4] Cold-Start User Verification:")
        cold_id = uuid.uuid4()
        cold_als = ALSCollaborativeCandidateGenerator.generate_candidates(db, cold_id, limit=30)
        print(f"  * Cold user ALS candidate count: {len(cold_als)} (Expected: 0)")
        cold_all = CandidatePipeline.generate_all_candidates(db, cold_id, limit_per_channel=30)
        print(f"  * Cold user pipeline candidates: {len(cold_all)} (From Popularity + Freshness)")
        cold_ranked = HybridRanker.rank_candidates(db, cold_id, cold_all, limit=20)
        print(f"  * Cold user final recommendations: {len(cold_ranked)} (Clean fallback)")

        # 5. Explainability Breakdown Sample Table
        print(f"\n[5] Explainability Breakdown Sample (Aryan Top 15 Ranked):")
        print(f"{'Rank':<4} | {'Score':<6} | {'Content':<7} | {'ALS':<6} | {'Pop':<6} | {'Fresh':<6} | {'Pref':<6} | {'Title':<28} | Sources")
        print("-" * 115)
        for r in ranked_aryan[:15]:
            srcs = ", ".join(r.sources)
            print(
                f"{r.rank:<4} | {r.score:.4f} | {r.content_score:.4f}  | {r.collaborative_score:.4f} | {r.popularity_score:.4f} | {r.freshness_score:.4f} | {r.preference_score:.4f} | {r.content.title[:26]:<28} | {srcs}"
            )

        print(f"\n[5b] Explainability Breakdown Sample (Bharat Top 15 Ranked):")
        print(f"{'Rank':<4} | {'Score':<6} | {'Content':<7} | {'ALS':<6} | {'Pop':<6} | {'Fresh':<6} | {'Pref':<6} | {'Title':<28} | Sources")
        print("-" * 115)
        for r in ranked_bharat[:15]:
            srcs = ", ".join(r.sources)
            print(
                f"{r.rank:<4} | {r.score:.4f} | {r.content_score:.4f}  | {r.collaborative_score:.4f} | {r.popularity_score:.4f} | {r.freshness_score:.4f} | {r.preference_score:.4f} | {r.content.title[:26]:<28} | {srcs}"
            )

        # 6. HTTP API Endpoint Verification
        print(f"\n[6] HTTP API Endpoints Verification (FastAPI /api/recommendations):")
        aryan_token = create_access_token(user_id=aryan.id)
        headers = {"Authorization": f"Bearer {aryan_token}"}
        base_url = "http://localhost:8000/api"

        # Force refresh uncached
        t0 = time.perf_counter()
        resp_uncached = requests.get(f"{base_url}/recommendations?force_refresh=true&limit=20", headers=headers, timeout=10)
        t_api_uncached = (time.perf_counter() - t0) * 1000
        assert resp_uncached.status_code == 200, f"Uncached API failed with {resp_uncached.status_code}: {resp_uncached.text}"
        data_uncached = resp_uncached.json()
        items_uncached = data_uncached.get("items", [])
        print(f"  * GET /api/recommendations (force_refresh=True): HTTP 200 | {len(items_uncached)} items | {t_api_uncached:.2f} ms")

        # Cached request
        t0 = time.perf_counter()
        resp_cached = requests.get(f"{base_url}/recommendations?limit=20", headers=headers, timeout=10)
        t_api_cached = (time.perf_counter() - t0) * 1000
        assert resp_cached.status_code == 200, f"Cached API failed with {resp_cached.status_code}: {resp_cached.text}"
        data_cached = resp_cached.json()
        items_cached = data_cached.get("items", [])
        print(f"  * GET /api/recommendations (cached):             HTTP 200 | {len(items_cached)} items | {t_api_cached:.2f} ms")
        print(f"  * Cache speedup: {t_api_uncached / max(t_api_cached, 0.1):.1f}x")

        # POST /refresh
        t0 = time.perf_counter()
        resp_ref = requests.post(f"{base_url}/recommendations/refresh", headers=headers, timeout=10)
        t_api_ref = (time.perf_counter() - t0) * 1000
        assert resp_ref.status_code == 200, f"POST /refresh failed with {resp_ref.status_code}: {resp_ref.text}"
        print(f"  * POST /api/recommendations/refresh:             HTTP 200 | {t_api_ref:.2f} ms")

        print("\n" + "=" * 80)
        print("ALL AUDIT CHECKS COMPLETED SUCCESSFULLY!")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    run_audit()
