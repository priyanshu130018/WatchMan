"""FastAPI router for trending movies and web series."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.constants import TRENDING_ITEMS
from app.services.tmdb.service import TMDBService

router = APIRouter(prefix="/trending", tags=["Trending"])

tmdb = TMDBService()


@router.get("")
@router.get("/")
async def get_trending_all(time_window: str = Query(default="week", pattern="^(day|week)$")):
    """Get trending content (movies & web series combined) for the time window.

    This is a single, fixed-size showcase — NOT a paginated list. The upstream
    ``trending/all`` feed can include people; those are filtered out so exactly
    the top ``TRENDING_ITEMS`` movies/series (in TMDB's own trending order) are
    returned on one page. There is deliberately no ``page`` parameter.
    """
    data = await tmdb.trending_all(time_window=time_window)
    raw = data.get("results") if isinstance(data, dict) else None
    filtered = [
        item
        for item in (raw or [])
        if isinstance(item, dict) and item.get("media_type") in ("movie", "tv")
    ][:TRENDING_ITEMS]
    return {
        "page": 1,
        "page_size": TRENDING_ITEMS,
        "total_pages": 1,
        "total_results": len(filtered),
        "results": filtered,
    }


@router.get("/{content_type}/{tmdb_id}")
async def get_trending_content_details(content_type: str, tmdb_id: int):
    """Get details for a specific trending content item by content_type and tmdb_id."""
    return await tmdb.content_details(content_type, tmdb_id)
