import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SavedContent(Base):
    """User-saved items (favorites / bookmarks / watchlist) referencing unified Content."""
    __tablename__ = "saved_content"
    __table_args__ = (
        UniqueConstraint("user_id", "content_id", name="uq_user_content_saved"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    content = relationship("Content", lazy="joined")
    user = relationship("User", lazy="joined")

    @property
    def movie_id(self) -> int:
        """Backward-compatibility accessor for legacy endpoints."""
        return self.content_id

    @property
    def movie(self):
        """Backward-compatibility accessor for legacy movie relation."""
        return self.content


class WatchHistory(Base):
    """Watch tracking and progress for unified Content items."""
    __tablename__ = "watch_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    watched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    content = relationship("Content", lazy="joined")
    user = relationship("User", lazy="joined")

    @property
    def movie_id(self) -> int:
        """Backward-compatibility accessor for legacy endpoints."""
        return self.content_id

    @property
    def movie(self):
        """Backward-compatibility accessor for legacy movie relation."""
        return self.content


class InteractionEvent(Base):
    """Normalized interaction events (view, click, save, rate, search, etc.) for collaborative filtering."""
    __tablename__ = "interaction_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    content_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), index=True, nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    event_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_data: Mapped[dict | None] = mapped_column(JSON, default=dict, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    content = relationship("Content", lazy="joined")
    user = relationship("User", lazy="joined")


class SearchHistory(Base):
    """Search queries logged per user."""
    __tablename__ = "search_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
