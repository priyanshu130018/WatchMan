from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.content import Content, ContentType
from app.models.interaction import WatchHistory
from app.core.security import get_current_user
from app.core.exceptions import WatchHistoryNotFoundException, ValidationException
from app.services.catalog import ContentCatalogService
from app.repositories.content_repository import ContentRepository
from app.api.watch_history.schemas import (
    WatchHistoryCreate,
    WatchHistoryUpdate,
    WatchHistoryResponse,
    PaginatedWatchHistoryResponse,
)
from app.api.watch_history.service import WatchHistoryService

router = APIRouter(
    prefix="/watch-history",
    tags=["Watch History"],
)
catalog = ContentCatalogService()


def _to_history_dto(item: WatchHistory) -> WatchHistoryResponse:
    content_dto = None
    if item.content:
        content_dto = catalog.content_to_summary_dto(item.content)
    return WatchHistoryResponse(
        id=item.id,
        user_id=str(item.user_id),
        content_id=item.content_id,
        movie_id=item.content_id,
        progress=item.progress,
        completed=item.completed,
        watched_at=item.watched_at,
        content=content_dto,
    )


@router.get("/", response_model=list[WatchHistoryResponse])
@router.get("", response_model=list[WatchHistoryResponse])
def get_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all watch history entries for the authenticated user."""
    items = WatchHistoryService.get_all(db, str(current_user.id))
    return [_to_history_dto(item) for item in items]


@router.get("/paginated", response_model=PaginatedWatchHistoryResponse)
def get_history_paginated(
    page: int = Query(1, ge=1),
    limit: int = Query(16, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get paginated watch history for the authenticated user."""
    items, total, total_pages = WatchHistoryService.get_paginated(
        db, str(current_user.id), page=page, limit=limit
    )
    return PaginatedWatchHistoryResponse(
        page=page,
        limit=limit,
        total=total,
        total_pages=total_pages,
        results=[_to_history_dto(item) for item in items],
    )


@router.post("/", response_model=WatchHistoryResponse)
@router.post("", response_model=WatchHistoryResponse)
async def add_history(
    data: WatchHistoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record progress for a movie or TV show in watch history."""
    content_id = data.content_id
    if content_id is None:
        if data.tmdb_id is not None:
            content_type = data.content_type or ContentType.MOVIE.value
            content = await catalog.ensure_content(db, content_type, data.tmdb_id)
            content_id = content.id
        elif data.movie_id is not None:
            existing_by_id = db.query(Content).filter(Content.id == data.movie_id).first()
            if existing_by_id:
                content_id = existing_by_id.id
            else:
                content = await catalog.ensure_movie(db, data.movie_id)
                content_id = content.id
        else:
            raise ValidationException("Either tmdb_id, movie_id, or content_id must be provided.")

    history = WatchHistoryService.add(
        db,
        str(current_user.id),
        content_id,
        data.progress,
        data.completed,
    )
    db.refresh(history)
    return _to_history_dto(history)


@router.put("/{history_id}", response_model=WatchHistoryResponse)
def update_history(
    history_id: int,
    data: WatchHistoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update progress on a watch history record (must be owner)."""
    history = WatchHistoryService.update(
        db,
        history_id,
        current_user.id,
        data.progress,
        data.completed,
    )
    return _to_history_dto(history)


@router.delete("/{history_id}")
def delete_history(
    history_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a watch history entry (must be owner)."""
    WatchHistoryService.delete(db, history_id, current_user.id)
    return {"message": "Watch history entry deleted successfully"}
