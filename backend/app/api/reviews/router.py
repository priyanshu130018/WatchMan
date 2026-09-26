from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.content import Content, ContentType
from app.models.review import Review
from app.core.security import get_current_user
from app.core.exceptions import NotFoundException, ValidationException
from app.services.catalog import ContentCatalogService
from app.repositories.content_repository import ContentRepository
from app.api.reviews.schemas import (
    ReviewCreate,
    ReviewUpdate,
    ReviewResponse,
    ReviewAuthor,
    PaginatedReviewsResponse,
)
from app.api.reviews.service import ReviewService

router = APIRouter(prefix="/reviews", tags=["Reviews"])
catalog = ContentCatalogService()


def _to_review_dto(item: Review) -> ReviewResponse:
    author = None
    if item.user:
        author = ReviewAuthor(
            id=str(item.user.id),
            username=item.user.username,
            full_name=item.user.full_name,
            avatar_url=item.user.avatar_url,
        )
    content_dto = None
    if item.content_item:
        content_dto = catalog.content_to_summary_dto(item.content_item)

    return ReviewResponse(
        id=item.id,
        user_id=str(item.user_id),
        content_id=item.content_id,
        title=item.title,
        content=item.content,
        rating=item.rating,
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
        author=author,
        content_item=content_dto,
    )


@router.get("/{content_type}/{tmdb_id}", response_model=PaginatedReviewsResponse)
async def get_reviews_for_content(
    content_type: str,
    tmdb_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(16, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Retrieve paginated public reviews for a specific movie or web-series."""
    content = ContentRepository.get_by_tmdb_id(db, content_type, tmdb_id)
    if not content:
        # Return empty list rather than 404 for content with 0 reviews
        return PaginatedReviewsResponse(page=page, limit=limit, total=0, total_pages=0, results=[])

    items, total, total_pages = ReviewService.get_paginated_for_content(
        db, content.id, page=page, limit=limit
    )
    return PaginatedReviewsResponse(
        page=page,
        limit=limit,
        total=total,
        total_pages=total_pages,
        results=[_to_review_dto(r) for r in items],
    )


@router.post("/", response_model=ReviewResponse)
@router.post("", response_model=ReviewResponse)
async def create_review(
    payload: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Publish a review for a movie or TV show."""
    content_id = payload.content_id
    if content_id is None:
        if payload.tmdb_id is not None:
            content_type = payload.content_type or ContentType.MOVIE.value
            content = await catalog.ensure_content(db, content_type, payload.tmdb_id)
            content_id = content.id
        else:
            raise ValidationException("Either tmdb_id or content_id must be provided.")

    review = ReviewService.create(
        db,
        user_id=current_user.id,
        content_id=content_id,
        title=payload.title,
        content=payload.content,
        rating=payload.rating,
    )
    return _to_review_dto(review)


@router.put("/{review_id}", response_model=ReviewResponse)
def update_review(
    review_id: int,
    payload: ReviewUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a review (must be the review author)."""
    review = ReviewService.update(db, review_id, current_user.id, payload)
    return _to_review_dto(review)


@router.delete("/{review_id}")
def delete_review(
    review_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a review (must be the review author)."""
    ReviewService.delete(db, review_id, current_user.id)
    return {"message": "Review deleted successfully"}
