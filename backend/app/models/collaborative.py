"""
Persisted ALS / matrix-factorization latent factors.

These are the COLLABORATIVE representation (User <-> Movie), learned from the
User x Movie interaction matrix. They are deliberately kept in their own tables
and stored as JSON float arrays (NOT pgvector `Vector`) so they are never
confused with, or accidentally used as, the content/semantic embeddings that
live in `content_embeddings` / `user_embeddings`.

    content_embeddings.embedding  -> semantic meaning of a movie (Hugging Face)
    als_item_factors.factors      -> collaborative behavioural factors of a movie
    als_user_factors.factors      -> collaborative behavioural factors of a user

The two are different representations of different things and generally have
different dimensionality.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ALSUserFactors(Base):
    """Latent user factors learned by ALS matrix factorization."""

    __tablename__ = "als_user_factors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    # JSON list[float]; length == num_factors. Intentionally NOT a pgvector column.
    factors: Mapped[list] = mapped_column(JSON, nullable=False)
    num_factors: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), default="als-1.0.0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user = relationship("User", lazy="joined")


class ALSItemFactors(Base):
    """Latent item (content) factors learned by ALS matrix factorization."""

    __tablename__ = "als_item_factors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("contents.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    factors: Mapped[list] = mapped_column(JSON, nullable=False)
    num_factors: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), default="als-1.0.0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    content = relationship("Content", lazy="joined")
