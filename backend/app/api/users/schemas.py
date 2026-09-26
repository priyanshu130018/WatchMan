from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class GenreSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tmdb_id: int
    name: str


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    username: Optional[str] = Field(default=None, max_length=100)
    avatar_url: Optional[str] = Field(default=None, max_length=1000)


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UserPreferenceUpdate(BaseModel):
    favorite_genres: list[int] = Field(default_factory=list)
    disliked_genres: list[int] = Field(default_factory=list)


class UserPreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    favorite_genres: list[int] = Field(default_factory=list)
    disliked_genres: list[int] = Field(default_factory=list)
    favorite_genre_details: list[GenreSummary] = Field(default_factory=list)
    disliked_genre_details: list[GenreSummary] = Field(default_factory=list)
