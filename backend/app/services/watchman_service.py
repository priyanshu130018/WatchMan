"""WatchMan scoring, classification, and user decision service."""

from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.content import Content
from app.models.interaction import InteractionEvent
from app.models.recommendation import Recommendation
from app.models.watchman import WatchmanDecision
from app.schemas.watchman import (
    WatchmanCommunityCounts,
    WatchmanDecisionEnum,
    WatchmanScoreResponse,
)

# Score adjustment factors
MUST_WATCH_ADJUSTMENT = 12.0
TIME_PASS_ADJUSTMENT = 0.0
SKIP_ADJUSTMENT = -18.0


def get_watchman_label(score: float) -> str:
    """Classify a 0-100 score into WatchMan categories.

    Thresholds:
      75 - 100: must_watch
      45 - 74:  time_pass
      0  - 44:  skip
    """
    if score >= 75.0:
        return "must_watch"
    elif score >= 45.0:
        return "time_pass"
    else:
        return "skip"


def get_watchman_display(label: str) -> str:
    """Return user-facing uppercase label string."""
    mapping = {
        "must_watch": "MUST WATCH",
        "time_pass": "TIME PASS",
        "skip": "SKIP",
    }
    return mapping.get(label, "TIME PASS")


class WatchmanService:
    """Core domain logic for WatchMan scores and user decisions."""

    @classmethod
    def get_community_counts(cls, db: Session, content_id: int) -> WatchmanCommunityCounts:
        """Aggregate community decisions for a given content item."""
        rows = (
            db.query(WatchmanDecision.decision, func.count(WatchmanDecision.id))
            .filter(WatchmanDecision.content_id == content_id)
            .group_by(WatchmanDecision.decision)
            .all()
        )
        counts = {"must_watch": 0, "time_pass": 0, "skip": 0}
        total = 0
        for decision, count in rows:
            if decision in counts:
                counts[decision] = count
                total += count

        return WatchmanCommunityCounts(
            must_watch=counts["must_watch"],
            time_pass=counts["time_pass"],
            skip=counts["skip"],
            total=total,
        )

    @classmethod
    def get_user_decision(
        cls, db: Session, user_id: uuid.UUID, content_id: int
    ) -> WatchmanDecision | None:
        """Fetch existing user decision if present."""
        return (
            db.query(WatchmanDecision)
            .filter(
                WatchmanDecision.user_id == user_id,
                WatchmanDecision.content_id == content_id,
            )
            .first()
        )

    @classmethod
    def compute_watchman_score(
        cls,
        db: Session,
        content: Content,
        user_id: uuid.UUID | None = None,
    ) -> WatchmanScoreResponse:
        """Calculate dynamic WatchMan score combining base signals, community, and personal feedback."""
        # 1. Base Score calculation from vote_average / ratings
        vote_avg = content.vote_average or 0.0
        if vote_avg > 0:
            raw_base = vote_avg * 10.0
        else:
            raw_base = 50.0
        base_score = max(10.0, min(95.0, round(raw_base, 1)))

        # 2. Check for personalized recommendation signal if user is logged in
        if user_id:
            rec = (
                db.query(Recommendation)
                .filter(
                    Recommendation.user_id == user_id,
                    Recommendation.content_id == content.id,
                )
                .first()
            )
            if rec and rec.score is not None:
                # Blend 60% personalized recommendation + 40% base quality
                blended = (rec.score * 100.0) * 0.6 + base_score * 0.4
                base_score = max(10.0, min(95.0, round(blended, 1)))

        # 3. Community feedback adjustment
        community = cls.get_community_counts(db, content.id)
        if community.total > 0:
            # Net sentiment ratio from -1.0 to +1.0
            sentiment_ratio = (community.must_watch - community.skip) / community.total
            community_delta = round(sentiment_ratio * 12.0, 1)
        else:
            community_delta = 0.0

        # 4. User decision adjustment
        user_decision_str: str | None = None
        user_delta = 0.0
        if user_id:
            decision_obj = cls.get_user_decision(db, user_id, content.id)
            if decision_obj:
                user_decision_str = decision_obj.decision
                if decision_obj.decision == "must_watch":
                    user_delta = MUST_WATCH_ADJUSTMENT
                elif decision_obj.decision == "time_pass":
                    user_delta = TIME_PASS_ADJUSTMENT
                elif decision_obj.decision == "skip":
                    user_delta = SKIP_ADJUSTMENT

        # 5. Final calculation strictly clamped between 0 and 100
        total_raw = base_score + community_delta + user_delta
        final_score = max(0.0, min(100.0, round(total_raw, 1)))
        label = get_watchman_label(final_score)
        label_display = get_watchman_display(label)

        return WatchmanScoreResponse(
            content_id=content.id,
            content_type=content.content_type,
            base_score=base_score,
            final_score=final_score,
            watchman_label=label,
            label_display=label_display,
            user_decision=user_decision_str,
            community_counts=community,
        )

    @classmethod
    def upsert_user_decision(
        cls,
        db: Session,
        user_id: uuid.UUID,
        content: Content,
        decision: WatchmanDecisionEnum,
        content_type: str | None = None,
    ) -> WatchmanDecision:
        """Upsert a user decision (must_watch, time_pass, skip) without duplicates."""
        resolved_type = content_type or content.content_type
        decision_val = decision.value if hasattr(decision, "value") else str(decision)
        existing = cls.get_user_decision(db, user_id, content.id)

        if existing:
            existing.decision = decision_val
            existing.content_type = resolved_type
            existing.updated_at = datetime.utcnow()
            record = existing
        else:
            record = WatchmanDecision(
                user_id=user_id,
                content_id=content.id,
                content_type=resolved_type,
                decision=decision_val,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(record)

        # Log an InteractionEvent for collaborative filtering / analytics
        val_map = {"must_watch": 1.0, "time_pass": 0.5, "skip": 0.0}
        event = InteractionEvent(
            user_id=user_id,
            content_id=content.id,
            event_type="watchman_decision",
            event_value=val_map.get(decision_val, 0.5),
            event_data={"decision": decision_val, "content_type": resolved_type},
            created_at=datetime.utcnow(),
        )
        db.add(event)

        db.commit()
        db.refresh(record)

        from app.services.interaction import enqueue_interaction_ml_update
        enqueue_interaction_ml_update(user_id, content.id)

        return record

    @classmethod
    def compute_card_score(cls, item: Content) -> tuple[float, str]:
        """Compute fast static baseline WatchMan score and label for catalog cards."""
        vote_avg = item.vote_average or 0.0
        if vote_avg > 0:
            score = round(vote_avg * 10.0, 1)
        else:
            score = 50.0
        clamped_score = max(0.0, min(100.0, score))
        label = get_watchman_label(clamped_score)
        return clamped_score, label
