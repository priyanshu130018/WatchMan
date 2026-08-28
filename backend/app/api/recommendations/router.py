from fastapi import APIRouter, Query

from app.api.recommendations.service import RecommendationService

router = APIRouter(
    prefix="/recommendations",
    tags=["Recommendations"],
)

service = RecommendationService()


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