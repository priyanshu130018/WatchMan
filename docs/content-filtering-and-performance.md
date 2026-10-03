# WatchMan Content Filtering and Performance

This document provides a technical explanation of how WatchMan filters content, generates user embeddings, computes personalized recommendations, handles caching, and manages database performance.

---

## 1. Purpose

WatchMan is a discovery and recommendation platform for movies and TV/web-series. The recommendation engine personalizes suggestions based on:
1. **User behavior and interactions** (ratings, saved items, watch history, and WatchMan decisions).
2. **Dense content embeddings** capturing genres, themes, and overview semantics.
3. **Collaborative filtering** across user community preferences.
4. **Catalog metadata** (popularity and release freshness).

All recommendations are served through a layered architecture using PostgreSQL for persistent state, Upstash Redis for caching, and Celery for asynchronous background ML processing.

---

## 2. Content Filtering Flow

When an authenticated user requests recommendations, the system retrieves eligible items and removes any content the user has already interacted with or explicitly skipped.

```
+----------------------------------------------------------------------+
|                           User Action                                |
|   (Star Rating, Save/Watchlist, Playback Progress, WatchMan Decision)|
+-----------------------------------+----------------------------------+
                                    |
                                    v
+----------------------------------------------------------------------+
|                      PostgreSQL Interaction Tables                    |
|   (ratings, saved_content, watch_history, interaction_events,        |
|    watchman_decisions)                                               |
+-----------------------------------+----------------------------------+
                                    |
                                    v
+----------------------------------------------------------------------+
|                     Seen-Content Filter (Exclusion Set)              |
|   - Content user has saved / rated / watched                         |
|   - Content user marked as "skip"                                    |
+-----------------------------------+----------------------------------+
                                    |
                                    v
+----------------------------------------------------------------------+
|                     Multi-Channel Candidate Retrieval                |
|   1. Content-Based (pgvector cosine similarity with user vector)     |
|   2. Collaborative (ALS latent factors / memory-based KNN fallback)  |
|   3. Popularity (log-scaled popularity + audience rating)            |
|   4. Freshness (exponential recency decay + quality score)           |
+-----------------------------------+----------------------------------+
                                    |
                                    v
+----------------------------------------------------------------------+
|                     Hybrid Ranker & Diversity Filter                 |
|   - Composite weighted scoring across channels                       |
|   - Explicit genre/language preference matching                      |
|   - "Must Watch" boost / "Skip" suppression                          |
|   - Dominant genre saturation limits (max 4 per genre)               |
+-----------------------------------+----------------------------------+
                                    |
                                    v
+----------------------------------------------------------------------+
|                     Final Personalized Recommendations               |
+----------------------------------------------------------------------+
```

### Interaction Signals Used by Current Code
The exclusion set and taste profile use the following database records:
- **`ratings`**: Star ratings (1.0 to 10.0). Positive ratings ($\ge 6.0$) contribute to taste vectors; negative ratings ($\le 5.0$) are penalised or excluded.
- **`saved_content`**: Content saved to the user's watchlist or library.
- **`watch_history`**: Content playback entries including completion status and progress percentage.
- **`watchman_decisions`**: Explicit user classifications:
  - `must_watch`: High-confidence positive affinity (boosts ranking).
  - `time_pass`: Neutral positive interest.
  - `skip`: Explicit negative filter (immediately excluded from recommendations).
- **`interaction_events`**: Audit log of discrete user events (`save`, `rate`, `watch`, `watchman_decision`).

---

## 3. User Embeddings

A **user embedding** is a 384-dimensional dense floating-point vector representing the user's aggregated taste profile in the same semantic space as content embeddings.

```
Content Embedding (384-D)  <--\
Content Embedding (384-D)  <---- Weighted Combination ----> User Embedding (384-D)
Content Embedding (384-D)  <--/     (L2 Normalized)
```

### How User Embeddings Are Built
1. **Model**: `BAAI/bge-small-en-v1.5` (dimension: 384).
2. **Content Embeddings**: Computed from item metadata (title, overview, tagline, genres, cast, director) and stored in the `content_embeddings` table.
3. **Interaction Weighting**: The user's positive interactions are retrieved and weighted:
   - High ratings ($\ge 8.0$): Weight $1.0$
   - Moderate ratings ($6.0 - 7.9$): Weight $0.7$
   - `must_watch` decision: Weight $1.0$
   - `time_pass` decision: Weight $0.5$
   - Completed watch: Weight $0.8$
   - Saved content: Weight $0.6$
4. **Vector Combination**: Content vectors corresponding to positive interactions are multiplied by their weights, summed, and L2-normalized:
   $$\vec{u} = \frac{\sum_{i} w_i \vec{c}_i}{\|\sum_{i} w_i \vec{c}_i\|_2}$$
