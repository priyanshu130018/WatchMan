import uuid
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Rating(Base):
    """User rating and optional short review on unified Content."""
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "content_id", name="uq_user_content_rating"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    review: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

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


class Review(Base):
    """Long-form review for unified Content."""
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="published", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    content_item = relationship("Content", lazy="joined")
    user = relationship("User", lazy="joined")
