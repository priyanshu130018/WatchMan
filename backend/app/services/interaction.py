import uuid
from typing import Any, Optional
from sqlalchemy.orm import Session

from app.models.interaction import InteractionEvent
from app.core.logger import logger


def enqueue_interaction_ml_update(user_id: uuid.UUID | str, content_id: int) -> None:
    """
    Enqueues an asynchronous background Celery task to:
    a. Ensure the interacted content has a content embedding.
    b. Recompute that user's user_embedding.
    c. Recompute that user's recommendations.

    Does NOT run expensive embedding/recommendation generation synchronously inside the HTTP request.
    """
    if not user_id or not content_id:
        return
    try:
        from app.tasks.recommendation import process_user_interaction_ml
        process_user_interaction_ml.delay(str(user_id), int(content_id))
    except Exception as exc:
        logger.warning(
            "Failed to enqueue background ML update for user %s, content %s: %s",
            user_id, content_id, exc
        )


class InteractionTrackingService:
    """Best-effort user behavioral telemetry service for collaborative filtering and analytics."""

    ML_TRIGGER_EVENTS = {"watch", "save", "rate", "review", "watchman_decision"}

    @staticmethod
    def log_event(
        db: Session,
        *,
        event_type: str,
        user_id: Optional[uuid.UUID | str] = None,
        content_id: Optional[int] = None,
        event_value: Optional[float] = None,
        event_data: Optional[dict[str, Any]] = None,
    ) -> Optional[InteractionEvent]:
        """
        Record a user interaction event asynchronously or best-effort synchronously.
        Failures are captured and logged without interrupting the parent transaction.
        When a genuine user interaction occurs, enqueues the background ML update.
        """
        try:
            parsed_user_id = None
            if user_id:
                try:
                    parsed_user_id = uuid.UUID(str(user_id))
                except (ValueError, TypeError):
                    parsed_user_id = None

            # Filter out sensitive fields from event_data if any were passed
            clean_event_data = {}
            if event_data:
                sensitive_keys = {"password", "token", "access_token", "refresh_token", "secret", "authorization"}
                clean_event_data = {
                    k: v for k, v in event_data.items()
                    if k.lower() not in sensitive_keys
                }

            event = InteractionEvent(
                user_id=parsed_user_id,
                content_id=content_id,
                event_type=event_type,
                event_value=event_value,
                event_data=clean_event_data or None,
            )
            db.add(event)
            db.commit()

            # Trigger background ML update for genuine user activity
            if parsed_user_id and content_id and event_type in InteractionTrackingService.ML_TRIGGER_EVENTS:
                enqueue_interaction_ml_update(parsed_user_id, content_id)

            return event
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning(f"Best-effort telemetry recording failed for event '{event_type}': {e}")
            return None
