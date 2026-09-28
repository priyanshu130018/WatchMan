# WatchMan Recommendation & Embedding Architecture

## Architectural Philosophy: Selective + On-Demand Embeddings

WatchMan deliberately **does NOT generate embeddings for the entire ~11,280-item catalog**.

In a production streaming / discovery platform, embedding the entire long-tail catalog up-front is computationally wasteful, incurs unnecessary API latency and cost, and provides negligible quality improvements for unviewed titles. Instead, WatchMan employs a **hybrid selective and on-demand architecture**:

1. **Selective Initial High-Value Embeddings**:
   - Top 500 popular movies
   - Top 500 popular TV/web-series
   - Initial target: ~1,000 dense 384-dimensional content vectors (`all-MiniLM-L6-v2`).
   - Uses real catalog popularity metrics and ranking rather than random or arbitrary database rows.

2. **Interaction-Driven On-Demand Embeddings**:
   - Generated and persisted whenever a real user interacts with content:
     - Watched content (`watch_history`)
     - Saved / Favorited content (`saved_content`)
     - Star ratings (`ratings`)
     - User reviews (`reviews`)
     - WatchMan feedback decisions (`must_watch`, `time_pass`, `skip`)
   - If an embedding already exists and is current (matching `content_hash`, `model_name`, `dimension`, and `model_version`), it is reused idempotently.
   - If missing or stale, the vector is computed and persisted asynchronously via Celery background tasks.
   - The user's taste embedding (`user_embeddings`) is then incrementally refreshed from the updated vector pool.

3. **Optional Search / Open-Driven Embeddings**:
   - Gated behind `ENABLE_SEARCH_EMBEDDING=false` (default: disabled).
   - Only triggered when a user genuinely opens / inspects content details beyond a configured threshold (`SEARCH_EMBED_THRESHOLD=3`), never merely for appearing in search results.

4. **Multi-Channel Candidate Generation Without Vector Assumption**:
   - The candidate pipeline combines multiple diverse retrieval channels:
     - **Content-Based Candidates**: Cosine vector similarity against available embeddings in pgvector. If few or zero embeddings exist, this channel gracefully returns empty candidates without failing.
     - **Collaborative Filtering**: Alternating Least Squares (ALS) matrix factorization and memory-based collaborative filtering.
     - **Popularity**: Top trending and highly rated catalog titles.
     - **Freshness**: Recent releases and premiering content.
     - **User Preferences**: Explicit genre and language preferences.
   - No recommendation query triggers a full catalog backfill.

5. **Hybrid Ranking & Diversity**:
   - The `HybridRanker` blends scores with configurable weights:
     - `REC_WEIGHT_CONTENT` (0.40)
     - `REC_WEIGHT_COLLABORATIVE` (0.30)
     - `REC_WEIGHT_POPULARITY` (0.15)
     - `REC_WEIGHT_FRESHNESS` (0.10)
     - `REC_WEIGHT_PREFERENCE` (0.05)
   - Diversity filtering prevents genre saturation (max 4 per genre).

---

## Architectural Flow Diagram

```
                             ALL CATALOG (11,280+ items)
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
                    ▼                   ▼                   ▼
               Popularity           Freshness          Preferences
                    │                   │                   │
                    └───────────────────┼───────────────────┘
                                        ▼
                                 Candidate Pool
                                        │
                        ┌───────────────┴───────────────┐
                        │                               │
                        ▼                               ▼
               Embedded Candidates               ALS Candidates
           (from ~1K initial + interacted)       (User-Item Latent)
                        │                               │
                        └───────────────┬───────────────┘
                                        ▼
                                  HybridRanker
                            (Weights + Diversity)
                                        │
                                        ▼
                               Final Recommendations
```

---

## Interaction Lifecycle

```
REAL USER INTERACTION (watch, save, rate, review, decision)
                    ↓
InteractionTrackingService / WatchmanService
                    ↓
enqueue_interaction_ml_update
                    ↓
check content_embeddings
                    ↓
        IF EMBEDDING EXISTS AND CURRENT
            reuse existing vector
        ELSE
            generate 384-D vector via SentenceEncoder
            persist to content_embeddings
                    ↓
UserEmbeddingService (compute weighted taste vector)
                    ↓
RecommendationGenerator (generate & persist ranked recommendations)
```

---

## Management & CLI Scripts

### Selective Content Embedding Backfill

The backfill script (`scripts/backfill_content_embeddings.py`) provides targeted modes:

- **Mode A (Popular - Default)**:
  ```bash
  python scripts/backfill_content_embeddings.py --popular --limit 1000
  ```
  Embeds the top 500 movies and top 500 TV shows based on catalog popularity ranking. Idempotent and skips existing current embeddings.

- **Mode B (Interaction-Driven)**:
  ```bash
  python scripts/backfill_content_embeddings.py --interacted
  ```
  Finds real content referenced by user watch history, favorites, ratings, reviews, decisions, and interaction telemetry, embedding only missing vectors.

- **Mode C (Explicit IDs)**:
  ```bash
  python scripts/backfill_content_embeddings.py --content-ids 15,550,1024
  ```

- **Mode D (Full Catalog - Gated Opt-In)**:
  ```bash
  python scripts/backfill_content_embeddings.py --all --confirm-all
  ```
  *Strong warning required. Never executed automatically.*

### ML Data Flow Verification

Verify database status, embedding coverage, and policy state:

```bash
python scripts/verify_ml_data_flow.py
```

Outputs:
- Total catalog items
- Total content embeddings and percentage coverage
- Popular embedded items vs target (e.g., `1000/1000`)
- Interacted embedded items vs total interacted titles
- Registered users and active user taste embeddings
- Collaborative ALS state and persisted recommendations
- Configured embedding policy flags

---

## Configuration Reference

Key settings in `.env`:

| Setting | Default | Description |
|---|---|---|
| `INITIAL_POPULAR_MOVIE_EMBED_LIMIT` | `500` | Target top popular movies for initial embedding |
| `INITIAL_POPULAR_TV_EMBED_LIMIT` | `500` | Target top popular TV shows for initial embedding |
| `ENABLE_INTERACTION_EMBEDDING` | `true` | Enable on-demand embedding on real user interaction |
| `ENABLE_SEARCH_EMBEDDING` | `false` | Enable open/search-driven embedding gating |
| `SEARCH_EMBED_THRESHOLD` | `3` | Detail view threshold to qualify for search embedding |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model identifier |
| `VECTOR_DIMENSION` | `384` | Dense vector dimension |
| `ENABLE_PGVECTOR` | `true` | Enable native pgvector cosine distance |
