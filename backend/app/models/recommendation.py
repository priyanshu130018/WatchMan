import uuid
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RecommendationCandidate(Base):
    """Candidate items generated during the recommendation pipeline."""
    __tablename__ = "recommendation_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    content = relationship("Content", lazy="joined")
    user = relationship("User", lazy="joined")


class Recommendation(Base):
    """Persisted final recommendations scored and ranked for a user."""
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    content = relationship("Content", lazy="joined")
    user = relationship("User", lazy="joined")


class RecommendationCache(Base):
    """Cached recommendation list for quick retrieval."""
    __tablename__ = "recommendation_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recommendations: Mapped[list | dict | None] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
