import time
from typing import Any
from uuid import UUID
from sqlalchemy.orm import Session, selectinload
from app.models.taxonomy import ContentGenre

from app.core.timing import get_current_timing_ctx
from app.models.content import Content
from app.models.interaction import InteractionEvent, SavedContent, WatchHistory
from app.models.recommendation import RecommendationCandidate
from app.models.review import Rating
from app.ml.candidates.content_based import ContentBasedCandidateGenerator
from app.ml.candidates.collaborative import CollaborativeCandidateGenerator
from app.ml.candidates.als_collaborative import ALSCollaborativeCandidateGenerator
from app.ml.candidates.popularity import PopularityCandidateGenerator
from app.ml.candidates.freshness import FreshnessCandidateGenerator


class CandidateItem:
    def __init__(
        self,
        content_id: int,
        content: Content | None = None,
        content_score: float = 0.0,
        collaborative_score: float = 0.0,
        popularity_score: float = 0.0,
        freshness_score: float = 0.0,
        sources: list[str] | None = None,
        explanations: list[str] | None = None,
    ):
        self.content_id = content_id
        self.content = content
        self.content_score = content_score
        self.collaborative_score = collaborative_score
        self.popularity_score = popularity_score
        self.freshness_score = freshness_score
        self.sources = sources or []
        self.explanations = explanations or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_id": self.content_id,
            "content": self.content,
            "content_score": self.content_score,
            "collaborative_score": self.collaborative_score,
            "popularity_score": self.popularity_score,
            "freshness_score": self.freshness_score,
            "sources": self.sources,
            "explanations": self.explanations,
        }


