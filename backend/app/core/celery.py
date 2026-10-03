from celery import Celery
from celery.schedules import crontab
from kombu import Queue
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
    task_default_queue="default",
    task_queues=(
        Queue("default", routing_key="default"),
        Queue("content_based", routing_key="content_based"),
        Queue("als", routing_key="als"),
    ),
    task_routes={
        # Content-based recommendation & embedding pipeline tasks -> content_based queue
        "app.tasks.embeddings.refresh_changed_user_embeddings": {"queue": "content_based"},
        "app.tasks.embeddings.update_user_embeddings_batch": {"queue": "content_based"},
        "app.tasks.embeddings.generate_missing_content_embeddings": {"queue": "content_based"},
        "app.tasks.embeddings.backfill_all_content_embeddings": {"queue": "content_based"},
        "app.tasks.embeddings.embed_single_content": {"queue": "content_based"},
        "app.tasks.recommendation.process_user_interaction_ml": {"queue": "content_based"},
        "app.tasks.recommendation.recompute_user_recommendations": {"queue": "content_based"},
        "app.tasks.recommendation.generate_user_recommendations_batch": {"queue": "content_based"},
        # ALS Collaborative Filtering ML tasks -> als queue
        "app.tasks.collaborative.train_als_model": {"queue": "als"},
        # Catalog / TMDB ingest & cleanup tasks -> default queue
        "app.tasks.fetch_tmdb.sync_single_content": {"queue": "default"},
        "app.tasks.fetch_tmdb.sync_trending_catalog": {"queue": "default"},
        "app.tasks.fetch_tmdb.sync_popular_catalog": {"queue": "default"},
        "app.tasks.cleanup.cleanup_orphan_candidates": {"queue": "default"},
    },
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
        "refresh-user-embeddings-10min": {
            "task": "app.tasks.embeddings.refresh_changed_user_embeddings",
            "schedule": 600.0,  # Run every 10 minutes (testing schedule)
            "options": {"queue": "content_based"},
        },
        "sync-trending-catalog-hourly": {
            "task": "app.tasks.fetch_tmdb.sync_trending_catalog",
            "schedule": 3600.0,  # Run every hour
            "args": ("week", 20),
            "options": {"queue": "default"},
        },
        "generate-missing-embeddings-hourly": {
            "task": "app.tasks.embeddings.generate_missing_content_embeddings",
            "schedule": 3600.0,
            "args": (100, 32),
            "options": {"queue": "content_based"},
        },
        "train-als-collaborative-model": {
            "task": "app.tasks.collaborative.train_als_model",
            # Retrain ALS factors daily at 02:30 UTC, ahead of the recommendation
            # batch so it consumes fresh latent factors (per spec: every 1-2 days).
            "schedule": crontab(hour=2, minute=30),
            "options": {"queue": "als"},
        },
        "batch-recompute-recommendations": {
            "task": "app.tasks.recommendation.generate_user_recommendations_batch",
            "schedule": timedelta(days=2),  # Run every 2 days (per spec: every 1-2 days)
            "args": (50,),
            "options": {"queue": "content_based"},
        },
        "cleanup-orphan-candidates-daily": {
            "task": "app.tasks.cleanup.cleanup_orphan_candidates",
            "schedule": crontab(hour=4, minute=0),
            "args": (7,),
            "options": {"queue": "default"},
        },
    },
)
