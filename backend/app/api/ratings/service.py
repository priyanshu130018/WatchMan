from sqlalchemy.orm import Session

from app.database.models.rating import Rating


class RatingService:
    @staticmethod
    def upsert(
        db: Session, *, user_id: object, movie_id: int, value: float, review: str | None
    ) -> Rating:
        rating = (
            db.query(Rating)
            .filter(Rating.user_id == user_id, Rating.movie_id == movie_id)
            .first()
        )
        if rating is None:
            rating = Rating(user_id=user_id, movie_id=movie_id, rating=value, review=review)
            db.add(rating)
        else:
            rating.rating = value
            rating.review = review

        db.commit()
        db.refresh(rating)
        return rating

    @staticmethod
    def get_for_user(db: Session, user_id: object) -> list[Rating]:
        return (
            db.query(Rating)
            .filter(Rating.user_id == user_id)
            .order_by(Rating.updated_at.desc())
            .all()
        )
