"""Pydantic schemas and DTOs for the Unified Content domain and TMDB integration."""

from __future__ import annotations

from typing import Any, Generic, TypeVar
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import CONTENT_PAGE_SIZE

T = TypeVar("T")


class ContentPaginationResponse(BaseModel, Generic[T]):
    """Generic paginated envelope for catalog, listing, and search endpoints.

    Wraps a page of ``results`` with the pagination metadata the frontend grids
    expect (page/limit/total/total_pages). Exposes both ``limit``/``total`` and
    ``page_size``/``total_results`` for complete API client compatibility.
    """

    page: int
    limit: int
    total: int
    total_pages: int
    results: list[T]
    page_size: int | None = None
    total_results: int | None = None

    @model_validator(mode="after")
    def populate_pagination_aliases(self) -> "ContentPaginationResponse[T]":
        if self.page_size is None:
            self.page_size = self.limit
        if self.total_results is None:
            self.total_results = self.total
        return self

    model_config = ConfigDict(from_attributes=True)


class GenreDTO(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class LanguageDTO(BaseModel):
    code: str
    name: str | None = None
    english_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CastMemberDTO(BaseModel):
    id: int
    name: str
    original_name: str | None = None
    character: str | None = None
    profile_path: str | None = None
    order: int | None = None

    model_config = ConfigDict(from_attributes=True)


class CrewMemberDTO(BaseModel):
    id: int
    name: str
    original_name: str | None = None
    department: str | None = None
    job: str | None = None
    profile_path: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ExternalIdDTO(BaseModel):
    provider: str
    external_id: str

    model_config = ConfigDict(from_attributes=True)


class RatingDTO(BaseModel):
    """A rating from an external provider (e.g. IMDb, Rotten Tomatoes, Metacritic)."""
    source: str
    value: str

    model_config = ConfigDict(from_attributes=True)


class VideoDTO(BaseModel):
    id: int | None = None
    key: str
    site: str = "YouTube"
    name: str | None = None
    type: str | None = None
    official: bool = False

    model_config = ConfigDict(from_attributes=True)


class ContentSummaryDTO(BaseModel):
    """Normalized content card for lists, rows, and search results."""
    id: int
    tmdb_id: int
    content_type: str = "movie"
    title: str
    original_title: str | None = None
    overview: str | None = None
    release_date: str | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None
    vote_average: float = 0.0
    vote_count: int = 0
    popularity: float = 0.0
    runtime: int | None = None
    number_of_seasons: int | None = None
    number_of_episodes: int | None = None
    genres: list[GenreDTO] = Field(default_factory=list)
    watchman_score: float | None = None
    watchman_label: str | None = None

    model_config = ConfigDict(from_attributes=True)


# Backward compatibility alias
ContentCardResponse = ContentSummaryDTO


class ContentDetailResponse(BaseModel):
    """Comprehensive content response including relational entities."""
    id: int
    tmdb_id: int
    content_type: str = "movie"
    title: str
    original_title: str | None = None
    overview: str | None = None
    release_date: str | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None
    original_language: str | None = None
    popularity: float = 0.0
    vote_average: float = 0.0
    vote_count: int = 0
    adult: bool = False
    runtime: int | None = None
    status: str | None = None
    tagline: str | None = None
    homepage: str | None = None
    number_of_seasons: int | None = None
    number_of_episodes: int | None = None
    genres: list[GenreDTO] = Field(default_factory=list)
    languages: list[LanguageDTO] = Field(default_factory=list)
    cast: list[CastMemberDTO] = Field(default_factory=list)
    crew: list[CrewMemberDTO] = Field(default_factory=list)
    external_ids: list[ExternalIdDTO] = Field(default_factory=list)
    videos: list[VideoDTO] = Field(default_factory=list)

    # External ratings (IMDb / Rotten Tomatoes / Metacritic) sourced via OMDb.
    imdb_rating: str | None = None
    imdb_votes: str | None = None
    ratings: list[RatingDTO] = Field(default_factory=list)
    watchman_score: float | None = None
    watchman_label: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ContentFilterParams(BaseModel):
    content_type: str | None = None
    genre_ids: list[int] | None = None
    language_code: str | None = None
    year: int | None = None
    sort_by: str = "popularity_desc"
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=CONTENT_PAGE_SIZE, ge=1, le=100)


class SearchQueryParams(BaseModel):
    q: str | None = None
    type: str = Field(default="all", pattern="^(all|movie|tv)$")
    genre: int | None = None
    language: str | None = None
    year: int | None = None
    sort: str = "popularity_desc"
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=CONTENT_PAGE_SIZE, ge=1, le=100)


class MovieSyncRequest(BaseModel):
    movie_id: int


class WebSeriesSyncRequest(BaseModel):
    tv_id: int


class ContentSyncRequest(BaseModel):
    content_type: str = Field(default="movie", pattern="^(movie|tv)$")
    tmdb_id: int


class ContentSyncResponse(BaseModel):
    status: str = "success"
    message: str
    content: ContentSummaryDTO
