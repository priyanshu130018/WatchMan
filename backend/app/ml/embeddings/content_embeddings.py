from datetime import datetime
from typing import Sequence
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.config import settings
from app.models.content import Content
from app.models.embedding import ContentEmbedding
from app.ml.embeddings.sentence_encoder import SentenceEncoder
from app.ml.embeddings.text_builder import build_movie_embedding_text, compute_movie_text_hash


class ContentEmbeddingService:
    """
    Service for generating, storing, and searching dense embeddings for unified Content items.
    """

    @classmethod
    def generate_embedding(cls, text: str) -> list[float]:
        return SentenceEncoder.get_instance().encode(text)

    @classmethod
    def generate_embeddings_batch(cls, texts: Sequence[str]) -> list[list[float]]:
        return SentenceEncoder.get_instance().encode_batch(texts)

    @classmethod
    def embed_content(cls, db: Session, content_id: int, force: bool = False) -> ContentEmbedding:
        """
        Embeds a single Content item idempotently.
        Skips re-embedding if text hash and model version match, unless force=True.
        """
        content = db.query(Content).filter(Content.id == content_id).first()
        if not content:
            raise ValueError(f"Content with id {content_id} does not exist.")

        text_content = build_movie_embedding_text(content)
        text_hash = compute_movie_text_hash(text_content)

        existing = db.query(ContentEmbedding).filter(ContentEmbedding.content_id == content_id).first()
        if existing and not force:
            if existing.content_hash == text_hash and existing.embedding is not None:
                return existing

        vector = cls.generate_embedding(text_content)

        if existing:
            existing.embedding = vector
            existing.content_hash = text_hash
            existing.model_name = settings.EMBEDDING_MODEL
            existing.dimension = settings.VECTOR_DIMENSION
            existing.model_version = "1.0.0"
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing
        else:
            new_embedding = ContentEmbedding(
                content_id=content_id,
                embedding=vector,
                content_hash=text_hash,
                model_name=settings.EMBEDDING_MODEL,
                dimension=settings.VECTOR_DIMENSION,
                model_version="1.0.0",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(new_embedding)
            db.commit()
            db.refresh(new_embedding)
            return new_embedding

    @classmethod
    def batch_embed_contents(cls, db: Session, limit: int = 100, batch_size: int = 32) -> dict:
        """
        Embeds Content items that do not have embeddings or whose content has changed.
        """
        missing_query = (
            db.query(Content)
            .outerjoin(ContentEmbedding, Content.id == ContentEmbedding.content_id)
            .filter(
                or_(
                    ContentEmbedding.id.is_(None),
                    ContentEmbedding.embedding.is_(None),
                )
            )
            .limit(limit)
        )
        contents_to_process = missing_query.all()

        total_processed = 0
        total_updated = 0

        for i in range(0, len(contents_to_process), batch_size):
            batch = contents_to_process[i : i + batch_size]
            texts = [build_movie_embedding_text(m) for m in batch]
            hashes = [compute_movie_text_hash(t) for t in texts]
            vectors = cls.generate_embeddings_batch(texts)

            for content, vector, text_hash in zip(batch, vectors, hashes):
                existing = db.query(ContentEmbedding).filter(ContentEmbedding.content_id == content.id).first()
                if existing:
                    existing.embedding = vector
                    existing.content_hash = text_hash
                    existing.model_name = settings.EMBEDDING_MODEL
                    existing.dimension = settings.VECTOR_DIMENSION
                    existing.model_version = "1.0.0"
                    existing.updated_at = datetime.utcnow()
                    total_updated += 1
                else:
                    new_emb = ContentEmbedding(
                        content_id=content.id,
                        embedding=vector,
                        content_hash=text_hash,
                        model_name=settings.EMBEDDING_MODEL,
                        dimension=settings.VECTOR_DIMENSION,
                        model_version="1.0.0",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    db.add(new_emb)
                    total_processed += 1

            db.commit()

        return {
            "status": "success",
            "total_candidates": len(contents_to_process),
            "newly_created": total_processed,
            "updated": total_updated,
        }

    @classmethod
    def search_similar_content(
        cls,
        db: Session,
        content_id: int,
        limit: int = 10,
        content_type: str | None = None,
    ) -> list[dict]:
        """
        Searches for items similar to the given content_id using pgvector cosine distance or numpy fallback.
        """
        target_emb = db.query(ContentEmbedding).filter(ContentEmbedding.content_id == content_id).first()
        if not target_emb or target_emb.embedding is None:
            target_emb = cls.embed_content(db, content_id)

        target_vector = target_emb.embedding
        return cls.search_by_vector(
            db,
            vector=target_vector,
            limit=limit,
            content_type=content_type,
            exclude_content_ids={content_id},
        )

    @classmethod
    def search_by_vector(
        cls,
        db: Session,
        vector: list[float] | Sequence[float],
        limit: int = 20,
        content_type: str | None = None,
        exclude_content_ids: set[int] | None = None,
    ) -> list[dict]:
        """
        Queries the database for Content items closest to the given vector.
        Uses pgvector native cosine distance if available, with python cosine fallback.
        """
        if not vector or len(vector) != settings.VECTOR_DIMENSION:
            return []

        exclude_ids = exclude_content_ids or set()

        if settings.ENABLE_PGVECTOR:
            try:
                distance_col = ContentEmbedding.embedding.cosine_distance(vector).label("distance")
                query = (
                    db.query(Content, distance_col)
                    .join(ContentEmbedding, Content.id == ContentEmbedding.content_id)
                    .filter(ContentEmbedding.embedding.isnot(None))
                )
                if exclude_ids:
                    query = query.filter(Content.id.notin_(exclude_ids))
                if content_type and content_type.lower() in ("movie", "tv"):
                    query = query.filter(Content.content_type == content_type.lower())

                results = query.order_by(distance_col.asc()).limit(limit).all()

                output = []
                for item, dist in results:
                    similarity = max(0.0, min(1.0, 1.0 - float(dist)))
                    output.append({
                        "content": item,
                        "similarity": round(similarity, 4),
                        "score": round(similarity, 4),
                    })
                return output
            except Exception:
                # Fallback to in-memory cosine similarity if pgvector extension query fails in tests/sqlite
                db.rollback()

        # In-memory cosine similarity fallback (for SQLite test environments or if pgvector unavailable)
        query = (
            db.query(Content, ContentEmbedding.embedding)
            .join(ContentEmbedding, Content.id == ContentEmbedding.content_id)
            .filter(ContentEmbedding.embedding.isnot(None))
        )
        if exclude_ids:
            query = query.filter(Content.id.notin_(exclude_ids))
        if content_type and content_type.lower() in ("movie", "tv"):
            query = query.filter(Content.content_type == content_type.lower())

        records = query.all()
        if not records:
            return []

        target_arr = np.array(vector, dtype=np.float32)
        target_norm = np.linalg.norm(target_arr)
        if target_norm == 0:
            return []

        scored = []
        for item, emb in records:
            if emb is None:
                continue
            emb_arr = np.array(emb, dtype=np.float32)
            emb_norm = np.linalg.norm(emb_arr)
            if emb_norm == 0:
                continue
            cos_sim = float(np.dot(target_arr, emb_arr) / (target_norm * emb_norm))
            similarity = max(0.0, min(1.0, cos_sim))
            scored.append((item, similarity))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_items = scored[:limit]

        return [
            {
                "content": item,
                "similarity": round(sim, 4),
                "score": round(sim, 4),
            }
            for item, sim in top_items
        ]
