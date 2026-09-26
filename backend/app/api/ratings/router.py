from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.ratings.schemas import RatingResponse, RatingUpsert, PaginatedRatingsResponse
from app.api.ratings.service import RatingService
from app.core.security import get_current_user
from app.core.exceptions import NotFoundException, ValidationException
from app.models.user import User
from app.models.content import Content, ContentType
from app.models.review import Rating
from app.db.session import get_db
from app.services.catalog import ContentCatalogService
from app.repositories.content_repository import ContentRepository

router = APIRouter(prefix="/ratings", tags=["Ratings"])
catalog = ContentCatalogService()


def _to_rating_dto(item: Rating) -> RatingResponse:
    content_dto = None
    if item.content:
        content_dto = catalog.content_to_summary_dto(item.content)
    return RatingResponse(
        id=item.id,
        user_id=str(item.user_id),
        content_id=item.content_id,
        movie_id=item.content_id,
        rating=item.rating,
        review=item.review,
        created_at=item.created_at,
        updated_at=item.updated_at,
        content=content_dto,
    )


@router.get("/", response_model=list[RatingResponse])
@router.get("", response_model=list[RatingResponse])
def get_my_ratings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve all ratings submitted by the authenticated user."""
    items = RatingService.get_for_user(db, current_user.id)
    return [_to_rating_dto(r) for r in items]


@router.get("/paginated", response_model=PaginatedRatingsResponse)
def get_my_ratings_paginated(
    page: int = Query(1, ge=1),
    limit: int = Query(16, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve paginated ratings submitted by the authenticated user."""
    items, total, total_pages = RatingService.get_paginated(db, current_user.id, page=page, limit=limit)
    return PaginatedRatingsResponse(
        page=page,
        limit=limit,
        total=total,
        total_pages=total_pages,
        results=[_to_rating_dto(r) for r in items],
    )


@router.get("/{content_type}/{tmdb_id}", response_model=RatingResponse)
async def get_my_content_rating(
    content_type: str,
    tmdb_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the authenticated user's rating for a specific content item."""
    content = ContentRepository.get_by_tmdb_id(db, content_type, tmdb_id)
    if not content:
        raise NotFoundException(f"{content_type.capitalize()} with TMDB ID {tmdb_id} not found.")

    rating = RatingService.get_by_content(db, current_user.id, content.id)
    if not rating:
        raise NotFoundException("You have not rated this title yet.")

    return _to_rating_dto(rating)


@router.post("/", response_model=RatingResponse)
@router.post("", response_model=RatingResponse)
async def create_rating(
    payload: RatingUpsert,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update rating for a content item."""
    content_id = payload.content_id
    if content_id is None:
        if payload.tmdb_id is not None:
            content_type = payload.content_type or ContentType.MOVIE.value
            content = await catalog.ensure_content(db, content_type, payload.tmdb_id)
            content_id = content.id
        else:
            raise ValidationException("Either tmdb_id or content_id must be provided.")

    rating = RatingService.upsert(
        db,
        user_id=current_user.id,
        content_id=content_id,
        value=payload.rating,
        review=payload.review,
    )
    return _to_rating_dto(rating)


@router.put("/{content_type}/{tmdb_id}", response_model=RatingResponse)
async def upsert_rating_by_tmdb(
    content_type: str,
    tmdb_id: int,
    payload: RatingUpsert,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update a rating for a specific movie or TV show by TMDB ID."""
    content = await catalog.ensure_content(db, content_type, tmdb_id)
    rating = RatingService.upsert(
        db,
        user_id=current_user.id,
        content_id=content.id,
        value=payload.rating,
        review=payload.review,
    )
    return _to_rating_dto(rating)


@router.put("/{movie_id}", response_model=RatingResponse)
async def upsert_rating_legacy(
    movie_id: int,
    payload: RatingUpsert,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update rating by internal content ID or movie TMDB ID."""
    existing_by_id = db.query(Content).filter(Content.id == movie_id).first()
    if existing_by_id:
        target_content_id = existing_by_id.id
    else:
        content = await catalog.ensure_movie(db, movie_id)
        target_content_id = content.id

    rating = RatingService.upsert(
        db,
        user_id=current_user.id,
        content_id=target_content_id,
        value=payload.rating,
        review=payload.review,
    )
    return _to_rating_dto(rating)


@router.delete("/{content_type}/{tmdb_id}")
async def delete_rating_by_tmdb(
    content_type: str,
    tmdb_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete authenticated user's rating for a specific item by TMDB ID."""
    content = ContentRepository.get_by_tmdb_id(db, content_type, tmdb_id)
    if not content:
        raise NotFoundException(f"{content_type.capitalize()} not found.")

    RatingService.delete(db, current_user.id, content.id)
    return {"message": "Rating deleted successfully"}


@router.delete("/{movie_id}")
def delete_rating_by_id(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete authenticated user's rating by content ID."""
    RatingService.delete(db, current_user.id, movie_id)
    return {"message": "Rating deleted successfully"}
