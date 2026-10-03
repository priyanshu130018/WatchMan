import sys
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.content import Content
from app.models.embedding import ContentEmbedding
from app.ml.embeddings.content_embeddings import ContentEmbeddingService
from app.core.config import settings

def process_chunk(content_ids: list[int]):
    db = SessionLocal()
    try:
        contents = db.query(Content).filter(Content.id.in_(content_ids)).all()
        res = ContentEmbeddingService.batch_embed_items(db, contents, batch_size=len(contents), force=False)
        return len(contents), res.get("newly_created", 0), res.get("updated", 0), res.get("skipped_current", 0)
    finally:
        db.close()

def main(target_count: int = 1000, batch_size: int = 25, max_workers: int = 8):
    db: Session = SessionLocal()
    print(f"Target count: {target_count}")
    print(f"Workers: {max_workers} | Batch size: {batch_size}")
    print(f"Embedding model: {settings.EMBEDDING_MODEL}")
    print(f"Vector dimension: {settings.VECTOR_DIMENSION}")

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
    content_ids = [c.id for c in combined]
    db.close()

    print(f"Selected {len(content_ids)} target items. Checking existing embeddings...")
    chunks = [content_ids[i:i+batch_size] for i in range(0, len(content_ids), batch_size)]
    print(f"Total chunks to process: {len(chunks)}")

    start_time = time.time()
    total_processed = 0
    total_new = 0
    total_skipped = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_chunk, chunk): idx for idx, chunk in enumerate(chunks)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                cnt, n_new, n_up, n_skip = future.result()
                total_processed += cnt
                total_new += n_new
                total_skipped += n_skip
                print(f"[Worker] Chunk {idx+1}/{len(chunks)} done: {n_new} new, {n_skip} skipped. (Progress: {total_processed}/{len(content_ids)})", flush=True)
            except Exception as exc:
                print(f"[Worker] Chunk {idx+1} failed: {exc}", flush=True)

    elapsed = time.time() - start_time
    print(f"\n--- Embedding Generation Finished in {elapsed:.2f}s ---")
    print(f"Newly created: {total_new}")
    print(f"Skipped (already current): {total_skipped}")

    # Verification
    db = SessionLocal()
    total_in_db = db.query(ContentEmbedding).count()
    print(f"Total ContentEmbedding rows in DB: {total_in_db}")

    # Check that all have dimension 384 and model BAAI/bge-small-en-v1.5
    invalid_dim = db.query(ContentEmbedding).filter(ContentEmbedding.dimension != 384).count()
    print(f"Rows with invalid dimension (!=384): {invalid_dim}")
    assert invalid_dim == 0, "Some embeddings have invalid dimensions!"

    sample = db.query(ContentEmbedding).first()
    print(f"Sample: ID={sample.id}, content_id={sample.content_id}, dim={len(sample.embedding)}, model={sample.model_name}, hash={sample.content_hash[:16]}...")
    db.close()

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    main(count)
