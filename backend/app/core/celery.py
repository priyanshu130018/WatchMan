from celery import Celery
from celery.schedules import crontab
from datetime import timedelta
import ssl

from app.core.config import settings

celery_app = Celery(
    "watchman",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.embeddings",
        "app.tasks.recommendation",
        "app.tasks.collaborative",
        "app.tasks.fetch_tmdb",
        "app.tasks.cleanup",
    ],
)

# When the broker/backend use TLS (rediss://, e.g. Upstash) Celery needs an
# explicit SSL policy. Upstash terminates TLS with a valid public cert, so
# CERT_REQUIRED is appropriate; we do not disable verification.
_broker_is_tls = str(settings.CELERY_BROKER_URL).startswith("rediss://")
_backend_is_tls = str(settings.CELERY_RESULT_BACKEND).startswith("rediss://")
_ssl_opts = {"ssl_cert_reqs": ssl.CERT_REQUIRED}

if _broker_is_tls:
    celery_app.conf.broker_use_ssl = _ssl_opts
if _backend_is_tls:
    celery_app.conf.redis_backend_use_ssl = _ssl_opts

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    # Hosted Redis (Upstash) friendliness: cap reconnect churn and give queued
    # tasks a sane re-delivery window.
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    result_backend_transport_options={"visibility_timeout": 3600},
    # Periodic Celery Beat Schedule
    beat_schedule={
        "sync-trending-catalog-hourly": {
            "task": "app.tasks.fetch_tmdb.sync_trending_catalog",
            "schedule": 3600.0,  # Run every hour
            "args": ("week", 20),
        },
        "generate-missing-embeddings-hourly": {
            "task": "app.tasks.embeddings.generate_missing_content_embeddings",
            "schedule": 3600.0,
            "args": (100, 32),
        },
        "train-als-collaborative-model": {
            "task": "app.tasks.collaborative.train_als_model",
            # Retrain ALS factors daily at 02:30 UTC, ahead of the recommendation
            # batch so it consumes fresh latent factors (per spec: every 1-2 days).
            "schedule": crontab(hour=2, minute=30),
        },
        "batch-recompute-recommendations": {
            "task": "app.tasks.recommendation.generate_user_recommendations_batch",
            "schedule": timedelta(days=2),  # Run every 2 days (per spec: every 1-2 days)
            "args": (50,),
        },
        "cleanup-orphan-candidates-daily": {
            "task": "app.tasks.cleanup.cleanup_orphan_candidates",
            "schedule": crontab(hour=4, minute=0),
            "args": (7,),
        },
    },
)
