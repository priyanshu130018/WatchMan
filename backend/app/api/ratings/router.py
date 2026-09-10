from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.ratings.schemas import RatingResponse, RatingUpsert
from app.api.ratings.service import RatingService
from app.core.security import get_current_user
from app.database.models.user import User
from app.database.session import get_db
from app.services.catalog import MovieCatalogService

router = APIRouter(prefix="/ratings", tags=["Ratings"])
catalog = MovieCatalogService()


@router.get("/", response_model=list[RatingResponse])
def get_my_ratings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return RatingService.get_for_user(db, current_user.id)


@router.put("/{movie_id}", response_model=RatingResponse)
async def upsert_rating(
    movie_id: int,
    payload: RatingUpsert,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update an explicit preference for hybrid recommendations."""
    await catalog.ensure_movie(db, movie_id)
    return RatingService.upsert(
        db,
        user_id=current_user.id,
        movie_id=movie_id,
        value=payload.rating,
        review=payload.review,
    )
