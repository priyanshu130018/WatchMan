import logging
from uuid import UUID
from app.core.celery import celery_app
from app.db.session import SessionLocal
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.ml.embeddings.eligibility import ContentEmbeddingEligibilityService
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.models.content import Content
from app.models.user import User

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.embeddings.generate_missing_content_embeddings")
def generate_missing_content_embeddings(limit: int = 100, batch_size: int = 32) -> dict:
    """
    Background Celery task to batch-embed missing embeddings for ELIGIBLE content only.
    Eligible content includes:
      1. Initial popular target (~500 movies, ~500 TV series).
      2. Content with genuine user interactions.
    Does NOT automatically embed the entire catalog.
    """
    db = SessionLocal()
    try:
        popular_items = ContentEmbeddingEligibilityService.get_initial_popular_candidates(db)
        interacted_ids = ContentEmbeddingEligibilityService.get_interacted_content_ids(db)
        interacted_items = (
            db.query(Content).filter(Content.id.in_(interacted_ids)).all()
            if interacted_ids
            else []
        )

        eligible_map = {c.id: c for c in popular_items}
        for item in interacted_items:
            eligible_map[item.id] = item

        all_eligible = list(eligible_map.values())
        if limit and limit > 0:
            all_eligible = all_eligible[:limit]

        res = ContentEmbeddingService.batch_embed_items(
            db, all_eligible, batch_size=batch_size, force=False
        )
        logger.info("Selective batch embedded contents: %s", res)
        return res
    finally:
        db.close()


@celery_app.task(name="app.tasks.embeddings.backfill_all_content_embeddings")
def backfill_all_content_embeddings(batch_size: int = 32, force_all: bool = False) -> dict:
    """
    Background Celery task to backfill embeddings.
    By default, restricts to eligible content (popular + interacted).
    Full catalog backfill requires explicit force_all=True with warning logged.
    """
    if not force_all:
        logger.warning(
            "backfill_all_content_embeddings invoked without force_all=True. "
            "Restricting to eligible catalog items (popular + interacted) per selective embedding policy."
        )
        return generate_missing_content_embeddings(limit=None, batch_size=batch_size)

    logger.warning("WARNING: Full catalog content embedding backfill triggered (force_all=True).")
    db = SessionLocal()
    try:
        res = ContentEmbeddingService.batch_embed_contents(db, limit=None, batch_size=batch_size)
        logger.info("Backfill all content embeddings completed: %s", res)
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
