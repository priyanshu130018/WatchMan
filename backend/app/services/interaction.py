import uuid
from typing import Any, Optional
from sqlalchemy.orm import Session

from app.models.interaction import InteractionEvent
from app.core.logger import logger


class InteractionTrackingService:
    """Best-effort user behavioral telemetry service for collaborative filtering and analytics."""

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
            return event
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            logger.warning(f"Best-effort telemetry recording failed for event '{event_type}': {e}")
            return None
