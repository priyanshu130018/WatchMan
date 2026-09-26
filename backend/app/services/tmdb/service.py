"""Client for TMDB REST API supporting Movies, TV Shows, and unified multi-type operations with caching."""

from __future__ import annotations

import json
import logging
from typing import Any
import httpx

from app.core.config import settings
from app.core.exceptions import (
    MovieNotFoundException,
    TVShowNotFoundException,
    ContentNotFoundException,
    NoResultsFoundException,
    TMDBAuthenticationException,
    TMDBException,
    TMDBInvalidResponseException,
    TMDBRateLimitedException,
    TMDBTimeoutException,
    TMDBUnavailableException,
)
from app.core.redis import cache
from app.core.telemetry import telemetry

logger = logging.getLogger(__name__)

# A descriptive User-Agent and JSON Accept header. Some CDN/WAF layers in front
# of TMDB reset connections that present the default client UA; sending an explicit
# UA avoids that class of intermittent resets without touching TLS behavior.
_TMDB_USER_AGENT = "WatchMan/1.0 (+https://www.themoviedb.org; httpx)"

# Per-request timeout budget. Connect is kept shorter than the overall read budget
# so a flaky/reset TCP+TLS path fails fast and is retried rather than hanging.
_TMDB_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# httpx retries transient connection-establishment failures (ConnectError /
# connection reset during TCP+TLS setup) by re-establishing the connection. This
# is the smallest robust fix for the observed intermittent
# "ConnectionResetError: [Errno 104]" during TLS: instead of surfacing the first
# reset as a 503, the client transparently reconnects (mirroring what curl's
# connection racing achieves). TLS verification is left fully enabled.
_TMDB_TRANSPORT_RETRIES = 3


def _build_tmdb_client() -> httpx.AsyncClient:
    """Construct a hardened httpx client for outbound TMDB calls.

    A fresh client is used per request so no keep-alive connection is reused
    across calls (a silently-dropped pooled connection is itself a common source
    of "connection reset by peer"). Certificate verification uses httpx's default
    certifi CA bundle and is never disabled. ``trust_env`` stays on so an
    environment-provided proxy (HTTPS_PROXY) is honored without hardcoding one.
    """
    return httpx.AsyncClient(
        timeout=_TMDB_TIMEOUT,
        transport=httpx.AsyncHTTPTransport(retries=_TMDB_TRANSPORT_RETRIES),
        follow_redirects=True,
        trust_env=True,
        headers={"User-Agent": _TMDB_USER_AGENT, "Accept": "application/json"},
    )


