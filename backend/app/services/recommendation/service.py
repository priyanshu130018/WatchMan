import logging
import time
from datetime import datetime
from math import ceil
from typing import Any
from uuid import UUID
from sqlalchemy.orm import Session, selectinload
from app.models.taxonomy import ContentGenre

from app.core.redis import cache
from app.core.telemetry import telemetry
from app.core.timing import start_timing_ctx, get_current_timing_ctx
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
        from app.services.watchman_service import WatchmanService
        wm_score, wm_label = WatchmanService.compute_card_score(content)

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
            "watchman_score": wm_score,
            "watchman_label": wm_label,
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
        ctx = get_current_timing_ctx()
        is_root_ctx = False
        if ctx is None:
            ctx = start_timing_ctx("/api/recommendations")
            is_root_ctx = True

        try:
            is_cold_user = not self.user_has_activity(db, user_id)
            cache_key = f"recommendations:user:{user_id}:type:{content_type or 'all'}:v:1.0.0"

            # 1. Check Redis cache unless force_refresh
            if not force_refresh:
                cached_data = await cache.get(cache_key)
                if cached_data and isinstance(cached_data, list) and len(cached_data) > 0:
                    t_ser = time.perf_counter()
                    all_items = cached_data
                    total = len(all_items)
                    start_idx = (page - 1) * limit
                    end_idx = start_idx + limit
                    paginated_items = all_items[start_idx:end_idx]
                    res = {
                        "items": paginated_items,
                        "total": total,
                        "page": page,
                        "page_size": limit,
                        "total_pages": max(1, ceil(total / limit)),
                        "is_cold_start": is_cold_user,
                    }
                    ctx.serialization_ms += (time.perf_counter() - t_ser) * 1000
                    return res

            # 2. Query persisted recommendations from DB
            db_query = (
                db.query(Recommendation, Content)
                .join(Content, Recommendation.content_id == Content.id)
                .options(selectinload(Content.genres).joinedload(ContentGenre.genre))
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
                            sources=["persisted_hybrid"],
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
                all_ranked_items = [r.to_dict() if hasattr(r, "to_dict") else r for r in generated]

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
            is_cold_start = is_cold_user or any("cold_start" in (item.get("sources") or []) for item in all_ranked_items)
            telemetry.record_recommendation_run(duration_ms=0.0, success=True, is_cold_start=is_cold_start)

            # Paginate results
            t_ser = time.perf_counter()
            total = len(all_ranked_items)
            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            paginated_items = all_ranked_items[start_idx:end_idx]

            res = {
                "items": paginated_items,
                "total": total,
                "page": page,
                "page_size": limit,
                "total_pages": max(1, ceil(total / limit)),
                "is_cold_start": is_cold_start,
            }
            ctx.serialization_ms += (time.perf_counter() - t_ser) * 1000
            return res
        finally:
            if is_root_ctx:
                ctx.log_recommendations()

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

        if not output:
            try:
                if content_type.lower() == "movie":
                    res = await self.tmdb.similar_movies(tmdb_id)
                else:
                    res = await self.tmdb.similar_tv(tmdb_id)
                return res.get("results", [])[:limit]
            except Exception as exc:
                logger.warning("TMDB similar fallback failed: %s", exc)

        return output

    @staticmethod
    def _normalize_progress_percent(raw_progress: float | None) -> float:
        if raw_progress is None:
            return 0.0
        val = float(raw_progress)
        if 0.0 < val <= 1.0:
            return round(val * 100.0, 1)
        return round(min(100.0, max(0.0, val)), 1)

    def user_has_activity(self, db: Session, user_id: UUID) -> bool:
        """Determine if the user has any genuine interaction history (not cold start)."""
        from app.models.interaction import SavedContent, WatchHistory, InteractionEvent
        from app.models.review import Rating
        from app.models.watchman import WatchmanDecision

        if db.query(WatchHistory.id).filter(WatchHistory.user_id == user_id).first() is not None:
            return True
        if db.query(Rating.id).filter(Rating.user_id == user_id).first() is not None:
            return True
        if db.query(SavedContent.id).filter(SavedContent.user_id == user_id).first() is not None:
            return True
        if db.query(WatchmanDecision.id).filter(WatchmanDecision.user_id == user_id).first() is not None:
            return True
        if (
            db.query(InteractionEvent.id)
            .filter(
                InteractionEvent.user_id == user_id,
                InteractionEvent.content_id.isnot(None),
                InteractionEvent.event_type.in_(["save", "rate", "watch", "watchman_decision"]),
            )
            .first()
            is not None
        ):
            return True
        return False

    async def get_continue_watching(
        self,
        db: Session,
        user_id: UUID,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """
        Shelf: Continue Watching.
        Returns items where playback progress > 5% and < 90% and completed is False.
        Always reads fresh from DB.
        """
        from app.models.interaction import WatchHistory

        rows = (
            db.query(WatchHistory, Content)
            .join(Content, WatchHistory.content_id == Content.id)
            .options(selectinload(Content.genres).joinedload(ContentGenre.genre))
            .filter(
                WatchHistory.user_id == user_id,
                WatchHistory.completed.is_(False),
            )
            .order_by(WatchHistory.watched_at.desc())
            .all()
        )

        items: list[dict[str, Any]] = []
        for history, content in rows:
            pct = self._normalize_progress_percent(history.progress)
            if 5.0 <= pct < 90.0 and not history.completed:
                formatted = self._format_content_item(
                    content=content,
                    score=round(pct / 100.0, 4),
                    rank=len(items) + 1,
                    explanation=f"{int(pct)}% watched",
                    sources=["playback_progress"],
                )
                formatted["progress"] = pct
                formatted["progress_percent"] = pct
                formatted["completed"] = False
                formatted["watched_at"] = history.watched_at.isoformat() if history.watched_at else None
                if content.runtime:
                    formatted["duration_seconds"] = content.runtime * 60
                    formatted["progress_seconds"] = int((content.runtime * 60) * (pct / 100.0))
                items.append(formatted)
                if len(items) >= limit:
                    break

        return items

    async def get_watched_liked(
        self,
        db: Session,
        user_id: UUID,
        limit: int = 12,
        exclude_content_ids: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Shelf: You Already Watched & Liked.
        Show content the user has actually watched AND expressed positive feedback toward.
        Must NOT show content that the user has not actually watched.
        Must NOT count merely saving or opening details page as liked.
        """
        from app.models.interaction import WatchHistory
        from app.models.review import Rating
        from app.models.watchman import WatchmanDecision

        exclude_ids = set(exclude_content_ids or set())

        # 1. Gather all watched content for user
        watched_rows = (
            db.query(WatchHistory, Content)
            .join(Content, WatchHistory.content_id == Content.id)
            .options(selectinload(Content.genres).joinedload(ContentGenre.genre))
            .filter(WatchHistory.user_id == user_id)
            .order_by(WatchHistory.watched_at.desc())
            .all()
        )

        if not watched_rows:
            return []

        # 2. Gather user's ratings and watchman decisions
        ratings = {
            r.content_id: r
            for r in db.query(Rating).filter(Rating.user_id == user_id).all()
        }
        decisions = {
            d.content_id: d
            for d in db.query(WatchmanDecision).filter(WatchmanDecision.user_id == user_id).all()
        }

        candidates_scored: list[tuple[float, Content, str, datetime]] = []

        for history, content in watched_rows:
            cid = content.id
            if cid in exclude_ids:
                continue

            pct = self._normalize_progress_percent(history.progress)
            # Meaningful watch check: completed or substantial progress (>= 50%)
            is_meaningfully_watched = history.completed or pct >= 50.0
            if not is_meaningfully_watched:
                continue

            # Check for negative feedback: explicit skip or bad rating (< 5.5) -> disqualify
            dec = decisions.get(cid)
            rat = ratings.get(cid)
            if dec and dec.decision == "skip":
                continue
            if rat and rat.rating is not None and rat.rating < 5.5:
                continue

            # Evaluate positive signals
            has_positive_signal = False
            score_boost = 0.0
            explanation = "Watched and completed"

            if dec and dec.decision == "must_watch":
                has_positive_signal = True
                score_boost += 3.0
                explanation = "You marked this Must Watch"
            elif rat and rat.rating is not None and rat.rating >= 7.0:
                has_positive_signal = True
                score_boost += 2.0 + (rat.rating / 10.0)
                explanation = f"You rated this {rat.rating:g}/10"
            elif history.completed or pct >= 90.0:
                has_positive_signal = True
                score_boost += 1.0
                explanation = "You watched and completed this"

            if has_positive_signal:
                recency_timestamp = history.watched_at or datetime.min
                candidates_scored.append((score_boost, content, explanation, recency_timestamp))

        # Sort by score boost descending, then recency descending
        candidates_scored.sort(key=lambda x: (x[0], x[3]), reverse=True)

        results: list[dict[str, Any]] = []
        for rank_idx, (boost, content, expl, _) in enumerate(candidates_scored[:limit], start=1):
            item = self._format_content_item(
                content=content,
                score=round(min(1.0, 0.7 + boost * 0.1), 4),
                rank=rank_idx,
                explanation=expl,
                sources=["watched_and_liked"],
            )
            results.append(item)

        return results

    async def get_must_like(
        self,
        db: Session,
        user_id: UUID,
        limit: int = 12,
        exclude_content_ids: set[int] | None = None,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Shelf: You Must Like.
        Uses the existing recommendation architecture (UnifiedRecommendationService ->
        RecommendationGenerator -> CandidatePipeline -> HybridRanker).
        Returns the highest-confidence predictions for the user.
        Excludes:
        - items in higher-priority shelves (exclude_content_ids)
        - already watched content
        - content the user explicitly skipped
        If user is cold start or results are only generic cold_start_popularity fallback, returns [].
        """
        from app.models.interaction import WatchHistory
        from app.models.watchman import WatchmanDecision

        # Cold start verification: if user has no genuine activity, return empty
        if not self.user_has_activity(db, user_id):
            return []

        # Exclusions
        exclude_ids = set(exclude_content_ids or set())

        # Exclude already watched
        for w in db.query(WatchHistory.content_id).filter(WatchHistory.user_id == user_id).all():
            exclude_ids.add(w[0])

        # Exclude skipped
        for d in db.query(WatchmanDecision.content_id).filter(
            WatchmanDecision.user_id == user_id, WatchmanDecision.decision == "skip"
        ).all():
            exclude_ids.add(d[0])

        # Request recommendations from existing pipeline
        rec_data = await self.get_personalized_recommendations(
            db=db,
            user_id=user_id,
            limit=max(limit * 3, 30),
            force_refresh=force_refresh,
        )
        raw_items = rec_data.get("items", [])

        # If engine returned only cold-start popularity fallback, reject it for "You Must Like"
        is_cold_start = any(
            any("cold_start" in src for src in (it.get("sources") or []))
            for it in raw_items
        )
        if is_cold_start:
            return []

        filtered: list[dict[str, Any]] = []
        seen_ids: set[int] = set()

        for item in raw_items:
            cid = item.get("id") or item.get("content_id")
            if not cid or cid in exclude_ids or cid in seen_ids:
                continue
            seen_ids.add(cid)
            expl = item.get("explanation")
            if not expl or expl == "Recommended for you":
                item["explanation"] = "Picked from your taste and activity"
                item["reason"] = "Picked from your taste and activity"
            filtered.append(item)
            if len(filtered) >= limit:
                break

        return filtered

    async def get_homepage_sections(
        self,
        db: Session,
        user_id: UUID,
        limit: int = 12,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """
        Unified homepage personalized sections endpoint.
        Priority for deduplication:
        1. Continue Watching
        2. You Already Watched & Liked
        3. You Must Like
        Display structure:
        1. You Must Like
        2. You Already Watched & Liked
        3. Continue Watching
        """
        if not self.user_has_activity(db, user_id):
            return {
                "has_personalization": False,
                "sections": [],
            }

        # Priority 1: Continue Watching
        continue_watching = await self.get_continue_watching(db, user_id, limit=limit)
        cw_ids = {it["id"] for it in continue_watching if "id" in it}

        # Priority 2: You Already Watched & Liked (deduped from Continue Watching)
        watched_liked = await self.get_watched_liked(
            db, user_id, limit=limit, exclude_content_ids=cw_ids
        )
        wl_ids = {it["id"] for it in watched_liked if "id" in it}

        # Priority 3: You Must Like (deduped from CW + WL)
        must_like = await self.get_must_like(
            db, user_id, limit=limit, exclude_content_ids=cw_ids.union(wl_ids), force_refresh=force_refresh
        )

        sections = []
        if must_like:
            sections.append({
                "key": "must_like",
                "title": "You Must Like",
                "subtitle": "Picked from your taste and activity",
                "items": must_like,
            })
        if watched_liked:
            sections.append({
                "key": "watched_liked",
                "title": "You Already Watched & Liked",
                "subtitle": "Titles you completed and enjoyed",
                "items": watched_liked,
            })
        if continue_watching:
            sections.append({
                "key": "continue_watching",
                "title": "Continue Watching",
                "subtitle": "Pick up where you left off",
                "items": continue_watching,
            })

        return {
            "has_personalization": len(sections) > 0,
            "sections": sections,
        }

    async def invalidate_user_cache(self, user_id: UUID) -> None:
        """
        Invalidates cached recommendation lists for a user across all content types.
        """
        await cache.delete_pattern(f"recommendations:user:{user_id}:*")
        await cache.delete_pattern(f"recommendations:home:*:user:{user_id}*")

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