5. **Persistence**: The resulting vector is stored in the `user_embeddings` table with model name, dimension, and timestamp.

> [!NOTE]
> Explicit profile preferences (such as selected favorite genres or original languages in `user_preferences`) are stored as profile metadata and evaluated during hybrid ranking. They are not directly embedded into the BGE vector representation.

---

## 4. Asynchronous User Embedding Refresh

User embeddings are **derived data**. They are computed asynchronously to keep API request latency low and deterministic.

```
User interacts with UI (rate, save, watch, decide)
       |
       v (synchronous HTTP write)
PostgreSQL Interaction Tables
       |
       +------------------------------------+
       |                                    |
       v                                    v
Celery Beat (Every 10 min)           Real-time Trigger (Celery Task)
       |                                    |
       +-----------------+------------------+
                         |
                         v (enqueue via Redis)
                 Celery Worker Process
                         |
       Reads interaction state from PostgreSQL
                         |
       Calculates weighted 384-D vector
                         |
       Saves to `user_embeddings` table
                         |
                         v
Recommendation GET requests read stored vector
```

### Why Embedding Calculation is Asynchronous
- **Latency Protection**: Calculating embeddings involves database reads, vector math, and normalization. Running this inside an HTTP `GET /api/recommendations` request would cause multi-second stalls.
- **Database Decoupling**: PostgreSQL interaction tables remain the transactional source of truth; `user_embeddings` is an indexed read-optimized projection.
- **Graceful Fallback**: If a user is new or an embedding update is pending, the recommendation pipeline falls back to collaborative and popularity channels without error.

---

## 5. Candidate Generation Channels

The recommendation pipeline retrieves candidates across 4 distinct channels before merging and ranking:

| Channel | Method | Source Data | Description |
| :--- | :--- | :--- | :--- |
| **Content-Based** | Vector Similarity | `user_embeddings` + `content_embeddings` (`pgvector` cosine distance) | Finds catalog items closest in embedding space to the user's taste vector. |
| **Collaborative (ALS)** | Matrix Factorization | `als_user_factors` + `als_item_factors` | Computes dot product between precomputed user and item latent factors. |
| **Collaborative (KNN Fallback)** | User-User Cosine | `ratings`, `saved_content`, `watch_history` | Memory-based k-nearest neighbors fallback when ALS factors are not yet trained. |
| **Popularity** | Log-Scaled Quality | `contents.popularity`, `contents.vote_average` | Balances overall catalog view count and audience rating quality. |
| **Freshness** | Exponential Recency Decay | `contents.release_date`, `contents.vote_average` | Prioritizes recently released movies/series with a 180-day half-life decay. |

---

## 6. Content Filtering Rules

Before candidates enter final ranking, rigorous exclusion rules are applied:

```
[ All Catalog Items ]
         |
         v
 [ Exclude Seen Items ]  <-- ratings, saved_content, completed watch_history
         |
         v
 [ Exclude Skipped Items ] <-- watchman_decisions (decision == 'skip')
         |
         v
 [ Apply Channel Limit ]   <-- top candidates per channel (e.g. 50 items)
         |
         v
 [ Saturated Genre Filter ]<-- max 4 items per primary genre
         |
         v
 [ Top-N Ranked Output ]
```

### Concrete Filtering Example
1. User watches *Inception* and rates it 9/10.
2. User skips *The Matrix*.
3. Next recommendation request:
   - *Inception* is identified in `seen_ids` $\rightarrow$ **Excluded**.
   - *The Matrix* is identified in `skip_ids` $\rightarrow$ **Excluded**.
   - *Interstellar* matches *Inception*'s embedding profile $\rightarrow$ **Retained and Boosted**.
   - *Tenet* matches *Inception*'s theme and director $\rightarrow$ **Retained**.

---

## 7. Recommendation Cache

WatchMan uses a two-tier recommendation lookup:

```
GET /api/recommendations
         |
         v
+------------------------+
|   Redis Cache Check    |
+-----------+------------+
            |
      +-----+-----+
      |           |
 (Cache HIT) (Cache MISS)
      |           |
      |           v
      |   +------------------------------------+
      |   | PostgreSQL `recommendations` Table |
      |   +-----------------+------------------+
      |                     |
      |               +-----+-----+
      |               |           |
      |          (Found Recs) (No Recs / Force Refresh)
      |               |           |
      |               |           v
      |               |   +---------------------------------+
      |               |   | On-The-Fly Candidate Generation |
      |               |   | & Hybrid Ranking Pipeline       |
      |               |   +---------------+-----------------+
      |               |                   |
      |               +---------+---------+
      |                         |
      |                         v
      |               +--------------------+
      |               | Store in Redis TTL |
      |               +---------+----------+
      |                         |
      v                         v
+----------------------------------------------+
|         Return Paginated JSON Response       |
+----------------------------------------------+
```

