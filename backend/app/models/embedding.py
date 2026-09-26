import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.db.base import Base


class ContentEmbedding(Base):
    """Dense vector embedding for unified Content item."""
    __tablename__ = "content_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    embedding = mapped_column(Vector(settings.VECTOR_DIMENSION), nullable=True)
    model_name: Mapped[str] = mapped_column(String(150), default=settings.EMBEDDING_MODEL, nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, default=settings.VECTOR_DIMENSION, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model_version: Mapped[str | None] = mapped_column(String(100), default="1.0.0", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    content = relationship("Content", back_populates="embedding")

    @property
    def movie_id(self) -> int:
        """Backward-compatibility accessor for legacy embeddings."""
        return self.content_id

    @property
    def movie(self):
        """Backward-compatibility accessor for legacy movie relation."""
        return self.content


class UserEmbedding(Base):
    """Dense vector preference embedding for User."""
    __tablename__ = "user_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    embedding = mapped_column(Vector(settings.VECTOR_DIMENSION), nullable=True)
    model_name: Mapped[str] = mapped_column(String(150), default=settings.EMBEDDING_MODEL, nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, default=settings.VECTOR_DIMENSION, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(100), default="1.0.0", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user = relationship("User", lazy="joined")
