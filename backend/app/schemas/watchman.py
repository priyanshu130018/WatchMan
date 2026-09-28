"""Pydantic schemas for the WatchMan scoring and decision system."""

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class WatchmanDecisionEnum(str, Enum):
    MUST_WATCH = "must_watch"
    TIME_PASS = "time_pass"
    SKIP = "skip"


class WatchmanDecisionRequest(BaseModel):
    decision: WatchmanDecisionEnum
    content_type: str = Field(default="movie", pattern="^(movie|tv)$")


class WatchmanCommunityCounts(BaseModel):
    must_watch: int = 0
    time_pass: int = 0
    skip: int = 0
    total: int = 0

    model_config = ConfigDict(from_attributes=True)


class WatchmanScoreResponse(BaseModel):
    content_id: int
    content_type: str = "movie"
    base_score: float
    final_score: float
    watchman_label: str  # "must_watch" | "time_pass" | "skip"
    label_display: str  # "MUST WATCH" | "TIME PASS" | "SKIP"
    user_decision: str | None = None
    community_counts: WatchmanCommunityCounts

    model_config = ConfigDict(from_attributes=True)
