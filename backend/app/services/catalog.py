"""Unified Content catalog synchronization, searching, and filtering service."""

from __future__ import annotations

import logging
import time
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.constants import CONTENT_PAGE_SIZE
from app.core.exceptions import DatabaseException, TMDBInvalidResponseException, ContentNotFoundException
from app.core.timing import get_current_timing_ctx
from app.models.content import Content, ContentType
from app.repositories.content_repository import ContentRepository
from app.schemas.content import (
    ContentSummaryDTO,
    ContentDetailResponse,
    GenreDTO,
    LanguageDTO,
    CastMemberDTO,
    CrewMemberDTO,
    ExternalIdDTO,
    RatingDTO,
    VideoDTO,
)
from app.services.tmdb.service import TMDBService
from app.services.omdb.service import OMDBService
from app.services.watchman_service import WatchmanService

logger = logging.getLogger(__name__)


class ContentCatalogService:
    """Persist normalized TMDB movie and TV records into unified Content domain and manage catalog queries."""

    def __init__(self, tmdb: TMDBService | None = None, omdb: OMDBService | None = None) -> None:
        self.tmdb = tmdb or TMDBService()
        self.omdb = omdb or OMDBService()

    async def ensure_content(
        self, db: Session, content_type: str, tmdb_id: int
    ) -> Content:
        """Fetch content from local database or ingest from TMDB on-demand."""
        content = ContentRepository.get_by_tmdb_id(db, content_type, tmdb_id)
        if content is not None:
            return content
        return await self.sync_content(db, content_type, tmdb_id)

    async def ensure_movie(self, db: Session, movie_id: int) -> Content:
        """Backward-compatibility helper for movie-specific calls."""
        return await self.ensure_content(db, ContentType.MOVIE.value, movie_id)

    async def ensure_tv(self, db: Session, tv_id: int) -> Content:
        """Helper for TV-specific calls."""
        return await self.ensure_content(db, ContentType.TV.value, tv_id)

    async def sync_movie(self, db: Session, movie_id: int) -> Content:
        """Backward-compatibility helper for movie sync."""
        return await self.sync_content(db, ContentType.MOVIE.value, movie_id)

    async def sync_tv(self, db: Session, tv_id: int) -> Content:
        """Helper for TV sync."""
        return await self.sync_content(db, ContentType.TV.value, tv_id)

    async def sync_content(
        self, db: Session, content_type: str, tmdb_id: int
    ) -> Content:
        """Synchronize complete content graph from TMDB into PostgreSQL."""
        details = await self.tmdb.content_details(content_type, tmdb_id)
        if not isinstance(details, dict) or not details.get("id"):
            raise TMDBInvalidResponseException(
                f"TMDB returned an invalid {content_type} payload for ID {tmdb_id}"
            )

        credits = await self._optional_request(self.tmdb.content_credits, content_type, tmdb_id)
        videos_resp = await self._optional_request(self.tmdb.content_videos, content_type, tmdb_id)
        external_resp = await self._optional_request(self.tmdb.content_external_ids, content_type, tmdb_id)

        # Normalize content record
        content_dict = self._normalize_content_data(details, content_type)
        genres = details.get("genres") or []
        languages = details.get("spoken_languages") or []
        cast = credits.get("cast") or []
        crew = credits.get("crew") or []
        videos = videos_resp.get("results") or []
        external_ids = self._normalize_external_ids(external_resp)

        try:
            content = ContentRepository.upsert_content(
                db=db,
                content_dict=content_dict,
                genres=genres,
                languages=languages,
                cast=cast,
                crew=crew,
                external_ids=external_ids,
                videos=videos,
            )
            db.commit()
            db.refresh(content)
            return content
        except SQLAlchemyError as e:
            db.rollback()
            raise DatabaseException(
                f"Failed to persist synced {content_type} into catalog."
            ) from e

    def list_content(
        self,
        db: Session,
        content_type: str | None = None,
        genre_ids: list[int] | None = None,
        language_code: str | None = None,
        year: int | None = None,
        sort_by: str = "popularity_desc",
        page: int = 1,
        limit: int = CONTENT_PAGE_SIZE,
        max_items: int | None = None,
    ) -> tuple[list[ContentSummaryDTO], int, int]:
        """List content from database with pagination and filters.

        ``limit`` is the page size (used for the OFFSET/LIMIT window and to
        compute ``total_pages``). ``max_items`` optionally caps the collection to
        a finite size (e.g. the top-100 "popular" set), so ``total`` and
        ``total_pages`` reflect the cap rather than the full catalogue.
        """
        skip = (page - 1) * limit
        items, total = ContentRepository.list(
            db=db,
            content_type=content_type,
            genre_ids=genre_ids,
            language_code=language_code,
            year=year,
            sort_by=sort_by,
            skip=skip,
            limit=limit,
            max_items=max_items,
        )
        total_pages = (total + limit - 1) // limit if limit > 0 else 0
        dtos = [self.content_to_summary_dto(item) for item in items]
        return dtos, total, total_pages

    def search_content(
        self,
        db: Session,
        query_str: str,
        content_type: str | None = None,
        genre_ids: list[int] | None = None,
        language_code: str | None = None,
        year: int | None = None,
        sort_by: str = "popularity_desc",
        page: int = 1,
        limit: int = CONTENT_PAGE_SIZE,
    ) -> tuple[list[ContentSummaryDTO], int, int]:
        """Search content in database with filters and pagination."""
        if not query_str or not query_str.strip():
            return [], 0, 0

        skip = (page - 1) * limit
        items, total = ContentRepository.search(
            db=db,
            query_str=query_str,
            content_type=content_type,
            genre_ids=genre_ids,
            language_code=language_code,
            year=year,
            sort_by=sort_by,
            skip=skip,
            limit=limit,
        )
        total_pages = (total + limit - 1) // limit if limit > 0 else 0
        dtos = [self.content_to_summary_dto(item) for item in items]
        return dtos, total, total_pages

    def get_local_or_external_details(
        self, db: Session, content_type: str, tmdb_id: int
    ) -> ContentDetailResponse | None:
        """Fetch complete detail representation from local DB if available."""
        content = ContentRepository.get_by_tmdb_id(db, content_type, tmdb_id)
        if content is None:
            return None
        return self.content_to_detail_dto(content)

    async def get_details_with_ratings(
        self, db: Session, content_type: str, tmdb_id: int
    ) -> ContentDetailResponse | None:
        """Return local detail representation enriched with OMDb ratings.

        Returns ``None`` when the item is not stored locally, so the caller can
        fall back to a direct TMDB lookup.
        """
        detail = self.get_local_or_external_details(db, content_type, tmdb_id)
        if detail is None:
            return None
        await self.enrich_detail_with_ratings(detail)
        return detail

    async def enrich_detail_with_ratings(
        self, detail: ContentDetailResponse
    ) -> ContentDetailResponse:
        """Populate ``imdb_rating``/``imdb_votes``/``ratings`` from OMDb, in place.

        Best-effort: a missing IMDb ID or OMDb failure leaves the detail with
        its TMDB-only ``vote_average`` and empty ratings list.
        """
        imdb_id = next(
            (
                ext.external_id
                for ext in (detail.external_ids or [])
                if ext.provider == "imdb" and ext.external_id
            ),
            None,
        )
        if not imdb_id:
            return detail

        t0 = time.perf_counter()
        ratings = await self.omdb.ratings_by_imdb_id(imdb_id)
        ctx = get_current_timing_ctx()
        if ctx:
            ctx.omdb_ms += (time.perf_counter() - t0) * 1000
        if ratings:
            detail.imdb_rating = ratings.get("imdb_rating")
            detail.imdb_votes = ratings.get("imdb_votes")
            detail.ratings = [
                RatingDTO(source=r["source"], value=r["value"])
                for r in ratings.get("ratings", [])
            ]
        return detail

    @classmethod
    def content_to_summary_dto(cls, item: Content) -> ContentSummaryDTO:
        """Convert Content ORM entity to ContentSummaryDTO."""
        genres_dto = []
        if getattr(item, "genres", None):
            for cg in item.genres:
                if cg.genre:
                    genres_dto.append(GenreDTO(id=cg.genre.tmdb_id, name=cg.genre.name))

        score, label = WatchmanService.compute_card_score(item)
        return ContentSummaryDTO(
            id=item.id,
            tmdb_id=item.tmdb_id,
            content_type=item.content_type,
            title=item.title,
            original_title=item.original_title,
            overview=item.overview,
            release_date=item.release_date,
            poster_path=item.poster_path,
            backdrop_path=item.backdrop_path,
            vote_average=item.vote_average,
            vote_count=item.vote_count,
            popularity=item.popularity,
            runtime=item.runtime,
            number_of_seasons=item.number_of_seasons,
            number_of_episodes=item.number_of_episodes,
            genres=genres_dto,
            watchman_score=score,
            watchman_label=label,
        )

    @classmethod
    def content_to_detail_dto(cls, item: Content) -> ContentDetailResponse:
        """Convert Content ORM entity to ContentDetailResponse."""
        genres_dto = [
            GenreDTO(id=cg.genre.tmdb_id, name=cg.genre.name)
            for cg in (item.genres or [])
            if cg.genre
        ]
        languages_dto = [
            LanguageDTO(
                code=cl.language.code,
                name=cl.language.name,
                english_name=cl.language.english_name,
            )
            for cl in (item.languages or [])
            if cl.language
        ]
        cast_dto = [
            CastMemberDTO(
                id=c.person.tmdb_id if c.person else c.person_id,
                name=c.person.name if c.person else "Unknown",
                original_name=c.person.original_name if c.person else None,
                character=c.character,
                profile_path=c.person.profile_path if c.person else None,
                order=c.cast_order,
            )
            for c in (item.cast or [])
        ]
        crew_dto = [
            CrewMemberDTO(
                id=cr.person.tmdb_id if cr.person else cr.person_id,
                name=cr.person.name if cr.person else "Unknown",
                original_name=cr.person.original_name if cr.person else None,
                department=cr.department,
                job=cr.job,
                profile_path=cr.person.profile_path if cr.person else None,
            )
            for cr in (item.crew or [])
        ]
        external_dto = [
            ExternalIdDTO(provider=ext.provider, external_id=ext.external_id)
            for ext in (item.external_ids or [])
        ]
        videos_dto = [
            VideoDTO(
                id=v.id,
                key=v.key,
                site=v.site,
                name=v.name,
                type=v.type,
                official=v.official,
            )
            for v in (item.videos or [])
        ]

        score, label = WatchmanService.compute_card_score(item)
        return ContentDetailResponse(
            id=item.id,
            tmdb_id=item.tmdb_id,
            content_type=item.content_type,
            title=item.title,
            original_title=item.original_title,
            overview=item.overview,
            release_date=item.release_date,
            poster_path=item.poster_path,
            backdrop_path=item.backdrop_path,
            original_language=item.original_language,
            popularity=item.popularity,
            vote_average=item.vote_average,
            vote_count=item.vote_count,
            adult=item.adult,
            runtime=item.runtime,
            status=item.status,
            tagline=item.tagline,
            homepage=item.homepage,
            number_of_seasons=item.number_of_seasons,
            number_of_episodes=item.number_of_episodes,
            genres=genres_dto,
            languages=languages_dto,
            cast=cast_dto,
            crew=crew_dto,
            external_ids=external_dto,
            videos=videos_dto,
            watchman_score=score,
            watchman_label=label,
        )

    @staticmethod
    async def _optional_request(request: Any, *args: Any) -> dict[str, Any]:
        try:
            result = await request(*args)
            return result if isinstance(result, dict) else {}
        except Exception as exc:  # noqa: BLE001 - supplementary data is best-effort
            logger.warning(
                "Optional TMDB request %s(%s) failed; continuing without it: %s",
                getattr(request, "__name__", request),
                args,
                exc,
            )
            return {}

    @staticmethod
    def _normalize_content_data(
        details: dict[str, Any], content_type: str
    ) -> dict[str, Any]:
        """Normalize TMDB payload differences between movies and TV shows."""
        tmdb_id = int(details["id"])
        is_tv = content_type == ContentType.TV.value

        title = (
            details.get("name")
            if is_tv
            else details.get("title") or details.get("original_title") or "Unknown"
        )
        original_title = (
            details.get("original_name") if is_tv else details.get("original_title")
        )
        release_date = (
            details.get("first_air_date") if is_tv else details.get("release_date")
        )

        runtime = None
        if is_tv:
            episode_runtimes = details.get("episode_run_time") or []
            runtime = episode_runtimes[0] if episode_runtimes else None
        else:
            runtime = details.get("runtime")

        return {
            "content_type": content_type,
            "tmdb_id": tmdb_id,
            "title": title or "Unknown",
            "original_title": original_title,
            "overview": details.get("overview"),
            "release_date": release_date,
            "poster_path": details.get("poster_path"),
            "backdrop_path": details.get("backdrop_path"),
            "original_language": details.get("original_language"),
            "popularity": float(details.get("popularity") or 0.0),
            "vote_average": float(details.get("vote_average") or 0.0),
            "vote_count": int(details.get("vote_count") or 0),
            "adult": bool(details.get("adult", False)),
            "runtime": runtime,
            "status": details.get("status"),
            "tagline": details.get("tagline"),
            "homepage": details.get("homepage"),
            "number_of_seasons": details.get("number_of_seasons") if is_tv else None,
            "number_of_episodes": details.get("number_of_episodes") if is_tv else None,
        }

    @staticmethod
    def _normalize_external_ids(external_resp: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize external ID providers into relational rows."""
        providers = [
            ("imdb", "imdb_id"),
            ("freebase_mid", "freebase_mid"),
            ("freebase_id", "freebase_id"),
            ("tvdb", "tvdb_id"),
            ("tvrage", "tvrage_id"),
            ("wikidata", "wikidata_id"),
            ("facebook", "facebook_id"),
            ("instagram", "instagram_id"),
            ("twitter", "twitter_id"),
        ]
        results = []
        for prov_name, key in providers:
            val = external_resp.get(key)
            if val:
                results.append({"provider": prov_name, "external_id": str(val)})
        return results


# Backward compatibility alias
MovieCatalogService = ContentCatalogService
