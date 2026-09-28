"""
Content Embedding Eligibility Service.

Policy engine responsible for deciding whether content items qualify for:
1. Initial selective embedding (top popular catalog content).
2. Interaction-driven on-demand embedding (watch, save, rate, review, decision).
3. Search/open-driven embedding (threshold-gated).
4. Embedding freshness verification (content hash, model name, dimension, model version).
"""

from __future__ import annotations

import logging
from typing import Sequence
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.content import Content, ContentType
from app.models.embedding import ContentEmbedding
from app.models.interaction import InteractionEvent, SavedContent, WatchHistory
from app.models.review import Rating, Review
from app.models.watchman import WatchmanDecision
from app.ml.embeddings.text_builder import (
    build_movie_embedding_text,
    compute_movie_text_hash,
)

logger = logging.getLogger(__name__)


class ContentEmbeddingEligibilityService:
    """
    Decoupled policy service determining embedding eligibility and freshness.
    Does not encode vectors directly; delegates to ContentEmbeddingService.
    """

    CURRENT_MODEL_VERSION = "1.0.0"

    @classmethod
    def is_embedding_current(
        cls,
        content: Content,
        embedding: ContentEmbedding | None,
    ) -> bool:
        """
        Validates if an existing embedding is present, matches the current text hash,
        model name, dimension, and model version.

        Returns True if the existing vector can be safely reused without re-generation.
        """
        if embedding is None or embedding.embedding is None:
            return False

        if embedding.model_name != settings.EMBEDDING_MODEL:
            return False

        if embedding.dimension != settings.VECTOR_DIMENSION:
            return False

        if embedding.model_version != cls.CURRENT_MODEL_VERSION:
            return False

        text_content = build_movie_embedding_text(content)
        current_hash = compute_movie_text_hash(text_content)
        if embedding.content_hash != current_hash:
            return False

        return True

    @classmethod
    def should_embed_initially(
        cls,
        content: Content,
        db: Session | None = None,
    ) -> bool:
        """
        Determines whether a content item is part of the initial high-value / popular set.
        """
        if content is None:
            return False

        if db is None:
            # Fallback heuristic if session not provided: item has positive popularity
            return float(content.popularity or 0.0) > 0.0

        cutoff = cls.get_popularity_cutoff(db, content.content_type)
        return float(content.popularity or 0.0) >= cutoff

    @classmethod
    def should_embed_on_interaction(cls, content: Content | None) -> bool:
        """
        Determines whether content should be embedded following a real user interaction.
        Enabled by default via ENABLE_INTERACTION_EMBEDDING.
        """
        if not settings.ENABLE_INTERACTION_EMBEDDING:
            return False
        return content is not None

    @classmethod
    def should_embed_on_search(
        cls,
        content: Content | None,
        search_open_count: int = 1,
    ) -> bool:
        """
        Determines whether content should be embedded based on search-open telemetry.
        Only generates an embedding if ENABLE_SEARCH_EMBEDDING is True and open
        count meets or exceeds SEARCH_EMBED_THRESHOLD.
        """
        if not settings.ENABLE_SEARCH_EMBEDDING:
            return False
        if content is None:
            return False
        return search_open_count >= settings.SEARCH_EMBED_THRESHOLD

    @classmethod
    def get_initial_popular_candidates(
        cls,
        db: Session,
        movie_limit: int | None = None,
        tv_limit: int | None = None,
    ) -> list[Content]:
        """
        Retrieves the top popular movies and TV series using real catalog popularity data.
        Defaults to configured limits (~500 movies, ~500 TV series).
        """
        eff_movie_limit = (
            movie_limit
            if movie_limit is not None
            else settings.INITIAL_POPULAR_MOVIE_EMBED_LIMIT
        )
        eff_tv_limit = (
            tv_limit
            if tv_limit is not None
            else settings.INITIAL_POPULAR_TV_EMBED_LIMIT
        )

        movies = (
            db.query(Content)
            .filter(Content.content_type == ContentType.MOVIE.value)
            .order_by(Content.popularity.desc().nullslast(), Content.id.asc())
            .limit(eff_movie_limit)
            .all()
        )

        tv_shows = (
            db.query(Content)
            .filter(Content.content_type == ContentType.TV.value)
            .order_by(Content.popularity.desc().nullslast(), Content.id.asc())
            .limit(eff_tv_limit)
            .all()
        )

        return movies + tv_shows

    @classmethod
    def get_interacted_content_ids(cls, db: Session) -> set[int]:
        """
        Finds all content IDs referenced by real user activity across the database:
        - watch_history
        - saved_content
        - ratings
        - reviews
        - interaction_events
        - watchman_decisions
        """
        content_ids: set[int] = set()

        for (cid,) in db.query(WatchHistory.content_id).distinct().all():
            if cid:
                content_ids.add(cid)

        for (cid,) in db.query(SavedContent.content_id).distinct().all():
            if cid:
                content_ids.add(cid)

        for (cid,) in db.query(Rating.content_id).distinct().all():
            if cid:
                content_ids.add(cid)

        for (cid,) in db.query(Review.content_id).distinct().all():
            if cid:
                content_ids.add(cid)

        for (cid,) in (
            db.query(InteractionEvent.content_id)
            .filter(InteractionEvent.content_id.isnot(None))
            .distinct()
            .all()
        ):
            if cid:
                content_ids.add(cid)

        for (cid,) in db.query(WatchmanDecision.content_id).distinct().all():
            if cid:
                content_ids.add(cid)

        return content_ids

    @classmethod
    def get_popularity_cutoff(cls, db: Session, content_type: str) -> float:
        """
        Computes the minimum popularity threshold for the top N items of given type.
        """
        limit = (
            settings.INITIAL_POPULAR_MOVIE_EMBED_LIMIT
            if content_type == ContentType.MOVIE.value
            else settings.INITIAL_POPULAR_TV_EMBED_LIMIT
        )
        row = (
            db.query(Content.popularity)
            .filter(Content.content_type == content_type)
            .order_by(Content.popularity.desc().nullslast())
            .offset(max(0, limit - 1))
            .limit(1)
            .first()
        )
        return float(row[0] or 0.0) if row else 0.0
