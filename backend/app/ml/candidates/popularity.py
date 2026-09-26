from math import log1p
from sqlalchemy.orm import Session
from app.models.content import Content


class PopularityCandidateGenerator:
    """
    Generates candidates based on catalog popularity and vote score quality.
    """

    @classmethod
    def generate_candidates(
        cls,
        db: Session,
        limit: int = 50,
        content_type: str | None = None,
        exclude_content_ids: set[int] | None = None,
    ) -> list[dict]:
        """
        Retrieves candidates sorted by popularity and quality metrics.
        """
        exclude_ids = exclude_content_ids or set()
        query = db.query(Content)

        if exclude_ids:
            query = query.filter(Content.id.notin_(exclude_ids))
        if content_type and content_type.lower() in ("movie", "tv"):
            query = query.filter(Content.content_type == content_type.lower())

        items = query.order_by(Content.popularity.desc().nullslast()).limit(limit * 2).all()
        if not items:
            return []

        max_pop = max((float(c.popularity or 0.0) for c in items), default=1.0)
        max_pop = max(1.0, max_pop)

        candidates = []
        for c in items:
            pop_val = float(c.popularity or 0.0)
            vote_val = float(c.vote_average or 0.0)

            # Score combining log-scaled popularity (60%) and normalized vote average (40%)
            pop_norm = log1p(max(0.0, pop_val)) / log1p(max_pop)
            vote_norm = max(0.0, min(10.0, vote_val)) / 10.0

            score = 0.6 * pop_norm + 0.4 * vote_norm
            candidates.append({
                "content_id": c.id,
                "content": c,
                "score": round(min(1.0, max(0.0, score)), 4),
                "source": "popularity",
                "explanation": "Trending and widely acclaimed by audiences",
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:limit]
