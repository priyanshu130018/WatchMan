import uuid
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.database.models.favorite import Favorite


class FavoriteService:

    @staticmethod
    def get_all(db: Session, user_id: str):
        """Get all favorites for a user"""
        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, AttributeError):
            return []
        
        return (
            db.query(Favorite)
            .filter(Favorite.user_id == user_uuid)
            .all()
        )

    @staticmethod
    def add(db: Session, user_id: str, movie_id: int):
        """Add a movie to favorites"""
        try:
            user_uuid = uuid.UUID(user_id)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID"
            )
        
        try:
            favorite = Favorite(
                user_id=user_uuid,
                movie_id=movie_id,
            )
            db.add(favorite)
            db.commit()
            db.refresh(favorite)
            return favorite
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Movie already in favorites"
            )

    @staticmethod
    def delete(db: Session, favorite_id: int):
        """Delete a favorite by ID"""
        favorite = (
            db.query(Favorite)
            .filter(Favorite.id == favorite_id)
            .first()
        )

        if favorite:
            db.delete(favorite)
            db.commit()

        return favorite
