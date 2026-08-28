from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.favorites.schemas import (
    FavoriteCreate,
    FavoriteResponse,
)
from app.api.favorites.service import FavoriteService

router = APIRouter(
    prefix="/favorites",
    tags=["Favorites"],
)


@router.get("/", response_model=list[FavoriteResponse])
def get_favorites(
    user_id: str,
    db: Session = Depends(get_db),
):
    return FavoriteService.get_all(db, user_id)


@router.post("/", response_model=FavoriteResponse)
def add_favorite(
    favorite: FavoriteCreate,
    user_id: str,
    db: Session = Depends(get_db),
):
    return FavoriteService.add(
        db,
        user_id,
        favorite.movie_id,
    )


@router.delete("/{favorite_id}")
def remove_favorite(
    favorite_id: int,
    db: Session = Depends(get_db),
):
    deleted = FavoriteService.delete(db, favorite_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Favorite not found",
        )

    return {"message": "Favorite removed"}