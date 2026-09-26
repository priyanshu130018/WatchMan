from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ContentType(str, Enum):
    MOVIE = "movie"
    TV = "tv"


class Content(Base):
    """Unified Content entity for movies and web-series/TV shows."""
    __tablename__ = "contents"
    __table_args__ = (
        UniqueConstraint("content_type", "tmdb_id", name="uq_content_type_tmdb_id"),
        Index("ix_contents_content_type", "content_type"),
        Index("ix_contents_tmdb_id", "tmdb_id"),
        Index("ix_contents_type_popularity", "content_type", "popularity"),
        Index("ix_contents_type_release_date", "content_type", "release_date"),
        Index("ix_contents_title", "title"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False, default=ContentType.MOVIE.value)
    tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    original_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    release_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    poster_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    backdrop_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    popularity: Mapped[float] = mapped_column(Float, default=0.0)
    vote_average: Mapped[float] = mapped_column(Float, default=0.0)
    vote_count: Mapped[int] = mapped_column(Integer, default=0)
    adult: Mapped[bool] = mapped_column(Boolean, default=False)
    runtime: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tagline: Mapped[str | None] = mapped_column(Text, nullable=True)
    homepage: Mapped[str | None] = mapped_column(String(500), nullable=True)
    number_of_seasons: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number_of_episodes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    genres = relationship("ContentGenre", cascade="all, delete-orphan", lazy="selectin")
    languages = relationship("ContentLanguage", cascade="all, delete-orphan", lazy="selectin")
    cast = relationship(
        "ContentCast",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ContentCast.cast_order",
    )
    crew = relationship("ContentCrew", cascade="all, delete-orphan", lazy="selectin")
    videos = relationship("ContentVideo", cascade="all, delete-orphan", lazy="selectin")
    external_ids = relationship("ContentExternalId", cascade="all, delete-orphan", lazy="selectin")
    embedding = relationship(
        "ContentEmbedding",
        cascade="all, delete-orphan",
        back_populates="content",
        uselist=False,
    )


class ContentExternalId(Base):
    """Normalized external identifiers (IMDb, TMDB, TVDb, etc.) for Content."""
    __tablename__ = "content_external_ids"
    __table_args__ = (
        UniqueConstraint("content_id", "provider", name="uq_content_external_id_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)


class ContentVideo(Base):
    """Normalized video metadata (trailers, teasers, clips) for Content."""
    __tablename__ = "content_videos"
    __table_args__ = (
        UniqueConstraint("content_id", "key", name="uq_content_video_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    site: Mapped[str] = mapped_column(String(100), default="YouTube", nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[str] = mapped_column(String(100), default="Trailer", nullable=False)
    official: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
