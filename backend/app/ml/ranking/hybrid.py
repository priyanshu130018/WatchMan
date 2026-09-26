from collections import defaultdict
from typing import Any
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.config import settings
from app.models.content import Content
from app.models.user import UserPreference
from app.ml.candidates.pipeline import CandidateItem


class RankedRecommendation:
    def __init__(
        self,
        content_id: int,
        content: Content,
        score: float,
        rank: int,
        content_score: float,
        collaborative_score: float,
        popularity_score: float,
        freshness_score: float,
        preference_score: float,
        explanation: str,
        sources: list[str],
    ):
        self.content_id = content_id
        self.content = content
        self.score = score
        self.rank = rank
        self.content_score = content_score
        self.collaborative_score = collaborative_score
        self.popularity_score = popularity_score
        self.freshness_score = freshness_score
        self.preference_score = preference_score
        self.explanation = explanation
        self.sources = sources

    def to_dict(self) -> dict[str, Any]:
        genre_names = [
            g.genre.name
            if hasattr(g, "genre") and hasattr(g.genre, "name")
            else (g.get("name") if isinstance(g, dict) else str(g))
            for g in (self.content.genres or [])
        ]
        return {
            "id": self.content.id,
            "content_id": self.content.id,
            "tmdb_id": self.content.tmdb_id,
            "title": self.content.title,
            "overview": self.content.overview,
            "content_type": self.content.content_type,
            "release_date": self.content.release_date,
            "poster_path": self.content.poster_path,
            "backdrop_path": self.content.backdrop_path,
            "vote_average": self.content.vote_average,
            "vote_count": self.content.vote_count,
            "popularity": self.content.popularity,
            "genres": genre_names,
            "runtime": self.content.runtime,
            "tagline": self.content.tagline,
            "score": round(self.score, 4),
            "recommendation_score": round(self.score, 4),
            "rank": self.rank,
            "explanation": self.explanation,
            "reason": self.explanation,
            "content_score": round(self.content_score, 4),
            "collaborative_score": round(self.collaborative_score, 4),
            "popularity_score": round(self.popularity_score, 4),
            "freshness_score": round(self.freshness_score, 4),
            "preference_score": round(self.preference_score, 4),
            "sources": self.sources,
        }


