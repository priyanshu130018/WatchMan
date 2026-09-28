"""FastAPI router for Movies catalog, synchronization, discovery, and search."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.constants import CONTENT_PAGE_SIZE, POPULAR_COLLECTION_MAX
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.content import ContentType
from app.schemas.content import (
    ContentPaginationResponse,
    ContentSummaryDTO,
    MovieSyncRequest,
)
from app.services.catalog import ContentCatalogService
from app.services.tmdb.service import TMDBService

router = APIRouter(prefix="/movies", tags=["Movies"])

logger = logging.getLogger(__name__)

tmdb = TMDBService()
catalog = ContentCatalogService(tmdb)


@router.get("", response_model=ContentPaginationResponse[ContentSummaryDTO])
@router.get("/", response_model=ContentPaginationResponse[ContentSummaryDTO])
def list_movies(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=CONTENT_PAGE_SIZE, ge=1, le=100),
    sort: str = Query(default="popularity_desc"),
    year: int | None = Query(default=None),
    genre_id: int | None = Query(default=None),
    language: str | None = Query(default=None),
    collection: str | None = Query(
        default=None,
        description="Optional named collection. 'popular' exposes the top-100 "
        "most popular movies as a finite, paginated set (6 pages of 18).",
    ),
    db: Session = Depends(get_db),
):
    """List movies stored locally with database-level pagination and filtering.

    With ``collection=popular`` the result set is the top ``POPULAR_COLLECTION_MAX``
    titles by popularity (ordering fixed to ``popularity_desc``); filters still
    apply and narrow within that set.
    """
    genre_ids = [genre_id] if genre_id else None
    max_items = None
    effective_sort = sort
    if collection == "popular":
        max_items = POPULAR_COLLECTION_MAX
        effective_sort = "popularity_desc"
    results, total, total_pages = catalog.list_content(
        db=db,
        content_type=ContentType.MOVIE.value,
        genre_ids=genre_ids,
        language_code=language,
        year=year,
        sort_by=effective_sort,
        page=page,
        limit=limit,
        max_items=max_items,
    )
    return ContentPaginationResponse[ContentSummaryDTO](
        page=page,
        limit=limit,
        total=total,
        total_pages=total_pages,
        results=results,
    )


@router.post("/sync")
async def sync_movie(
    payload: MovieSyncRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ingest/synchronize a movie from TMDB into the unified database."""
    content_record = await catalog.sync_movie(db, payload.movie_id)

    return {
        "status": "success",
        "message": f"Movie '{content_record.title}' synced successfully",
        "movie": {
            "id": content_record.id,
            "tmdb_id": content_record.tmdb_id,
            "content_type": content_record.content_type,
            "title": content_record.title,
            "release_date": content_record.release_date,
            "runtime": content_record.runtime,
        },
    }


@router.get("/trending")
async def trending(time_window: str = "week"):
    """Get trending movies from TMDB (normalized to one grid page)."""
    data = await tmdb.trending_movies(time_window=time_window)
    return tmdb.normalize_page(data, page_size=CONTENT_PAGE_SIZE, raise_if_empty=True)


@router.get("/top-10")
async def top_10():
    """Get the top 10 movies (from TMDB top-rated), for the landing rail."""
    data = await tmdb.top_rated_movies(page=1)
    return tmdb.normalize_page(data, page_size=10, raise_if_empty=True)


@router.get("/popular")
async def popular(page: int = Query(default=1, ge=1)):
    """Get popular movies from TMDB (normalized to one grid page)."""
    data = await tmdb.popular_movies(page=page)
    return tmdb.normalize_page(data, page_size=CONTENT_PAGE_SIZE, raise_if_empty=True)


@router.get("/top-rated")
async def top_rated(page: int = Query(default=1, ge=1)):
    """Get top-rated movies from TMDB (normalized to one grid page)."""
    data = await tmdb.top_rated_movies(page=page)
    return tmdb.normalize_page(data, page_size=CONTENT_PAGE_SIZE, raise_if_empty=True)


@router.get("/latest")
async def latest(page: int = Query(default=1, ge=1)):
    """Get latest / now-playing ('new') movies from TMDB (one grid page)."""
    data = await tmdb.latest_movies(page=page)
    return tmdb.normalize_page(data, page_size=CONTENT_PAGE_SIZE, raise_if_empty=True)


@router.get("/search")
async def search(query: str = Query(..., min_length=1), page: int = Query(default=1, ge=1)):
    """Search movies via TMDB (normalized to one grid page).

    An empty result set is a valid search outcome and is returned as an empty
    page rather than an error.
    """
    data = await tmdb.search_movies(query=query, page=page)
    return tmdb.normalize_page(data, page_size=CONTENT_PAGE_SIZE, raise_if_empty=False)


@router.get("/{movie_id}")
async def details(movie_id: int, db: Session = Depends(get_db)):
    """Get movie details (with IMDb / external ratings) from local DB or TMDB."""
    local = await catalog.get_details_with_ratings(db, ContentType.MOVIE.value, movie_id)
    if local is not None:
        return local

    data = await tmdb.movie_details(movie_id)
    # TMDB movie payloads expose imdb_id directly; enrich with OMDb ratings.
    imdb_id = data.get("imdb_id") if isinstance(data, dict) else None
    if imdb_id:
        ratings = await catalog.omdb.ratings_by_imdb_id(imdb_id)
        if ratings:
            data = {**data, **ratings}
    return data


@router.get("/{movie_id}/similar")
async def get_similar_movies(
    movie_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Get similar movies via pgvector embeddings if available, fallback to TMDB."""
    try:
        from app.ml.embeddings.service import MovieEmbeddingService
        results = MovieEmbeddingService.search_similar_movies(
            db=db,
            movie_id=movie_id,
            limit=limit,
        )
        if results:
            return {
                "movie_id": movie_id,
                "results": results,
            }
    except Exception as exc:  # noqa: BLE001 - embeddings are best-effort; fall back to TMDB
        logger.warning(
            "pgvector similar-movie lookup failed for movie_id=%s; falling back to TMDB: %s",
            movie_id,
            exc,
        )

    return await tmdb.similar_movies(movie_id)


@router.get("/{movie_id}/watch-providers")
async def movie_watch_providers(
    movie_id: int,
    region: str = Query(default="IN", min_length=2, max_length=2),
):
    """Where-to-watch streaming offers for a movie in a region (TMDB/JustWatch).

    Availability is exactly what TMDB reports for the region; an unavailable
    title yields empty provider arrays rather than fabricated data.
    """
    data = await tmdb.movie_watch_providers(movie_id)
    return tmdb.extract_region_providers(data, region)


@router.get("/{movie_id}/images")
async def movie_images(movie_id: int):
    """Image gallery (backdrops + posters) for a movie from TMDB."""
    data = await tmdb.movie_images(movie_id)
    backdrops = data.get("backdrops") if isinstance(data, dict) else None
    posters = data.get("posters") if isinstance(data, dict) else None
    return {
        "backdrops": (backdrops or [])[:20],
        "posters": (posters or [])[:20],
    }


@router.get("/{movie_id}/tmdb-reviews")
async def movie_tmdb_reviews(movie_id: int, page: int = Query(default=1, ge=1)):
    """Community reviews for a movie sourced from TMDB.

    These are distinct from WatchMan's own user reviews and are labeled as such
    in the UI.
    """
    data = await tmdb.movie_reviews(movie_id, page=page)
    return tmdb.normalize_reviews(data)
