from datetime import datetime
from sqlalchemy import Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.database.base import Base


class MovieEmbedding(Base):
    __tablename__ = "movie_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    movie_id: Mapped[int] = mapped_column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    embedding = mapped_column(Vector(384), nullable=True)
    model_name: Mapped[str] = mapped_column(String(150), default="sentence-transformers/all-MiniLM-L6-v2")
    dimension: Mapped[int] = mapped_column(Integer, default=384)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    model_version: Mapped[str | None] = mapped_column(String(100), default="1.0.0", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


    movie = relationship("Movie")
