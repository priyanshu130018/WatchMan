from pydantic import BaseModel
from datetime import datetime


class WatchHistoryCreate(BaseModel):
    movie_id: int
    progress: float = 0.0


class WatchHistoryUpdate(BaseModel):
    progress: float


class WatchHistoryResponse(BaseModel):
    id: int
    user_id: str
    movie_id: int
    progress: float
    watched_at: datetime

    class Config:
        from_attributes = True