from uuid import UUID
import logging
import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.recommendation import Recommendation
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.candidates.pipeline import CandidatePipeline
from app.ml.ranking.hybrid import HybridRanker, RankedRecommendation

logger = logging.getLogger(__name__)


class RecommendationGenerator:
    """
    End-to-end recommendation generation and persistence pipeline.
    """

    MODEL_VERSION = "1.0.0"

    @classmethod
    def _persist_ranked(
        cls,
        db: Session,
        user_id: UUID,
        ranked: list[RankedRecommendation],
    ) -> None:
        try:
            db.query(Recommendation).filter(Recommendation.user_id == user_id).delete()
            for r in ranked:
                db.add(
                    Recommendation(
                        user_id=user_id,
                        content_id=r.content_id,
                        score=r.score,
                        rank=r.rank,
                        model_version=cls.MODEL_VERSION,
                        explanation=r.explanation,
                    )
                )
            db.commit()
        except Exception:
            db.rollback()

    @classmethod
    def generate_and_persist_for_user(
        cls,
        db: Session,
        user_id: UUID,
        limit: int = 50,
        content_type: str | None = None,
        weights: dict[str, float] | None = None,
    ) -> list[RankedRecommendation]:
        """
        Executes the AI recommendation pipeline for a user and transactionally updates persisted recommendations.
        Uses the latest persisted user taste vector computed asynchronously by the Celery background worker.
        """
        # 1. Multi-channel candidate retrieval (uses persisted user_embeddings)
        candidates = CandidatePipeline.generate_all_candidates(
            db=db,
            user_id=user_id,
            limit_per_channel=max(limit, 30),
            content_type=content_type,
            persist_candidates=False,
        )

        # 3. Hybrid ranking & diversity filtering
        ranked = HybridRanker.rank_candidates(
            db=db,
            user_id=user_id,
            candidates=candidates,
            limit=limit,
            weights=weights,
            apply_diversity=True,
        )

        # Convert to dictionary representation while all Content entities & relationships are loaded in session
        formatted_items = [r.to_dict() for r in ranked]

        # 4. Atomic snapshot replacement in recommendations table
        cls._persist_ranked(db, user_id, ranked)

        return formatted_items

