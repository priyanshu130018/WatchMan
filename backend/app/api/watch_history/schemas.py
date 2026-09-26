from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.content import ContentSummaryDTO


class WatchHistoryCreate(BaseModel):
    content_type: Optional[str] = Field(default="movie", pattern="^(movie|tv)$")
    tmdb_id: Optional[int] = None
    content_id: Optional[int] = None
    movie_id: Optional[int] = None
    progress: float = Field(default=0.0, ge=0.0)
    completed: bool = False


class WatchHistoryUpdate(BaseModel):
    progress: float = Field(..., ge=0.0)
    completed: Optional[bool] = None


class WatchHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    content_id: int
    movie_id: int
    progress: float
    completed: bool = False
    watched_at: datetime
    content: Optional[ContentSummaryDTO] = None


class PaginatedWatchHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page: int
    limit: int
    total: int
    total_pages: int
    results: list[WatchHistoryResponse] = Field(default_factory=list)