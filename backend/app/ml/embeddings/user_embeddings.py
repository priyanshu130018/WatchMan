from collections import defaultdict
from datetime import datetime
from uuid import UUID
import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.embedding import ContentEmbedding, UserEmbedding
from app.models.interaction import InteractionEvent, SavedContent, WatchHistory
from app.models.review import Rating
from app.ml.embeddings.content_embeddings import ContentEmbeddingService


class UserEmbeddingService:
    """
    Computes and persists dense user taste embeddings by aggregating positive user interactions.
    """

    @classmethod
    def get_user_interaction_weights(cls, db: Session, user_id: UUID) -> dict[int, float]:
        """
        Gathers positive interaction signals for a user and maps content_id -> weight.
        """
        weights: dict[int, float] = defaultdict(float)

        # 1. Saved / Favorited content
        saved_items = db.query(SavedContent).filter(SavedContent.user_id == user_id).all()
        for item in saved_items:
            weights[item.content_id] = max(weights[item.content_id], 1.0)

        # 2. Ratings (>= 3.0 on 5-scale or >= 6.0 on 10-scale)
        ratings = db.query(Rating).filter(Rating.user_id == user_id).all()
        for r in ratings:
            raw_val = float(r.rating)
            normalized_val = raw_val / 5.0 if raw_val <= 5.0 else raw_val / 10.0
            if normalized_val >= 0.6:  # positive rating
                weights[r.content_id] = max(weights[r.content_id], normalized_val)

        # 3. Watch History (progress >= 0.4)
        history_items = db.query(WatchHistory).filter(WatchHistory.user_id == user_id).all()
        for h in history_items:
            prog = max(0.0, min(1.0, float(h.progress or 0.0)))
            if prog >= 0.4 or h.completed:
                strength = 0.5 + 0.5 * prog
                weights[h.content_id] = max(weights[h.content_id], strength)

        # 4. Interaction Events (e.g. 'save', 'share', 'view')
        events = (
            db.query(InteractionEvent)
            .filter(
                InteractionEvent.user_id == user_id,
                InteractionEvent.event_type.in_(["save", "share", "rate", "watch"]),
            )
            .all()
        )
        for ev in events:
            weights[ev.content_id] = max(weights[ev.content_id], 0.5)

        return dict(weights)

    @classmethod
    def compute_and_save_user_embedding(
        cls,
        db: Session,
        user_id: UUID,
        force: bool = False,
    ) -> UserEmbedding | None:
        """
        Aggregates content vectors for interacted items into a normalized preference vector.
        Persists the vector to the `user_embeddings` table.
        Returns None if user has no positive interactions (cold start).
        """
        item_weights = cls.get_user_interaction_weights(db, user_id)
        if not item_weights:
            return None

        # Fetch embeddings for all interacted items
        content_ids = list(item_weights.keys())
        embeddings_records = (
            db.query(ContentEmbedding)
            .filter(
                ContentEmbedding.content_id.in_(content_ids),
                ContentEmbedding.embedding.isnot(None),
            )
            .all()
        )
        found_ids = {r.content_id: r.embedding for r in embeddings_records}

        # Generate on-demand for any missing content embeddings
        for cid in content_ids:
            if cid not in found_ids or found_ids[cid] is None:
                try:
                    new_emb = ContentEmbeddingService.embed_content(db, cid)
                    if new_emb and new_emb.embedding is not None:
                        found_ids[cid] = new_emb.embedding
                except Exception:
                    continue

        if not found_ids:
            return None

        # Weighted vector sum
        dim = settings.VECTOR_DIMENSION
        accumulated_vector = np.zeros(dim, dtype=np.float32)
        total_weight = 0.0

        for cid, weight in item_weights.items():
            emb_vec = found_ids.get(cid)
            if emb_vec is not None and len(emb_vec) == dim:
                accumulated_vector += np.array(emb_vec, dtype=np.float32) * float(weight)
                total_weight += float(weight)

        if total_weight == 0.0:
            return None

        # L2 normalization
        norm = np.linalg.norm(accumulated_vector)
        if norm == 0:
            return None

        normalized_vector = (accumulated_vector / norm).tolist()

        # Persist to database
        existing = db.query(UserEmbedding).filter(UserEmbedding.user_id == user_id).first()
        if existing:
            existing.embedding = normalized_vector
            existing.model_name = settings.EMBEDDING_MODEL
            existing.dimension = dim
            existing.model_version = "1.0.0"
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing
        else:
            new_user_emb = UserEmbedding(
                user_id=user_id,
                embedding=normalized_vector,
                model_name=settings.EMBEDDING_MODEL,
                dimension=dim,
                model_version="1.0.0",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(new_user_emb)
            db.commit()
            db.refresh(new_user_emb)
            return new_user_emb

    @classmethod
    def get_or_compute_user_embedding(
        cls,
        db: Session,
        user_id: UUID,
    ) -> list[float] | None:
        """
        Retrieves user embedding from DB or computes it dynamically if missing/stale.
        """
        record = db.query(UserEmbedding).filter(UserEmbedding.user_id == user_id).first()
        if record and record.embedding is not None:
            return record.embedding

        computed = cls.compute_and_save_user_embedding(db, user_id)
        return computed.embedding if computed else None