- **Redis Cache HIT**: Returns pre-ranked, serialized recommendation items immediately.
- **Redis Cache MISS**: Reads persisted snapshots from the PostgreSQL `recommendations` table or executes on-the-fly candidate generation if empty or `force_refresh=true`.

---

## 8. API Performance (Latency Audit Snapshot)

The following metrics represent real-world baseline timings captured during the system latency audit when connected to remote cloud infrastructure (Supabase PostgreSQL and Upstash Redis):

### Latency Audit Snapshot

| Endpoint | Scenario | Total Time | DB Time | Redis Time | External / ML Time | SQL Queries |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `GET /api/movies` | Listing (page 1) | 5,860 ms | 3,203 ms | — | — | 8 |
| `GET /api/movies/550` | Cold Detail (OMDb Miss) | 2,880 ms | 1,042 ms | 204 ms | OMDb: 923 ms | 8 |
| `GET /api/movies/550` | Warm Detail (OMDb Hit) | 1,777 ms | 1,009 ms | 24 ms | OMDb: 24 ms | 8 |
| `GET /api/recommendations` | Redis Miss (Persisted DB) | 10,014 ms | 9,824 ms | 113 ms | — | 14 |
| `GET /api/recommendations` | Redis Hit | 207 ms | 126 ms | 80 ms | — | 1 |
| `GET /api/recommendations` | `force_refresh=true` | 28,942 ms | 28,500 ms | 144 ms | Vector: 1,115 ms<br>Candidates: 13,824 ms<br>Ranking: 940 ms | 125 |

> [!NOTE]
> These numbers represent an audit snapshot under remote cross-region network conditions. They are diagnostic measurements rather than permanent performance guarantees.

---

## 9. Performance Bottlenecks & Analysis

The audit identified 6 primary root causes for latency:

### 1. `Content` Model Default Relationship Loading (`lazy="selectin"`)
- **What happened**: The SQLAlchemy `Content` model declared `lazy="selectin"` on `genres`, `languages`, `cast`, `crew`, `videos`, `external_ids`, and `embedding`.
- **Why it was slow**: Querying a simple list of 20 movies automatically triggered 7 secondary queries to load cast, crew, videos, etc., even though movie cards only display title and genres.
- **Resolution**: Changed default relationship loading to `lazy="select"`. Configured endpoints to explicitly specify only the relationships they require via `options(selectinload(...))`.

### 2. Unbounded Collaborative Table Loading
- **What happened**: `CollaborativeCandidateGenerator._build_interaction_matrix` executed `.all()` on `Rating`, `SavedContent`, `WatchHistory`, and `InteractionEvent`.
- **Why it was slow**: Loading tens of thousands of full ORM objects into Python memory caused significant database and deserialization overhead.
- **Resolution**: Query only scalar tuples `(user_id, content_id, rating/progress)` instead of full ORM entities.

### 3. Sequential Seen-History Queries
- **What happened**: `CandidatePipeline.get_user_seen_content_ids` issued 6 sequential roundtrips for saved content, ratings, watch history, interaction events, and decisions.
- **Why it was slow**: Each sequential query paid a ~120 ms network roundtrip cost ($6 \times 120 = 720\text{ ms}$).
- **Resolution**: Combined the 6 lookups into a single SQL `UNION` query.

### 4. Full ORM Entity Instantiation in Candidate Channels
- **What happened**: `PopularityCandidateGenerator` and `FreshnessCandidateGenerator` loaded 100 complete `Content` ORM objects each.
- **Why it was slow**: Instantiating large numbers of ORM entities created memory pressure and triggered relationship loading during hybrid ranking.
- **Resolution**: Generators query lightweight column tuples `(id, popularity, vote_average)`. The candidate pipeline batch-loads only the merged candidate subset.

### 5. Synchronous External OMDb API Calls
- **What happened**: Movie detail requests synchronously contacted OMDb on cold lookups to fetch external Rotten Tomatoes / IMDb scores.
- **Why it was slow**: External HTTP requests blocked response completion for up to 923 ms.
- **Resolution**: Bounded OMDb HTTP timeouts to 3.0s, added Redis caching with 24-hour TTL for valid ratings, and added negative caching (1-hour TTL) for missing titles.

### 6. Remote Database Network Roundtrip Latency (RTT)
- **What happened**: Supabase PostgreSQL is hosted in a remote cloud region (`ap-northeast-2`).
- **Why it matters**: Each individual SQL query incurs a baseline 110–130 ms network roundtrip. An endpoint executing 10 sequential queries takes $> 1.2\text{ s}$ purely in wire transit time.

---

## 10. Why Database Query Count Matters

When querying a local database, executing 10 queries costs $< 5\text{ ms}$. However, with a managed cloud database:

