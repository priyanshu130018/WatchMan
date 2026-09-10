from fastapi import APIRouter, Query
from app.services.tmdb.service import TMDBService

router = APIRouter(prefix="/search", tags=["Search"])
tmdb = TMDBService()


@router.get("/movies")
async def search_movies(query: str = Query(..., min_length=1)):
    return await tmdb.search_movies(query)