class TMDBService:
    """Client for TMDB REST API supporting Movies, TV Shows, and trending content with non-blocking cache."""

    def __init__(self, redis_cache=None) -> None:
        self.api_key = settings.TMDB_API_KEY
        self.base_url = settings.TMDB_BASE_URL.rstrip("/")
        self.cache = redis_cache or cache

    # -------------------------------------------------------------------------
    # Response normalization helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def normalize_page(
        data: dict[str, Any],
        page_size: int = 16,
        raise_if_empty: bool = False,
    ) -> dict[str, Any]:
        """Cap a TMDB list payload to ``page_size`` items (4x4 = 16 by default).

        Raises ``NoResultsFoundException`` when ``raise_if_empty`` is set and the
        upstream returned no results, so empty feeds surface as a proper error
        instead of a silent empty list.
        """
        results = data.get("results") if isinstance(data, dict) else None
        if not results:
            if raise_if_empty:
                raise NoResultsFoundException()
            results = []
        capped = results[:page_size]
        return {
            "page": data.get("page", 1),
            "page_size": page_size,
            "total_pages": data.get("total_pages"),
            "total_results": data.get("total_results", len(results)),
            "results": capped,
        }


    async def _request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        use_cache: bool = True,
        ttl: int = 3600,
    ) -> dict[str, Any]:
        params = dict(params) if params else {}
        params["api_key"] = self.api_key

        clean_endpoint = endpoint.lstrip("/")
        cache_key = f"tmdb:{clean_endpoint}:{sorted(params.items())}" if use_cache else None

        if use_cache and cache_key:
            cached_data = await self.cache.get(cache_key)
            if cached_data is not None and isinstance(cached_data, dict):
                telemetry.record_tmdb_call(cache_hit=True)
                return cached_data

        telemetry.record_tmdb_call(cache_hit=False)
        url = f"{self.base_url}/{clean_endpoint}"

        try:
            async with _build_tmdb_client() as client:
                response = await client.get(url, params=params)

            if response.status_code == 404:
                if clean_endpoint.startswith("tv/") or "search/tv" in clean_endpoint:
                    parts = clean_endpoint.split("/")
                    item_id = parts[1] if len(parts) > 1 else "requested"
                    raise TVShowNotFoundException(
                        f"Web series with ID {item_id} was not found on TMDB."
                    )
                elif clean_endpoint.startswith("movie/") or "search/movie" in clean_endpoint:
                    parts = clean_endpoint.split("/")
                    item_id = parts[1] if len(parts) > 1 else "requested"
                    raise MovieNotFoundException(
                        f"Movie with ID {item_id} was not found on TMDB."
                    )
                raise ContentNotFoundException("Requested resource was not found on TMDB.")

            if response.status_code in (401, 403):
                raise TMDBAuthenticationException(
                    "Failed to authenticate with TMDB API. Please verify TMDB API key configuration."
                )

            if response.status_code == 429:
                raise TMDBRateLimitedException(
                    "TMDB API rate limit exceeded. Please retry shortly."
                )

            if response.status_code >= 500:
                raise TMDBUnavailableException(
                    f"TMDB service is temporarily unavailable (HTTP {response.status_code})."
                )

            if response.status_code != 200:
                raise TMDBException(
                    message=f"TMDB request failed with status code {response.status_code}.",
                    status_code=502,
                )

            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                raise TMDBInvalidResponseException(
                    "TMDB returned an invalid or unparseable JSON payload."
                ) from e

            if use_cache and cache_key and isinstance(data, dict):
                await self.cache.set(cache_key, data, ttl=ttl)

            return data

        except (httpx.TimeoutException, TimeoutError) as e:
            raise TMDBTimeoutException(
                "Timed out while waiting for TMDB API response."
            ) from e
        except (httpx.ConnectError, httpx.NetworkError) as e:
            raise TMDBUnavailableException(
                "Unable to establish connection to TMDB service."
            ) from e

    # -------------------------------------------------------------------------
    # Movies API
    # -------------------------------------------------------------------------

    async def trending_movies(self, time_window: str = "week") -> dict[str, Any]:
        return await self._request(f"trending/movie/{time_window}", ttl=900)

    async def popular_movies(self, page: int = 1) -> dict[str, Any]:
        return await self._request("movie/popular", {"page": page}, ttl=900)

    async def top_rated_movies(self, page: int = 1) -> dict[str, Any]:
        return await self._request("movie/top_rated", {"page": page}, ttl=900)

    async def latest_movies(self, page: int = 1) -> dict[str, Any]:
        return await self._request("movie/now_playing", {"page": page}, ttl=900)

    async def movie_details(self, movie_id: int) -> dict[str, Any]:
        return await self._request(f"movie/{movie_id}", ttl=3600)

    async def search_movies(self, query: str, page: int = 1) -> dict[str, Any]:
        return await self._request(
            "search/movie",
            {"query": query, "page": page},
            ttl=300,
        )

    async def recommendations(self, movie_id: int, page: int = 1) -> dict[str, Any]:
        return await self._request(f"movie/{movie_id}/recommendations", {"page": page}, ttl=1800)

    async def similar_movies(self, movie_id: int, page: int = 1) -> dict[str, Any]:
        return await self._request(f"movie/{movie_id}/similar", {"page": page}, ttl=1800)

    async def movie_credits(self, movie_id: int) -> dict[str, Any]:
        return await self._request(f"movie/{movie_id}/credits", ttl=3600)

    async def movie_keywords(self, movie_id: int) -> dict[str, Any]:
        return await self._request(f"movie/{movie_id}/keywords", ttl=3600)

    async def movie_videos(self, movie_id: int) -> dict[str, Any]:
        return await self._request(f"movie/{movie_id}/videos", ttl=3600)

    async def movie_external_ids(self, movie_id: int) -> dict[str, Any]:
        return await self._request(f"movie/{movie_id}/external_ids", ttl=3600)

    # -------------------------------------------------------------------------
    # TV Shows / Web Series API
    # -------------------------------------------------------------------------

    async def trending_tv(self, time_window: str = "week") -> dict[str, Any]:
        return await self._request(f"trending/tv/{time_window}", ttl=900)

    async def popular_tv(self, page: int = 1) -> dict[str, Any]:
        return await self._request("tv/popular", {"page": page}, ttl=900)

    async def top_rated_tv(self, page: int = 1) -> dict[str, Any]:
        return await self._request("tv/top_rated", {"page": page}, ttl=900)

    async def latest_tv(self, page: int = 1) -> dict[str, Any]:
        return await self._request("tv/on_the_air", {"page": page}, ttl=900)

    async def tv_details(self, tv_id: int) -> dict[str, Any]:
        return await self._request(f"tv/{tv_id}", ttl=3600)

    async def search_tv(self, query: str, page: int = 1) -> dict[str, Any]:
        return await self._request(
            "search/tv",
            {"query": query, "page": page},
            ttl=300,
        )

    async def similar_tv(self, tv_id: int, page: int = 1) -> dict[str, Any]:
        return await self._request(f"tv/{tv_id}/similar", {"page": page}, ttl=1800)

    async def tv_credits(self, tv_id: int) -> dict[str, Any]:
        return await self._request(f"tv/{tv_id}/credits", ttl=3600)

    async def tv_keywords(self, tv_id: int) -> dict[str, Any]:
        return await self._request(f"tv/{tv_id}/keywords", ttl=3600)

    async def tv_videos(self, tv_id: int) -> dict[str, Any]:
        return await self._request(f"tv/{tv_id}/videos", ttl=3600)

    async def tv_external_ids(self, tv_id: int) -> dict[str, Any]:
        return await self._request(f"tv/{tv_id}/external_ids", ttl=3600)

    # -------------------------------------------------------------------------
    # Unified / Polymorphic Content API
    # -------------------------------------------------------------------------

    async def trending_all(self, time_window: str = "week") -> dict[str, Any]:
        return await self._request(f"trending/all/{time_window}", ttl=900)

    async def search_multi(self, query: str, page: int = 1) -> dict[str, Any]:
        return await self._request(
            "search/multi",
            {"query": query, "page": page},
            ttl=300,
        )

    async def content_details(self, content_type: str, tmdb_id: int) -> dict[str, Any]:
        if content_type == "tv":
            return await self.tv_details(tmdb_id)
        return await self.movie_details(tmdb_id)

    async def content_credits(self, content_type: str, tmdb_id: int) -> dict[str, Any]:
        if content_type == "tv":
            return await self.tv_credits(tmdb_id)
        return await self.movie_credits(tmdb_id)

    async def content_keywords(self, content_type: str, tmdb_id: int) -> dict[str, Any]:
        if content_type == "tv":
            return await self.tv_keywords(tmdb_id)
        return await self.movie_keywords(tmdb_id)

    async def content_videos(self, content_type: str, tmdb_id: int) -> dict[str, Any]:
        if content_type == "tv":
            return await self.tv_videos(tmdb_id)
        return await self.movie_videos(tmdb_id)

    async def content_external_ids(self, content_type: str, tmdb_id: int) -> dict[str, Any]:
        if content_type == "tv":
            return await self.tv_external_ids(tmdb_id)
        return await self.movie_external_ids(tmdb_id)

    # -------------------------------------------------------------------------
    # Watch Providers / OTT (region-aware) — TMDB "watch/providers" is powered
    # by JustWatch. Availability is reported per ISO-3166-1 region and is only
    # ever what TMDB returns for that region (never fabricated / assumed).
    # -------------------------------------------------------------------------

    @staticmethod
    def extract_region_providers(data: dict[str, Any], region: str) -> dict[str, Any]:
        """Reduce a TMDB watch/providers payload to a single region's offers.

        Returns the JustWatch attribution ``link`` plus provider arrays split by
        monetization type. A region with no data yields empty arrays — a valid
        "not available here" outcome, never a fabricated one.
        """
        region_code = (region or "").upper()
        results = data.get("results") if isinstance(data, dict) else None
        region_block = results.get(region_code) if isinstance(results, dict) else None
        empty = {
            "region": region_code,
            "link": None,
            "flatrate": [],
            "rent": [],
            "buy": [],
            "free": [],
            "ads": [],
        }
        if not isinstance(region_block, dict):
            return empty

        def _providers(key: str) -> list[dict[str, Any]]:
            return [
                {
                    "provider_id": p.get("provider_id"),
                    "provider_name": p.get("provider_name"),
                    "logo_path": p.get("logo_path"),
                    "display_priority": p.get("display_priority"),
                }
                for p in (region_block.get(key) or [])
                if isinstance(p, dict)
            ]

        return {
            "region": region_code,
            "link": region_block.get("link"),
            "flatrate": _providers("flatrate"),
            "rent": _providers("rent"),
            "buy": _providers("buy"),
            "free": _providers("free"),
            "ads": _providers("ads"),
        }

    async def movie_watch_providers(self, movie_id: int) -> dict[str, Any]:
        return await self._request(f"movie/{movie_id}/watch/providers", ttl=21600)

    async def tv_watch_providers(self, tv_id: int) -> dict[str, Any]:
        return await self._request(f"tv/{tv_id}/watch/providers", ttl=21600)

    async def content_watch_providers(self, content_type: str, tmdb_id: int) -> dict[str, Any]:
        if content_type == "tv":
            return await self.tv_watch_providers(tmdb_id)
        return await self.movie_watch_providers(tmdb_id)

    async def watch_providers_list(self, content_type: str, watch_region: str) -> dict[str, Any]:
        media = "tv" if content_type == "tv" else "movie"
        return await self._request(
            f"watch/providers/{media}",
            {"watch_region": watch_region},
            ttl=86400,
        )

    async def watch_provider_regions(self) -> dict[str, Any]:
        """List the ISO-3166-1 regions TMDB has watch-provider data for."""
        return await self._request("watch/providers/regions", ttl=86400)

    async def discover_by_provider(
        self,
        content_type: str,
        provider_id: int,
        watch_region: str,
        page: int = 1,
        sort_by: str = "popularity.desc",
    ) -> dict[str, Any]:
        media = "tv" if content_type == "tv" else "movie"
        return await self._request(
            f"discover/{media}",
            {
                "with_watch_providers": provider_id,
                "watch_region": watch_region,
                "with_watch_monetization_types": "flatrate|free|ads|rent|buy",
                "sort_by": sort_by,
                "page": page,
            },
            ttl=1800,
        )

    # -------------------------------------------------------------------------
    # Detail enrichment: image galleries + TMDB (community) reviews
    # -------------------------------------------------------------------------

    async def movie_images(self, movie_id: int) -> dict[str, Any]:
        return await self._request(f"movie/{movie_id}/images", ttl=86400)

    async def tv_images(self, tv_id: int) -> dict[str, Any]:
        return await self._request(f"tv/{tv_id}/images", ttl=86400)

    async def content_images(self, content_type: str, tmdb_id: int) -> dict[str, Any]:
        if content_type == "tv":
            return await self.tv_images(tmdb_id)
        return await self.movie_images(tmdb_id)

    async def movie_reviews(self, movie_id: int, page: int = 1) -> dict[str, Any]:
        return await self._request(f"movie/{movie_id}/reviews", {"page": page}, ttl=3600)

    async def tv_reviews(self, tv_id: int, page: int = 1) -> dict[str, Any]:
        return await self._request(f"tv/{tv_id}/reviews", {"page": page}, ttl=3600)

    async def content_reviews(
        self, content_type: str, tmdb_id: int, page: int = 1
    ) -> dict[str, Any]:
        if content_type == "tv":
            return await self.tv_reviews(tmdb_id, page)
        return await self.movie_reviews(tmdb_id, page)

    @staticmethod
    def normalize_reviews(data: dict[str, Any]) -> dict[str, Any]:
        """Flatten a TMDB reviews payload into a stable, minimal shape.

        These are TMDB community reviews and must be surfaced separately from
        WatchMan's own user reviews — the frontend labels them accordingly.
        """
        results = data.get("results") if isinstance(data, dict) else None
        reviews = []
        for r in results or []:
            if not isinstance(r, dict):
                continue
            details = r.get("author_details") or {}
            reviews.append(
                {
                    "id": r.get("id"),
                    "author": r.get("author") or details.get("username"),
                    "rating": details.get("rating"),
                    "avatar_path": details.get("avatar_path"),
                    "content": r.get("content"),
                    "created_at": r.get("created_at"),
                    "url": r.get("url"),
                }
            )
        return {
            "page": data.get("page", 1) if isinstance(data, dict) else 1,
            "total_pages": data.get("total_pages", 1) if isinstance(data, dict) else 1,
            "total_results": (
                data.get("total_results", len(reviews)) if isinstance(data, dict) else len(reviews)
            ),
            "results": reviews,
        }