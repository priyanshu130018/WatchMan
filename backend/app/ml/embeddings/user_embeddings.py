from collections import defaultdict
from datetime import datetime
import logging
from uuid import UUID
import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.content import Content
from app.models.embedding import ContentEmbedding, UserEmbedding
from app.models.interaction import InteractionEvent, SavedContent, WatchHistory
from app.models.review import Rating
from app.models.watchman import WatchmanDecision
from app.ml.embeddings.content_embeddings import ContentEmbeddingService

logger = logging.getLogger(__name__)


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

        # 2. Ratings (consistently normalized on 10-point scale: rating / 10.0)
        # Ratings >= 6.0 (>= 0.6) are positive signals. Lower ratings do not contribute positive taste weights.
        ratings = db.query(Rating).filter(Rating.user_id == user_id).all()
        for r in ratings:
            raw_val = float(r.rating)
            normalized_val = max(0.0, min(1.0, raw_val / 10.0))
            if normalized_val >= 0.6:  # positive rating
                weights[r.content_id] = max(weights[r.content_id], normalized_val)

        # 3. Watch History (based on actual progress / completion)
        history_items = db.query(WatchHistory).filter(WatchHistory.user_id == user_id).all()
        for h in history_items:
            prog = max(0.0, min(1.0, float(h.progress or 0.0)))
            if h.completed:
                weights[h.content_id] = max(weights[h.content_id], 1.0)
            elif prog >= 0.4:
                strength = 0.5 + 0.5 * prog
                weights[h.content_id] = max(weights[h.content_id], strength)

        # 4. Interaction Events (e.g. 'save', 'share')
        # Respect canonical signals and prevent generic events from contaminating taste with 0.5 weights.
        events = (
            db.query(InteractionEvent)
            .filter(
                InteractionEvent.user_id == user_id,
                InteractionEvent.event_type.in_(["save", "share", "rate", "watch"]),
            )
            .all()
        )
        for ev in events:
            if not ev.content_id:
                continue

            if ev.event_type == "save":
                weights[ev.content_id] = max(weights[ev.content_id], 1.0)
            elif ev.event_type == "share":
                weights[ev.content_id] = max(weights[ev.content_id], 0.5)
            elif ev.event_type == "rate":
                # Only use if event provides an explicit positive rating value (>= 6.0 on 10-scale)
                if ev.event_value is not None:
                    norm_val = max(0.0, min(1.0, float(ev.event_value) / 10.0))
                    if norm_val >= 0.6:
                        weights[ev.content_id] = max(weights[ev.content_id], norm_val)
            elif ev.event_type == "watch":
                # Only use if event provides an explicit watch progress (>= 0.4)
                if ev.event_value is not None:
                    prog_val = max(0.0, min(1.0, float(ev.event_value)))
                    if prog_val >= 0.4:
                        strength = 0.5 + 0.5 * prog_val
                        weights[ev.content_id] = max(weights[ev.content_id], strength)

        # 5. WatchMan Decisions
        from app.models.watchman import WatchmanDecision
        decisions = db.query(WatchmanDecision).filter(WatchmanDecision.user_id == user_id).all()
        skip_cids: set[int] = set()
        for dec in decisions:
            if dec.decision == "must_watch":
                weights[dec.content_id] = max(weights[dec.content_id], 1.0)
            elif dec.decision == "time_pass":
                weights[dec.content_id] = max(weights[dec.content_id], 0.35)
            elif dec.decision == "skip":
                skip_cids.add(dec.content_id)
                weights.pop(dec.content_id, None)

        # Interaction events from watchman decisions
        wm_events = (
            db.query(InteractionEvent)
            .filter(
                InteractionEvent.user_id == user_id,
                InteractionEvent.event_type == "watchman_decision",
            )
            .all()
        )
        for ev in wm_events:
            if not ev.content_id:
                continue
            dec = (ev.event_data or {}).get("decision") if ev.event_data else None
            val = ev.event_value
            if dec == "must_watch" or val == 1.0:
                weights[ev.content_id] = max(weights[ev.content_id], 1.0)
            elif dec == "skip" or val == 0.0:
                skip_cids.add(ev.content_id)
                weights.pop(ev.content_id, None)

        # Enforce hard exclusion for skipped items
        for cid in skip_cids:
            weights.pop(cid, None)

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
            existing = db.query(UserEmbedding).filter(UserEmbedding.user_id == user_id).first()
            if existing:
                db.delete(existing)
                db.commit()
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

        # Generate on-demand for any missing content embeddings if interaction embedding is enabled
        if settings.ENABLE_INTERACTION_EMBEDDING:
            missing_cids = [cid for cid in content_ids if cid not in found_ids or found_ids[cid] is None]
            if missing_cids:
                missing_contents = db.query(Content).filter(Content.id.in_(missing_cids)).all()
                if missing_contents:
                    try:
                        ContentEmbeddingService.batch_embed_items(db, missing_contents)
                        embeddings_records = (
                            db.query(ContentEmbedding)
                            .filter(
                                ContentEmbedding.content_id.in_(missing_cids),
                                ContentEmbedding.embedding.isnot(None),
                            )
                            .all()
                        )
                        for r in embeddings_records:
                            found_ids[r.content_id] = r.embedding
                    except Exception as exc:
                        logger.warning("Batch embedding for interaction items failed: %s; falling back to per-item", exc)
                        for cid in missing_cids:
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
            try:
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
            except Exception:
                db.rollback()
                concurrent_user_emb = (
                    db.query(UserEmbedding)
                    .filter(UserEmbedding.user_id == user_id)
                    .first()
                )
                if concurrent_user_emb:
                    return concurrent_user_emb
                raise

    @classmethod
    def get_stored_user_embedding(
        cls,
        db: Session,
        user_id: UUID,
    ) -> list[float] | None:
        """
        Retrieves the persisted user taste embedding directly from PostgreSQL user_embeddings.
        Does NOT block HTTP API requests with synchronous recomputation.
        Returns None if user is cold-start or pending background worker calculation.
        """
        record = db.query(UserEmbedding).filter(UserEmbedding.user_id == user_id).first()
        if record and record.embedding is not None and len(record.embedding) == settings.VECTOR_DIMENSION:
            return record.embedding
        return None

    @classmethod
    def get_or_compute_user_embedding(
        cls,
        db: Session,
        user_id: UUID,
    ) -> list[float] | None:
        """
        Retrieves user embedding from DB without blocking on expensive calculation.
        """
        return cls.get_stored_user_embedding(db, user_id)

    @classmethod
    def get_users_needing_embedding_update(cls, db: Session) -> list[UUID]:
        """
        Identifies users whose interaction state has changed since their user_embedding was last updated,
        or users who have interactions but no user_embedding, or users whose embeddings need cleanup.
        Uses single aggregated database queries for maximum performance.
        """
        from sqlalchemy import func
        from app.models.user import User
        from app.models.watchman import WatchmanDecision

        # Fetch max interaction timestamps per user across all positive interaction channels
        max_saved = dict(db.query(SavedContent.user_id, func.max(SavedContent.created_at)).group_by(SavedContent.user_id).all())
        max_rating = dict(db.query(Rating.user_id, func.max(func.coalesce(Rating.updated_at, Rating.created_at))).group_by(Rating.user_id).all())
        max_wh = dict(db.query(WatchHistory.user_id, func.max(WatchHistory.watched_at)).group_by(WatchHistory.user_id).all())
        max_ev = dict(db.query(InteractionEvent.user_id, func.max(InteractionEvent.created_at)).filter(InteractionEvent.user_id.isnot(None)).group_by(InteractionEvent.user_id).all())
        max_wm = dict(db.query(WatchmanDecision.user_id, func.max(func.coalesce(WatchmanDecision.updated_at, WatchmanDecision.created_at))).group_by(WatchmanDecision.user_id).all())

        all_interacted_user_ids = set(max_saved.keys()) | set(max_rating.keys()) | set(max_wh.keys()) | set(max_ev.keys()) | set(max_wm.keys())
        existing_embs = {e.user_id: e for e in db.query(UserEmbedding).all()}
        all_active_users = db.query(User.id).filter(User.is_active == True).all()

        changed_user_ids: list[UUID] = []
        for (uid,) in all_active_users:
            emb = existing_embs.get(uid)
            ts_list = [
                ts for ts in [
                    max_saved.get(uid),
                    max_rating.get(uid),
                    max_wh.get(uid),
                    max_ev.get(uid),
                    max_wm.get(uid),
                ] if ts is not None
            ]

            if uid in all_interacted_user_ids and ts_list:
                latest_ts = max(ts_list)
                if emb is None or emb.embedding is None or emb.updated_at is None or latest_ts > emb.updated_at:
                    changed_user_ids.append(uid)
            else:
                # User has no interactions currently. If they have an existing embedding, clean it up
                if emb is not None and emb.embedding is not None:
                    changed_user_ids.append(uid)

        return changed_user_ids
