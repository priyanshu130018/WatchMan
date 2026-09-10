from app.services.tmdb.service import TMDBService
from app.services.catalog import MovieCatalogService
from app.services.recommendation.hybrid import HybridRecommendationService
from app.database.models.favorite import Favorite
from app.database.models.movie import Movie
from app.database.models.watch_history import WatchHistory


class RecommendationService:

    def __init__(self):
        self.tmdb = TMDBService()
        self.catalog = MovieCatalogService(self.tmdb)
        self.hybrid = HybridRecommendationService()

    async def personalized(self, db, user_id, limit: int = 20):
        """Warm a small local candidate set, then rank it with hybrid signals."""
        results = self.hybrid.recommend(db, user_id, limit)
        # After the local catalog has been warmed, returning the available
        # unseen results avoids calling TMDB again on every client refresh.
        if len(results) >= limit or db.query(Movie).count() >= max(limit * 2, 20):
            return results

        seed_ids = [
            favorite.movie_id
            for favorite in (
                db.query(Favorite)
                .filter(Favorite.user_id == user_id)
                .order_by(Favorite.created_at.desc())
                .limit(2)
                .all()
            )
        ]
        seed_ids.extend(
            history.movie_id
            for history in (
                db.query(WatchHistory)
                .filter(WatchHistory.user_id == user_id)
                .order_by(WatchHistory.watched_at.desc())
                .limit(2)
                .all()
            )
            if history.movie_id not in seed_ids
        )
        if not seed_ids:
            return results

        # A newly active user has only the titles they interacted with locally.
        # Pull a bounded TMDB neighborhood once, then score those candidates locally.
        try:
            payload = await self.tmdb.recommendations(seed_ids[0])
            candidate_ids = [
                item.get("id")
                for item in payload.get("results", [])
                if isinstance(item, dict) and item.get("id")
            ][: max(limit * 2, 20)]
            for movie_id in candidate_ids:
                await self.catalog.ensure_movie(db, int(movie_id))
        except Exception:
            return results

        return self.hybrid.recommend(db, user_id, limit)

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
        return await self.tmdb.search_movies(
            query=query,
            page=page,
        )
