from datetime import datetime
import threading
from typing import Any, Sequence
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, not_

from sentence_transformers import SentenceTransformer

from app.database.models.movie import Movie
from app.database.models.movie_embedding import MovieEmbedding
from app.ml.embeddings.text_builder import build_movie_embedding_text, compute_movie_text_hash

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EXPECTED_DIMENSION = 384


class MovieEmbeddingService:
    _instance = None
    _lock = threading.Lock()
    _model: SentenceTransformer | None = None

    @classmethod
    def get_model(cls) -> SentenceTransformer:
        if cls._model is None:
            with cls._lock:
                if cls._model is None:
                    cls._model = SentenceTransformer(MODEL_NAME, token=False)
        return cls._model

    @classmethod
    def generate_embedding(cls, text: str) -> list[float]:
        """Generates a normalized 384-dimensional embedding for the given text."""
        model = cls.get_model()
        vector = model.encode(text, normalize_embeddings=True)
        if len(vector) != EXPECTED_DIMENSION:
            raise ValueError(
                f"Embedding dimension mismatch: expected {EXPECTED_DIMENSION}, got {len(vector)}"
            )
        return vector.tolist() if isinstance(vector, np.ndarray) else list(vector)

    @classmethod
    def generate_embeddings_batch(cls, texts: Sequence[str]) -> list[list[float]]:
        """Generates normalized embeddings for a batch of texts."""
        if not texts:
            return []
        model = cls.get_model()
        vectors = model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
        result = []
        for vec in vectors:
            if len(vec) != EXPECTED_DIMENSION:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {EXPECTED_DIMENSION}, got {len(vec)}"
                )
            result.append(vec.tolist() if isinstance(vec, np.ndarray) else list(vec))
        return result

    @classmethod
    def embed_movie(cls, db: Session, movie_id: int, force: bool = False) -> MovieEmbedding:
        """
        Embeds a single movie idempotently.
        If the movie already has an up-to-date embedding, skips regeneration unless force=True.
        """
        movie = db.query(Movie).filter(Movie.id == movie_id).first()
        if not movie:
            raise ValueError(f"Movie with id {movie_id} does not exist.")

        text_content = build_movie_embedding_text(movie)
        text_hash = compute_movie_text_hash(text_content)

        existing = db.query(MovieEmbedding).filter(MovieEmbedding.movie_id == movie_id).first()
        if existing and not force:
            if existing.content_hash == text_hash and existing.embedding is not None:
                return existing

        # Generate embedding
        vector = cls.generate_embedding(text_content)

        if existing:
            existing.embedding = vector
            existing.content_hash = text_hash
            existing.model_name = MODEL_NAME
            existing.dimension = EXPECTED_DIMENSION
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing
        else:
            new_embedding = MovieEmbedding(
                movie_id=movie_id,
                embedding=vector,
                content_hash=text_hash,
                model_name=MODEL_NAME,
                dimension=EXPECTED_DIMENSION,
                model_version="1.0.0",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(new_embedding)
            db.commit()
            db.refresh(new_embedding)
            return new_embedding

    @classmethod
    def batch_embed_movies(cls, db: Session, limit: int = 100, batch_size: int = 32) -> dict:
        """
        Embeds movies that do not have embeddings or whose content has changed.
        Uses pagination to process in memory-efficient chunks.
        """
        # Find movies without embeddings or with missing embedding vectors
        missing_query = (
            db.query(Movie)
            .outerjoin(MovieEmbedding, Movie.id == MovieEmbedding.movie_id)
            .filter(
                or_(
                    MovieEmbedding.id.is_(None),
                    MovieEmbedding.embedding.is_(None)
                )
            )
            .limit(limit)
        )
        movies_to_process = missing_query.all()

        total_processed = 0
        total_updated = 0

        for i in range(0, len(movies_to_process), batch_size):
            batch = movies_to_process[i:i + batch_size]
            texts = [build_movie_embedding_text(m) for m in batch]
            hashes = [compute_movie_text_hash(t) for t in texts]
            vectors = cls.generate_embeddings_batch(texts)

            for movie, vector, text_hash in zip(batch, vectors, hashes):
                existing = db.query(MovieEmbedding).filter(MovieEmbedding.movie_id == movie.id).first()
                if existing:
                    existing.embedding = vector
                    existing.content_hash = text_hash
                    existing.model_name = MODEL_NAME
                    existing.dimension = EXPECTED_DIMENSION
                    existing.updated_at = datetime.utcnow()
                    total_updated += 1
                else:
                    new_emb = MovieEmbedding(
                        movie_id=movie.id,
                        embedding=vector,
                        content_hash=text_hash,
                        model_name=MODEL_NAME,
                        dimension=EXPECTED_DIMENSION,
                        model_version="1.0.0",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(new_emb)
                    total_processed += 1

            db.commit()

        return {
            "status": "success",
            "total_candidates": len(movies_to_process),
            "newly_created": total_processed,
            "updated": total_updated
        }

    @classmethod
    def search_similar_movies(
        cls,
        db: Session,
        movie_id: int,
        limit: int = 10
    ) -> list[dict]:
        """
        Searches for movies similar to the given movie_id using pgvector cosine distance.
        The similarity calculation happens entirely inside PostgreSQL / pgvector.
        """
        target_emb_record = db.query(MovieEmbedding).filter(MovieEmbedding.movie_id == movie_id).first()
        if not target_emb_record or target_emb_record.embedding is None:
            # Generate on demand
            target_emb_record = cls.embed_movie(db, movie_id)

        target_vector = target_emb_record.embedding

        # Query using pgvector cosine distance operator (<=>)
        # Cosine similarity = 1 - cosine_distance
        distance_col = MovieEmbedding.embedding.cosine_distance(target_vector).label("distance")

        results = (
            db.query(Movie, distance_col)
            .join(MovieEmbedding, Movie.id == MovieEmbedding.movie_id)
            .filter(Movie.id != movie_id)
            .filter(MovieEmbedding.embedding.isnot(None))
            .order_by(distance_col.asc())
            .limit(limit)
            .all()
        )

        similar_movies = []
        for movie, distance in results:
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            similar_movies.append({
                "movie": {
                    "id": movie.id,
                    "tmdb_id": movie.tmdb_id,
                    "title": movie.title,
                    "overview": movie.overview,
                    "release_date": movie.release_date,
                    "poster_path": movie.poster_path,
                    "backdrop_path": movie.backdrop_path,
                    "vote_average": movie.vote_average,
                    "vote_count": movie.vote_count,
                    "popularity": movie.popularity,
                    "genres": movie.genres,
                    "runtime": movie.runtime,
                    "tagline": movie.tagline,
                },
                "similarity": round(similarity, 4)
            })

        return similar_movies
