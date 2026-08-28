from pydantic import BaseModel
from datetime import datetime


class FavoriteCreate(BaseModel):
    movie_id: int


class FavoriteResponse(BaseModel):
    id: int
    user_id: str
    movie_id: int
    created_at: datetime

    class Config:
        from_attributes = True