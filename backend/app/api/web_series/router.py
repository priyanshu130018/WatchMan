"""FastAPI router for Web Series / TV shows catalog, synchronization, discovery, and search."""

from __future__ import annotations

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
    WebSeriesSyncRequest,
)
from app.services.catalog import ContentCatalogService
from app.services.tmdb.service import TMDBService

router = APIRouter(prefix="/web-series", tags=["Web Series"])

tmdb = TMDBService()
catalog = ContentCatalogService(tmdb)


@router.get("", response_model=ContentPaginationResponse[ContentSummaryDTO])
@router.get("/", response_model=ContentPaginationResponse[ContentSummaryDTO])
def list_web_series(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=CONTENT_PAGE_SIZE, ge=1, le=100),
    page_size: int | None = Query(default=None, ge=1, le=100, description="Alias for limit"),
    sort: str = Query(default="popularity_desc"),
    year: int | None = Query(default=None),
    genre_id: int | None = Query(default=None),
    genre: int | None = Query(default=None, description="Alias for genre_id"),
    language: str | None = Query(default=None),
    collection: str | None = Query(
        default=None,
        description="Optional named collection. 'popular' exposes the top-100 "
        "most popular web series as a finite, paginated set (6 pages of 18).",
    ),
    db: Session = Depends(get_db),
):
    """List web series / TV shows stored locally with database-level pagination and filtering.

    With ``collection=popular`` the result set is the top ``POPULAR_COLLECTION_MAX``
    titles by popularity (ordering fixed to ``popularity_desc``); filters still
    apply and narrow within that set.
    """
    effective_limit = page_size if page_size is not None else limit
    effective_genre = genre_id if genre_id is not None else genre
    genre_ids = [effective_genre] if effective_genre else None
    max_items = None
    effective_sort = sort
    if collection == "popular":
        max_items = POPULAR_COLLECTION_MAX
        effective_sort = "popularity_desc"
    results, total, total_pages = catalog.list_content(
        db=db,
        content_type=ContentType.TV.value,
        genre_ids=genre_ids,
        language_code=language,
        year=year,
        sort_by=effective_sort,
        page=page,
        limit=effective_limit,
        max_items=max_items,
    )
    return ContentPaginationResponse[ContentSummaryDTO](
        page=page,
        limit=effective_limit,
        page_size=effective_limit,
        total=total,
        total_results=total,
        total_pages=total_pages,
        results=results,
    )


@router.post("/sync")
async def sync_web_series(
    payload: WebSeriesSyncRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ingest/synchronize a TV show from TMDB into the unified database."""
    content_record = await catalog.sync_tv(db, payload.tv_id)

    return {
        "status": "success",
        "message": f"Web series '{content_record.title}' synced successfully",
        "web_series": {
            "id": content_record.id,
            "tmdb_id": content_record.tmdb_id,
            "content_type": content_record.content_type,
            "title": content_record.title,
            "release_date": content_record.release_date,
            "number_of_seasons": content_record.number_of_seasons,
            "number_of_episodes": content_record.number_of_episodes,
        },
    }


@router.get("/trending")
async def trending_web_series(time_window: str = "week"):
    """Get trending TV shows from TMDB (normalized to one grid page)."""
    data = await tmdb.trending_tv(time_window=time_window)
    return tmdb.normalize_page(data, page_size=CONTENT_PAGE_SIZE, raise_if_empty=True)


@router.get("/top-10")
async def top_10_web_series():
    """Get the top 10 web series (from TMDB top-rated), for the landing rail."""
    data = await tmdb.top_rated_tv(page=1)
    return tmdb.normalize_page(data, page_size=10, raise_if_empty=True)


@router.get("/popular")
async def popular_web_series(page: int = Query(default=1, ge=1)):
    """Get popular TV shows from TMDB (normalized to one grid page)."""
    data = await tmdb.popular_tv(page=page)
    return tmdb.normalize_page(data, page_size=CONTENT_PAGE_SIZE, raise_if_empty=True)


@router.get("/top-rated")
async def top_rated_web_series(page: int = Query(default=1, ge=1)):
    """Get top-rated TV shows from TMDB (normalized to one grid page)."""
    data = await tmdb.top_rated_tv(page=page)
    return tmdb.normalize_page(data, page_size=CONTENT_PAGE_SIZE, raise_if_empty=True)


@router.get("/latest")
async def latest_web_series(page: int = Query(default=1, ge=1)):
    """Get latest / on-the-air ('new') TV shows from TMDB (one grid page)."""
    data = await tmdb.latest_tv(page=page)
    return tmdb.normalize_page(data, page_size=CONTENT_PAGE_SIZE, raise_if_empty=True)


@router.get("/search")
async def search_web_series(query: str = Query(..., min_length=1), page: int = Query(default=1, ge=1)):
    """Search TV shows via TMDB (normalized to one grid page).

    An empty result set is a valid search outcome and is returned as an empty
    page rather than an error.
    """
    data = await tmdb.search_tv(query=query, page=page)
    return tmdb.normalize_page(data, page_size=CONTENT_PAGE_SIZE, raise_if_empty=False)


@router.get("/{tv_id}")
async def web_series_details(tv_id: int, db: Session = Depends(get_db)):
    """Get TV show details (with IMDb / external ratings) from local DB or TMDB."""
    local = await catalog.get_details_with_ratings(db, ContentType.TV.value, tv_id)
    if local is not None:
        return local

    data = await tmdb.tv_details(tv_id)
    # TV payloads don't carry imdb_id inline; resolve it via external_ids safely.
    try:
        external = await tmdb.tv_external_ids(tv_id)
        imdb_id = external.get("imdb_id") if isinstance(external, dict) else None
        if imdb_id:
            ratings = await catalog.omdb.ratings_by_imdb_id(imdb_id)
            if ratings:
                data = {**data, **ratings}
    except Exception:
        pass
    return data


@router.get("/{tv_id}/similar")
async def similar_web_series(tv_id: int):
    """Get similar TV shows from TMDB."""
    return await tmdb.similar_tv(tv_id)


@router.get("/{tv_id}/watch-providers")
async def web_series_watch_providers(
    tv_id: int,
    region: str = Query(default="IN", min_length=2, max_length=2),
):
    """Where-to-watch streaming offers for a series in a region (TMDB/JustWatch).

    Availability is exactly what TMDB reports for the region; an unavailable
    title yields empty provider arrays rather than fabricated data.
    """
    data = await tmdb.tv_watch_providers(tv_id)
    return tmdb.extract_region_providers(data, region)


@router.get("/{tv_id}/images")
async def web_series_images(tv_id: int):
    """Image gallery (backdrops + posters) for a series from TMDB."""
    data = await tmdb.tv_images(tv_id)
    backdrops = data.get("backdrops") if isinstance(data, dict) else None
    posters = data.get("posters") if isinstance(data, dict) else None
    return {
        "backdrops": (backdrops or [])[:20],
        "posters": (posters or [])[:20],
    }


@router.get("/{tv_id}/tmdb-reviews")
async def web_series_tmdb_reviews(tv_id: int, page: int = Query(default=1, ge=1)):
    """Community reviews for a series sourced from TMDB.

    These are distinct from WatchMan's own user reviews and are labeled as such
    in the UI.
    """
    data = await tmdb.tv_reviews(tv_id, page=page)
    return tmdb.normalize_reviews(data)
