import httpx
from fastapi import HTTPException
from app.core.config import settings


class TMDBService:
    BASE_URL = "https://api.themoviedb.org/3"

    def __init__(self):
        self.api_key = settings.TMDB_API_KEY

    async def _request(self, endpoint: str, params=None):
        params = params or {}
        params["api_key"] = self.api_key.strip() if self.api_key else ""

        endpoints_to_try = [
            f"{self.BASE_URL}/{endpoint}",
            f"https://api.tmdb.org/3/{endpoint}",
        ]

        last_error = None
        for url in endpoints_to_try:
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.get(url, params=params)
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=response.text,
                    )
                return response.json()
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                last_error = e
                continue

        if last_error:
            raise HTTPException(
                status_code=503,
                detail=f"TMDB connection error: {last_error}"
            )


    async def trending_movies(self):
        return await self._request("trending/movie/week")

    async def popular_movies(self):
        return await self._request("movie/popular")

    async def top_rated_movies(self):
        return await self._request("movie/top_rated")

    async def latest_movies(self):
        return await self._request("movie/now_playing")

    async def movie_details(self, movie_id: int):
        return await self._request(f"movie/{movie_id}")

    async def search_movies(self, query: str):
        return await self._request(
            "search/movie",
            {"query": query},
        )

    async def recommendations(self, movie_id: int):
        return await self._request(
            f"movie/{movie_id}/recommendations"
        )

    async def similar_movies(self, movie_id: int):
        return await self._request(
            f"movie/{movie_id}/similar"
        )

    async def movie_credits(self, movie_id: int):
        return await self._request(
            f"movie/{movie_id}/credits"
        )

    async def movie_keywords(self, movie_id: int):
        return await self._request(
            f"movie/{movie_id}/keywords"
        )