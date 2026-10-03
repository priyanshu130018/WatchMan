from __future__ import annotations

from datetime import datetime
from typing import Any
from sqlalchemy import desc, asc, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.constants import CONTENT_PAGE_SIZE
from app.models.content import Content, ContentExternalId, ContentType, ContentVideo
from app.models.taxonomy import Genre, ContentGenre, Language, ContentLanguage
from app.models.people import Person, ContentCast, ContentCrew

DEFAULT_PAGE_SIZE = CONTENT_PAGE_SIZE


class ContentRepository:
    """Repository handling all database queries and transactions for unified Content."""

    DEFAULT_PAGE_SIZE = DEFAULT_PAGE_SIZE

    @staticmethod
    def get_by_id(db: Session, content_id: int) -> Content | None:
        """Fetch content item by internal primary key ID."""
        return (
            db.query(Content)
            .options(
                selectinload(Content.genres).joinedload(ContentGenre.genre),
                selectinload(Content.languages).joinedload(ContentLanguage.language),
                selectinload(Content.cast).joinedload(ContentCast.person),
                selectinload(Content.crew).joinedload(ContentCrew.person),
                selectinload(Content.videos),
                selectinload(Content.external_ids),
                selectinload(Content.embedding),
            )
            .filter(Content.id == content_id)
            .first()
        )

    @staticmethod
    def get_by_tmdb_id(db: Session, content_type: str, tmdb_id: int) -> Content | None:
        """Fetch content item strictly by composite identity (content_type, tmdb_id)."""
        return (
            db.query(Content)
            .options(
                selectinload(Content.genres).joinedload(ContentGenre.genre),
                selectinload(Content.languages).joinedload(ContentLanguage.language),
                selectinload(Content.cast).joinedload(ContentCast.person),
                selectinload(Content.crew).joinedload(ContentCrew.person),
                selectinload(Content.videos),
                selectinload(Content.external_ids),
                selectinload(Content.embedding),
            )
            .filter(
                Content.content_type == content_type,
                Content.tmdb_id == tmdb_id,
            )
            .first()
        )

    @staticmethod
    def list(
        db: Session,
        content_type: str | None = None,
        genre_ids: list[int] | None = None,
        language_code: str | None = None,
        year: int | None = None,
        sort_by: str = "popularity_desc",
        skip: int = 0,
        limit: int = DEFAULT_PAGE_SIZE,
        max_items: int | None = None,
    ) -> tuple[list[Content], int]:
        """List and filter content with pagination and total count.

        When ``max_items`` is set (e.g. a "popular" top-100 collection), the
        reported ``total`` is clamped to that cap and the returned window never
        reaches past it — so pagination sees a finite set (100 -> 6 pages of 18,
        last page = 10) without fetching or fabricating extra rows. Slicing stays
        at the database level via OFFSET/LIMIT.
        """
        query = db.query(Content)

        if content_type:
            query = query.filter(Content.content_type == content_type)

        if genre_ids:
            query = query.filter(
                Content.genres.any(
                    ContentGenre.genre.has(
                        or_(
                            Genre.tmdb_id.in_(genre_ids),
                            Genre.id.in_(genre_ids),
                        )
                    )
                )
            )

        if language_code:
            query = query.filter(
                or_(
                    Content.original_language == language_code,
                    Content.languages.any(ContentLanguage.language_code == language_code),
                )
            )

        if year:
            query = query.filter(Content.release_date.like(f"{year}%"))

        # Sorting
        if sort_by == "popularity_desc":
            query = query.order_by(desc(Content.popularity), desc(Content.id))
        elif sort_by == "popularity_asc":
            query = query.order_by(asc(Content.popularity), asc(Content.id))
        elif sort_by == "release_date_desc":
            query = query.order_by(desc(Content.release_date), desc(Content.id))
        elif sort_by == "release_date_asc":
            query = query.order_by(asc(Content.release_date), asc(Content.id))
        elif sort_by == "vote_average_desc":
            query = query.order_by(desc(Content.vote_average), desc(Content.id))
        else:
            query = query.order_by(desc(Content.popularity), desc(Content.id))

        total = query.count()
        if max_items is not None and total > max_items:
            total = max_items

        # Clamp the fetch window to the capped total so the final page returns
        # only the remainder (e.g. skip=90, total=100 -> 10 rows) and any page
        # beyond the cap returns nothing.
        effective_limit = limit
        if max_items is not None:
            remaining = total - skip
            if remaining <= 0:
                return [], total
            effective_limit = min(limit, remaining)

        items = (
            query.options(
                selectinload(Content.genres).joinedload(ContentGenre.genre),
            )
            .offset(skip)
            .limit(effective_limit)
            .all()
        )
        return items, total

    @staticmethod
    def search(
        db: Session,
        query_str: str,
        content_type: str | None = None,
        genre_ids: list[int] | None = None,
        language_code: str | None = None,
        year: int | None = None,
        sort_by: str = "popularity_desc",
        skip: int = 0,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[Content], int]:
        """Search content titles and overviews with pagination and optional filters."""
        if not query_str or not query_str.strip():
            return [], 0

        search_pattern = f"%{query_str.strip()}%"
        query = db.query(Content).filter(
            or_(
                Content.title.ilike(search_pattern),
                Content.original_title.ilike(search_pattern),
                Content.overview.ilike(search_pattern),
            )
        )

        if content_type:
            query = query.filter(Content.content_type == content_type)

        if genre_ids:
            query = query.filter(
                Content.genres.any(
                    ContentGenre.genre.has(
                        or_(
                            Genre.tmdb_id.in_(genre_ids),
                            Genre.id.in_(genre_ids),
                        )
                    )
                )
            )

        if language_code:
            query = query.filter(
                or_(
                    Content.original_language == language_code,
                    Content.languages.any(ContentLanguage.language_code == language_code),
                )
            )

        if year:
            query = query.filter(Content.release_date.like(f"{year}%"))

        # Sorting
        if sort_by == "popularity_desc":
            query = query.order_by(desc(Content.popularity), desc(Content.id))
        elif sort_by == "popularity_asc":
            query = query.order_by(asc(Content.popularity), asc(Content.id))
        elif sort_by == "release_date_desc":
            query = query.order_by(desc(Content.release_date), desc(Content.id))
        elif sort_by == "release_date_asc":
            query = query.order_by(asc(Content.release_date), asc(Content.id))
        elif sort_by == "vote_average_desc":
            query = query.order_by(desc(Content.vote_average), desc(Content.id))
        else:
            query = query.order_by(desc(Content.popularity), desc(Content.id))

        total = query.count()
        items = (
            query.options(
                selectinload(Content.genres).joinedload(ContentGenre.genre),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )
        return items, total

    @staticmethod
    def get_or_create_genre(db: Session, tmdb_id: int, name: str) -> Genre:
        """Fetch or insert a normalized Genre record."""
        genre = db.query(Genre).filter(or_(Genre.tmdb_id == tmdb_id, Genre.name == name)).first()
        if not genre:
            genre = Genre(tmdb_id=tmdb_id, name=name)
            db.add(genre)
            db.flush()
        return genre

    @staticmethod
    def get_or_create_language(
        db: Session, code: str, name: str | None = None, english_name: str | None = None
    ) -> Language:
        """Fetch or insert a normalized Language record."""
        language = db.query(Language).filter(Language.code == code).first()
        if not language:
            language = Language(
                code=code,
                name=name or code,
                english_name=english_name or name or code,
            )
            db.add(language)
            db.flush()
        return language

    @staticmethod
    def get_or_create_person(
        db: Session,
        tmdb_id: int,
        name: str,
        original_name: str | None = None,
        profile_path: str | None = None,
        known_for_department: str | None = None,
        popularity: float = 0.0,
    ) -> Person:
        """Fetch or insert a normalized Person record."""
        person = db.query(Person).filter(Person.tmdb_id == tmdb_id).first()
        if not person:
            person = Person(
                tmdb_id=tmdb_id,
                name=name,
                original_name=original_name,
                profile_path=profile_path,
                known_for_department=known_for_department,
                popularity=popularity,
            )
            db.add(person)
            db.flush()
        else:
            if profile_path and not person.profile_path:
                person.profile_path = profile_path
            if popularity and popularity > (person.popularity or 0.0):
                person.popularity = popularity
        return person

    @classmethod
    def upsert_content(
        cls,
        db: Session,
        content_dict: dict[str, Any],
        genres: list[dict[str, Any]] | None = None,
        languages: list[dict[str, Any]] | None = None,
        cast: list[dict[str, Any]] | None = None,
        crew: list[dict[str, Any]] | None = None,
        external_ids: list[dict[str, Any]] | None = None,
        videos: list[dict[str, Any]] | None = None,
    ) -> Content:
        """Create or update a Content record with all normalized relational children."""
        content_type = content_dict.get("content_type", ContentType.MOVIE.value)
        tmdb_id = content_dict["tmdb_id"]

        content = (
            db.query(Content)
            .filter(
                Content.content_type == content_type,
                Content.tmdb_id == tmdb_id,
            )
            .first()
        )

        if content is None:
            content = Content(**content_dict)
            db.add(content)
            db.flush()
        else:
            for key, val in content_dict.items():
                setattr(content, key, val)
            db.flush()

        # Update Genres
        if genres is not None:
            db.query(ContentGenre).filter(ContentGenre.content_id == content.id).delete()
            seen_genre_ids = set()
            for g in genres:
                g_tmdb_id = g.get("id") or g.get("tmdb_id")
                g_name = g.get("name")
                if g_tmdb_id and g_name:
                    genre_obj = cls.get_or_create_genre(db, int(g_tmdb_id), str(g_name))
                    if genre_obj.id not in seen_genre_ids:
                        seen_genre_ids.add(genre_obj.id)
                        db.add(ContentGenre(content_id=content.id, genre_id=genre_obj.id))

        # Update Languages
        if languages is not None:
            db.query(ContentLanguage).filter(ContentLanguage.content_id == content.id).delete()
            seen_lang_codes = set()
            for lang in languages:
                code = lang.get("iso_639_1") or lang.get("code")
                if code and code not in seen_lang_codes:
                    seen_lang_codes.add(code)
                    lang_obj = cls.get_or_create_language(
                        db,
                        code=code,
                        name=lang.get("name"),
                        english_name=lang.get("english_name"),
                    )
                    db.add(ContentLanguage(content_id=content.id, language_code=lang_obj.code))

        # Update Cast
        if cast is not None:
            db.query(ContentCast).filter(ContentCast.content_id == content.id).delete()
            seen_cast = set()
            for idx, member in enumerate(cast[:25]):
                p_tmdb_id = member.get("id") or member.get("tmdb_id")
                p_name = member.get("name")
                if p_tmdb_id and p_name:
                    person = cls.get_or_create_person(
                        db,
                        tmdb_id=int(p_tmdb_id),
                        name=str(p_name),
                        original_name=member.get("original_name"),
                        profile_path=member.get("profile_path"),
                        known_for_department=member.get("known_for_department", "Acting"),
                        popularity=float(member.get("popularity") or 0.0),
                    )
                    char_name = member.get("character")
                    cast_key = (person.id, char_name)
                    if cast_key not in seen_cast:
                        seen_cast.add(cast_key)
                        db.add(
                            ContentCast(
                                content_id=content.id,
                                person_id=person.id,
                                character=char_name,
                                cast_order=member.get("order", idx),
                            )
                        )

        # Update Crew
        if crew is not None:
            db.query(ContentCrew).filter(ContentCrew.content_id == content.id).delete()
            seen_crew = set()
            for member in crew[:25]:
                p_tmdb_id = member.get("id") or member.get("tmdb_id")
                p_name = member.get("name")
                if p_tmdb_id and p_name:
                    person = cls.get_or_create_person(
                        db,
                        tmdb_id=int(p_tmdb_id),
                        name=str(p_name),
                        original_name=member.get("original_name"),
                        profile_path=member.get("profile_path"),
                        known_for_department=member.get("department"),
                        popularity=float(member.get("popularity") or 0.0),
                    )
                    dept = member.get("department")
                    job = member.get("job")
                    crew_key = (person.id, dept, job)
                    if crew_key not in seen_crew:
                        seen_crew.add(crew_key)
                        db.add(
                            ContentCrew(
                                content_id=content.id,
                                person_id=person.id,
                                department=dept,
                                job=job,
                            )
                        )

        # Update External IDs
        if external_ids is not None:
            db.query(ContentExternalId).filter(ContentExternalId.content_id == content.id).delete()
            seen_providers = set()
            for ext in external_ids:
                provider = ext.get("provider")
                ext_id = ext.get("external_id")
                if provider and ext_id and provider not in seen_providers:
                    seen_providers.add(provider)
                    db.add(
                        ContentExternalId(
                            content_id=content.id,
                            provider=str(provider),
                            external_id=str(ext_id),
                        )
                    )

        # Update Videos
        if videos is not None:
            db.query(ContentVideo).filter(ContentVideo.content_id == content.id).delete()
            seen_video_keys = set()
            for v in videos:
                v_key = v.get("key")
                if v_key and v_key not in seen_video_keys:
                    seen_video_keys.add(v_key)
                    published_str = v.get("published_at")
                    published_dt = None
                    if published_str:
                        try:
                            published_dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                        except Exception:
                            published_dt = None
                    db.add(
                        ContentVideo(
                            content_id=content.id,
                            key=str(v_key),
                            site=v.get("site", "YouTube"),
                            name=v.get("name", "Trailer"),
                            type=v.get("type", "Trailer"),
                            official=bool(v.get("official", False)),
                            published_at=published_dt,
                        )
                    )

        db.flush()
        return content
