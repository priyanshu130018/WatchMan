"""Local movie-catalog synchronization used by interaction endpoints."""

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database.models.movie import Movie
from app.services.tmdb.service import TMDBService


class MovieCatalogService:
    """Persist the TMDB records needed by favorites, ratings, and recommendations."""

    def __init__(self, tmdb: TMDBService | None = None) -> None:
        self.tmdb = tmdb or TMDBService()

    async def ensure_movie(self, db: Session, movie_id: int) -> Movie:
        movie = db.get(Movie, movie_id)
        if movie is not None:
            return movie
        return await self.sync_movie(db, movie_id)

    async def sync_movie(self, db: Session, movie_id: int) -> Movie:
        details = await self.tmdb.movie_details(movie_id)
        if not isinstance(details, dict) or not details.get("id"):
            raise HTTPException(status_code=502, detail="TMDB returned an invalid movie payload")

        credits = await self._optional_request(self.tmdb.movie_credits, movie_id)
        keywords = await self._optional_request(self.tmdb.movie_keywords, movie_id)

        movie_data = self._movie_data(details, credits, keywords)
        movie = db.get(Movie, movie_id)
        if movie is None:
            movie = Movie(**movie_data)
            db.add(movie)
        else:
            for key, value in movie_data.items():
                setattr(movie, key, value)

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(movie)
        return movie

    @staticmethod
    async def _optional_request(request: Any, movie_id: int) -> dict[str, Any]:
        try:
            result = await request(movie_id)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _movie_data(
        details: dict[str, Any], credits: dict[str, Any], keywords: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "id": int(details["id"]),
            "tmdb_id": int(details["id"]),
            "title": details.get("title") or details.get("original_title") or "Unknown",
            "overview": details.get("overview"),
            "release_date": details.get("release_date"),
            "poster_path": details.get("poster_path"),
            "backdrop_path": details.get("backdrop_path"),
            "vote_average": float(details.get("vote_average") or 0.0),
            "vote_count": int(details.get("vote_count") or 0),
            "popularity": float(details.get("popularity") or 0.0),
            "genres": details.get("genres") or [],
            "runtime": details.get("runtime"),
            "status": details.get("status"),
            "tagline": details.get("tagline"),
            "keywords": keywords.get("keywords") or [],
            "cast": (credits.get("cast") or [])[:20],
            "crew": (credits.get("crew") or [])[:20],
        }