class CandidatePipeline:
    """
    Multi-channel candidate generation pipeline.
    """

    @classmethod
    def get_user_seen_content_ids(cls, db: Session, user_id: UUID) -> set[int]:
        """
        Retrieves all content IDs that the user has already interacted with in a single batched query.
        """
        from sqlalchemy import select, or_, and_
        from app.models.watchman import WatchmanDecision

        saved_q = select(SavedContent.content_id).where(SavedContent.user_id == user_id)
        ratings_q = select(Rating.content_id).where(Rating.user_id == user_id)
        watch_q = select(WatchHistory.content_id).where(WatchHistory.user_id == user_id)
        ev_q = select(InteractionEvent.content_id).where(
            InteractionEvent.user_id == user_id,
            InteractionEvent.content_id.isnot(None),
            or_(
                InteractionEvent.event_type.in_(["save", "rate", "watch"]),
                and_(
                    InteractionEvent.event_type == "watchman_decision",
                    InteractionEvent.event_value == 0.0,
                ),
            ),
        )
        wm_q = select(WatchmanDecision.content_id).where(
            WatchmanDecision.user_id == user_id,
            WatchmanDecision.decision == "skip",
        )

        union_stmt = saved_q.union(ratings_q, watch_q, ev_q, wm_q)
        rows = db.execute(union_stmt).scalars().all()
        return {cid for cid in rows if cid is not None}

    @classmethod
    def generate_all_candidates(
        cls,
        db: Session,
        user_id: UUID,
        limit_per_channel: int = 50,
        content_type: str | None = None,
        persist_candidates: bool = False,
    ) -> list[CandidateItem]:
        """
        Retrieves, deduplicates, and merges candidates from all 4 generation channels.
        """
        t0 = time.perf_counter()
        try:
            return cls._do_generate_all_candidates(
                db=db,
                user_id=user_id,
                limit_per_channel=limit_per_channel,
                content_type=content_type,
                persist_candidates=persist_candidates,
            )
        finally:
            elapsed = (time.perf_counter() - t0) * 1000
            ctx = get_current_timing_ctx()
            if ctx:
                ctx.candidate_retrieval_ms += elapsed

    @classmethod
    def _do_generate_all_candidates(
        cls,
        db: Session,
        user_id: UUID,
        limit_per_channel: int = 50,
        content_type: str | None = None,
        persist_candidates: bool = False,
    ) -> list[CandidateItem]:
        seen_ids = cls.get_user_seen_content_ids(db, user_id)

        # 1. Content-based candidates
        content_candidates = ContentBasedCandidateGenerator.generate_candidates(
            db=db,
            user_id=user_id,
            limit=limit_per_channel,
            content_type=content_type,
            exclude_content_ids=seen_ids,
        )

        # 2. Collaborative candidates.
        #    Primary source is ALS matrix factorization (precomputed latent
        #    factors). If the user has no trained factors yet (cold start /
        #    model not trained), fall back to the memory-based user-user KNN
        #    generator so the channel still contributes.
        collab_candidates = ALSCollaborativeCandidateGenerator.generate_candidates(
            db=db,
            user_id=user_id,
            limit=limit_per_channel,
            content_type=content_type,
            exclude_content_ids=seen_ids,
        )
        if not collab_candidates:
            collab_candidates = CollaborativeCandidateGenerator.generate_candidates(
                db=db,
                user_id=user_id,
                limit=limit_per_channel,
                content_type=content_type,
                exclude_content_ids=seen_ids,
            )

        # 3. Popularity candidates
        pop_candidates = PopularityCandidateGenerator.generate_candidates(
            db=db,
            limit=limit_per_channel,
            content_type=content_type,
            exclude_content_ids=seen_ids,
        )

        # 4. Freshness candidates
        fresh_candidates = FreshnessCandidateGenerator.generate_candidates(
            db=db,
            limit=limit_per_channel,
            content_type=content_type,
            exclude_content_ids=seen_ids,
        )

        # Merge and aggregate into unified CandidateItems
        items_map: dict[int, CandidateItem] = {}

        for c in content_candidates:
            cid = c["content_id"]
            if cid not in items_map:
                items_map[cid] = CandidateItem(content_id=cid, content=c.get("content"))
            items_map[cid].content_score = max(items_map[cid].content_score, c["score"])
            items_map[cid].sources.append("content_based")
            items_map[cid].explanations.append(c["explanation"])

        for c in collab_candidates:
            cid = c["content_id"]
            if cid not in items_map:
                items_map[cid] = CandidateItem(content_id=cid, content=c.get("content"))
            items_map[cid].collaborative_score = max(items_map[cid].collaborative_score, c["score"])
            items_map[cid].sources.append("collaborative")
            items_map[cid].explanations.append(c["explanation"])

        for c in pop_candidates:
            cid = c["content_id"]
            if cid not in items_map:
                items_map[cid] = CandidateItem(content_id=cid, content=c.get("content"))
            items_map[cid].popularity_score = max(items_map[cid].popularity_score, c["score"])
            if "popularity" not in items_map[cid].sources:
                items_map[cid].sources.append("popularity")
                items_map[cid].explanations.append(c["explanation"])

        for c in fresh_candidates:
            cid = c["content_id"]
            if cid not in items_map:
                items_map[cid] = CandidateItem(content_id=cid, content=c.get("content"))
            items_map[cid].freshness_score = max(items_map[cid].freshness_score, c["score"])
            if "freshness" not in items_map[cid].sources:
                items_map[cid].sources.append("freshness")
                items_map[cid].explanations.append(c["explanation"])

        # Batch load Content entities and their genres in a single efficient query
        all_cids = list(items_map.keys())
        if all_cids:
            contents = (
                db.query(Content)
                .filter(Content.id.in_(all_cids))
                .options(selectinload(Content.genres).joinedload(ContentGenre.genre))
                .populate_existing()
                .all()
            )
            content_map = {c.id: c for c in contents}
            for cid in list(items_map.keys()):
                c = content_map.get(cid)
                if c is not None:
                    items_map[cid].content = c
                else:
                    del items_map[cid]

        candidate_list = list(items_map.values())

        if persist_candidates and candidate_list:
            try:
                # Optionally record top candidate snapshots
                for item in candidate_list[:100]:
                    rc = RecommendationCandidate(
                        user_id=user_id,
                        content_id=item.content_id,
                        source=",".join(set(item.sources)),
                        score=max(
                            item.content_score,
                            item.collaborative_score,
                            item.popularity_score,
                            item.freshness_score,
                        ),
                    )
                    db.add(rc)
                db.commit()
            except Exception:
                db.rollback()

        return candidate_list
