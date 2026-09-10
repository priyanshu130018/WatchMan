from fastapi import APIRouter, Depends, Query

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models.user import User
from app.core.security import get_current_user
from app.services.catalog import MovieCatalogService
from app.services.tmdb.service import TMDBService

router = APIRouter(prefix="/movies", tags=["Movies"])

tmdb = TMDBService()
catalog = MovieCatalogService(tmdb)


class MovieSyncRequest(BaseModel):
    movie_id: int


@router.post("/sync")
async def sync_movie(
    payload: MovieSyncRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    movie_record = await catalog.sync_movie(db, payload.movie_id)

    return {
        "status": "success",
        "message": f"Movie '{movie_record.title}' synced successfully",
        "movie": {
            "id": movie_record.id,
            "tmdb_id": movie_record.tmdb_id,
            "title": movie_record.title,
            "release_date": movie_record.release_date
        }
    }


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


from app.ml.embeddings.service import MovieEmbeddingService


@router.get("/{movie_id}")
async def details(movie_id: int):
    return await tmdb.movie_details(movie_id)


@router.get("/{movie_id}/similar")
async def get_similar_movies(
    movie_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    try:
        results = MovieEmbeddingService.search_similar_movies(
            db=db,
            movie_id=movie_id,
            limit=limit
        )
        return {
            "movie_id": movie_id,
            "results": results
        }
    except Exception:
        # Browsed TMDB titles are not necessarily stored locally or embedded yet.
        # Keep the detail page live by falling back to TMDB while the catalog warms.
        return await tmdb.similar_movies(movie_id)

