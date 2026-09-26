import logging
from math import ceil
from typing import Any
from uuid import UUID
from sqlalchemy.orm import Session

from app.core.redis import cache
from app.core.telemetry import telemetry
from app.models.content import Content
from app.models.recommendation import Recommendation
from app.ml.recommendations.generator import RecommendationGenerator
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.services.tmdb.service import TMDBService
from app.services.catalog import ContentCatalogService

logger = logging.getLogger(__name__)


class UnifiedRecommendationService:
    """
    Unified recommendation service with Redis caching, PostgreSQL persistence, and graceful fallback.
    """

    CACHE_TTL = 3600  # 1 hour

    def __init__(self) -> None:
        self.tmdb = TMDBService()
        self.catalog = ContentCatalogService(self.tmdb)

    @classmethod
    def _format_content_item(
        cls,
        content: Content,
        score: float = 0.0,
        rank: int = 0,
        explanation: str | None = None,
        sources: list[str] | None = None,
    ) -> dict[str, Any]:
        genre_names = [
            g.genre.name
            if hasattr(g, "genre") and hasattr(g.genre, "name")
            else (g.get("name") if isinstance(g, dict) else str(g))
            for g in (content.genres or [])
        ]
        return {
            "id": content.id,
            "content_id": content.id,
            "tmdb_id": content.tmdb_id,
            "title": content.title,
            "overview": content.overview,
            "content_type": content.content_type,
            "release_date": content.release_date,
            "poster_path": content.poster_path,
            "backdrop_path": content.backdrop_path,
            "vote_average": content.vote_average,
            "vote_count": content.vote_count,
            "popularity": content.popularity,
            "genres": genre_names,
            "runtime": content.runtime,
            "tagline": content.tagline,
            "score": round(score, 4),
            "recommendation_score": round(score, 4),
            "rank": rank,
            "explanation": explanation or "Recommended for you",
            "reason": explanation or "Recommended for you",
            "sources": sources or ["hybrid_ranking"],
        }

    async def get_personalized_recommendations(
        self,
        db: Session,
        user_id: UUID,
        limit: int = 20,
        page: int = 1,
        content_type: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """
        Retrieves ranked recommendations for a user.
        Uses Redis cache -> PostgreSQL recommendations table -> on-the-fly generation -> cold-start fallback.
        """
        cache_key = f"recommendations:user:{user_id}:type:{content_type or 'all'}:v:1.0.0"

        # 1. Check Redis cache unless force_refresh
        if not force_refresh:
            cached_data = await cache.get(cache_key)
            if cached_data and isinstance(cached_data, list) and len(cached_data) > 0:
                all_items = cached_data
                total = len(all_items)
                start_idx = (page - 1) * limit
                end_idx = start_idx + limit
                paginated_items = all_items[start_idx:end_idx]
                return {
                    "items": paginated_items,
                    "total": total,
                    "page": page,
                    "page_size": limit,
                    "total_pages": max(1, ceil(total / limit)),
                }

        # 2. Query persisted recommendations from DB
        db_query = (
            db.query(Recommendation, Content)
            .join(Content, Recommendation.content_id == Content.id)
            .filter(Recommendation.user_id == user_id)
        )
        if content_type and content_type.lower() in ("movie", "tv"):
            db_query = db_query.filter(Content.content_type == content_type.lower())

        persisted_records = db_query.order_by(Recommendation.rank.asc()).all()

        all_ranked_items: list[dict[str, Any]] = []

        if persisted_records and not force_refresh:
            for rec, content in persisted_records:
                all_ranked_items.append(
                    self._format_content_item(
                        content=content,
                        score=rec.score,
                        rank=rec.rank,
                        explanation=rec.explanation,
                    )
                )
        else:
            # 3. Generate on-the-fly via RecommendationGenerator
            generated = RecommendationGenerator.generate_and_persist_for_user(
                db=db,
                user_id=user_id,
                limit=max(limit * 2, 50),
                content_type=content_type,
            )
            for r in generated:
                all_ranked_items.append(r.to_dict())

        # 4. Cold-start fallback if still empty (catalog items matching preferences or highest popularity)
        if not all_ranked_items:
            fallback_query = db.query(Content)
            if content_type and content_type.lower() in ("movie", "tv"):
                fallback_query = fallback_query.filter(Content.content_type == content_type.lower())

            fallback_items = fallback_query.order_by(Content.popularity.desc().nullslast()).limit(limit * 2).all()
            for idx, item in enumerate(fallback_items, start=1):
                all_ranked_items.append(
                    self._format_content_item(
                        content=item,
                        score=0.8 - (idx * 0.01),
                        rank=idx,
                        explanation="Popular in the catalog with high audience interest",
                        sources=["cold_start_popularity"],
                    )
                )

        # 5. Store in Redis cache
        if all_ranked_items:
            await cache.set(cache_key, all_ranked_items, ttl=self.CACHE_TTL)

        # Record recommendation pipeline execution metrics
        is_cold_start = any("cold_start" in (item.get("sources") or []) for item in all_ranked_items)
        telemetry.record_recommendation_run(duration_ms=0.0, success=True, is_cold_start=is_cold_start)

        # Paginate results
        total = len(all_ranked_items)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_items = all_ranked_items[start_idx:end_idx]

        return {
            "items": paginated_items,
            "total": total,
            "page": page,
            "page_size": limit,
            "total_pages": max(1, ceil(total / limit)),
        }

    async def get_similar_content(
        self,
        db: Session,
        content_type: str,
        tmdb_id: int,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Retrieves items similar to a given content item using dense embeddings.
        """
        content = (
            db.query(Content)
            .filter(Content.content_type == content_type.lower(), Content.tmdb_id == tmdb_id)
            .first()
        )

        if not content:
            # Sync or fetch from TMDB
            try:
                if content_type.lower() == "movie":
                    content = await self.catalog.ensure_movie(db, tmdb_id)
                elif content_type.lower() == "tv":
                    content = await self.catalog.ensure_tv(db, tmdb_id)
            except Exception as exc:  # noqa: BLE001 - fall back to direct TMDB below
                logger.warning(
                    "Failed to sync %s tmdb_id=%s for similarity; will fall back to TMDB: %s",
                    content_type,
                    tmdb_id,
                    exc,
                )

        if not content:
            # Fallback to direct TMDB similar
            try:
                if content_type.lower() == "movie":
                    res = await self.tmdb.similar_movies(tmdb_id)
                else:
                    res = await self.tmdb.similar_tv(tmdb_id)
                return res.get("results", [])[:limit]
            except Exception as exc:  # noqa: BLE001 - similarity is best-effort
                logger.warning(
                    "TMDB similar fallback failed for %s tmdb_id=%s: %s",
                    content_type,
                    tmdb_id,
                    exc,
                )
                return []

        # Use vector search
        similar_items = ContentEmbeddingService.search_similar_content(
            db=db,
            content_id=content.id,
            limit=limit,
            content_type=content_type,
        )

        output = []
        for item_data in similar_items:
            c: Content = item_data["content"]
            output.append(
                self._format_content_item(
                    content=c,
                    score=item_data["similarity"],
                    rank=len(output) + 1,
                    explanation=f"Similar themes and creative elements to {content.title}",
                    sources=["embedding_cosine_similarity"],
                )
            )

        return output

    async def invalidate_user_cache(self, user_id: UUID) -> None:
        """
        Invalidates cached recommendation lists for a user across all content types.
        """
        await cache.delete_pattern(f"recommendations:user:{user_id}:*")

    # Backward compatibility methods for legacy API
    async def personalized(self, db: Session, user_id: UUID, limit: int = 20):
        rec_data = await self.get_personalized_recommendations(
            db=db, user_id=user_id, limit=limit, content_type=None
        )
        return rec_data.get("items", [])

    async def trending(self):
        return await self.tmdb.trending_movies()

    async def popular(self):
        return await self.tmdb.popular_movies()

    async def top_rated(self):
        return await self.tmdb.top_rated_movies()

    async def similar(self, movie_id: int):
        return await self.tmdb.similar_movies(movie_id)

    async def recommend_from_movie(self, movie_id: int):
        return await self.tmdb.recommendations(movie_id)

    async def search(self, query: str, page: int = 1):
        return await self.tmdb.search_movies(query=query, page=page)
