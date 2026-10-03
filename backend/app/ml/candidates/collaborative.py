from collections import defaultdict
from math import sqrt
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.content import Content
from app.models.interaction import InteractionEvent, SavedContent, WatchHistory
from app.models.review import Rating


class CollaborativeCandidateGenerator:
    """
    Generates candidates based on item-item / user-user collaborative interactions.
    """

    @classmethod
    def _build_interaction_matrix(cls, db: Session) -> dict[UUID, dict[int, float]]:
        matrix: dict[UUID, dict[int, float]] = defaultdict(dict)

        # Ratings
        for r_user_id, r_content_id, r_rating in db.query(Rating.user_id, Rating.content_id, Rating.rating).all():
            norm = (r_rating / 5.0) if r_rating <= 5.0 else (r_rating / 10.0)
            matrix[r_user_id][r_content_id] = max(matrix[r_user_id].get(r_content_id, 0.0), norm)

        # Saved content
        for s_user_id, s_content_id in db.query(SavedContent.user_id, SavedContent.content_id).all():
            matrix[s_user_id][s_content_id] = max(matrix[s_user_id].get(s_content_id, 0.0), 0.9)

        # Watch history
        for h_user_id, h_content_id, h_progress in db.query(WatchHistory.user_id, WatchHistory.content_id, WatchHistory.progress).all():
            prog = max(0.0, min(1.0, float(h_progress or 0.0)))
            strength = 0.3 + 0.7 * prog
            matrix[h_user_id][h_content_id] = max(matrix[h_user_id].get(h_content_id, 0.0), strength)

        # Interaction events
        for ev_user_id, ev_content_id, ev_type in (
            db.query(InteractionEvent.user_id, InteractionEvent.content_id, InteractionEvent.event_type)
            .filter(InteractionEvent.content_id.isnot(None), InteractionEvent.user_id.isnot(None))
            .all()
        ):
            ev_weight = 0.6 if ev_type in ("save", "rate", "watch") else 0.3
            matrix[ev_user_id][ev_content_id] = max(matrix[ev_user_id].get(ev_content_id, 0.0), ev_weight)

        return matrix

    @classmethod
    def generate_candidates(
        cls,
        db: Session,
        user_id: UUID,
        limit: int = 50,
        content_type: str | None = None,
        exclude_content_ids: set[int] | None = None,
    ) -> list[dict]:
        """
        Retrieves candidates recommended by peers with similar interaction histories.
        """
        exclude_ids = exclude_content_ids or set()
        interactions = cls._build_interaction_matrix(db)
        target = interactions.get(user_id, {})
        if not target:
            return []

        target_norm = sqrt(sum(w * w for w in target.values()))
        if target_norm == 0:
            return []

        # Calculate peer similarities
        peer_scores: dict[UUID, float] = {}
        for peer_id, peer_items in interactions.items():
            if peer_id == user_id or not peer_items:
                continue
            shared = set(target.keys()).intersection(peer_items.keys())
            if not shared:
                continue

            dot = sum(target[cid] * peer_items[cid] for cid in shared)
            peer_norm = sqrt(sum(w * w for w in peer_items.values()))
            if peer_norm > 0:
                sim = dot / (target_norm * peer_norm)
                if sim > 0:
                    peer_scores[peer_id] = sim

        if not peer_scores:
            return []

        # Score candidate items from peer interactions
        candidate_scores: dict[int, float] = defaultdict(float)
        candidate_weights: dict[int, float] = defaultdict(float)

        for peer_id, sim in peer_scores.items():
            for cid, weight in interactions[peer_id].items():
                if cid in target or cid in exclude_ids:
                    continue
                candidate_scores[cid] += sim * weight
                candidate_weights[cid] += sim

        if not candidate_scores:
            return []

        normalized_scores = {
            cid: min(1.0, candidate_scores[cid] / candidate_weights[cid])
            for cid in candidate_scores
            if candidate_weights[cid] > 0
        }

        if content_type and content_type.lower() in ("movie", "tv"):
            valid_ids = {
                r[0]
                for r in db.query(Content.id)
                .filter(Content.id.in_(list(normalized_scores.keys())), Content.content_type == content_type.lower())
                .all()
            }
        else:
            valid_ids = set(normalized_scores.keys())

        results = []
        for cid, score in normalized_scores.items():
            if cid in valid_ids:
                results.append({
                    "content_id": cid,
                    "score": round(score, 4),
                    "source": "collaborative",
                    "explanation": "Popular with viewers who share your entertainment tastes",
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
