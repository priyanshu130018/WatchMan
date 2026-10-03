"""Client for the OMDb API, used to enrich content with external ratings.

TMDB only exposes its own ``vote_average``. To surface IMDb, Rotten Tomatoes,
and Metacritic ratings (per the product spec), we look the title up on OMDb by
its IMDb ID (obtained from TMDB ``external_ids``) and normalize the response.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.redis import cache

logger = logging.getLogger(__name__)


class OMDBService:
    """Fetch and normalize external ratings from OMDb by IMDb ID."""

    def __init__(self, redis_cache=None) -> None:
        self.api_key = settings.OMDB_API_KEY
        self.base_url = settings.OMDB_BASE_URL.rstrip("/")
        self.cache = redis_cache or cache

    async def ratings_by_imdb_id(self, imdb_id: str) -> dict[str, Any]:
        """Return normalized ratings for an IMDb ID.

        Best-effort: on any failure or missing data returns an empty dict so
        callers can degrade gracefully to TMDB-only ratings. Shape:
        ``{"imdb_rating": str|None, "imdb_votes": str|None, "ratings": [{"source", "value"}]}``
        """
        if not imdb_id or not imdb_id.strip():
            return {}

        imdb_id = imdb_id.strip()
        cache_key = f"omdb:ratings:{imdb_id}"

        cached = await self.cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

        params = {"i": imdb_id, "apikey": self.api_key, "tomatoes": "true"}

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(self.base_url, params=params)
            if response.status_code != 200:
                logger.warning(
                    "OMDb request for imdb_id=%s returned HTTP %s",
                    imdb_id,
                    response.status_code,
                )
                return {}
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:  # network or JSON error
            logger.warning("OMDb lookup failed for imdb_id=%s: %s", imdb_id, exc)
            return {}

        if not isinstance(data, dict) or data.get("Response") == "False":
            await self.cache.set(cache_key, {}, ttl=3600)
            return {}

        normalized = self._normalize(data)
        await self.cache.set(cache_key, normalized, ttl=86400)
        return normalized

    @staticmethod
    def _normalize(data: dict[str, Any]) -> dict[str, Any]:
        imdb_rating = data.get("imdbRating")
        imdb_votes = data.get("imdbVotes")
        # Treat OMDb's "N/A" sentinel as missing.
        if imdb_rating in (None, "", "N/A"):
            imdb_rating = None
        if imdb_votes in (None, "", "N/A"):
            imdb_votes = None

        ratings: list[dict[str, str]] = []
        for entry in data.get("Ratings") or []:
            source = entry.get("Source")
            value = entry.get("Value")
            if source and value and value != "N/A":
                ratings.append({"source": source, "value": value})

        return {
            "imdb_rating": imdb_rating,
            "imdb_votes": imdb_votes,
            "ratings": ratings,
        }
