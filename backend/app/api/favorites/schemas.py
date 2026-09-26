from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.content import ContentSummaryDTO, GenreDTO


class SavedContentCreate(BaseModel):
    content_type: str = Field(default="movie", pattern="^(movie|tv)$")
    tmdb_id: Optional[int] = None
    content_id: Optional[int] = None
    movie_id: Optional[int] = None


class SavedContentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    content_id: int
    movie_id: int
    created_at: datetime
    content: Optional[ContentSummaryDTO] = None


class PaginatedSavedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page: int
    limit: int
    total: int
    total_pages: int
    results: list[SavedContentResponse] = Field(default_factory=list)


# Backward compatibility aliases
FavoriteCreate = SavedContentCreate
FavoriteResponse = SavedContentResponse