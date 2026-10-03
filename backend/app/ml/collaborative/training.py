"""
ALS training service: builds the User x Movie interaction matrix from WatchMan's
interaction data, evaluates on train/test split, and persists learned latent factors.

This is an OFFLINE / background operation. It must not run on the online
recommendation request path.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.collaborative import ALSItemFactors, ALSUserFactors
from app.models.interaction import InteractionEvent, SavedContent, WatchHistory
from app.models.review import Rating
from app.models.watchman import WatchmanDecision
from app.ml.collaborative.als import ALSModel

logger = logging.getLogger(__name__)


class ALSTrainingService:
    """Builds interactions, trains ALS, evaluates on validation split, and persists user/item latent factors."""

    @classmethod
    def build_interactions(
        cls, db: Session
    ) -> tuple[dict[UUID, dict[int, float]], list[UUID], list[int]]:
        """
        Build an implicit-feedback interaction map: user_id -> {content_id: weight}.

        Weights follow WatchMan's unified interaction semantics:
        - Rating: normalized 0..1 (rating / 5.0 or rating / 10.0)
        - Saved content: 0.9
        - Watch history: 0.3 + 0.7 * progress (0.4..1.0)
        - Interaction events: 0.6 for save/rate/watch, 0.3 for view/other
        - WatchMan decisions: 1.0 for must_watch, 0.35 for time_pass, 0.0 / excluded for skip
        """
        matrix: dict[UUID, dict[int, float]] = defaultdict(dict)

        def _bump(uid: UUID, cid: int, w: float) -> None:
            if uid is None or cid is None or w <= 0.0:
                return
            matrix[uid][cid] = max(matrix[uid].get(cid, 0.0), float(w))

        # 1. User Ratings
        for r in db.query(Rating).all():
            norm = (r.rating / 5.0) if r.rating <= 5.0 else (r.rating / 10.0)
            _bump(r.user_id, r.content_id, max(0.0, min(1.0, norm)))

        # 2. Saved / Watchlist Items
        for s in db.query(SavedContent).all():
            _bump(s.user_id, s.content_id, 0.9)

        # 3. Watch History
        for h in db.query(WatchHistory).all():
            prog = max(0.0, min(1.0, float(h.progress or 0.0)))
            _bump(h.user_id, h.content_id, 0.3 + 0.7 * prog)

        # 4. Telemetry / Behavioral Events
        for ev in db.query(InteractionEvent).all():
            if not ev.content_id:
                continue
            if ev.event_type in ("save", "rate", "watch"):
                _bump(ev.user_id, ev.content_id, 0.6)
            elif ev.event_type == "watchman_decision":
                dec = (ev.event_data or {}).get("decision") if ev.event_data else None
                if dec == "must_watch" or ev.event_value == 1.0:
                    _bump(ev.user_id, ev.content_id, 1.0)
                elif dec == "time_pass" or ev.event_value == 0.5:
                    _bump(ev.user_id, ev.content_id, 0.35)
            else:
                _bump(ev.user_id, ev.content_id, 0.3)

        # 5. WatchMan Decisions
        for dec in db.query(WatchmanDecision).all():
            if dec.decision == "must_watch":
                _bump(dec.user_id, dec.content_id, 1.0)
            elif dec.decision == "time_pass":
                _bump(dec.user_id, dec.content_id, 0.35)

        user_ids = sorted(matrix.keys(), key=str)
        item_ids = sorted({cid for items in matrix.values() for cid in items})
        return matrix, user_ids, item_ids

    @classmethod
    def train_test_split(
        cls,
        matrix: dict[UUID, dict[int, float]],
        test_ratio: float = 0.2,
        seed: int = 42,
    ) -> tuple[dict[UUID, dict[int, float]], dict[UUID, dict[int, float]]]:
        """
        Split interactions per user into training and validation sets without data leakage.
        """
        rng = np.random.default_rng(seed)
        train_matrix: dict[UUID, dict[int, float]] = defaultdict(dict)
        test_matrix: dict[UUID, dict[int, float]] = defaultdict(dict)

        for uid, items in matrix.items():
            item_list = list(items.items())
            if len(item_list) < 5:
                # Keep small interaction histories fully in train
                for cid, w in item_list:
                    train_matrix[uid][cid] = w
                continue

            rng.shuffle(item_list)
            n_test = max(1, int(len(item_list) * test_ratio))
            test_items = item_list[:n_test]
            train_items = item_list[n_test:]

            for cid, w in train_items:
                train_matrix[uid][cid] = w
            for cid, w in test_items:
                test_matrix[uid][cid] = w

        return train_matrix, test_matrix

    @classmethod
    def evaluate_model(
        cls,
        model: ALSModel,
        user_index: dict[UUID, int],
        item_index: dict[int, int],
        test_matrix: dict[UUID, dict[int, float]],
        train_matrix: dict[UUID, dict[int, float]],
        k: int = 20,
    ) -> dict[str, float]:
        """
        Compute top-K ranking evaluation metrics (Precision@K, Recall@K, NDCG@K, MRR@K).
        """
        precisions = []
        recalls = []
        ndcgs = []
        mrrs = []

        for uid, test_items in test_matrix.items():
            if uid not in user_index or not test_items:
                continue
            ui = user_index[uid]
            train_seen = set(train_matrix.get(uid, {}).keys())
            train_seen_indices = {item_index[cid] for cid in train_seen if cid in item_index}

            # Top-K recommendations
            recs = model.recommend(ui, n=k, exclude_item_indices=train_seen_indices)
            rec_cids = []
            inv_item_map = {idx: cid for cid, idx in item_index.items()}
            for idx, _ in recs:
                if idx in inv_item_map:
                    rec_cids.append(inv_item_map[idx])

            test_target_set = set(test_items.keys())
            hits = [cid for cid in rec_cids if cid in test_target_set]

            # Precision & Recall @ K
            p_k = len(hits) / float(k)
            r_k = len(hits) / float(len(test_target_set)) if test_target_set else 0.0
            precisions.append(p_k)
            recalls.append(r_k)

            # MRR @ K
            mrr_k = 0.0
            for rank_idx, cid in enumerate(rec_cids, 1):
                if cid in test_target_set:
                    mrr_k = 1.0 / rank_idx
                    break
            mrrs.append(mrr_k)

            # NDCG @ K
            dcg = 0.0
            idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(test_target_set), k)))
            for rank_idx, cid in enumerate(rec_cids):
                if cid in test_target_set:
                    dcg += 1.0 / math.log2(rank_idx + 2)
            ndcg_k = (dcg / idcg) if idcg > 0 else 0.0
            ndcgs.append(ndcg_k)

        return {
            f"precision@{k}": round(float(np.mean(precisions)), 4) if precisions else 0.0,
            f"recall@{k}": round(float(np.mean(recalls)), 4) if recalls else 0.0,
            f"ndcg@{k}": round(float(np.mean(ndcgs)), 4) if ndcgs else 0.0,
            f"mrr@{k}": round(float(np.mean(mrrs)), 4) if mrrs else 0.0,
        }

    @classmethod
    def train_and_persist(cls, db: Session, evaluate: bool = True) -> dict:
        """
        Train ALS on current interactions, evaluate on train/test split, and persist factors.
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

        # 1. Train / Test Evaluation Split
        eval_metrics = {}
        if evaluate and total_interactions >= 20:
            train_matrix, test_matrix = cls.train_test_split(matrix, test_ratio=0.2, seed=params["seed"])
            R_train = np.zeros((len(user_ids), len(item_ids)), dtype=np.float64)
            for uid, items in train_matrix.items():
                ui = user_index[uid]
                for cid, w in items.items():
                    if cid in item_index:
                        R_train[ui, item_index[cid]] = w

            eval_factors = min(params["factors"], max(1, min(len(user_ids), len(item_ids)) - 1))
            eval_model = ALSModel(
                factors=eval_factors,
                regularization=params["regularization"],
                alpha=params["alpha"],
                iterations=params["iterations"],
                seed=params["seed"],
            ).fit(R_train)

            eval_metrics = cls.evaluate_model(
                model=eval_model,
                user_index=user_index,
                item_index=item_index,
                test_matrix=test_matrix,
                train_matrix=train_matrix,
                k=20,
            )
            logger.info("ALS evaluation metrics on test split: %s", eval_metrics)

        # 2. Fit Full Model on all interactions for production factor persistence
        R_full = np.zeros((len(user_ids), len(item_ids)), dtype=np.float64)
        for uid, items in matrix.items():
            ui = user_index[uid]
            for cid, w in items.items():
                R_full[ui, item_index[cid]] = w

        factors = min(params["factors"], max(1, min(len(user_ids), len(item_ids)) - 1))

        model = ALSModel(
            factors=factors,
            regularization=params["regularization"],
            alpha=params["alpha"],
            iterations=params["iterations"],
            seed=params["seed"],
        ).fit(R_full)

        model_version = f"als-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-f{factors}"

        # Wholesale replacement keeps the persisted factors internally consistent
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
            "evaluation_metrics": eval_metrics,
        }
