from fastapi import APIRouter

from app.services.tmdb.service import TMDBService

router = APIRouter(prefix="/movies", tags=["Movies"])

tmdb = TMDBService()


@router.get("/trending")
async def trending():
    return await tmdb.trending_movies()


@router.get("/popular")
async def popular():
    return await tmdb.popular_movies()


@router.get("/top-rated")
async def top_rated():
    return await tmdb.top_rated_movies()


@router.get("/latest")
async def latest():
    return await tmdb.latest_movies()


@router.get("/search")
async def search(query: str):
    return await tmdb.search_movies(query)


@router.get("/{movie_id}")
async def details(movie_id: int):
    return await tmdb.movie_details(movie_id)