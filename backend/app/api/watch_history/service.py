import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import (
    DatabaseException,
    NotFoundException,
    WatchHistoryNotFoundException,
    ValidationException,
)
from app.core.security import require_resource_owner
from app.models.interaction import WatchHistory
from app.models.content import Content
from app.models.taxonomy import ContentGenre
from app.services.interaction import InteractionTrackingService


class WatchHistoryService:

    @staticmethod
    def get_all(db: Session, user_id: str | uuid.UUID) -> list[WatchHistory]:
        """Get all watch history entries for a user."""
        try:
            user_uuid = uuid.UUID(str(user_id))
        except (ValueError, AttributeError):
            return []
        
        return (
            db.query(WatchHistory)
            .options(
                selectinload(WatchHistory.content).selectinload(Content.genres).joinedload(ContentGenre.genre)
            )
            .filter(WatchHistory.user_id == user_uuid)
            .order_by(WatchHistory.watched_at.desc())
            .all()
        )

    @staticmethod
    def get_paginated(
        db: Session, user_id: str | uuid.UUID, page: int = 1, limit: int = 16
    ) -> tuple[list[WatchHistory], int, int]:
        """Get paginated watch history for a user."""
        try:
            user_uuid = uuid.UUID(str(user_id))
        except (ValueError, AttributeError):
            return [], 0, 0

        query = (
            db.query(WatchHistory)
            .options(
                selectinload(WatchHistory.content).selectinload(Content.genres).joinedload(ContentGenre.genre)
            )
            .filter(WatchHistory.user_id == user_uuid)
            .order_by(WatchHistory.watched_at.desc())
        )
        total = query.count()
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        skip = (page - 1) * limit
        items = query.offset(skip).limit(limit).all()
        return items, total, total_pages

    @staticmethod
    def add(
        db: Session,
        user_id: str | uuid.UUID,
        content_id: int,
        progress: float = 0.0,
        completed: bool = False,
    ) -> WatchHistory:
        """Add or update a watch history item."""
        try:
            user_uuid = uuid.UUID(str(user_id))
        except (ValueError, AttributeError):
            raise ValidationException(
                message="Invalid user ID format.",
                code="VALIDATION_ERROR",
            )
        
        try:
            existing = (
                db.query(WatchHistory)
                .filter(WatchHistory.user_id == user_uuid, WatchHistory.content_id == content_id)
                .first()
            )
            if existing:
                existing.progress = progress
                existing.completed = completed
                existing.watched_at = datetime.utcnow()
                history = existing
            else:
                history = WatchHistory(
                    user_id=user_uuid,
                    content_id=content_id,
                    progress=progress,
                    completed=completed,
                    watched_at=datetime.utcnow(),
                )
                db.add(history)

            db.commit()
            db.refresh(history)

            # Telemetry signal
            InteractionTrackingService.log_event(
                db,
                event_type="watch",
                user_id=user_uuid,
                content_id=content_id,
                event_value=progress,
            )

            return history
        except SQLAlchemyError as e:
            db.rollback()
            raise DatabaseException(
                message="Failed to save watch history.",
                code="DATABASE_ERROR",
            ) from e

    @staticmethod
    def update(
        db: Session,
        history_id: int,
        user_id: str | uuid.UUID,
        progress: float,
        completed: Optional[bool] = None,
    ) -> WatchHistory:
        """Update watch progress with strict ownership verification."""
        history = db.query(WatchHistory).filter(WatchHistory.id == history_id).first()
        if not history:
            raise WatchHistoryNotFoundException("Watch history entry not found.")

        require_resource_owner(history.user_id, user_id)

        history.progress = progress
        if completed is not None:
            history.completed = completed
        history.watched_at = datetime.utcnow()

        db.commit()
        db.refresh(history)
        return history

    @staticmethod
    def delete(db: Session, history_id: int, user_id: str | uuid.UUID) -> bool:
        """Delete a watch history entry with strict ownership verification."""
        history = db.query(WatchHistory).filter(WatchHistory.id == history_id).first()
        if not history:
            raise WatchHistoryNotFoundException("Watch history entry not found.")

        require_resource_owner(history.user_id, user_id)

        db.delete(history)
        db.commit()
        return True
