from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.recommendations.service import RecommendationService
from app.core.security import get_current_user
from app.models.user import User
from app.db.session import get_db

router = APIRouter(
    prefix="/recommendations",
    tags=["Recommendations"],
)

service = RecommendationService()


@router.get("")
@router.get("/")
async def get_recommendations(
    limit: int = Query(default=20, ge=1, le=50),
    page: int = Query(default=1, ge=1),
    content_type: Literal["all", "movie", "tv"] | None = Query(default=None),
    force_refresh: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get personalized hybrid recommendations for the authenticated user.
    Supports filtering by content_type ('all', 'movie', 'tv') and pagination.
    """
    type_filter = None if content_type == "all" else content_type
    return await service.get_personalized_recommendations(
        db=db,
        user_id=current_user.id,
        limit=limit,
        page=page,
        content_type=type_filter,
        force_refresh=force_refresh,
    )


@router.post("/refresh")
async def refresh_recommendations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Invalidates cached recommendations and triggers on-demand recomputation.
    """
    await service.invalidate_user_cache(current_user.id)
    rec_data = await service.get_personalized_recommendations(
        db=db,
        user_id=current_user.id,
        limit=20,
        page=1,
        force_refresh=True,
    )
    return {"status": "success", "message": "Recommendations refreshed", "data": rec_data}


@router.get("/personalized")
async def personalized(
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Live hybrid recommendations from content, peer activity, and popularity."""
    return {"results": await service.personalized(db, current_user.id, limit)}


@router.get("/trending")
async def trending():
    return await service.trending()


@router.get("/popular")
async def popular():
    return await service.popular()


@router.get("/top-rated")
async def top_rated():
    return await service.top_rated()


@router.get("/similar/{movie_id}")
async def similar(movie_id: int):
    return await service.similar(movie_id)




@router.get("/{content_type}/{tmdb_id}")
async def similar_content(
    content_type: Literal["movie", "tv"],
    tmdb_id: int,
    limit: int = Query(default=10, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """
    Get similar content for a movie or TV show using dense vector embeddings.
    """
    results = await service.get_similar_content(
        db=db,
        content_type=content_type,
        tmdb_id=tmdb_id,
        limit=limit,
    )
    return {"results": results}


@router.get("/search")
async def search(
    query: str = Query(..., min_length=1),
    page: int = 1,
):
    return await service.search(query, page)
