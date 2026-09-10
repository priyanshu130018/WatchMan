from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models.user import User
from app.core.security import get_current_user
from app.services.catalog import MovieCatalogService
from app.api.favorites.schemas import (
    FavoriteCreate,
    FavoriteResponse,
)
from app.api.favorites.service import FavoriteService

router = APIRouter(
    prefix="/favorites",
    tags=["Favorites"],
)
catalog = MovieCatalogService()


@router.get("/", response_model=list[FavoriteResponse])
def get_favorites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all favorites for the authenticated user"""
    return FavoriteService.get_all(db, str(current_user.id))


@router.post("/", response_model=FavoriteResponse)
async def add_favorite(
    favorite: FavoriteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a movie to favorites"""
    await catalog.ensure_movie(db, favorite.movie_id)
    return FavoriteService.add(
        db,
        str(current_user.id),
        favorite.movie_id,
    )


@router.delete("/{movie_id}")
def remove_favorite(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a movie from favorites"""
    from app.database.models.favorite import Favorite
    
    favorite = db.query(Favorite).filter(
        Favorite.user_id == current_user.id,
        Favorite.movie_id == movie_id
    ).first()
    
    if not favorite:
        raise HTTPException(
            status_code=404,
            detail="Favorite not found",
        )
    
    db.delete(favorite)
    db.commit()
    
    return {"message": "Favorite removed successfully"}
