import uuid
from typing import Optional
from sqlalchemy.orm import Session, selectinload, joinedload

from app.models.review import Rating
from app.models.content import Content
from app.models.taxonomy import ContentGenre
from app.core.exceptions import NotFoundException
from app.services.interaction import InteractionTrackingService


class RatingService:
    @staticmethod
    def upsert(
        db: Session, *, user_id: uuid.UUID | str, content_id: int, value: float, review: Optional[str] = None
    ) -> Rating:
        user_uuid = uuid.UUID(str(user_id))
        rating = (
            db.query(Rating)
            .filter(Rating.user_id == user_uuid, Rating.content_id == content_id)
            .first()
        )
        if rating is None:
            rating = Rating(user_id=user_uuid, content_id=content_id, rating=value, review=review)
            db.add(rating)
        else:
            rating.rating = value
            rating.review = review

        db.commit()
        db.refresh(rating)

        # Telemetry signal
        InteractionTrackingService.log_event(
            db,
            event_type="rate",
            user_id=user_uuid,
            content_id=content_id,
            event_value=value,
        )

        return rating

    @staticmethod
    def get_for_user(db: Session, user_id: uuid.UUID | str) -> list[Rating]:
        user_uuid = uuid.UUID(str(user_id))
        return (
            db.query(Rating)
            .options(
                selectinload(Rating.content).selectinload(Content.genres).joinedload(ContentGenre.genre)
            )
            .filter(Rating.user_id == user_uuid)
            .order_by(Rating.updated_at.desc())
            .all()
        )

    @staticmethod
    def get_paginated(
        db: Session, user_id: uuid.UUID | str, page: int = 1, limit: int = 16
    ) -> tuple[list[Rating], int, int]:
        user_uuid = uuid.UUID(str(user_id))
        query = (
            db.query(Rating)
            .options(
                selectinload(Rating.content).selectinload(Content.genres).joinedload(ContentGenre.genre)
            )
            .filter(Rating.user_id == user_uuid)
            .order_by(Rating.updated_at.desc())
        )
        total = query.count()
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        skip = (page - 1) * limit
        items = query.offset(skip).limit(limit).all()
        return items, total, total_pages

    @staticmethod
    def get_by_content(db: Session, user_id: uuid.UUID | str, content_id: int) -> Optional[Rating]:
        user_uuid = uuid.UUID(str(user_id))
        return (
            db.query(Rating)
            .options(
                selectinload(Rating.content).selectinload(Content.genres).joinedload(ContentGenre.genre)
            )
            .filter(Rating.user_id == user_uuid, Rating.content_id == content_id)
            .first()
        )

    @staticmethod
    def delete(db: Session, user_id: uuid.UUID | str, content_id: int) -> bool:
        user_uuid = uuid.UUID(str(user_id))
        rating = (
            db.query(Rating)
            .filter(Rating.user_id == user_uuid, Rating.content_id == content_id)
            .first()
        )
        if not rating:
            raise NotFoundException("Rating not found.")

        db.delete(rating)
        db.commit()
        return True
