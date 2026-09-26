"""
ALS training service: builds the User x Movie interaction matrix from WatchMan's
interaction data and persists learned latent factors.

This is an OFFLINE / background operation. It must not run on the online
recommendation request path.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.collaborative import ALSItemFactors, ALSUserFactors
from app.models.interaction import InteractionEvent, SavedContent, WatchHistory
from app.models.review import Rating
from app.ml.collaborative.als import ALSModel

logger = logging.getLogger(__name__)


class ALSTrainingService:
    """Builds interactions, trains ALS, and persists user/item latent factors."""

    @classmethod
    def build_interactions(
        cls, db: Session
    ) -> tuple[dict[UUID, dict[int, float]], list[UUID], list[int]]:
        """
        Build an implicit-feedback interaction map: user_id -> {content_id: weight}.

        Weights follow the same semantics used elsewhere in WatchMan (max signal
        per user/item): rating (normalized 0..1), saved (0.9),
        watch progress (0.3 + 0.7*progress), interaction events (0.6/0.3).
        """
        matrix: dict[UUID, dict[int, float]] = defaultdict(dict)

        def _bump(uid: UUID, cid: int, w: float) -> None:
            if uid is None or cid is None:
                return
            matrix[uid][cid] = max(matrix[uid].get(cid, 0.0), float(w))

        for r in db.query(Rating).all():
            norm = (r.rating / 5.0) if r.rating <= 5.0 else (r.rating / 10.0)
            _bump(r.user_id, r.content_id, max(0.0, min(1.0, norm)))

        for s in db.query(SavedContent).all():
            _bump(s.user_id, s.content_id, 0.9)

        for h in db.query(WatchHistory).all():
            prog = max(0.0, min(1.0, float(h.progress or 0.0)))
            _bump(h.user_id, h.content_id, 0.3 + 0.7 * prog)

        for ev in db.query(InteractionEvent).all():
            w = 0.6 if ev.event_type in ("save", "rate", "watch") else 0.3
            _bump(ev.user_id, ev.content_id, w)

        user_ids = sorted(matrix.keys(), key=str)
        item_ids = sorted({cid for items in matrix.values() for cid in items})
        return matrix, user_ids, item_ids

    @classmethod
    def train_and_persist(cls, db: Session) -> dict:
        """
        Train ALS on current interactions and persist factors. Returns a status
        dict. Skips training gracefully when there is too little data (cold
        catalog) so the caller can fall back to other channels.
        """
        params = settings.als_params
        matrix, user_ids, item_ids = cls.build_interactions(db)

        total_interactions = sum(len(v) for v in matrix.values())
        if (
            len(user_ids) < params["min_users"]
            or len(item_ids) < params["min_items"]
            or total_interactions < params["min_interactions"]
        ):
            logger.info(
                "ALS training skipped (insufficient data): users=%d items=%d interactions=%d",
                len(user_ids), len(item_ids), total_interactions,
            )
            return {
                "status": "skipped",
                "reason": "insufficient_interactions",
                "users": len(user_ids),
                "items": len(item_ids),
                "interactions": total_interactions,
            }

        user_index = {uid: i for i, uid in enumerate(user_ids)}
        item_index = {cid: j for j, cid in enumerate(item_ids)}

        R = np.zeros((len(user_ids), len(item_ids)), dtype=np.float64)
        for uid, items in matrix.items():
            ui = user_index[uid]
            for cid, w in items.items():
                R[ui, item_index[cid]] = w

        # Number of factors cannot exceed the smaller matrix dimension.
        factors = min(params["factors"], max(1, min(len(user_ids), len(item_ids)) - 1))

        model = ALSModel(
            factors=factors,
            regularization=params["regularization"],
            alpha=params["alpha"],
            iterations=params["iterations"],
            seed=params["seed"],
        ).fit(R)

        model_version = f"als-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-f{factors}"

        # Wholesale replacement keeps the persisted factors internally consistent
        # for a single trained model version.
        db.query(ALSUserFactors).delete()
        db.query(ALSItemFactors).delete()

        for uid, ui in user_index.items():
            db.add(ALSUserFactors(
                user_id=uid,
                factors=[float(x) for x in model.user_factors[ui]],
                num_factors=factors,
                model_version=model_version,
            ))
        for cid, ii in item_index.items():
            db.add(ALSItemFactors(
                content_id=cid,
                factors=[float(x) for x in model.item_factors[ii]],
                num_factors=factors,
                model_version=model_version,
            ))
        db.commit()

        logger.info(
            "ALS training complete: version=%s users=%d items=%d factors=%d",
            model_version, len(user_ids), len(item_ids), factors,
        )
        return {
            "status": "trained",
            "model_version": model_version,
            "users": len(user_ids),
            "items": len(item_ids),
            "factors": factors,
            "interactions": total_interactions,
        }
