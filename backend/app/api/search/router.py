"""FastAPI router for unified and multi-type search across Movies and Web Series."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.constants import CONTENT_PAGE_SIZE
from app.models.content import ContentType
from app.schemas.content import (
    ContentPaginationResponse,
    ContentSummaryDTO,
)
from app.services.catalog import ContentCatalogService
from app.services.tmdb.service import TMDBService

router = APIRouter(prefix="/search", tags=["Search"])

tmdb = TMDBService()
catalog = ContentCatalogService(tmdb)


@router.get("", response_model=ContentPaginationResponse[ContentSummaryDTO])
@router.get("/", response_model=ContentPaginationResponse[ContentSummaryDTO])
async def search_unified(
    q: str | None = Query(default=None),
    query: str | None = Query(default=None),
    type: str = Query(default="all", pattern="^(all|movie|tv)$"),
    content_type: str | None = Query(default=None, pattern="^(all|movie|tv)$", description="Alias for type"),
    genre: int | None = Query(default=None),
    genre_id: int | None = Query(default=None, description="Alias for genre"),
    language: str | None = Query(default=None),
    year: int | None = Query(default=None),
    sort: str = Query(default="popularity_desc"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=CONTENT_PAGE_SIZE, ge=1, le=100),
    page_size: int | None = Query(default=None, ge=1, le=100, description="Alias for limit"),
    db: Session = Depends(get_db),
):
    """Unified search endpoint for movies and web series with filtering, pagination, and TMDB fallback.
    
    Returns 200 OK with empty results if search query is blank and no filters applied.
    """
    effective_limit = page_size if page_size is not None else limit
    effective_genre = genre_id if genre_id is not None else genre
    effective_type = content_type if content_type is not None else type

    search_query = (q or query or "").strip()
    has_filters = effective_type != "all" or effective_genre is not None or language is not None or year is not None
    has_sort = sort != "popularity_desc"

    if not search_query and not has_filters and not has_sort:
        return ContentPaginationResponse[ContentSummaryDTO](
            page=page,
            limit=effective_limit,
            page_size=effective_limit,
            total=0,
            total_results=0,
            total_pages=0,
            results=[],
        )

    resolved_content_type = None
    if effective_type == "movie":
        resolved_content_type = ContentType.MOVIE.value
    elif effective_type == "tv":
        resolved_content_type = ContentType.TV.value

    genre_ids = [effective_genre] if effective_genre else None

    # Browse the local catalog when filters are used without a title query;
    # otherwise search titles and overviews as before.
    if search_query:
        results, total, total_pages = catalog.search_content(
            db=db,
            query_str=search_query,
            content_type=resolved_content_type,
            genre_ids=genre_ids,
            language_code=language,
            year=year,
            sort_by=sort,
            page=page,
            limit=effective_limit,
        )
    else:
        results, total, total_pages = catalog.list_content(
            db=db,
            content_type=resolved_content_type,
            genre_ids=genre_ids,
            language_code=language,
            year=year,
            sort_by=sort,
            page=page,
            limit=effective_limit,
        )

    if total > 0:
        return ContentPaginationResponse[ContentSummaryDTO](
            page=page,
            limit=effective_limit,
            page_size=effective_limit,
            total=total,
            total_results=total,
            total_pages=total_pages,
            results=results,
        )

    # Fallback to TMDB external search if local catalog yields 0 matches
    try:
        if type == "movie":
            tmdb_resp = await tmdb.search_movies(query=search_query, page=page)
        elif type == "tv":
            tmdb_resp = await tmdb.search_tv(query=search_query, page=page)
        else:
            tmdb_resp = await tmdb.search_multi(query=search_query, page=page)

        raw_results = tmdb_resp.get("results") or []
        fallback_results: list[ContentSummaryDTO] = []

        for item in raw_results:
            media_type = item.get("media_type") or type
            if media_type not in ("movie", "tv"):
                continue

            is_tv = media_type == "tv"
            title = (
                item.get("name")
                if is_tv
                else item.get("title") or item.get("original_title") or "Unknown"
            )
            original_title = (
                item.get("original_name") if is_tv else item.get("original_title")
            )
            release_date = (
                item.get("first_air_date") if is_tv else item.get("release_date")
            )

            fallback_results.append(
                ContentSummaryDTO(
                    id=int(item["id"]),
                    tmdb_id=int(item["id"]),
                    content_type=media_type,
                    title=title,
                    original_title=original_title,
                    overview=item.get("overview"),
                    release_date=release_date,
                    poster_path=item.get("poster_path"),
                    backdrop_path=item.get("backdrop_path"),
                    vote_average=float(item.get("vote_average") or 0.0),
                    vote_count=int(item.get("vote_count") or 0),
                    popularity=float(item.get("popularity") or 0.0),
                    runtime=None,
                    number_of_seasons=None,
                    number_of_episodes=None,
                    genres=[],
                )
            )

        tmdb_total = int(tmdb_resp.get("total_results") or len(fallback_results))
        tmdb_pages = int(tmdb_resp.get("total_pages") or 1)

        return ContentPaginationResponse[ContentSummaryDTO](
            page=page,
            limit=effective_limit,
            page_size=effective_limit,
            total=tmdb_total,
            total_results=tmdb_total,
            total_pages=tmdb_pages,
            results=fallback_results[:effective_limit],
        )
    except Exception:
        # If external TMDB fails during fallback, return empty result set gracefully
        return ContentPaginationResponse[ContentSummaryDTO](
            page=page,
            limit=effective_limit,
            page_size=effective_limit,
            total=0,
            total_results=0,
            total_pages=0,
            results=[],
        )


@router.get("/movies")
async def search_movies(
    query: str = Query(default=""),
    page: int = Query(default=1, ge=1),
):
    """Backward-compatible endpoint for movie search."""
    if not query.strip():
        return {"page": page, "results": [], "total_pages": 0, "total_results": 0}
    return await tmdb.search_movies(query=query, page=page)


@router.get("/tv")
@router.get("/web-series")
async def search_web_series(
    query: str = Query(default=""),
    page: int = Query(default=1, ge=1),
):
    """Backward-compatible endpoint for web series search."""
    if not query.strip():
        return {"page": page, "results": [], "total_pages": 0, "total_results": 0}
    return await tmdb.search_tv(query=query, page=page)