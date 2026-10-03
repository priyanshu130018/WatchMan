import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.content import Content
from app.models.embedding import ContentEmbedding
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.core.config import settings

def main(target_count: int = 1000, batch_size: int = 50):
    db: Session = SessionLocal()
    print(f"Target count: {target_count}")
    print(f"Embedding model: {settings.EMBEDDING_MODEL}")
    print(f"Vector dimension: {settings.VECTOR_DIMENSION}")

    # Fetch top candidate items: mix of movies and TV shows ordered by popularity/vote_count
    # e.g., 800 top movies and 200 top TV shows or top 1000 overall by popularity
    top_movies = (
        db.query(Content)
        .filter(Content.content_type == "movie")
        .order_by(Content.popularity.desc().nullslast(), Content.vote_count.desc().nullslast())
        .limit(800)
        .all()
    )
    top_tv = (
        db.query(Content)
        .filter(Content.content_type == "tv")
        .order_by(Content.popularity.desc().nullslast(), Content.vote_count.desc().nullslast())
        .limit(200)
        .all()
    )

    combined = top_movies + top_tv
    print(f"Selected {len(combined)} items for embedding ({len(top_movies)} movies, {len(top_tv)} TV shows)")

    start_time = time.time()
    total_embedded = 0
    total_failed = 0

    for i in range(0, len(combined), batch_size):
        chunk = combined[i : i + batch_size]
        chunk_start = time.time()
        try:
            res = ContentEmbeddingService.batch_embed_items(db, chunk, batch_size=batch_size, force=False)
            total_embedded += (res.get("newly_created", 0) + res.get("updated", 0) + res.get("skipped_current", 0))
            elapsed = time.time() - chunk_start
            print(f"Batch {i // batch_size + 1}/{(len(combined) + batch_size - 1) // batch_size}: "
                  f"Processed {len(chunk)} items in {elapsed:.2f}s (Total so far: {total_embedded})")
        except Exception as e:
            print(f"Batch {i // batch_size + 1} failed: {e}")
            # Try per item fallback
            for item in chunk:
                try:
                    ContentEmbeddingService.embed_content(db, item.id)
                    total_embedded += 1
                except Exception as inner_e:
                    print(f"Failed to embed content_id={item.id}: {inner_e}")
                    total_failed += 1

    total_time = time.time() - start_time
    print("\n--- Summary ---")
    print(f"Total time: {total_time:.2f}s")
    print(f"Total successfully embedded: {total_embedded}")
    print(f"Total failed: {total_failed}")

    # Verification
    stored_count = db.query(ContentEmbedding).count()
    print(f"Total rows in content_embeddings: {stored_count}")

    # Check dimensions and sample
    sample_records = db.query(ContentEmbedding).limit(5).all()
    all_384 = True
    for r in sample_records:
        dim = len(r.embedding) if r.embedding is not None else 0
        if dim != 384:
            all_384 = False
        print(f"Sample content_id={r.content_id}, dim={dim}, model={r.model_name}, hash={r.content_hash[:10]}...")

    print(f"All sampled vectors are exactly 384 dimensions: {all_384}")
    db.close()

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    main(count)
