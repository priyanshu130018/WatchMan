from datetime import datetime
from typing import Sequence
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.config import settings
from app.models.content import Content
from app.models.embedding import ContentEmbedding
import time
from app.core.timing import get_current_timing_ctx
from app.ml.embeddings.sentence_encoder import SentenceEncoder
from app.ml.embeddings.text_builder import build_movie_embedding_text, compute_movie_text_hash
from app.ml.embeddings.eligibility import ContentEmbeddingEligibilityService


class ContentEmbeddingService:
    """
    Service for generating, storing, and searching dense embeddings for unified Content items.
    """

    MODEL_VERSION = "1.0.0"

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
        Skips re-embedding if text hash, model name, dimension, and model version match,
        unless force=True.
        """
        content = db.query(Content).filter(Content.id == content_id).first()
        if not content:
            raise ValueError(f"Content with id {content_id} does not exist.")

        existing = db.query(ContentEmbedding).filter(ContentEmbedding.content_id == content_id).first()
        if existing and not force:
            if ContentEmbeddingEligibilityService.is_embedding_current(content, existing):
                return existing

        text_content = build_movie_embedding_text(content)
        text_hash = compute_movie_text_hash(text_content)
        vector = cls.generate_embedding(text_content)

        if existing:
            existing.embedding = vector
            existing.content_hash = text_hash
            existing.model_name = settings.EMBEDDING_MODEL
            existing.dimension = settings.VECTOR_DIMENSION
            existing.model_version = cls.MODEL_VERSION
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing
        else:
            try:
                new_embedding = ContentEmbedding(
                    content_id=content_id,
                    embedding=vector,
                    content_hash=text_hash,
                    model_name=settings.EMBEDDING_MODEL,
                    dimension=settings.VECTOR_DIMENSION,
                    model_version=cls.MODEL_VERSION,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.add(new_embedding)
                db.commit()
                db.refresh(new_embedding)
                return new_embedding
            except Exception:
                db.rollback()
                # Race condition guard: concurrent worker may have inserted the embedding
                concurrent_existing = (
                    db.query(ContentEmbedding)
                    .filter(ContentEmbedding.content_id == content_id)
                    .first()
                )
                if concurrent_existing:
                    return concurrent_existing
                raise

    @classmethod
    def batch_embed_items(
        cls,
        db: Session,
        contents: Sequence[Content],
        batch_size: int = 32,
        force: bool = False,
    ) -> dict:
        """
        Embeds a given collection of Content items idempotently.
        Skips items that already have a current embedding matching hash, model, and version,
        unless force=True.
        """
        if not contents:
            return {
                "status": "success",
                "total_candidates": 0,
                "to_embed": 0,
                "newly_created": 0,
                "updated": 0,
                "skipped_current": 0,
            }

        # Normalize contents: support either Content models or integer IDs
        if isinstance(contents[0], (int, str)):
            int_ids = [int(i) for i in contents]
            contents = db.query(Content).filter(Content.id.in_(int_ids)).all()
            if not contents:
                return {
                    "status": "success",
                    "total_candidates": 0,
                    "to_embed": 0,
                    "newly_created": 0,
                    "updated": 0,
                    "skipped_current": 0,
                }

        content_ids = [c.id for c in contents]
        existing_recs = {
            rec.content_id: rec
            for rec in db.query(ContentEmbedding).filter(ContentEmbedding.content_id.in_(content_ids)).all()
        }

        to_embed: list[Content] = []
        skipped_count = 0

        for c in contents:
            existing = existing_recs.get(c.id)
            if not force and ContentEmbeddingEligibilityService.is_embedding_current(c, existing):
                skipped_count += 1
            else:
                to_embed.append(c)

        newly_created = 0
        updated = 0

        for i in range(0, len(to_embed), batch_size):
            chunk = to_embed[i : i + batch_size]
            texts = [build_movie_embedding_text(c) for c in chunk]
            hashes = [compute_movie_text_hash(t) for t in texts]
            vectors = cls.generate_embeddings_batch(texts)

            for content, vector, text_hash in zip(chunk, vectors, hashes):
                existing = existing_recs.get(content.id) or (
                    db.query(ContentEmbedding)
                    .filter(ContentEmbedding.content_id == content.id)
                    .first()
                )
                if existing:
                    existing.embedding = vector
                    existing.content_hash = text_hash
                    existing.model_name = settings.EMBEDDING_MODEL
                    existing.dimension = settings.VECTOR_DIMENSION
                    existing.model_version = cls.MODEL_VERSION
                    existing.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    new_emb = ContentEmbedding(
                        content_id=content.id,
                        embedding=vector,
                        content_hash=text_hash,
                        model_name=settings.EMBEDDING_MODEL,
                        dimension=settings.VECTOR_DIMENSION,
                        model_version=cls.MODEL_VERSION,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    db.add(new_emb)
                    existing_recs[content.id] = new_emb
                    newly_created += 1

            db.commit()

        return {
            "status": "success",
            "total_candidates": len(contents),
            "to_embed": len(to_embed),
            "newly_created": newly_created,
            "updated": updated,
            "skipped_current": skipped_count,
        }

    @classmethod
    def batch_embed_contents(
        cls,
        db: Session,
        limit: int | None = 100,
        batch_size: int = 32,
        content_ids: Sequence[int] | None = None,
        force: bool = False,
    ) -> dict:
        """
        Embeds Content items that do not have embeddings or whose content has changed.
        If content_ids is provided, restricts to those IDs.
        If limit is None or <= 0, processes the entire eligible catalog in batches.
        """
        if content_ids is not None:
            contents = db.query(Content).filter(Content.id.in_(content_ids)).all()
            return cls.batch_embed_items(db, contents, batch_size=batch_size, force=force)

        total_processed = 0
        total_updated = 0

        while True:
            chunk_limit = batch_size
            if limit is not None and limit > 0:
                remaining = limit - (total_processed + total_updated)
                if remaining <= 0:
                    break
                chunk_limit = min(batch_size, remaining)

            missing_query = (
                db.query(Content)
                .outerjoin(ContentEmbedding, Content.id == ContentEmbedding.content_id)
                .filter(
                    or_(
                        ContentEmbedding.id.is_(None),
                        ContentEmbedding.embedding.is_(None),
                    )
                )
                .limit(chunk_limit)
            )
            batch = missing_query.all()
            if not batch:
                break

            res = cls.batch_embed_items(db, batch, batch_size=batch_size, force=force)
            total_processed += res["newly_created"]
            total_updated += res["updated"]

        return {
            "status": "success",
            "total_candidates": total_processed + total_updated,
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
        t0 = time.perf_counter()
        try:
            return cls._do_search_by_vector(db, vector, limit, content_type, exclude_content_ids)
        finally:
            elapsed = (time.perf_counter() - t0) * 1000
            ctx = get_current_timing_ctx()
            if ctx:
                ctx.vector_search_ms += elapsed

    @classmethod
    def _do_search_by_vector(
        cls,
        db: Session,
        vector: list[float] | Sequence[float],
        limit: int = 20,
        content_type: str | None = None,
        exclude_content_ids: set[int] | None = None,
    ) -> list[dict]:
        if not vector or len(vector) != settings.VECTOR_DIMENSION:
            return []

        exclude_ids = exclude_content_ids or set()

        if settings.ENABLE_PGVECTOR:
            try:
                distance_col = ContentEmbedding.embedding.cosine_distance(vector).label("distance")
                query = (
                    db.query(ContentEmbedding.content_id, distance_col)
                    .join(Content, Content.id == ContentEmbedding.content_id)
                    .filter(ContentEmbedding.embedding.isnot(None))
                )
                if exclude_ids:
                    query = query.filter(Content.id.notin_(exclude_ids))
                if content_type and content_type.lower() in ("movie", "tv"):
                    query = query.filter(Content.content_type == content_type.lower())

                results = query.order_by(distance_col.asc()).limit(limit).all()

                output = []
                for cid, dist in results:
                    similarity = max(0.0, min(1.0, 1.0 - float(dist)))
                    output.append({
                        "content_id": cid,
                        "similarity": round(similarity, 4),
                        "score": round(similarity, 4),
                    })
                return output
            except Exception:
                # Fallback to in-memory cosine similarity if pgvector extension query fails in tests/sqlite
                db.rollback()

        # In-memory cosine similarity fallback (for SQLite test environments or if pgvector unavailable)
        query = (
            db.query(ContentEmbedding.content_id, ContentEmbedding.embedding)
            .join(Content, Content.id == ContentEmbedding.content_id)
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
        for cid, emb in records:
            if emb is None:
                continue
            emb_arr = np.array(emb, dtype=np.float32)
            emb_norm = np.linalg.norm(emb_arr)
            if emb_norm == 0:
                continue
            cos_sim = float(np.dot(target_arr, emb_arr) / (target_norm * emb_norm))
            similarity = max(0.0, min(1.0, cos_sim))
            scored.append((cid, similarity))

        scored.sort(key=lambda x: x[1], reverse=True)
        top_items = scored[:limit]

        return [
            {
                "content_id": cid,
                "similarity": round(sim, 4),
                "score": round(sim, 4),
            }
            for cid, sim in top_items
        ]
