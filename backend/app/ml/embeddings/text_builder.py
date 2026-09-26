import hashlib
from typing import Any


def _extract_names(items: Any, max_items: int = 20) -> list[str]:
    """Safely extracts 'name' strings from a list of dicts, ORM models, or strings."""
    if not items or not isinstance(items, (list, tuple, set)):
        return []
    
    names = []
    for item in items:
        if isinstance(item, dict):
            name = item.get("name")
            if name and isinstance(name, str) and name.strip():
                names.append(name.strip())
        elif hasattr(item, "genre") and hasattr(item.genre, "name") and item.genre.name:
            names.append(item.genre.name.strip())
        elif hasattr(item, "person") and hasattr(item.person, "name") and item.person.name:
            names.append(item.person.name.strip())
        elif hasattr(item, "name") and isinstance(item.name, str) and item.name.strip():
            names.append(item.name.strip())
        elif isinstance(item, str) and item.strip():
            names.append(item.strip())
        if len(names) >= max_items:
            break
    return names


def _extract_directors(crew_items: Any, max_directors: int = 3) -> list[str]:
    """Safely extracts director names from crew list or ORM relationship."""
    if not crew_items or not isinstance(crew_items, (list, tuple, set)):
        return []
    
    directors = []
    for member in crew_items:
        if isinstance(member, dict):
            job = member.get("job")
            name = member.get("name")
            if job == "Director" and name and isinstance(name, str) and name.strip():
                if name.strip() not in directors:
                    directors.append(name.strip())
        elif hasattr(member, "job") and member.job == "Director":
            name = getattr(member.person, "name", None) if hasattr(member, "person") else getattr(member, "name", None)
            if name and isinstance(name, str) and name.strip():
                if name.strip() not in directors:
                    directors.append(name.strip())
        if len(directors) >= max_directors:
            break
    return directors


def _extract_year(release_date: Any) -> str | None:
    """Extracts 4-digit year from release date string."""
    if not release_date or not isinstance(release_date, str):
        return None
    cleaned = release_date.strip()
    if len(cleaned) >= 4 and cleaned[:4].isdigit():
        return cleaned[:4]
    return None


def build_movie_embedding_text(movie: Any) -> str:
    """
    Builds a clean, deterministic textual representation of a movie or content item for embedding generation.
    
    Accepts either an ORM Content/Movie object or a dict.
    Gracefully handles NULLs, empty arrays, and missing attributes.
    """
    def get_val(attr: str) -> Any:
        if isinstance(movie, dict):
            return movie.get(attr)
        return getattr(movie, attr, None)

    parts: list[str] = []

    # Title
    title = get_val("title")
    if title and isinstance(title, str) and title.strip():
        parts.append(f"Title: {title.strip()}")

    # Tagline
    tagline = get_val("tagline")
    if tagline and isinstance(tagline, str) and tagline.strip():
        parts.append(f"Tagline: {tagline.strip()}")

    # Overview
    overview = get_val("overview")
    if overview and isinstance(overview, str) and overview.strip():
        parts.append(f"Overview: {overview.strip()}")

    # Genres
    genres = _extract_names(get_val("genres"), max_items=10)
    if genres:
        parts.append(f"Genres: {', '.join(genres)}")

    # Keywords
    keywords = _extract_names(get_val("keywords"), max_items=25)
    if keywords:
        parts.append(f"Keywords: {', '.join(keywords)}")

    # Director
    directors = _extract_directors(get_val("crew"), max_directors=3)
    if directors:
        parts.append(f"Director: {', '.join(directors)}")

    # Top Cast
    cast = _extract_names(get_val("cast"), max_items=10)
    if cast:
        parts.append(f"Cast: {', '.join(cast)}")

    # Release Year
    year = _extract_year(get_val("release_date"))
    if year:
        parts.append(f"Year: {year}")

    # Runtime
    runtime = get_val("runtime")
    if runtime and isinstance(runtime, (int, float)) and runtime > 0:
        parts.append(f"Runtime: {int(runtime)} min")

    return "\n".join(parts)


def compute_movie_text_hash(text: str) -> str:
    """Computes SHA-256 hash of movie representation text for stale detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
