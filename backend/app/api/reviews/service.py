import uuid
from typing import Optional
from sqlalchemy.orm import Session, selectinload, joinedload

from app.models.review import Review
from app.models.content import Content
from app.models.taxonomy import ContentGenre
from app.models.user import User
from app.core.exceptions import NotFoundException, AuthorizationException
from app.core.security import require_resource_owner
from app.services.interaction import InteractionTrackingService
from app.api.reviews.schemas import ReviewUpdate


class ReviewService:
    @staticmethod
    def create(
        db: Session,
        *,
        user_id: uuid.UUID | str,
        content_id: int,
        title: Optional[str],
        content: str,
        rating: Optional[float] = None,
    ) -> Review:
        user_uuid = uuid.UUID(str(user_id))
        review = Review(
            user_id=user_uuid,
            content_id=content_id,
            title=title.strip() if title else None,
            content=content.strip(),
            rating=rating,
            status="published",
        )
        db.add(review)
        db.commit()
        db.refresh(review)

        # Telemetry signal
        InteractionTrackingService.log_event(
            db,
            event_type="review",
            user_id=user_uuid,
            content_id=content_id,
            event_value=rating,
        )

        return review

    @staticmethod
    def get_paginated_for_content(
        db: Session, content_id: int, page: int = 1, limit: int = 16
    ) -> tuple[list[Review], int, int]:
        query = (
            db.query(Review)
            .options(
                joinedload(Review.user),
                selectinload(Review.content_item).selectinload(Content.genres).joinedload(ContentGenre.genre),
            )
            .filter(Review.content_id == content_id, Review.status == "published")
            .order_by(Review.created_at.desc())
        )
        total = query.count()
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        skip = (page - 1) * limit
        items = query.offset(skip).limit(limit).all()
        return items, total, total_pages

    @staticmethod
    def get_by_id(db: Session, review_id: int) -> Review:
        review = (
            db.query(Review)
            .options(
                joinedload(Review.user),
                selectinload(Review.content_item).selectinload(Content.genres).joinedload(ContentGenre.genre),
            )
            .filter(Review.id == review_id)
            .first()
        )
        if not review:
            raise NotFoundException("Review not found.")
        return review

    @staticmethod
    def update(
        db: Session, review_id: int, user_id: uuid.UUID | str, payload: ReviewUpdate
    ) -> Review:
        review = db.query(Review).filter(Review.id == review_id).first()
        if not review:
            raise NotFoundException("Review not found.")

        # Strict ownership verification
        require_resource_owner(review.user_id, user_id)

        if payload.title is not None:
            review.title = payload.title.strip() if payload.title else None
        if payload.content is not None:
            review.content = payload.content.strip()
        if payload.rating is not None:
            review.rating = payload.rating

        db.commit()
        db.refresh(review)
        return review

    @staticmethod
    def delete(db: Session, review_id: int, user_id: uuid.UUID | str) -> bool:
        review = db.query(Review).filter(Review.id == review_id).first()
        if not review:
            raise NotFoundException("Review not found.")

        # Strict ownership verification
        require_resource_owner(review.user_id, user_id)

        db.delete(review)
        db.commit()
        return True
