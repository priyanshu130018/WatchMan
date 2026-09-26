from typing import Any, Sequence
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ml.embeddings.sentence_encoder import SentenceEncoder
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.models.embedding import ContentEmbedding

MODEL_NAME = settings.EMBEDDING_MODEL
EXPECTED_DIMENSION = settings.VECTOR_DIMENSION


class MovieEmbeddingService:
    """
    Backward-compatible wrapper for ContentEmbeddingService.
    """

    @classmethod
    def get_model(cls):
        # Embeddings are now served via the HF Inference API; this returns the
        # remote encoder singleton rather than a local model object.
        return SentenceEncoder.get_instance()

    @classmethod
    def generate_embedding(cls, text: str) -> list[float]:
        return ContentEmbeddingService.generate_embedding(text)

    @classmethod
    def generate_embeddings_batch(cls, texts: Sequence[str]) -> list[list[float]]:
        return ContentEmbeddingService.generate_embeddings_batch(texts)

    @classmethod
    def embed_movie(cls, db: Session, movie_id: int, force: bool = False) -> ContentEmbedding:
        return ContentEmbeddingService.embed_content(db, movie_id, force=force)

    @classmethod
    def batch_embed_movies(cls, db: Session, limit: int = 100, batch_size: int = 32) -> dict:
        return ContentEmbeddingService.batch_embed_contents(db, limit=limit, batch_size=batch_size)

    @classmethod
    def search_similar_movies(cls, db: Session, movie_id: int, limit: int = 10) -> list[dict]:
        results = ContentEmbeddingService.search_similar_content(db, movie_id, limit=limit)
        # Adapt output to legacy movie schema dict if needed
        legacy_results = []
        for r in results:
            item = r["content"]
            legacy_results.append({
                "movie": {
                    "id": item.id,
                    "tmdb_id": item.tmdb_id,
                    "title": item.title,
                    "overview": item.overview,
                    "release_date": item.release_date,
                    "poster_path": item.poster_path,
                    "backdrop_path": item.backdrop_path,
                    "vote_average": item.vote_average,
                    "vote_count": item.vote_count,
                    "popularity": item.popularity,
                    "genres": [
                        g.genre.name if hasattr(g, "genre") and hasattr(g.genre, "name")
                        else (g.get("name") if isinstance(g, dict) else str(g))
                        for g in (item.genres or [])
                    ],
                    "runtime": item.runtime,
                    "tagline": item.tagline,
                },
                "similarity": r["similarity"],
            })
        return legacy_results
