from datetime import datetime

from pydantic import BaseModel, Field


class RatingUpsert(BaseModel):
    rating: float = Field(..., ge=1, le=5)
    review: str | None = Field(default=None, max_length=2_000)


class RatingResponse(BaseModel):
    id: int
    user_id: str
    movie_id: int
    rating: float
    review: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
