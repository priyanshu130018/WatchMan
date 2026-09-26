"""
ALS collaborative candidate generator (online, read-only).

Uses PRECOMPUTED ALS latent factors (see app.ml.collaborative.training). It never
trains and never touches the Hugging Face content embeddings. The collaborative
score is the dot product between the user's ALS factor vector and each item's
ALS factor vector.

If the user has no persisted factors yet (cold start / not-yet-trained), it
returns an empty list so the pipeline can fall back to other channels.
"""

from __future__ import annotations

import logging
import threading
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from app.models.collaborative import ALSItemFactors, ALSUserFactors
from app.models.content import Content

logger = logging.getLogger(__name__)

# Process-local cache of the item factor matrix, keyed by model_version, so we
# don't reload the whole item table on every request.
_CACHE_LOCK = threading.Lock()
_ITEM_CACHE: dict[str, tuple[list[int], np.ndarray]] = {}


class ALSCollaborativeCandidateGenerator:
    """Generates collaborative candidates from precomputed ALS factors."""

    @classmethod
    def _current_version(cls, db: Session) -> str | None:
        row = db.query(ALSItemFactors.model_version).first()
        return row[0] if row else None

    @classmethod
    def _load_item_factors(cls, db: Session, version: str) -> tuple[list[int], np.ndarray]:
        cached = _ITEM_CACHE.get(version)
        if cached is not None:
            return cached
        with _CACHE_LOCK:
            cached = _ITEM_CACHE.get(version)
            if cached is not None:
                return cached
            rows = (
                db.query(ALSItemFactors.content_id, ALSItemFactors.factors)
                .filter(ALSItemFactors.model_version == version)
                .all()
            )
            content_ids = [r[0] for r in rows]
            matrix = (
                np.array([r[1] for r in rows], dtype=np.float64)
                if rows
                else np.zeros((0, 0))
            )
            _ITEM_CACHE.clear()  # only keep the latest version
            _ITEM_CACHE[version] = (content_ids, matrix)
            return content_ids, matrix

    @classmethod
    def generate_candidates(
        cls,
        db: Session,
        user_id: UUID,
        limit: int = 50,
        content_type: str | None = None,
        exclude_content_ids: set[int] | None = None,
    ) -> list[dict]:
        exclude_ids = exclude_content_ids or set()

        version = cls._current_version(db)
        if not version:
            return []

        user_row = (
            db.query(ALSUserFactors)
            .filter(ALSUserFactors.user_id == user_id, ALSUserFactors.model_version == version)
            .first()
        )
        if user_row is None:
            return []  # cold user for this trained model -> fall back elsewhere

        content_ids, item_matrix = cls._load_item_factors(db, version)
        if item_matrix.size == 0:
            return []

        user_vec = np.asarray(user_row.factors, dtype=np.float64)
        if user_vec.shape[0] != item_matrix.shape[1]:
            logger.warning("ALS factor dimension mismatch for user_id=%s; skipping", user_id)
            return []

        scores = item_matrix @ user_vec  # collaborative dot-product scores

        # Rank, filter excluded, then resolve Content rows for the top slice.
        order = np.argsort(-scores)
        picked: list[tuple[int, float]] = []
        for idx in order:
            cid = content_ids[int(idx)]
            if cid in exclude_ids:
                continue
            picked.append((cid, float(scores[int(idx)])))
            if len(picked) >= limit * 3:  # over-fetch; content_type filter prunes later
                break

        if not picked:
            return []

        candidate_ids = [cid for cid, _ in picked]
        score_by_id = {cid: s for cid, s in picked}

        content_query = db.query(Content).filter(Content.id.in_(candidate_ids))
        if content_type and content_type.lower() in ("movie", "tv"):
            content_query = content_query.filter(Content.content_type == content_type.lower())
        contents_by_id = {c.id: c for c in content_query.all()}

        # Min-max normalize the raw dot-product scores to [0, 1] for blending.
        raw = [score_by_id[cid] for cid in candidate_ids if cid in contents_by_id]
        if not raw:
            return []
        lo, hi = min(raw), max(raw)
        span = (hi - lo) or 1.0

        results: list[dict] = []
        for cid in candidate_ids:
            c = contents_by_id.get(cid)
            if c is None:
                continue
            norm = (score_by_id[cid] - lo) / span
            results.append({
                "content_id": cid,
                "content": c,
                "score": round(max(0.0, min(1.0, norm)), 4),
                "source": "als_collaborative",
                "explanation": "Learned from the behaviour of users with similar taste (ALS)",
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
