from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.recommendations.service import RecommendationService
from app.core.security import get_current_user
from app.database.models.user import User
from app.database.session import get_db

router = APIRouter(
    prefix="/recommendations",
    tags=["Recommendations"],
)

service = RecommendationService()


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


@router.get("/movie/{movie_id}")
async def recommend_from_movie(movie_id: int):
    return await service.recommend_from_movie(movie_id)


@router.get("/search")
async def search(
    query: str = Query(..., min_length=1),
    page: int = 1,
):
    return await service.search(query, page)
