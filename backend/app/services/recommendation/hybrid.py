"""DEPRECATED — legacy standalone hybrid recommender (removed).

This module previously contained ``HybridRecommendationService``, a SECOND,
fully independent recommendation algorithm (token-overlap content scoring +
in-memory cosine collaborative filtering + hard-coded 0.55/0.35/0.10 weights).
It duplicated the production ranking/candidate logic and used neither the HF
content embeddings (pgvector cosine ANN) nor the ALS latent factors that the
canonical engine relies on.

Per the Phase 2 consolidation requirement ("ONE canonical recommendation
engine"), recommendations now run the canonical pipeline via
``RecommendationGenerator.generate_and_persist_for_user`` (CandidatePipeline +
HybridRanker). This shim remains only to fail loudly if any lingering import
references the old engine; it must not be reintroduced as a parallel production
algorithm.
"""

from __future__ import annotations


class HybridRecommendationService:  # pragma: no cover - deprecated guard
    """Removed. Use RecommendationGenerator.generate_and_persist_for_user (canonical engine)."""

    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError(
            "HybridRecommendationService has been removed. The canonical "
            "recommendation engine (RecommendationGenerator -> CandidatePipeline "
            "-> HybridRanker) now serves recommendations. "
            "Use RecommendationGenerator.generate_and_persist_for_user(...)."
        )
