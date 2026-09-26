"""FastAPI router for trending movies and web series."""

from __future__ import annotations

from fastapi import APIRouter, Query
from app.services.tmdb.service import TMDBService

router = APIRouter(prefix="/trending", tags=["Trending"])

tmdb = TMDBService()


@router.get("")
@router.get("/")
async def get_trending_all(time_window: str = Query(default="week", pattern="^(day|week)$")):
    """Get all trending content (movies & TV series) for the specified time window."""
    return await tmdb.trending_all(time_window=time_window)


@router.get("/{content_type}/{tmdb_id}")
async def get_trending_content_details(content_type: str, tmdb_id: int):
    """Get details for a specific trending content item by content_type and tmdb_id."""
    return await tmdb.content_details(content_type, tmdb_id)
