from sqlalchemy.orm import Session

from app.models.watch_history import WatchHistory


class WatchHistoryService:

    @staticmethod
    def get_all(db: Session, user_id: str):
        return (
            db.query(WatchHistory)
            .filter(WatchHistory.user_id == user_id)
            .order_by(WatchHistory.watched_at.desc())
            .all()
        )

    @staticmethod
    def add(db: Session, user_id: str, movie_id: int, progress: float):

        history = WatchHistory(
            user_id=user_id,
            movie_id=movie_id,
            progress=progress,
        )

        db.add(history)
        db.commit()
        db.refresh(history)

        return history

    @staticmethod
    def update(db: Session, history_id: int, progress: float):

        history = (
            db.query(WatchHistory)
            .filter(WatchHistory.id == history_id)
            .first()
        )

        if history:
            history.progress = progress
            db.commit()
            db.refresh(history)

        return history

    @staticmethod
    def delete(db: Session, history_id: int):

        history = (
            db.query(WatchHistory)
            .filter(WatchHistory.id == history_id)
            .first()
        )

        if history:
            db.delete(history)
            db.commit()

        return history