$$\text{Total DB Latency} \approx N \times (\text{Network RTT} + \text{Execution Time})$$

```
Local Database:
Query 1 (0.5 ms) -> Query 2 (0.5 ms) -> ... -> Query 10 (0.5 ms) = 5 ms Total

Remote Cloud Database (120 ms RTT):
Query 1 (120 ms) -> Query 2 (120 ms) -> ... -> Query 10 (120 ms) = 1,200 ms Total!
```

Reducing query count via batch loading, joined loads, and SQL unions is the single most effective way to optimize remote cloud API performance.

---

## 11. Movie Listing vs. Movie Detail

To avoid unnecessary network traffic and SQL queries, WatchMan separates content retrieval into two distinct access patterns:

```
+------------------------------------+    +------------------------------------+
|         Movie Listing API          |    |          Movie Detail API          |
|         GET /api/movies            |    |         GET /api/movies/{id}       |
+------------------------------------+    +------------------------------------+
| - Lightweight summary DTO          |    | - Comprehensive detail response    |
| - Paginated window (LIMIT/OFFSET)  |    | - Explicitly loads:                |
| - Loads only:                      |    |   * Genres                         |
|   * Core content columns           |    |   * Languages                      |
|   * Genres (selectinload)          |    |   * Cast & Crew (joinedload Person)|
| - Omits cast, crew, videos, etc.   |    |   * Trailers / Video clips         |
|                                    |    |   * External IDs (IMDb, Wikidata)  |
|                                    |    |   * OMDb external ratings          |
+------------------------------------+    +------------------------------------+
```

---

## 12. Troubleshooting Guide

| Symptom | Diagnostic Step | Likely Cause & Solution |
| :--- | :--- | :--- |
| **Movie listing is slow ($> 2\text{ s}$)** | Inspect `sql_query_count` in API logs. | Ensure `ContentRepository.list` is not loading unneeded relationships (`cast`, `crew`, `videos`). |
| **Recommendations are slow ($> 3\text{ s}$)** | Check Redis log for cache hit vs miss. | On cache miss, verify that `user_embeddings` row exists and is not triggering on-the-fly embedding calculation. |
| **`force_refresh=true` takes $> 10\text{ s}$** | Inspect `CandidatePipeline` timing logs. | Check if candidate generators are loading full ORM objects or triggering N+1 genre lookups during ranking. |
| **Movie detail first request is slow** | Check `omdb_ms` in latency log. | External OMDb API lookup latency on cold items. Subsequent calls should hit Redis (`< 30\text{ ms}`). |
| **Redis log shows `Event loop is closed`** | Check async Redis connection pool lifecycle. | Occurs when an async Redis client created in one event loop is accessed across a closed loop. Ensure client connection lifecycle is tracked per event loop. |

---

## 13. Performance Debugging Method

When diagnosing or optimizing performance in WatchMan, follow this rigorous measurement-driven workflow:

```
1. Measure Baseline
   Capture total_ms, db_ms, redis_ms, and sql_query_count with timing context.
         |
         v
2. Identify Bottleneck
   Locate the specific function or query with high duration or roundtrip count.
         |
         v
3. Apply Targeted Fix
   Modify ONLY the responsible query or service (e.g. add batching or eager loading).
         |
         v
4. Re-run Identical Benchmark
   Execute the same test script against the updated service.
         |
         v
5. Verify Correctness
   Confirm that payloads, fields, and recommendation ranking outputs remain identical.
         |
         v
6. Proceed to Next Optimization
```

---

## 14. Architecture Invariants

All future contributions to WatchMan must adhere to these core principles:

1. **PostgreSQL is the source of truth**: All catalog items, interaction logs, ratings, and user profiles originate in PostgreSQL.
2. **Redis is an ephemeral cache**: Caches accelerate reads; loss of Redis cache must never cause data loss or service downtime.
3. **User embeddings are derived data**: Embeddings are mathematical summaries of PostgreSQL interaction tables.
4. **User embedding generation is strictly asynchronous**: Managed by Celery background workers; never compute embeddings inside user HTTP request handlers.
5. **Recommendation GET endpoints read stored vectors**: `GET /api/recommendations` reads the latest precomputed vector from `user_embeddings`.
6. **Preserve seen-content filtering**: Users must never receive content they have already watched, rated, saved, or skipped unless explicitly requested.
7. **Explicit relationship loading**: Never re-enable global `lazy="selectin"` across all `Content` relationships. Load relationships explicitly where required.
8. **Avoid unbounded table scans**: Always scope interaction and history queries by `user_id` or date boundaries.
9. **Keep external API calls off critical paths**: TMDB and OMDb lookups must be cached and bounded with tight timeouts.
10. **Preserve API contracts**: Never strip fields or alter frontend JSON response structures during database optimizations.
