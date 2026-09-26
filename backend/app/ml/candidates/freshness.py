from datetime import datetime, date
from math import exp
from sqlalchemy.orm import Session
from app.models.content import Content


class FreshnessCandidateGenerator:
    """
    Generates candidates prioritizing recently released movies and series with exponential decay.
    """

    @classmethod
    def _parse_release_date(cls, release_date_str: str | None) -> date | None:
        if not release_date_str or not isinstance(release_date_str, str):
            return None
        cleaned = release_date_str.strip()
        try:
            return datetime.strptime(cleaned[:10], "%Y-%m-%d").date()
        except Exception:
            return None

    @classmethod
    def generate_candidates(
        cls,
        db: Session,
        limit: int = 50,
        content_type: str | None = None,
        exclude_content_ids: set[int] | None = None,
    ) -> list[dict]:
        """
        Retrieves newest candidates with recency decay scores.
        """
        exclude_ids = exclude_content_ids or set()
        query = db.query(Content).filter(Content.release_date.isnot(None))

        if exclude_ids:
            query = query.filter(Content.id.notin_(exclude_ids))
        if content_type and content_type.lower() in ("movie", "tv"):
            query = query.filter(Content.content_type == content_type.lower())

        items = query.order_by(Content.release_date.desc()).limit(limit * 2).all()
        if not items:
            return []

        today = date.today()
        candidates = []

        for c in items:
            rdate = cls._parse_release_date(c.release_date)
            if not rdate:
                continue

            days_old = max(0, (today - rdate).days)
            # Exponential decay: half-life of 180 days (~6 months)
            freshness_score = exp(-0.693 * days_old / 180.0)

            # Boost slightly with vote quality to avoid poor newly-released items
            vote_val = float(c.vote_average or 0.0)
            quality_factor = max(0.4, min(1.0, vote_val / 10.0)) if vote_val > 0 else 0.5
            final_score = 0.7 * freshness_score + 0.3 * quality_factor

            candidates.append({
                "content_id": c.id,
                "content": c,
                "score": round(min(1.0, max(0.0, final_score)), 4),
                "source": "freshness",
                "explanation": "Newly released title freshly added to the catalog",
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:limit]
