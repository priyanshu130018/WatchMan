from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.content import Content, ContentType
from app.models.interaction import SavedContent
from app.core.security import get_current_user
from app.core.exceptions import (
    FavoriteNotFoundException,
    NotFoundException,
    ValidationException,
)
from app.services.catalog import ContentCatalogService
from app.repositories.content_repository import ContentRepository
from app.api.favorites.schemas import (
    SavedContentCreate,
    SavedContentResponse,
    PaginatedSavedResponse,
)
from app.api.favorites.service import FavoriteService

router = APIRouter(
    tags=["Saved Content & Favorites"],
)
catalog = ContentCatalogService()


def _to_response_dto(item: SavedContent) -> SavedContentResponse:
    content_dto = None
    if item.content:
        content_dto = catalog.content_to_summary_dto(item.content)
    return SavedContentResponse(
        id=item.id,
        user_id=str(item.user_id),
        content_id=item.content_id,
        movie_id=item.content_id,
        created_at=item.created_at,
        content=content_dto,
    )


@router.get("/saved", response_model=list[SavedContentResponse])
@router.get("/favorites", response_model=list[SavedContentResponse])
@router.get("/favorites/", response_model=list[SavedContentResponse])
def get_saved_content(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all saved/favorite items for the authenticated user."""
    items = FavoriteService.get_all(db, str(current_user.id))
    return [_to_response_dto(item) for item in items]


@router.get("/saved/paginated", response_model=PaginatedSavedResponse)
def get_saved_content_paginated(
    page: int = Query(1, ge=1),
    limit: int = Query(16, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get paginated saved content items for the authenticated user."""
    items, total, total_pages = FavoriteService.get_paginated(db, str(current_user.id), page=page, limit=limit)
    return PaginatedSavedResponse(
        page=page,
        limit=limit,
        total=total,
        total_pages=total_pages,
        results=[_to_response_dto(item) for item in items],
    )


@router.post("/saved", response_model=SavedContentResponse)
@router.post("/favorites", response_model=SavedContentResponse)
@router.post("/favorites/", response_model=SavedContentResponse)
async def add_saved_content(
    payload: SavedContentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a movie or TV show to saved items / favorites."""
    content_id: Optional[int] = payload.content_id

    if content_id is None:
        if payload.tmdb_id is not None:
            content_type = payload.content_type or ContentType.MOVIE.value
            content = await catalog.ensure_content(db, content_type, payload.tmdb_id)
            content_id = content.id
        elif payload.movie_id is not None:
            # Check if movie_id refers to internal content_id or TMDB ID
            existing_by_id = db.query(Content).filter(Content.id == payload.movie_id).first()
            if existing_by_id:
                content_id = existing_by_id.id
            else:
                content = await catalog.ensure_movie(db, payload.movie_id)
                content_id = content.id
        else:
            raise ValidationException(
                message="Either tmdb_id, movie_id, or content_id must be provided.",
                code="VALIDATION_ERROR",
            )

    saved = FavoriteService.add(
        db,
        str(current_user.id),
        content_id,
    )
    # Refresh/load content relation
    db.refresh(saved)
    return _to_response_dto(saved)


@router.delete("/saved/{content_type}/{tmdb_id}")
async def remove_saved_by_tmdb(
    content_type: str,
    tmdb_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a content item from saved content by content_type and TMDB ID."""
    content = ContentRepository.get_by_tmdb_id(db, content_type, tmdb_id)
    if not content:
        raise FavoriteNotFoundException("Saved content not found.")

    FavoriteService.delete_by_content_id(db, current_user.id, content.id)
    return {"message": "Content removed from saved items successfully"}


@router.delete("/saved/{content_id}")
@router.delete("/favorites/{movie_id}")
def remove_saved_by_id(
    content_id: Optional[int] = None,
    movie_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a content item from saved/favorites by content ID."""
    target_id = content_id if content_id is not None else movie_id
    if target_id is None:
        raise ValidationException("Content ID required.")

    FavoriteService.delete_by_content_id(db, current_user.id, target_id)
    return {"message": "Favorite removed successfully"}
