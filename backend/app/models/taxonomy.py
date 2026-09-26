from sqlalchemy import Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Genre(Base):
    """Normalized genre taxonomy for both movies and TV."""
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)


class ContentGenre(Base):
    """Many-to-many relationship between Content and Genre."""
    __tablename__ = "content_genres"
    __table_args__ = (
        UniqueConstraint("content_id", "genre_id", name="uq_content_genre"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    genre_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("genres.id", ondelete="CASCADE"), index=True, nullable=False
    )

    genre = relationship("Genre", lazy="joined")


class Language(Base):
    """Normalized language taxonomy for content localization and filtering."""
    __tablename__ = "languages"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    english_name: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ContentLanguage(Base):
    """Many-to-many relationship between Content and Language."""
    __tablename__ = "content_languages"
    __table_args__ = (
        UniqueConstraint("content_id", "language_code", name="uq_content_language"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    language_code: Mapped[str] = mapped_column(
        String(10), ForeignKey("languages.code", ondelete="CASCADE"), index=True, nullable=False
    )

    language = relationship("Language", lazy="joined")
