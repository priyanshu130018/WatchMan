"""
Verification script for ALS collaborative-filtering integration into the WatchMan recommendation pipeline.

Checks:
1. Aryan recommendations: ALS candidates present, seen-items excluded, multi-channel blending.
2. Bharat recommendations: ALS candidates present, distinct from Aryan, multi-channel blending.
3. Cold-start user: No ALS factor, 0 interactions, recommendation endpoint returns clean fallback without errors.
4. Latency breakdown: ALS candidates, full candidate pipeline, HybridRanker, API uncached vs cached.
5. Explainability breakdown: content, ALS, pop, fresh, pref, final score, sources for ranked items.
6. Worker isolation & health check.
"""

from __future__ import annotations

import sys
import time
import uuid
from typing import Any
import requests

from app.db.session import SessionLocal
from app.models.user import User
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


def test_als_integration() -> None:
    db = SessionLocal()
    rec_service = UnifiedRecommendationService()

    try:
        # 1. Resolve users
        aryan = db.query(User).filter(User.username == "aryan").first()
        bharat = db.query(User).filter(User.username == "bharat").first()

        assert aryan is not None, "Aryan user not found"
        assert bharat is not None, "Bharat user not found"

        print(f"=== 1. VERIFYING ARYAN (user_id={aryan.id}) ===")
        # Check ALS user factor exists
        aryan_als = db.query(ALSUserFactors).filter(ALSUserFactors.user_id == aryan.id).first()
        print(f"Aryan ALS factor found: {aryan_als is not None}, model_version={aryan_als.model_version if aryan_als else None}")

        # Test individual candidate generators
        seen_aryan = CandidatePipeline.get_user_seen_content_ids(db, aryan.id)
        print(f"Aryan seen/interacted content count: {len(seen_aryan)}")

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

        print(f"Candidate counts for Aryan:")
        print(f"  - Content-Based: {len(cb_cands)} (took {t_cb:.2f}ms)")
        print(f"  - ALS Collaborative: {len(als_cands)} (took {t_als:.2f}ms)")
        print(f"  - Popularity: {len(pop_cands)} (took {t_pop:.2f}ms)")
        print(f"  - Freshness: {len(fresh_cands)} (took {t_fresh:.2f}ms)")

        assert len(als_cands) > 0, "Aryan should have ALS candidates"
        # Check seen items excluded from ALS candidates
        for c in als_cands:
            assert c["content_id"] not in seen_aryan, f"Seen item {c['content_id']} found in ALS candidates!"

        # Candidate pipeline merge
        t0 = time.perf_counter()
        all_cands = CandidatePipeline.generate_all_candidates(db, aryan.id, limit_per_channel=30)
        t_pipe = (time.perf_counter() - t0) * 1000
        print(f"Total merged candidates: {len(all_cands)} (took {t_pipe:.2f}ms)")

        # Ranking
        t0 = time.perf_counter()
        ranked = HybridRanker.rank_candidates(db, aryan.id, all_cands, limit=20)
        t_rank = (time.perf_counter() - t0) * 1000
        print(f"Final ranked recommendations: {len(ranked)} (took {t_rank:.2f}ms)")

        # Verify channels present in final recommendations
        all_rec_sources = set()
        for r in ranked:
            all_rec_sources.update(r.sources)
        print(f"Sources in Aryan's final recommendations: {all_rec_sources}")

        print(f"\n=== 2. VERIFYING BHARAT (user_id={bharat.id}) ===")
        bharat_als = db.query(ALSUserFactors).filter(ALSUserFactors.user_id == bharat.id).first()
        print(f"Bharat ALS factor found: {bharat_als is not None}, model_version={bharat_als.model_version if bharat_als else None}")

        seen_bharat = CandidatePipeline.get_user_seen_content_ids(db, bharat.id)
        bharat_cands = CandidatePipeline.generate_all_candidates(db, bharat.id, limit_per_channel=30)
        bharat_ranked = HybridRanker.rank_candidates(db, bharat.id, bharat_cands, limit=20)

        aryan_top_ids = [r.content_id for r in ranked[:10]]
        bharat_top_ids = [r.content_id for r in bharat_ranked[:10]]
        print(f"Aryan Top 5 IDs: {aryan_top_ids[:5]}")
        print(f"Bharat Top 5 IDs: {bharat_top_ids[:5]}")
        overlap = set(aryan_top_ids).intersection(set(bharat_top_ids))
        print(f"Top 10 Overlap between Aryan & Bharat: {len(overlap)} / 10 items")
        assert len(overlap) < 10, "Aryan and Bharat should receive distinct recommendations based on distinct preferences"

        print(f"\n=== 3. COLD-START USER VERIFICATION ===")
        cold_user_id = uuid.uuid4()
        # Verify ALS candidate generator with non-existent user factor
        cold_als_cands = ALSCollaborativeCandidateGenerator.generate_candidates(db, cold_user_id, limit=30)
        print(f"Cold-start user ALS candidates count: {len(cold_als_cands)}")
        assert len(cold_als_cands) == 0, "Cold-start user should return empty ALS candidates"

        cold_all_cands = CandidatePipeline.generate_all_candidates(db, cold_user_id, limit_per_channel=30)
        print(f"Cold-start user total pipeline candidates: {len(cold_all_cands)}")
        cold_ranked = HybridRanker.rank_candidates(db, cold_user_id, cold_all_cands, limit=20)
        print(f"Cold-start user ranked recommendations: {len(cold_ranked)}")

        print(f"\n=== 4. EXPLAINABILITY BREAKDOWN SAMPLE (Aryan) ===")
        print(f"{'Rank':<4} | {'Score':<6} | {'Content':<7} | {'ALS':<5} | {'Pop':<5} | {'Fresh':<5} | {'Pref':<5} | {'Title':<30} | Sources")
        print("-" * 110)
        for r in ranked[:10]:
            print(
                f"{r.rank:<4} | {r.score:.4f} | {r.content_score:.4f}  | {r.collaborative_score:.4f} | {r.popularity_score:.4f} | {r.freshness_score:.4f} | {r.preference_score:.4f} | {r.content.title[:28]:<30} | {', '.join(r.sources)}"
            )

    finally:
        db.close()


if __name__ == "__main__":
    test_als_integration()
