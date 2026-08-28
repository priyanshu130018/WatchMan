from pydantic import BaseModel
from typing import Optional


class SearchQuery(BaseModel):
    query: str
    page: Optional[int] = 1


class MovieSearchResult(BaseModel):
    id: int
    title: str
    overview: Optional[str] = None
    poster_path: Optional[str] = None
    release_date: Optional[str] = None
    vote_average: Optional[float] = None


class SearchResponse(BaseModel):
    page: int
    total_pages: int
    total_results: int
    results: list[MovieSearchResult]