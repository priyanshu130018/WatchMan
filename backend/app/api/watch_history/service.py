import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.database.models.watch_history import WatchHistory


class WatchHistoryService:

    @staticmethod
    def get_all(db: Session, user_id: str):
        """Get all watch history for a user"""
        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, AttributeError):
            return []
        
        return (
            db.query(WatchHistory)
            .filter(WatchHistory.user_id == user_uuid)
            .order_by(WatchHistory.watched_at.desc())
            .all()
        )

    @staticmethod
    def add(db: Session, user_id: str, movie_id: int, progress: float = 0.0):
        """Add a movie to watch history"""
        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID"
            )

        return WatchHistoryService.get_or_create_watch(db, user_uuid, movie_id, progress)

    @staticmethod
    def get_or_create_watch(db: Session, user_id: uuid.UUID, movie_id: int, progress: float):
        """Get existing watch history or create new one"""
        history = (
            db.query(WatchHistory)
            .filter(
                WatchHistory.user_id == user_id,
                WatchHistory.movie_id == movie_id
            )
            .first()
        )
        
        if history:
            history.progress = max(0.0, min(1.0, progress))
            history.completed = history.progress >= 0.9
            history.watched_at = datetime.utcnow()
            db.commit()
            db.refresh(history)
            return history
        
        # Create new entry
        history = WatchHistory(
            user_id=user_id,
            movie_id=movie_id,
            progress=max(0.0, min(1.0, progress)),
            completed=progress >= 0.9,
        )
        db.add(history)
        db.commit()
        db.refresh(history)
        return history

    @staticmethod
    def update(db: Session, history_id: int, progress: float):
        """Update watch history progress"""
        history = (
            db.query(WatchHistory)
            .filter(WatchHistory.id == history_id)
            .first()
        )

        if history:
            history.progress = max(0.0, min(1.0, progress))
            history.completed = history.progress >= 0.9
            history.watched_at = datetime.utcnow()
            db.commit()
            db.refresh(history)

        return history

    @staticmethod
    def delete(db: Session, history_id: int):
        """Delete a watch history entry"""
        history = (
            db.query(WatchHistory)
            .filter(WatchHistory.id == history_id)
            .first()
        )

        if history:
            db.delete(history)
            db.commit()

        return history
