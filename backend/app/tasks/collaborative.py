"""Celery task: offline ALS matrix-factorization training."""

import logging

from app.core.celery import celery_app
from app.db.session import SessionLocal
from app.ml.collaborative.training import ALSTrainingService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.collaborative.train_als_model")
def train_als_model() -> dict:
    """
    Rebuild the User x Movie interaction matrix and retrain ALS latent factors.
    Runs on the background worker; never on the online request path.
    """
    db = SessionLocal()
    try:
        result = ALSTrainingService.train_and_persist(db)
        logger.info("ALS training task finished: %s", result)
        return result
    except Exception as exc:  # noqa: BLE001 - report failure without crashing beat
        logger.exception("ALS training task failed: %s", exc)
        db.rollback()
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()
