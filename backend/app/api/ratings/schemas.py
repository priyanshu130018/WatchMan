from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.content import ContentSummaryDTO


class RatingUpsert(BaseModel):
    rating: float = Field(..., ge=0.5, le=10.0)
    review: Optional[str] = Field(default=None, max_length=2_000)
    content_type: Optional[str] = Field(default="movie", pattern="^(movie|tv)$")
    tmdb_id: Optional[int] = None
    content_id: Optional[int] = None


class RatingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    content_id: int
    movie_id: int
    rating: float
    review: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    content: Optional[ContentSummaryDTO] = None


class PaginatedRatingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page: int
    limit: int
    total: int
    total_pages: int
    results: list[RatingResponse] = Field(default_factory=list)
