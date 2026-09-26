import uuid
from typing import Optional
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.exceptions import (
    ConflictException,
    DatabaseException,
    FavoriteNotFoundException,
    ValidationException,
)
from app.models.interaction import SavedContent
from app.models.content import Content
from app.models.taxonomy import ContentGenre
from app.services.interaction import InteractionTrackingService


class FavoriteService:

    @staticmethod
    def get_all(db: Session, user_id: str | uuid.UUID) -> list[SavedContent]:
        """Get all saved content items for a user."""
        try:
            user_uuid = uuid.UUID(str(user_id))
        except (ValueError, AttributeError):
            return []
        
        return (
            db.query(SavedContent)
            .options(
                selectinload(SavedContent.content).selectinload(Content.genres).joinedload(ContentGenre.genre)
            )
            .filter(SavedContent.user_id == user_uuid)
            .order_by(SavedContent.created_at.desc())
            .all()
        )

    @staticmethod
    def get_paginated(
        db: Session, user_id: str | uuid.UUID, page: int = 1, limit: int = 16
    ) -> tuple[list[SavedContent], int, int]:
        """Get paginated saved content items for a user."""
        try:
            user_uuid = uuid.UUID(str(user_id))
        except (ValueError, AttributeError):
            return [], 0, 0

        query = (
            db.query(SavedContent)
            .options(
                selectinload(SavedContent.content).selectinload(Content.genres).joinedload(ContentGenre.genre)
            )
            .filter(SavedContent.user_id == user_uuid)
            .order_by(SavedContent.created_at.desc())
        )

        total = query.count()
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        skip = (page - 1) * limit
        items = query.offset(skip).limit(limit).all()

        return items, total, total_pages

    @staticmethod
    def add(db: Session, user_id: str | uuid.UUID, content_id: int) -> SavedContent:
        """Add a content item to saved content."""
        try:
            user_uuid = uuid.UUID(str(user_id))
        except (ValueError, AttributeError):
            raise ValidationException(
                message="Invalid user ID format.",
                code="VALIDATION_ERROR",
            )
        
        try:
            saved = SavedContent(
                user_id=user_uuid,
                content_id=content_id,
            )
            db.add(saved)
            db.commit()
            db.refresh(saved)
            
            # Telemetry signal
            InteractionTrackingService.log_event(
                db,
                event_type="save",
                user_id=user_uuid,
                content_id=content_id,
            )
            
            return saved
        except IntegrityError as e:
            db.rollback()
            raise ConflictException(
                message="Item is already in saved list.",
                code="RESOURCE_CONFLICT",
            ) from e
        except SQLAlchemyError as e:
            db.rollback()
            raise DatabaseException(
                message="Failed to save content.",
                code="DATABASE_ERROR",
            ) from e

    @staticmethod
    def delete_by_content_id(db: Session, user_id: str | uuid.UUID, content_id: int) -> SavedContent:
        """Remove a content item from saved content by content_id for a user."""
        try:
            user_uuid = uuid.UUID(str(user_id))
        except (ValueError, AttributeError):
            raise FavoriteNotFoundException("Saved item not found.")

        saved = (
            db.query(SavedContent)
            .filter(
                SavedContent.user_id == user_uuid,
                SavedContent.content_id == content_id,
            )
            .first()
        )

        if not saved:
            raise FavoriteNotFoundException("Favorite not found.")

        db.delete(saved)
        db.commit()

        InteractionTrackingService.log_event(
            db,
            event_type="unsave",
            user_id=user_uuid,
            content_id=content_id,
        )

        return saved
