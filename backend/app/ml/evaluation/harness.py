"""
Offline evaluation harness comparing the three recommendation strategies:

    A. content-only    (Hugging Face embeddings -> pgvector similarity)
    B. als-only        (ALS latent-factor dot product)
    C. hybrid          (full candidate pipeline + HybridRanker)

Protocol: leave-last-out per user. For each user with enough positive signals we
hold out their most recent positive item, ask each strategy for a top-K list
(excluding the user's *other* seen items), and score whether the held-out item
was retrieved. Metrics reuse app.ml.evaluation.metrics.

Limitation: the content user-embedding and the ALS factors used here are the
currently-persisted ones (trained on all data). This harness is intended for
RELATIVE comparison and smoke evaluation on WatchMan's real interactions; a
fully leakage-free result requires retraining each model with the holdout
removed. This caveat is documented in docs/RECOMMENDATION_ARCHITECTURE.md.
"""

from __future__ import annotations

import time
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.content import Content
from app.models.interaction import SavedContent, WatchHistory
from app.models.review import Rating
from app.ml.candidates.content_based import ContentBasedCandidateGenerator
from app.ml.candidates.als_collaborative import ALSCollaborativeCandidateGenerator
from app.ml.candidates.pipeline import CandidatePipeline
from app.ml.ranking.hybrid import HybridRanker
from app.ml.evaluation.metrics import (
    precision_at_k,
    recall_at_k,
    ndcg_at_k,
    hit_rate_at_k,
    catalog_coverage,
)


class RecommendationEvaluator:
    RATING_POSITIVE = 3.0  # on a 5-scale; >=6 on a 10-scale

    @classmethod
    def _positive_items(cls, db: Session, user_id: UUID) -> list[int]:
        """Ordered (oldest->newest) list of content_ids the user liked."""
        items: list[tuple[float, int]] = []
        for r in db.query(Rating).filter(Rating.user_id == user_id).all():
            thr = cls.RATING_POSITIVE if r.rating <= 5.0 else cls.RATING_POSITIVE * 2
            if r.rating >= thr:
                items.append((r.created_at.timestamp() if r.created_at else 0.0, r.content_id))
        for s in db.query(SavedContent).filter(SavedContent.user_id == user_id).all():
            items.append((s.created_at.timestamp() if s.created_at else 0.0, s.content_id))
        for w in db.query(WatchHistory).filter(
            WatchHistory.user_id == user_id, WatchHistory.completed.is_(True)
        ).all():
            items.append((w.watched_at.timestamp() if w.watched_at else 0.0, w.content_id))
        items.sort(key=lambda x: x[0])
        seen: set[int] = set()
        ordered: list[int] = []
        for _, cid in items:
            if cid not in seen:
                seen.add(cid)
                ordered.append(cid)
        return ordered

    @classmethod
    def _rank_ids(cls, strategy: str, db: Session, user_id: UUID, exclude: set[int], k: int) -> list[int]:
        if strategy == "content":
            cands = ContentBasedCandidateGenerator.generate_candidates(
                db=db, user_id=user_id, limit=k * 3, exclude_content_ids=exclude
            )
            cands.sort(key=lambda c: c["score"], reverse=True)
            return [c["content_id"] for c in cands[:k]]
        if strategy == "als":
            cands = ALSCollaborativeCandidateGenerator.generate_candidates(
                db=db, user_id=user_id, limit=k * 3, exclude_content_ids=exclude
            )
            return [c["content_id"] for c in cands[:k]]
        # hybrid
        candidates = CandidatePipeline.generate_all_candidates(
            db=db, user_id=user_id, limit_per_channel=k * 3, persist_candidates=False
        )
        candidates = [c for c in candidates if c.content_id not in exclude]
        ranked = HybridRanker.rank_candidates(db, user_id, candidates, limit=k, apply_diversity=False)
        return [r.content_id for r in ranked]

    @classmethod
    def evaluate(cls, db: Session, k: int = 10) -> dict:
        strategies = ("content", "als", "hybrid")
        agg = {s: {"precision": [], "recall": [], "ndcg": [], "hit": [], "latency_ms": [], "recommended": set()}
               for s in strategies}
        catalog_ids = {row[0] for row in db.query(Content.id).all()}
        evaluated_users = 0

        for (user_id,) in db.query(SavedContent.user_id).distinct().all() or []:
            positives = cls._positive_items(db, user_id)
            if len(positives) < 2:
                continue  # not enough history to hold one out
            holdout = positives[-1]
            exclude = set(positives[:-1])  # exclude other seen; allow holdout to surface
            evaluated_users += 1
            relevant = {holdout}
            for s in strategies:
                t0 = time.perf_counter()
                recs = cls._rank_ids(s, db, user_id, exclude, k)
                agg[s]["latency_ms"].append((time.perf_counter() - t0) * 1000.0)
                agg[s]["recommended"].update(recs)
                agg[s]["precision"].append(precision_at_k(recs, relevant, k))
                agg[s]["recall"].append(recall_at_k(recs, relevant, k))
                agg[s]["ndcg"].append(ndcg_at_k(recs, relevant, k))
                agg[s]["hit"].append(hit_rate_at_k(recs, relevant, k))

        def _mean(xs: list[float]) -> float:
            return round(sum(xs) / len(xs), 4) if xs else 0.0

        report = {"k": k, "evaluated_users": evaluated_users, "strategies": {}}
        for s in strategies:
            a = agg[s]
            report["strategies"][s] = {
                "precision_at_k": _mean(a["precision"]),
                "recall_at_k": _mean(a["recall"]),
                "ndcg_at_k": _mean(a["ndcg"]),
                "hit_rate_at_k": _mean(a["hit"]),
                "catalog_coverage": catalog_coverage(a["recommended"], catalog_ids),
                "avg_latency_ms": _mean(a["latency_ms"]),
            }
        return report
