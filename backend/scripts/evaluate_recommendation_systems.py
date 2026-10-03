"""
Offline evaluation script for WatchMan recommendation systems (Content-Based, ALS, Popularity+Freshness, HybridRanker, and Ablations).

Evaluates across the 10 ALS test users using the 80/20 train/test split (seed=42).
Calculates ranking metrics (Precision@10, Recall@10, NDCG@10, HitRate@10, MRR@10),
channel contributions, ablation comparisons, pairwise personalization overlap, and latency benchmarks.
"""

from __future__ import annotations

import itertools
import math
import time
from collections import defaultdict
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User, UserPreference
from app.models.collaborative import ALSUserFactors, ALSItemFactors
from app.models.content import Content
from app.ml.collaborative.training import ALSTrainingService
from app.ml.candidates.pipeline import CandidatePipeline, CandidateItem
from app.ml.candidates.als_collaborative import ALSCollaborativeCandidateGenerator
from app.ml.candidates.content_based import ContentBasedCandidateGenerator
from app.ml.candidates.popularity import PopularityCandidateGenerator
from app.ml.candidates.freshness import FreshnessCandidateGenerator
from app.ml.ranking.hybrid import HybridRanker, RankedRecommendation
from app.services.recommendation.service import UnifiedRecommendationService
from app.ml.recommendations.generator import RecommendationGenerator
from app.core.security import create_access_token


TARGET_USERNAMES = [
    "aryan",
    "bharat",
    "priyanshu",
    "aman",
    "saket",
    "sakshi",
    "neha",
    "priya",
    "aditya",
    "sid",
]


def calculate_metrics_at_k(rec_cids: list[int], target_cids: set[int], k: int = 10) -> dict[str, float]:
    """Computes Precision@K, Recall@K, NDCG@K, HitRate@K, MRR@K."""
    top_k = rec_cids[:k]
    hits = [cid for cid in top_k if cid in target_cids]
    n_hits = len(hits)
    n_target = len(target_cids)

    # Precision & Recall
    precision = n_hits / float(k)
    recall = (n_hits / float(n_target)) if n_target > 0 else 0.0

    # HitRate
    hit_rate = 1.0 if n_hits > 0 else 0.0

    # MRR
    mrr = 0.0
    for idx, cid in enumerate(top_k, 1):
        if cid in target_cids:
            mrr = 1.0 / idx
            break

    # NDCG
    dcg = 0.0
    for idx, cid in enumerate(top_k, 1):
        if cid in target_cids:
            dcg += 1.0 / math.log2(idx + 1)

    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(n_target, k)))
    ndcg = (dcg / idcg) if idcg > 0 else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "ndcg": ndcg,
        "hit_rate": hit_rate,
        "mrr": mrr,
    }


