from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db

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


@router.get("/", response_model=list[WatchHistoryResponse])
def get_history(
    user_id: str,
    db: Session = Depends(get_db),
):
    return WatchHistoryService.get_all(db, user_id)


@router.post("/", response_model=WatchHistoryResponse)
def add_history(
    data: WatchHistoryCreate,
    user_id: str,
    db: Session = Depends(get_db),
):
    return WatchHistoryService.add(
        db,
        user_id,
        data.movie_id,
        data.progress,
    )


@router.put("/{history_id}")
def update_history(
    history_id: int,
    data: WatchHistoryUpdate,
    db: Session = Depends(get_db),
):

    history = WatchHistoryService.update(
        db,
        history_id,
        data.progress,
    )

    if not history:
        raise HTTPException(
            status_code=404,
            detail="History not found",
        )

    return history


@router.delete("/{history_id}")
def delete_history(
    history_id: int,
    db: Session = Depends(get_db),
):

    history = WatchHistoryService.delete(
        db,
        history_id,
    )

    if not history:
        raise HTTPException(
            status_code=404,
            detail="History not found",
        )

    return {"message": "Deleted successfully"}