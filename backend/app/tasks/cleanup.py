import logging
from datetime import datetime, timezone, timedelta
from app.core.celery import celery_app
from app.db.session import SessionLocal
from app.models.recommendation import RecommendationCandidate

logger = logging.getLogger(__name__)


# NOTE: A previous ``cleanup_stale_cache`` task was removed here. It was a no-op
# that only returned a success message. Recommendation cache entries are written
# with an explicit Redis TTL (see app/core/redis.py + UnifiedRecommendationService
# CACHE_TTL), so Redis expires them automatically — a periodic cache-cleanup task
# is unnecessary. Do not reintroduce a fake operational task.


@celery_app.task(name="app.tasks.cleanup.cleanup_orphan_candidates")
def cleanup_orphan_candidates(days_threshold: int = 7) -> dict:
    """
    Prune temporary recommendation candidates older than threshold.
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_threshold)
        deleted = (
            db.query(RecommendationCandidate)
            .filter(RecommendationCandidate.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        logger.info("Cleaned up %d old recommendation candidates", deleted)
        return {"deleted_candidates": deleted}
    except Exception as e:
        db.rollback()
        logger.error("Error cleaning up recommendation candidates: %s", e)
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
