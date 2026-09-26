import logging
from uuid import UUID
from app.core.celery import celery_app
from app.db.session import SessionLocal
from app.ml.recommendations.generator import RecommendationGenerator
from app.models.user import User

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.recommendation.recompute_user_recommendations")
def recompute_user_recommendations(user_id_str: str, limit: int = 50) -> dict:
    """
    Background Celery task to recompute recommendations for a single user.
    """
    user_id = UUID(user_id_str)
    db = SessionLocal()
    try:
        ranked = RecommendationGenerator.generate_and_persist_for_user(
            db=db,
            user_id=user_id,
            limit=limit,
        )
        logger.info("Generated %d recommendations for user %s", len(ranked), user_id_str)
        return {"user_id": user_id_str, "recommendations_count": len(ranked)}
    finally:
        db.close()


@celery_app.task(name="app.tasks.recommendation.generate_user_recommendations_batch")
def generate_user_recommendations_batch(limit_per_user: int = 50) -> dict:
    """
    Background Celery task to batch recompute recommendations for all active users.
    """
    db = SessionLocal()
    try:
        users = db.query(User.id).all()
        processed = 0
        for u in users:
            try:
                RecommendationGenerator.generate_and_persist_for_user(
                    db=db,
                    user_id=u.id,
                    limit=limit_per_user,
                )
                processed += 1
            except Exception as e:
                logger.error("Failed to generate recommendations for user %s: %s", u.id, e)

        return {"total_users": len(users), "processed_users": processed}
    finally:
        db.close()
