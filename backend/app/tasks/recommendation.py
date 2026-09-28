import logging
from uuid import UUID
from app.core.celery import celery_app
from app.core.config import settings
from app.db.session import SessionLocal
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.recommendations.generator import RecommendationGenerator
from app.models.user import User

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.recommendation.process_user_interaction_ml")
def process_user_interaction_ml(user_id_str: str, content_id: int, db=None) -> dict:
    """
    Background Celery task triggered after user interaction (watch, save, rate, review, decision):
    a. Ensure the interacted content has a content embedding.
    b. Recompute that user's user_embedding.
    c. Recompute that user's recommendations.
    """
    user_id = UUID(user_id_str)
    session = db or SessionLocal()
    should_close = db is None
    try:
        # a. Ensure interacted content has an embedding (if interaction embedding enabled)
        if settings.ENABLE_INTERACTION_EMBEDDING:
            ContentEmbeddingService.embed_content(session, content_id=content_id, force=False)

        # b. Recompute that user's user_embedding
        user_emb = UserEmbeddingService.compute_and_save_user_embedding(session, user_id=user_id)

        # c. Recompute that user's recommendations
        recs = RecommendationGenerator.generate_and_persist_for_user(db=session, user_id=user_id)

        # d. Invalidate recommendation cache in Redis (best effort)
        try:
            from app.core.redis import cache
            import asyncio
            asyncio.run(cache.delete_pattern(f"recommendations:user:{user_id}:*"))
        except Exception:
            pass

        logger.info(
            "Processed interaction ML update for user %s, content %d: emb=%s, recs=%d",
            user_id_str, content_id, user_emb is not None, len(recs),
        )
        return {
            "user_id": user_id_str,
            "content_id": content_id,
            "user_embedding_updated": user_emb is not None,
            "recommendations_count": len(recs),
        }
    finally:
        if should_close:
            session.close()


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