class HybridRanker:
    """
    Combines multi-channel candidate scores with user profile taxonomy preferences and diversity guards.
    """

    # Blend weights are read from configuration (env-overridable). See
    # Settings.recommendation_weights and docs/RECOMMENDATION_ARCHITECTURE.md.
    DEFAULT_WEIGHTS = settings.recommendation_weights

    @classmethod
    def get_user_profile_preferences(cls, db: Session, user_id: UUID) -> tuple[set[str], set[str]]:
        """
        Retrieves user's explicit genre and language preferences.
        """
        pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        if not pref:
            return set(), set()

        pref_genres = {g.strip().lower() for g in (pref.favorite_genres or []) if g and isinstance(g, str)}
        pref_langs = set()
        return pref_genres, pref_langs

    @classmethod
    def _compute_preference_score(
        cls,
        content: Content,
        pref_genres: set[str],
        pref_langs: set[str],
    ) -> float:
        if not pref_genres and not pref_langs:
            return 0.0

        item_genres = set()
        for g in (content.genres or []):
            if hasattr(g, "genre") and hasattr(g.genre, "name") and g.genre.name:
                item_genres.add(g.genre.name.strip().lower())
            elif isinstance(g, dict) and g.get("name"):
                item_genres.add(str(g.get("name")).strip().lower())
            elif isinstance(g, str):
                item_genres.add(g.strip().lower())

        genre_match = 0.0
        if pref_genres and item_genres:
            common = pref_genres.intersection(item_genres)
            genre_match = len(common) / min(len(pref_genres), len(item_genres))

        lang_match = 0.0
        if pref_langs and content.original_language:
            if content.original_language.strip().lower() in pref_langs:
                lang_match = 1.0

        if pref_genres and pref_langs:
            return 0.7 * genre_match + 0.3 * lang_match
        elif pref_genres:
            return genre_match
        else:
            return lang_match

    @classmethod
    def _build_explanation(
        cls,
        content_score: float,
        collab_score: float,
        pop_score: float,
        fresh_score: float,
        pref_score: float,
        content: Content,
        pref_genres: set[str],
    ) -> str:
        # Determine dominant driver
        drivers = [
            ("content", content_score * cls.DEFAULT_WEIGHTS["content"]),
            ("collab", collab_score * cls.DEFAULT_WEIGHTS["collaborative"]),
            ("fresh", fresh_score * cls.DEFAULT_WEIGHTS["freshness"]),
            ("pref", pref_score * cls.DEFAULT_WEIGHTS["preference"]),
            ("pop", pop_score * cls.DEFAULT_WEIGHTS["popularity"]),
        ]
        drivers.sort(key=lambda x: x[1], reverse=True)
        top_driver = drivers[0][0]

        if top_driver == "content" and content_score >= 0.35:
            return "Matches your personal taste profile and favorite themes"
        elif top_driver == "collab" and collab_score >= 0.25:
            return "Recommended by viewers who share your entertainment tastes"
        elif top_driver == "pref" and pref_score >= 0.3:
            return "Curated to match your selected genre & language preferences"
        elif top_driver == "fresh" and fresh_score >= 0.5:
            return "Fresh new release recommended for you"
        elif pop_score >= 0.4:
            return "Popular and trending with high audience ratings"
        return "Recommended for you based on catalog activity"

    @classmethod
    def rank_candidates(
        cls,
        db: Session,
        user_id: UUID,
        candidates: list[CandidateItem],
        limit: int = 20,
        weights: dict[str, float] | None = None,
        apply_diversity: bool = True,
        max_per_genre: int = 4,
    ) -> list[RankedRecommendation]:
        """
        Ranks candidates by combining normalized scores, user preferences, and diversity filtering.
        """
        if not candidates:
            return []

        w = dict(cls.DEFAULT_WEIGHTS)
        if weights:
            w.update(weights)

        pref_genres, pref_langs = cls.get_user_profile_preferences(db, user_id)

        scored_items: list[dict[str, Any]] = []

        for item in candidates:
            c = item.content
            pref_score = cls._compute_preference_score(c, pref_genres, pref_langs)

            composite_score = (
                w["content"] * item.content_score
                + w["collaborative"] * item.collaborative_score
                + w["popularity"] * item.popularity_score
                + w["freshness"] * item.freshness_score
                + w["preference"] * pref_score
            )

            explanation = cls._build_explanation(
                content_score=item.content_score,
                collab_score=item.collaborative_score,
                pop_score=item.popularity_score,
                fresh_score=item.freshness_score,
                pref_score=pref_score,
                content=c,
                pref_genres=pref_genres,
            )

            scored_items.append({
                "item": item,
                "composite_score": composite_score,
                "preference_score": pref_score,
                "explanation": explanation,
            })

        # Deterministic sorting: composite_score desc, popularity desc, content_id asc
        scored_items.sort(
            key=lambda x: (
                x["composite_score"],
                float(x["item"].content.popularity or 0.0),
                -x["item"].content_id,
            ),
            reverse=True,
        )

        # Apply Diversity filtering (genre & type saturation control)
        final_ranked: list[RankedRecommendation] = []
        genre_counts: dict[str, int] = defaultdict(int)

        for s in scored_items:
            cand = s["item"]
            c = cand.content

            if apply_diversity:
                # Check dominant genre saturation
                primary_genre = None
                if c.genres and len(c.genres) > 0:
                    first_g = c.genres[0]
                    if hasattr(first_g, "genre") and hasattr(first_g.genre, "name"):
                        primary_genre = first_g.genre.name
                    elif isinstance(first_g, dict):
                        primary_genre = first_g.get("name")
                    elif isinstance(first_g, str):
                        primary_genre = first_g

                if primary_genre and genre_counts[primary_genre] >= max_per_genre:
                    # Penalty or skip if saturated and we have plenty of candidates
                    if len(final_ranked) < limit and len(scored_items) > limit * 2:
                        continue

                if primary_genre:
                    genre_counts[primary_genre] += 1

            rank = len(final_ranked) + 1
            ranked_rec = RankedRecommendation(
                content_id=cand.content_id,
                content=c,
                score=s["composite_score"],
                rank=rank,
                content_score=cand.content_score,
                collaborative_score=cand.collaborative_score,
                popularity_score=cand.popularity_score,
                freshness_score=cand.freshness_score,
                preference_score=s["preference_score"],
                explanation=s["explanation"],
                sources=cand.sources,
            )
            final_ranked.append(ranked_rec)

            if len(final_ranked) >= limit:
                break

        return final_ranked
