from sqlalchemy import Integer, String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Person(Base):
    """Unified person entity for cast and crew across movies and TV."""
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    known_for_department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    popularity: Mapped[float | None] = mapped_column(Float, default=0.0)


class ContentCast(Base):
    """Cast members participating in a content item."""
    __tablename__ = "content_cast"
    __table_args__ = (
        UniqueConstraint("content_id", "person_id", "character", name="uq_content_cast_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    person_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("people.id", ondelete="CASCADE"), index=True, nullable=False
    )
    character: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cast_order: Mapped[int] = mapped_column(Integer, default=0)

    person = relationship("Person", lazy="joined")


class ContentCrew(Base):
    """Crew members participating in a content item."""
    __tablename__ = "content_crew"
    __table_args__ = (
        UniqueConstraint("content_id", "person_id", "department", "job", name="uq_content_crew_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    person_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("people.id", ondelete="CASCADE"), index=True, nullable=False
    )
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    job: Mapped[str | None] = mapped_column(String(150), nullable=True)

    person = relationship("Person", lazy="joined")
