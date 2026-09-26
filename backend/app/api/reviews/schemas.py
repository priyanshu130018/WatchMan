from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.content import ContentSummaryDTO


class ReviewAuthor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class ReviewCreate(BaseModel):
    content_type: Optional[str] = Field(default="movie", pattern="^(movie|tv)$")
    tmdb_id: Optional[int] = None
    content_id: Optional[int] = None
    title: Optional[str] = Field(default=None, max_length=255)
    content: str = Field(..., min_length=1, max_length=10_000)
    rating: Optional[float] = Field(default=None, ge=0.5, le=10.0)


class ReviewUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    content: Optional[str] = Field(default=None, min_length=1, max_length=10_000)
    rating: Optional[float] = Field(default=None, ge=0.5, le=10.0)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    content_id: int
    title: Optional[str] = None
    content: str
    rating: Optional[float] = None
    status: str = "published"
    created_at: datetime
    updated_at: datetime
    author: Optional[ReviewAuthor] = None
    content_item: Optional[ContentSummaryDTO] = None


class PaginatedReviewsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page: int
    limit: int
    total: int
    total_pages: int
    results: list[ReviewResponse] = Field(default_factory=list)
