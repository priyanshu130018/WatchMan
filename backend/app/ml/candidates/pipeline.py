from typing import Any
from uuid import UUID
from sqlalchemy.orm import Session

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
        content: Content,
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
        Retrieves all content IDs that the user has already interacted with.
        """
        seen: set[int] = set()

        for s in db.query(SavedContent.content_id).filter(SavedContent.user_id == user_id).all():
            seen.add(s[0])

        for r in db.query(Rating.content_id).filter(Rating.user_id == user_id).all():
            seen.add(r[0])

        for w in db.query(WatchHistory.content_id).filter(WatchHistory.user_id == user_id).all():
            seen.add(w[0])

        for ev in (
            db.query(InteractionEvent.content_id)
            .filter(
                InteractionEvent.user_id == user_id,
                InteractionEvent.event_type.in_(["save", "rate", "watch"]),
            )
            .all()
        ):
            seen.add(ev[0])

        # Content explicitly skipped by user in WatchMan decisions
        from app.models.watchman import WatchmanDecision

        for d in (
            db.query(WatchmanDecision.content_id)
            .filter(
                WatchmanDecision.user_id == user_id,
                WatchmanDecision.decision == "skip",
            )
            .all()
        ):
            seen.add(d[0])

        for ev in (
            db.query(InteractionEvent.content_id)
            .filter(
                InteractionEvent.user_id == user_id,
                InteractionEvent.event_type == "watchman_decision",
                InteractionEvent.event_value == 0.0,
            )
            .all()
        ):
            if ev[0] is not None:
                seen.add(ev[0])

        return seen

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

        ``persist_candidates`` defaults to False: the production path
        (RecommendationGenerator) persists only the final ranked ``Recommendation``
        rows, not the intermediate candidate pool. Set it True only for
        offline debugging/inspection of the raw candidate set; the
        ``cleanup_orphan_candidates`` Celery task prunes any rows written that way.
        """
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
                items_map[cid] = CandidateItem(content_id=cid, content=c["content"])
            items_map[cid].content_score = max(items_map[cid].content_score, c["score"])
            items_map[cid].sources.append("content_based")
            items_map[cid].explanations.append(c["explanation"])

        for c in collab_candidates:
            cid = c["content_id"]
            if cid not in items_map:
                items_map[cid] = CandidateItem(content_id=cid, content=c["content"])
            items_map[cid].collaborative_score = max(items_map[cid].collaborative_score, c["score"])
            items_map[cid].sources.append("collaborative")
            items_map[cid].explanations.append(c["explanation"])

        for c in pop_candidates:
            cid = c["content_id"]
            if cid not in items_map:
                items_map[cid] = CandidateItem(content_id=cid, content=c["content"])
            items_map[cid].popularity_score = max(items_map[cid].popularity_score, c["score"])
            if "popularity" not in items_map[cid].sources:
                items_map[cid].sources.append("popularity")
                items_map[cid].explanations.append(c["explanation"])

        for c in fresh_candidates:
            cid = c["content_id"]
            if cid not in items_map:
                items_map[cid] = CandidateItem(content_id=cid, content=c["content"])
            items_map[cid].freshness_score = max(items_map[cid].freshness_score, c["score"])
            if "freshness" not in items_map[cid].sources:
                items_map[cid].sources.append("freshness")
                items_map[cid].explanations.append(c["explanation"])

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
