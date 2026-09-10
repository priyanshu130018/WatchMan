"""Hybrid personalized movie ranking without an online model dependency."""

from __future__ import annotations

from collections import defaultdict
from math import log1p, sqrt
import re
from typing import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from app.database.models.favorite import Favorite
from app.database.models.movie import Movie
from app.database.models.rating import Rating
from app.database.models.watch_history import WatchHistory


class HybridRecommendationService:
    """Rank local catalog movies from content, peer behavior, and popularity."""

    CONTENT_WEIGHT = 0.55
    COLLABORATIVE_WEIGHT = 0.35
    POPULARITY_WEIGHT = 0.10

    def recommend(self, db: Session, user_id: UUID, limit: int = 20) -> list[dict]:
        movies = db.query(Movie).all()
        if not movies:
            return []

        movies_by_id = {movie.id: movie for movie in movies}
        interactions = self._interaction_matrix(db)
        target = interactions.get(user_id, {})
        candidates = [movie for movie in movies if movie.id not in target]
        if not candidates:
            return []

        popularity_scores = self._popularity_scores(candidates)
        if not target:
            return [
                self._response(
                    movie,
                    0.0,
                    0.0,
                    popularity_scores[movie.id],
                    "Popular in the catalog",
                )
                for movie in sorted(
                    candidates, key=lambda movie: popularity_scores[movie.id], reverse=True
                )[:limit]
            ]

        profile = self._content_profile(target, movies_by_id)
        recommendations: list[dict] = []
        for movie in candidates:
            content_score = self._content_score(profile, movie)
            collaborative_score = self._collaborative_score(
                movie.id, user_id, target, interactions
            )
            popularity_score = popularity_scores[movie.id]
            recommendations.append(
                self._response(
                    movie,
                    content_score,
                    collaborative_score,
                    popularity_score,
                    self._reason(content_score, collaborative_score),
                )
            )

        return sorted(
            recommendations, key=lambda item: item["recommendation_score"], reverse=True
        )[:limit]

    @staticmethod
    def _interaction_matrix(db: Session) -> dict[UUID, dict[int, float]]:
        matrix: dict[UUID, dict[int, float]] = defaultdict(dict)

        for rating in db.query(Rating).all():
            matrix[rating.user_id][rating.movie_id] = max(
                matrix[rating.user_id].get(rating.movie_id, 0.0), rating.rating / 5.0
            )
        for favorite in db.query(Favorite).all():
            matrix[favorite.user_id][favorite.movie_id] = max(
                matrix[favorite.user_id].get(favorite.movie_id, 0.0), 0.9
            )
        for history in db.query(WatchHistory).all():
            strength = 0.25 + 0.75 * max(0.0, min(1.0, history.progress))
            matrix[history.user_id][history.movie_id] = max(
                matrix[history.user_id].get(history.movie_id, 0.0), strength
            )
        return matrix

    def _content_profile(
        self, interactions: dict[int, float], movies_by_id: dict[int, Movie]
    ) -> dict[str, float]:
        profile: dict[str, float] = defaultdict(float)
        for movie_id, weight in interactions.items():
            movie = movies_by_id.get(movie_id)
            if movie is None:
                continue
            for token in self._movie_tokens(movie):
                profile[token] += weight
        return profile

    def _content_score(self, profile: dict[str, float], movie: Movie) -> float:
        tokens = self._movie_tokens(movie)
        if not profile or not tokens:
            return 0.0
        numerator = sum(profile.get(token, 0.0) for token in tokens)
        profile_norm = sqrt(sum(weight * weight for weight in profile.values()))
        return min(1.0, numerator / max(1.0, profile_norm * sqrt(len(tokens))))

    @staticmethod
    def _collaborative_score(
        candidate_id: int,
        user_id: UUID,
        target: dict[int, float],
        interactions: dict[UUID, dict[int, float]],
    ) -> float:
        total = 0.0
        weight = 0.0
        for peer_id, peer in interactions.items():
            if peer_id == user_id or candidate_id not in peer:
                continue
            shared = set(target).intersection(peer)
            if not shared:
                continue
            dot = sum(target[movie_id] * peer[movie_id] for movie_id in shared)
            target_norm = sqrt(sum(target[movie_id] ** 2 for movie_id in shared))
            peer_norm = sqrt(sum(peer[movie_id] ** 2 for movie_id in shared))
            similarity = dot / (target_norm * peer_norm) if target_norm and peer_norm else 0.0
            if similarity:
                total += similarity * peer[candidate_id]
                weight += similarity
        return min(1.0, total / weight) if weight else 0.0

    @staticmethod
    def _popularity_scores(movies: Iterable[Movie]) -> dict[int, float]:
        movie_list = list(movies)
        max_popularity = max(
            (float(movie.popularity or 0.0) for movie in movie_list), default=1.0
        )
        max_popularity = max(1.0, max_popularity)
        return {
            movie.id: min(
                1.0,
                0.7
                * log1p(max(0.0, float(movie.popularity or 0.0)))
                / log1p(max_popularity)
                + 0.3 * max(0.0, min(10.0, float(movie.vote_average or 0.0))) / 10.0,
            )
            for movie in movie_list
        }

    @classmethod
    def _movie_tokens(cls, movie: Movie) -> set[str]:
        parts = [movie.title, movie.overview or "", movie.tagline or ""]
        for collection in (
            movie.genres or [],
            movie.keywords or [],
            movie.cast or [],
            movie.crew or [],
        ):
            for value in collection:
                if isinstance(value, dict):
                    parts.append(str(value.get("name") or value.get("job") or ""))
                else:
                    parts.append(str(value))
        return set(re.findall(r"[a-z0-9]{2,}", " ".join(parts).lower()))

    def _response(
        self,
        movie: Movie,
        content_score: float,
        collaborative_score: float,
        popularity_score: float,
        reason: str,
    ) -> dict:
        score = (
            self.CONTENT_WEIGHT * content_score
            + self.COLLABORATIVE_WEIGHT * collaborative_score
            + self.POPULARITY_WEIGHT * popularity_score
        )
        return {
            "id": movie.id,
            "tmdb_id": movie.tmdb_id,
            "title": movie.title,
            "overview": movie.overview,
            "release_date": movie.release_date,
            "poster_path": movie.poster_path,
            "backdrop_path": movie.backdrop_path,
            "vote_average": movie.vote_average,
            "vote_count": movie.vote_count,
            "popularity": movie.popularity,
            "genres": movie.genres or [],
            "runtime": movie.runtime,
            "tagline": movie.tagline,
            "recommendation_score": round(score, 4),
            "content_score": round(content_score, 4),
            "collaborative_score": round(collaborative_score, 4),
            "popularity_score": round(popularity_score, 4),
            "reason": reason,
        }

    @staticmethod
    def _reason(content_score: float, collaborative_score: float) -> str:
        if collaborative_score >= 0.35 and content_score >= 0.2:
            return "Matches your taste and users with similar activity"
        if collaborative_score >= 0.35:
            return "Liked by users with similar activity"
        if content_score >= 0.2:
            return "Matches your genres, cast, and themes"
        return "Popular in the catalog"
