import asyncio
import logging
from app.core.celery import celery_app
from app.db.session import SessionLocal
from app.services.catalog import ContentCatalogService
from app.services.tmdb.service import TMDBService

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.fetch_tmdb.sync_single_content",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def sync_single_content(self, content_type: str, tmdb_id: int) -> dict:
    """
    Celery task to sync a single movie or TV series from TMDB.
    Uses bounded retries and exponential backoff for transient failures.
    """
    db = SessionLocal()
    try:
        service = ContentCatalogService()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            content = loop.run_until_complete(service.sync_content(db, content_type, tmdb_id))
            return {
                "id": content.id,
                "content_type": content.content_type,
                "tmdb_id": content.tmdb_id,
                "title": content.title,
                "status": "synced",
            }
        finally:
            loop.close()
    except Exception as exc:
        logger.error("Failed to sync %s ID %s: %s. Retrying...", content_type, tmdb_id, exc)
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.fetch_tmdb.sync_trending_catalog",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def sync_trending_catalog(self, time_window: str = "week", max_items: int = 20) -> dict:
    """
    Periodic Celery task to ingest and sync trending movies and web-series from TMDB.
    """
    db = SessionLocal()
    try:
        tmdb = TMDBService()
        service = ContentCatalogService(tmdb=tmdb)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        synced_movies = 0
        synced_tv = 0

        try:
            # Sync trending movies
            trending_movies = loop.run_until_complete(tmdb.trending_movies(time_window=time_window))
            movie_results = trending_movies.get("results", [])[:max_items]
            for m in movie_results:
                m_id = m.get("id")
                if m_id:
                    try:
                        loop.run_until_complete(service.sync_content(db, "movie", m_id))
                        synced_movies += 1
                    except Exception as e:
                        logger.warning("Failed to sync trending movie %s: %s", m_id, e)

            # Sync trending TV series
            trending_tv = loop.run_until_complete(tmdb.trending_tv(time_window=time_window))
            tv_results = trending_tv.get("results", [])[:max_items]
            for t in tv_results:
                t_id = t.get("id")
                if t_id:
                    try:
                        loop.run_until_complete(service.sync_content(db, "tv", t_id))
                        synced_tv += 1
                    except Exception as e:
                        logger.warning("Failed to sync trending TV %s: %s", t_id, e)

            return {
                "status": "success",
                "synced_movies": synced_movies,
                "synced_tv": synced_tv,
            }
        finally:
            loop.close()
    except Exception as exc:
        logger.error("Error in sync_trending_catalog: %s", exc)
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.fetch_tmdb.sync_popular_catalog",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def sync_popular_catalog(self, max_items: int = 20) -> dict:
    """
    Periodic Celery task to ingest and sync popular catalog items.
    """
    db = SessionLocal()
    try:
        tmdb = TMDBService()
        service = ContentCatalogService(tmdb=tmdb)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        synced_movies = 0
        synced_tv = 0

        try:
            pop_movies = loop.run_until_complete(tmdb.popular_movies(page=1))
            for m in pop_movies.get("results", [])[:max_items]:
                m_id = m.get("id")
                if m_id:
                    try:
                        loop.run_until_complete(service.sync_content(db, "movie", m_id))
                        synced_movies += 1
                    except Exception as e:
                        logger.warning("Failed to sync popular movie %s: %s", m_id, e)

            pop_tv = loop.run_until_complete(tmdb.popular_tv(page=1))
            for t in pop_tv.get("results", [])[:max_items]:
                t_id = t.get("id")
                if t_id:
                    try:
                        loop.run_until_complete(service.sync_content(db, "tv", t_id))
                        synced_tv += 1
                    except Exception as e:
                        logger.warning("Failed to sync popular TV %s: %s", t_id, e)

            return {
                "status": "success",
                "synced_movies": synced_movies,
                "synced_tv": synced_tv,
            }
        finally:
            loop.close()
    except Exception as exc:
        logger.error("Error in sync_popular_catalog: %s", exc)
        raise self.retry(exc=exc)
    finally:
        db.close()
