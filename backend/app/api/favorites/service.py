from sqlalchemy.orm import Session
from app.models.favorite import Favorite


class FavoriteService:

    @staticmethod
    def get_all(db: Session, user_id: str):
        return (
            db.query(Favorite)
            .filter(Favorite.user_id == user_id)
            .all()
        )

    @staticmethod
    def add(db: Session, user_id: str, movie_id: int):
        favorite = Favorite(
            user_id=user_id,
            movie_id=movie_id,
        )

        db.add(favorite)
        db.commit()
        db.refresh(favorite)

        return favorite

    @staticmethod
    def delete(db: Session, favorite_id: int):
        favorite = (
            db.query(Favorite)
            .filter(Favorite.id == favorite_id)
            .first()
        )

        if favorite:
            db.delete(favorite)
            db.commit()

        return favorite