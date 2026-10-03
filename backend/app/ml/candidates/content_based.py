from uuid import UUID
from sqlalchemy.orm import Session

from app.models.content import Content
from app.ml.embeddings.user_embeddings import UserEmbeddingService
from app.ml.embeddings.content_embeddings import ContentEmbeddingService


class ContentBasedCandidateGenerator:
    """
    Generates candidate items by matching the user's taste embedding against content embeddings.
    """

    @classmethod
    def generate_candidates(
        cls,
        db: Session,
        user_id: UUID,
        limit: int = 50,
        content_type: str | None = None,
        exclude_content_ids: set[int] | None = None,
    ) -> list[dict]:
        """
        Retrieves candidate content items using dense vector similarity.
        """
        exclude_ids = exclude_content_ids or set()
        user_vector = UserEmbeddingService.get_stored_user_embedding(db, user_id)

        if not user_vector:
            # Cold start or pending background calculation: No user embedding available
            return []

        results = ContentEmbeddingService.search_by_vector(
            db=db,
            vector=user_vector,
            limit=limit,
            content_type=content_type,
            exclude_content_ids=exclude_ids,
        )

        candidates = []
        for r in results:
            cid = r["content_id"]
            similarity = r["similarity"]
            candidates.append({
                "content_id": cid,
                "score": similarity,
                "source": "content_based",
                "explanation": "Matches your semantic taste profile and favorite genres/themes",
            })
        return candidates
