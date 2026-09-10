from datetime import datetime
from sqlalchemy import Integer, String, Text, Float, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    tmdb_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    release_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    poster_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    backdrop_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vote_average: Mapped[float | None] = mapped_column(Float, default=0.0)
    vote_count: Mapped[int | None] = mapped_column(Integer, default=0)
    popularity: Mapped[float | None] = mapped_column(Float, default=0.0)
    genres: Mapped[list | None] = mapped_column(JSON, default=list)
    runtime: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tagline: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list | None] = mapped_column(JSON, default=list)
    cast: Mapped[list | None] = mapped_column(JSON, default=list)
    crew: Mapped[list | None] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
