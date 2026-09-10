from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models.user import User
from app.core.config import settings
from app.core.security import get_current_user
from app.ml.embeddings.service import MovieEmbeddingService, MODEL_NAME, EXPECTED_DIMENSION

router = APIRouter(prefix="/ml/embeddings", tags=["ML Embeddings"])


class BatchEmbedRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=100)
    batch_size: int = Field(default=32, ge=1, le=128)


def require_ml_admin(current_user: User = Depends(get_current_user)) -> User:
    """Restrict expensive embedding jobs to configured operators."""
    if current_user.email.lower() not in settings.ml_admin_emails:
        raise HTTPException(status_code=403, detail="ML operator access is required")
    return current_user


@router.post("/movies/batch")
def batch_generate_movie_embeddings(
    payload: BatchEmbedRequest | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_ml_admin),
):
    if payload is None:
        payload = BatchEmbedRequest()
    try:
        result = MovieEmbeddingService.batch_embed_movies(
            db=db,
            limit=payload.limit,
            batch_size=payload.batch_size
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to execute batch embedding")


@router.post("/movies/{movie_id}")
def generate_movie_embedding(
    movie_id: int,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_ml_admin),
):
    try:
        embedding_record = MovieEmbeddingService.embed_movie(db, movie_id, force=force)
        return {
            "status": "success",
            "movie_id": embedding_record.movie_id,
            "model": embedding_record.model_name or MODEL_NAME,
            "dimension": embedding_record.dimension or EXPECTED_DIMENSION,
            "content_hash": embedding_record.content_hash,
            "updated_at": embedding_record.updated_at.isoformat() if embedding_record.updated_at else None
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate embedding")


