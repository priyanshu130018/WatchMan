import logging
from uuid import UUID
from app.core.celery import celery_app
from app.db.session import SessionLocal
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.models.user import User

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.embeddings.generate_missing_content_embeddings")
def generate_missing_content_embeddings(limit: int = 100, batch_size: int = 32) -> dict:
    """
    Background Celery task to batch-embed contents missing embeddings.
    """
    db = SessionLocal()
    try:
        res = ContentEmbeddingService.batch_embed_contents(db, limit=limit, batch_size=batch_size)
        logger.info("Batch embedded contents: %s", res)
        return res
    finally:
        db.close()


@celery_app.task(name="app.tasks.embeddings.embed_single_content")
def embed_single_content(content_id: int, force: bool = False) -> dict:
    """
    Background task to embed a single content item.
    """
    db = SessionLocal()
    try:
        emb = ContentEmbeddingService.embed_content(db, content_id=content_id, force=force)
        return {"content_id": content_id, "dimension": emb.dimension, "model_name": emb.model_name}
    finally:
        db.close()


@celery_app.task(name="app.tasks.embeddings.update_user_embeddings_batch")
def update_user_embeddings_batch(user_ids: list[str] | None = None) -> dict:
    """
    Background task to update user preference embeddings.
    """
    db = SessionLocal()
    try:
        if user_ids:
            target_uuids = [UUID(uid) for uid in user_ids]
        else:
            target_uuids = [u.id for u in db.query(User.id).all()]

        updated_count = 0
        for uid in target_uuids:
            res = UserEmbeddingService.compute_and_save_user_embedding(db, uid)
            if res is not None:
                updated_count += 1

        return {"total_users": len(target_uuids), "updated_users": updated_count}
    finally:
        db.close()