def run_evaluation():
    db: Session = SessionLocal()

    try:
        print("=" * 90)
        print("WATCHMAN OFFLINE RECOMMENDATION SYSTEMS EVALUATION")
        print("=" * 90)

        # 1. Resolve 10 target users
        users = (
            db.query(User)
            .filter(User.username.in_(TARGET_USERNAMES))
            .all()
        )
        user_map = {u.username: u for u in users}
        ordered_users = [user_map[name] for name in TARGET_USERNAMES if name in user_map]
        user_id_to_name = {u.id: u.username for u in ordered_users}

        print(f"Loaded {len(ordered_users)} evaluation users: {', '.join(u.username for u in ordered_users)}")

        # 2. Build interaction matrix & 80/20 train-test split
        full_matrix, all_uids, all_iids = ALSTrainingService.build_interactions(db)
        train_matrix, test_matrix = ALSTrainingService.train_test_split(full_matrix, test_ratio=0.2, seed=42)

        total_interactions = sum(len(items) for items in full_matrix.values())
        eval_interactions = sum(len(full_matrix.get(u.id, {})) for u in ordered_users)
        eval_test_items = sum(len(test_matrix.get(u.id, {})) for u in ordered_users)

        print("\n--- DATASET & EVALUATION SPLIT SUMMARY ---")
        print(f"Total Interacted Items in Catalog: {len(all_iids)}")
        print(f"Total Interactions (10 users):     {eval_interactions}")
        print(f"Train Interactions (80%):          {eval_interactions - eval_test_items}")
        print(f"Test Interactions (20% holdout):   {eval_test_items}")
        for u in ordered_users:
            n_tot = len(full_matrix.get(u.id, {}))
            n_test = len(test_matrix.get(u.id, {}))
            n_train = n_tot - n_test
            print(f"  * {u.username:<10} (ID: {str(u.id)[:8]}...): Total={n_tot:3d} | Train={n_train:3d} | Test={n_test:2d}")

        # 3. System evaluations
        systems = [
            "Content-Based Only",
            "ALS Only",
            "Popularity + Freshness Baseline",
            "Current HybridRanker",
            "Hybrid (No ALS / Collab=0)",
            "Hybrid (No Content-Based / CB=0)",
        ]

        system_metrics: dict[str, dict[str, list[float]]] = {
            s: defaultdict(list) for s in systems
        }
        per_user_results: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)

        # Store Top-20 recommendations for overlap analysis
        user_system_recs_20: dict[str, dict[str, list[int]]] = defaultdict(dict)
        user_hybrid_ranked_objects: dict[str, list[RankedRecommendation]] = {}

        # Contribution metrics trackers for Current HybridRanker Top-20
        total_rec_slots = 0
        als_present_slots = 0
        cb_present_slots = 0
        als_only_slots = 0
        cb_only_slots = 0
        both_slots = 0
        pop_only_slots = 0
        fresh_only_slots = 0
        other_slots = 0
        als_scores_in_final: list[float] = []
        cb_scores_in_final: list[float] = []

        # Warm up caches
        ALSCollaborativeCandidateGenerator._load_item_factors(
            db, ALSCollaborativeCandidateGenerator._current_version(db) or ""
        )

        for u in ordered_users:
            uid = u.id
            uname = u.username
            train_seen = set(train_matrix.get(uid, {}).keys())
            test_target = set(test_matrix.get(uid, {}).keys())

            if not test_target:
                continue

            # A. Content-Based Only
            cb_cands = ContentBasedCandidateGenerator.generate_candidates(
                db, uid, limit=50, exclude_content_ids=train_seen
            )
            cb_cids = [c["content_id"] for c in cb_cands]
            m_cb = calculate_metrics_at_k(cb_cids, test_target, k=10)
            user_system_recs_20[uname]["Content-Based Only"] = cb_cids[:20]

            # B. ALS Only
            als_cands = ALSCollaborativeCandidateGenerator.generate_candidates(
                db, uid, limit=50, exclude_content_ids=train_seen
            )
            als_cids = [c["content_id"] for c in als_cands]
            m_als = calculate_metrics_at_k(als_cids, test_target, k=10)
            user_system_recs_20[uname]["ALS Only"] = als_cids[:20]

            # C. Popularity + Freshness Baseline
            pop_cands = PopularityCandidateGenerator.generate_candidates(
                db, limit=30, exclude_content_ids=train_seen
            )
            fresh_cands = FreshnessCandidateGenerator.generate_candidates(
                db, limit=30, exclude_content_ids=train_seen
            )
            # Merge baseline
            b_map: dict[int, float] = {}
            for p in pop_cands:
                b_map[p["content_id"]] = max(b_map.get(p["content_id"], 0.0), 0.5 * p["score"])
            for f in fresh_cands:
                b_map[f["content_id"]] = max(b_map.get(f["content_id"], 0.0), 0.5 * f["score"])
            sorted_baseline = sorted(b_map.items(), key=lambda x: x[1], reverse=True)
            baseline_cids = [cid for cid, _ in sorted_baseline]
            m_base = calculate_metrics_at_k(baseline_cids, test_target, k=10)
            user_system_recs_20[uname]["Popularity + Freshness Baseline"] = baseline_cids[:20]

            # D. Candidate Pipeline for Hybrid (excluding train_seen items)
            filtered_cands = CandidatePipeline.generate_all_candidates(
                db, uid, limit_per_channel=50, exclude_content_ids=train_seen
            )

            # D1. Current HybridRanker
            current_ranked = HybridRanker.rank_candidates(
                db, uid, filtered_cands, limit=20, apply_diversity=True
            )
            hybrid_cids = [r.content_id for r in current_ranked]
            m_hybrid = calculate_metrics_at_k(hybrid_cids, test_target, k=10)
            user_system_recs_20[uname]["Current HybridRanker"] = hybrid_cids[:20]
            user_hybrid_ranked_objects[uname] = current_ranked

            # Record contribution stats from current hybrid top-20
            for r in current_ranked:
                total_rec_slots += 1
                has_als = "als_collaborative" in r.sources or r.collaborative_score > 0
                has_cb = "content_based" in r.sources or r.content_score > 0
                has_pop = "popularity" in r.sources
                has_fresh = "freshness" in r.sources

                if has_als:
                    als_present_slots += 1
                if has_cb:
                    cb_present_slots += 1

                if has_als and has_cb:
                    both_slots += 1
                elif has_als:
                    als_only_slots += 1
                elif has_cb:
                    cb_only_slots += 1
                elif has_pop and not has_fresh:
                    pop_only_slots += 1
                elif has_fresh and not has_pop:
                    fresh_only_slots += 1
                else:
                    other_slots += 1

                als_scores_in_final.append(r.collaborative_score)
                cb_scores_in_final.append(r.content_score)

            # E. Ablation 1: Hybrid without ALS (collaborative = 0.0)
            no_als_ranked = HybridRanker.rank_candidates(
                db,
                uid,
                filtered_cands,
                limit=20,
                weights={"collaborative": 0.0},
                apply_diversity=True,
            )
            no_als_cids = [r.content_id for r in no_als_ranked]
            m_no_als = calculate_metrics_at_k(no_als_cids, test_target, k=10)
            user_system_recs_20[uname]["Hybrid (No ALS / Collab=0)"] = no_als_cids[:20]

            # F. Ablation 2: Hybrid without Content-Based (content = 0.0)
            no_cb_ranked = HybridRanker.rank_candidates(
                db,
                uid,
                filtered_cands,
                limit=20,
                weights={"content": 0.0},
                apply_diversity=True,
            )
            no_cb_cids = [r.content_id for r in no_cb_ranked]
            m_no_cb = calculate_metrics_at_k(no_cb_cids, test_target, k=10)
            user_system_recs_20[uname]["Hybrid (No Content-Based / CB=0)"] = no_cb_cids[:20]

            # Store per-user metrics
            metrics_map = {
                "Content-Based Only": m_cb,
                "ALS Only": m_als,
                "Popularity + Freshness Baseline": m_base,
                "Current HybridRanker": m_hybrid,
                "Hybrid (No ALS / Collab=0)": m_no_als,
                "Hybrid (No Content-Based / CB=0)": m_no_cb,
            }

            for sys_name, m_dict in metrics_map.items():
                per_user_results[sys_name][uname] = m_dict
                for k_metric, v_metric in m_dict.items():
                    system_metrics[sys_name][k_metric].append(v_metric)

        # 4. Print Per-User & Macro-Average Metrics
        print("\n" + "=" * 90)
        print("SYSTEM RANKING METRICS (@ Top-10) [DEVELOPMENT / EVALUATION BENCHMARK]")
        print("=" * 90)

        for sys_name in systems:
            print(f"\n--- {sys_name.upper()} ---")
            print(f"{'User':<12} | {'Precision@10':<12} | {'Recall@10':<10} | {'NDCG@10':<8} | {'HitRate@10':<10} | {'MRR@10':<8}")
            print("-" * 75)
            for uname in TARGET_USERNAMES:
                u_m = per_user_results[sys_name].get(uname, {})
                if u_m:
                    print(
                        f"{uname:<12} | {u_m['precision']:<12.4f} | {u_m['recall']:<10.4f} | {u_m['ndcg']:<8.4f} | {u_m['hit_rate']:<10.4f} | {u_m['mrr']:<8.4f}"
                    )
            print("-" * 75)
            avg_p = np.mean(system_metrics[sys_name]["precision"])
            avg_r = np.mean(system_metrics[sys_name]["recall"])
            avg_n = np.mean(system_metrics[sys_name]["ndcg"])
            avg_h = np.mean(system_metrics[sys_name]["hit_rate"])
            avg_m = np.mean(system_metrics[sys_name]["mrr"])
            print(
                f"{'MACRO-AVG':<12} | {avg_p:<12.4f} | {avg_r:<10.4f} | {avg_n:<8.4f} | {avg_h:<10.4f} | {avg_m:<8.4f}"
            )

        # 5. Macro Comparison Summary Table
        print("\n" + "=" * 90)
        print("SUMMARY COMPARISON TABLE (MACRO-AVERAGE @ Top-10)")
        print("=" * 90)
        print(f"{'System / Model':<35} | {'Prec@10':<8} | {'Recall@10':<10} | {'NDCG@10':<8} | {'HitRate@10':<10} | {'MRR@10':<8}")
        print("-" * 90)
        for sys_name in systems:
            print(
                f"{sys_name:<35} | "
                f"{np.mean(system_metrics[sys_name]['precision']):.4f}   | "
                f"{np.mean(system_metrics[sys_name]['recall']):.4f}     | "
                f"{np.mean(system_metrics[sys_name]['ndcg']):.4f}   | "
                f"{np.mean(system_metrics[sys_name]['hit_rate']):.4f}     | "
                f"{np.mean(system_metrics[sys_name]['mrr']):.4f}"
            )

        # 6. Candidate Contribution & Source Statistics
        print("\n" + "=" * 90)
        print("CANDIDATE CONTRIBUTION & COMPONENT SCORE ANALYSIS (Top-20 Recommendations)")
        print("=" * 90)
        print(f"Total Recommendation Slots Evaluated (10 users x 20): {total_rec_slots}")
        print(f"  * Slots containing an ALS Candidate:       {als_present_slots:3d} / {total_rec_slots} ({als_present_slots/total_rec_slots*100:5.1f}%)")
        print(f"  * Slots containing a Content-Based Cand:   {cb_present_slots:3d} / {total_rec_slots} ({cb_present_slots/total_rec_slots*100:5.1f}%)")
        print(f"  * Slots supplied ONLY by ALS:              {als_only_slots:3d} / {total_rec_slots} ({als_only_slots/total_rec_slots*100:5.1f}%)")
        print(f"  * Slots supplied ONLY by Content-Based:    {cb_only_slots:3d} / {total_rec_slots} ({cb_only_slots/total_rec_slots*100:5.1f}%)")
        print(f"  * Slots supplied by BOTH ALS + CB:         {both_slots:3d} / {total_rec_slots} ({both_slots/total_rec_slots*100:5.1f}%)")
        print(f"  * Slots supplied by Pop/Fresh/Other:       {pop_only_slots + fresh_only_slots + other_slots:3d} / {total_rec_slots} ({(pop_only_slots + fresh_only_slots + other_slots)/total_rec_slots*100:5.1f}%)")
        print(f"  * Average ALS Score in Final Recs:         {np.mean(als_scores_in_final):.4f}")
        print(f"  * Average Content Score in Final Recs:     {np.mean(cb_scores_in_final):.4f}")

        # 7. Channel Overlap Comparison
        print("\n" + "=" * 90)
        print("INTRA-USER RECOMMENDATION OVERLAP (Top-20 Items Between Channels)")
        print("=" * 90)
        overlap_cb_als = []
        overlap_cb_hybrid = []
        overlap_als_hybrid = []

        for uname in TARGET_USERNAMES:
            cb_set = set(user_system_recs_20[uname].get("Content-Based Only", []))
            als_set = set(user_system_recs_20[uname].get("ALS Only", []))
            hyb_set = set(user_system_recs_20[uname].get("Current HybridRanker", []))

            c_a = len(cb_set.intersection(als_set))
            c_h = len(cb_set.intersection(hyb_set))
            a_h = len(als_set.intersection(hyb_set))

            overlap_cb_als.append(c_a)
            overlap_cb_hybrid.append(c_h)
            overlap_als_hybrid.append(a_h)
            print(f"  * {uname:<10}: CB vs ALS = {c_a:2d}/20 | CB vs Hybrid = {c_h:2d}/20 | ALS vs Hybrid = {a_h:2d}/20")

        print("-" * 90)
        print(f"Average Overlap CB vs ALS:    {np.mean(overlap_cb_als):.2f} / 20 ({np.mean(overlap_cb_als)/20*100:.1f}%)")
        print(f"Average Overlap CB vs Hybrid: {np.mean(overlap_cb_hybrid):.2f} / 20 ({np.mean(overlap_cb_hybrid)/20*100:.1f}%)")
        print(f"Average Overlap ALS vs Hybrid:{np.mean(overlap_als_hybrid):.2f} / 20 ({np.mean(overlap_als_hybrid)/20*100:.1f}%)")

        # 8. User-to-User Personalization Overlap (Pairwise)
        print("\n" + "=" * 90)
        print("INTER-USER PERSONALIZATION OVERLAP (Pairwise Diversity on HybridRanker)")
        print("=" * 90)
        pairs = list(itertools.combinations(TARGET_USERNAMES, 2))
        pairwise_10 = []
        pairwise_20 = []

        for u1, u2 in pairs:
            recs1_10 = set(user_system_recs_20[u1]["Current HybridRanker"][:10])
            recs2_10 = set(user_system_recs_20[u2]["Current HybridRanker"][:10])
            recs1_20 = set(user_system_recs_20[u1]["Current HybridRanker"])
            recs2_20 = set(user_system_recs_20[u2]["Current HybridRanker"])

            ov_10 = len(recs1_10.intersection(recs2_10))
            ov_20 = len(recs1_20.intersection(recs2_20))
            pairwise_10.append(ov_10)
            pairwise_20.append(ov_20)

        print(f"Total User Pairs Evaluated: {len(pairs)}")
        print(f"Average Pairwise Top-10 Overlap: {np.mean(pairwise_10):.2f} / 10 ({np.mean(pairwise_10)/10*100:.1f}%)")
        print(f"Average Pairwise Top-20 Overlap: {np.mean(pairwise_20):.2f} / 20 ({np.mean(pairwise_20)/20*100:.1f}%)")
        print(f"Min Pairwise Top-10 Overlap:     {min(pairwise_10)} / 10")
        print(f"Max Pairwise Top-10 Overlap:     {max(pairwise_10)} / 10")

        # 9. Latency Profiling
        print("\n" + "=" * 90)
        print("SYSTEM LATENCY PROFILE (Measured across all 10 users)")
        print("=" * 90)
        cb_lats = []
        als_lats = []
        merge_lats = []
        rank_lats = []
        total_lats = []

        import asyncio
        rec_service = UnifiedRecommendationService()
        cached_get_lats = []

        for u in ordered_users:
            seen_u = CandidatePipeline.get_user_seen_content_ids(db, u.id)

            t0 = time.perf_counter()
            _ = ContentBasedCandidateGenerator.generate_candidates(db, u.id, limit=30, exclude_content_ids=seen_u)
            cb_lats.append((time.perf_counter() - t0) * 1000)

            t0 = time.perf_counter()
            _ = ALSCollaborativeCandidateGenerator.generate_candidates(db, u.id, limit=30, exclude_content_ids=seen_u)
            als_lats.append((time.perf_counter() - t0) * 1000)

            t0 = time.perf_counter()
            cands_u = CandidatePipeline.generate_all_candidates(db, u.id, limit_per_channel=30)
            merge_lats.append((time.perf_counter() - t0) * 1000)

            t0 = time.perf_counter()
            _ = HybridRanker.rank_candidates(db, u.id, cands_u, limit=20)
            rank_lats.append((time.perf_counter() - t0) * 1000)

            t0 = time.perf_counter()
            _ = asyncio.run(rec_service.get_personalized_recommendations(db, u.id, limit=20, force_refresh=True))
            total_lats.append((time.perf_counter() - t0) * 1000)

            t0 = time.perf_counter()
            _ = asyncio.run(rec_service.get_personalized_recommendations(db, u.id, limit=20, force_refresh=False))
            cached_get_lats.append((time.perf_counter() - t0) * 1000)

        print(f"  * Content Candidate Retrieval: {np.mean(cb_lats):6.2f} ms (p50: {np.median(cb_lats):.2f} ms)")
        print(f"  * ALS Candidate Retrieval:     {np.mean(als_lats):6.2f} ms (p50: {np.median(als_lats):.2f} ms)")
        print(f"  * Candidate Pipeline Merge:    {np.mean(merge_lats):6.2f} ms (p50: {np.median(merge_lats):.2f} ms)")
        print(f"  * HybridRanker Latency:        {np.mean(rank_lats):6.2f} ms (p50: {np.median(rank_lats):.2f} ms)")
        print(f"  * Total Generation Latency:    {np.mean(total_lats):6.2f} ms (p50: {np.median(total_lats):.2f} ms)")
        print(f"  * Cached GET Latency:          {np.mean(cached_get_lats):6.2f} ms (p50: {np.median(cached_get_lats):.2f} ms)")

        # 10. Aryan & Bharat Detailed Ranking Breakdown Sample
        for uname in ["aryan", "bharat"]:
            print(f"\n" + "=" * 90)
            print(f"DETAILED RANKING BREAKDOWN FOR {uname.upper()}")
            print("=" * 90)
            ranked_list = user_hybrid_ranked_objects.get(uname, [])
            print(f"{'Rank':<4} | {'Score':<6} | {'Content':<7} | {'ALS':<6} | {'Pop':<6} | {'Fresh':<6} | {'Pref':<6} | {'Title':<28} | Sources")
            print("-" * 115)
            for r in ranked_list[:15]:
                srcs = ", ".join(r.sources)
                print(
                    f"{r.rank:<4} | {r.score:.4f} | {r.content_score:.4f}  | {r.collaborative_score:.4f} | {r.popularity_score:.4f} | {r.freshness_score:.4f} | {r.preference_score:.4f} | {r.content.title[:26]:<28} | {srcs}"
                )

        print("\n" + "=" * 90)
        print("EVALUATION COMPLETED SUCCESSFULLY!")
        print("=" * 90)

    finally:
        db.close()


if __name__ == "__main__":
    run_evaluation()
