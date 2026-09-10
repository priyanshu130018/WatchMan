from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models.user import User
from app.core.security import get_current_user
from app.services.catalog import MovieCatalogService
from app.api.watch_history.schemas import (
    WatchHistoryCreate,
    WatchHistoryUpdate,
    WatchHistoryResponse,
)
from app.api.watch_history.service import WatchHistoryService

router = APIRouter(
    prefix="/watch-history",
    tags=["Watch History"],
)
catalog = MovieCatalogService()


@router.get("/", response_model=list[WatchHistoryResponse])
def get_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get watch history for the authenticated user"""
    return WatchHistoryService.get_all(db, str(current_user.id))


@router.post("/", response_model=WatchHistoryResponse)
async def add_history(
    data: WatchHistoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a movie to watch history"""
    await catalog.ensure_movie(db, data.movie_id)
    return WatchHistoryService.add(
        db,
        str(current_user.id),
        data.movie_id,
        data.progress,
    )


@router.put("/{history_id}")
def update_history(
    history_id: int,
    data: WatchHistoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update watch history progress"""
    from app.database.models.watch_history import WatchHistory
    
    # Verify ownership
    history = db.query(WatchHistory).filter(
        WatchHistory.id == history_id,
        WatchHistory.user_id == current_user.id
    ).first()
    
    if not history:
        raise HTTPException(
            status_code=404,
            detail="Watch history entry not found",
        )
    
    history = WatchHistoryService.update(
        db,
        history_id,
        data.progress,
    )
    
    return history


@router.delete("/{history_id}")
def delete_history(
    history_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a watch history entry"""
    from app.database.models.watch_history import WatchHistory
    
    # Verify ownership
    history = db.query(WatchHistory).filter(
        WatchHistory.id == history_id,
        WatchHistory.user_id == current_user.id
    ).first()
    
    if not history:
        raise HTTPException(
            status_code=404,
            detail="Watch history entry not found",
        )
    
    db.delete(history)
    db.commit()
    
    return {"message": "Watch history entry deleted successfully"}
