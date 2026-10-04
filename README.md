# WatchMan - Movie & Web Series Discovery & Recommendation Platform

A production-ready, full-stack movie and web-series discovery platform built with React (TypeScript), FastAPI, PostgreSQL (+pgvector), Upstash Redis, and Celery, powered by a hybrid recommendation engine.

---

## High-Level Architecture

                                  +-------------------+
                                  |   User / Browser  |
                                  +---------+---------+
                                            |
                                            v
                                  +-------------------+
                                  |   React Frontend  |
                                  | (TypeScript/Vite) |
                                  +---------+---------+
                                            | HTTPS / REST
                                            v
                                  +-------------------+
                                  |  FastAPI Backend  |
                                  |  (Python Service) |
                                  +----+----+----+----+
                                       |    |    |
                     +-----------------+    |    +-----------------+
                     |                      |                      |
                     v                      v                      v
          +--------------------+  +-------------------+  +--------------------+
          |    PostgreSQL      |  |   Upstash Redis   |  | Dedicated Workers  |
          | (Supabase+pgvector)|  | (Cache & Broker)  |  |  (Celery Cluster)  |
          +--------------------+  +---------+---------+  +---------+----------+
                     ^                      ^                      ^
                     |                      |                      |
                     |                      +----------------------+
                     |                                             |
                     |            +-------------------+            |
                     +------------+    Celery Beat    +------------+
                                  | (Periodic Worker) |
                                  +-------------------+

### Component Roles & Responsibilities
- **React Frontend**: Single-page application rendering the catalog browsing interface, search bar, personalized shelves, movie detail views, and user feedback controls (*Must Watch*, *Time Pass*, *Skip*).
- **FastAPI Backend**: High-performance asynchronous REST API handling authentication, catalog filtering, paginated content delivery, and recommendation requests.
- **PostgreSQL (Supabase)**: Relational database storing the primary content catalog (11K+ items), user profiles, ratings, saved content, watch history, WatchMan decisions, vector embeddings (`content_embeddings`, `user_embeddings`), and collaborative factors (`als_user_factors`, `als_item_factors`).
- **Upstash Redis**: In-memory data store used as a TLS-encrypted Celery message broker and a sub-second response cache for personalized recommendations and external metadata.
- **Celery Worker Cluster & Celery Beat**: Distributed background processing system with dedicated worker isolation:
  - `content_based_worker` (queue: `content_based`): Computes and refreshes 384-D BGE user taste embeddings and content-based recommendation updates.
  - `als_worker` (queue: `als`): Trains implicit-feedback ALS collaborative filtering models and persists 64-D latent factors.
  - `celery_worker` (queues: `default,celery`): Handles general background tasks, TMDB ingestion, and orphan cleanup.
  - `celery_beat`: Cron scheduler dispatching periodic task triggers.

---

## Core System Architecture

### 1. Authentication
WatchMan implements stateless JSON Web Token (JWT) authentication directly in FastAPI:

```
[ User Login / Signup ]
           |
           v
FastAPI generates signed HS256 JWT Access Token
(Contains `sub`: user_id, `exp`: expiration timestamp)
           |
           v
Frontend stores token & attaches Authorization: Bearer <token>
           |
           v
FastAPI `get_current_user` dependency:
  1. Decodes & validates JWT signature and expiry.
  2. Resolves user UUID from token `sub` claim.
  3. Loads authenticated `User` record from PostgreSQL.
```

- **JWT Access Token**: Cryptographically signed access token containing user identity claims (`sub` = user UUID).
- **Identity Resolution**: The FastAPI backend decodes the token on protected routes and queries the PostgreSQL `users` table to load the active account.
- **Database Authority**: PostgreSQL is the single source of truth for user identities and permissions. Supabase Auth is not responsible for internal application session management.

---

### 2. Movie & Series Catalog
WatchMan maintains a normalized catalog of over 11,000 movies and web series stored locally in PostgreSQL:

- **Local Storage**: Content metadata is indexed in PostgreSQL for instantaneous sorting, multi-attribute filtering (genres, release year, language), and full-text search.
- **External Data Source (TMDB)**: The Movie Database (TMDB) API serves as the external ingestion and synchronization source for new titles, official trailers, and poster assets.
- **Two Distinct API Patterns**:
  1. **Movie Listing (`GET /api/movies`)**: Optimized for high-throughput pagination. Returns lightweight summary records and eagerly loads only genre associations (`Content.genres`), omitting heavy relationship graphs.
  2. **Movie Detail (`GET /api/movies/{id}`)**: Designed for deep inspection of a single title. Explicitly loads rich relationships including `genres`, spoken `languages`, `cast` (ordered by billing), `crew` (directors/writers), `videos` (trailers), and `external_ids` (IMDb, Wikidata).

---

### 3. Recommendation System
WatchMan uses a multi-channel hybrid recommendation architecture combining dense content embeddings and implicit-feedback matrix factorization:

```
User
  │
  ▼
Recommendation API (`GET /api/recommendations`)
  │
  ▼
Redis Response Cache (Check TTL cache)
  │ (Cache Miss / Invalidation)
  ▼
Candidate Pipeline (Parallel Channel Generation)
  ├── Content-Based Candidates
  │     └── BGE 384-D taste vector + pgvector cosine similarity
  ├── ALS Collaborative Candidates
  │     └── 64-D user/item latent factors + dot product scoring
  ├── Popularity Candidates
  │     └── Global vote count and weighted ratings
  └── Freshness Candidates
        └── Recency-boosted catalog releases
  │
  ▼
Candidate Merge & Deduplication
  ├── Channel attribution tracking
  └── Seen-content suppression (ratings, watchlist, history, skips)
  │
  ▼
HybridRanker
  └── Multi-objective weighted scoring
  │
  ▼
Diversity & Business Logic Filtering
  └── Genre balancing and distribution guards
  │
  ▼
PostgreSQL Snapshot Persistence (`recommendations` table)
  │
  ▼
Redis Cache Write (1-hour TTL)
  │
  ▼
API JSON Response
  │
  ▼
React Frontend Personalized Shelves
```

#### HybridRanker Formula
The final candidate score is computed as a weighted linear combination of normalized channel signals and user preference alignment:

$$\text{Score} = 0.35 \times \text{Content} + 0.25 \times \text{ALS} + 0.15 \times \text{Popularity} + 0.15 \times \text{Freshness} + 0.10 \times \text{Preference}$$

- **Content Score ($0.35$)**: Cosine similarity between the user's 384-D BGE taste vector and the movie's 384-D content embedding.
- **ALS Score ($0.25$)**: Dot product between the user's 64-D latent vector and the item's 64-D latent vector, min-max normalized across candidates.
- **Popularity Score ($0.15$)**: Normalized logarithmic scale of total vote counts and rating averages.
- **Freshness Score ($0.15$)**: Exponential decay score favoring recent releases and newly added catalog items.
- **Preference Match ($0.10$)**: Direct genre alignment boost based on the user's explicit preference selections.

#### Representation Independence
The recommendation engine enforces strict vector space independence:
- **Content Space**: 384-dimensional semantic space (`BAAI/bge-small-en-v1.5`) capturing semantic synopses, cast, crew, and thematic metadata.
- **Collaborative Space**: 64-dimensional latent factor space derived via implicit Alternating Least Squares (ALS) matrix factorization over historical user interactions.
- **Zero Space Leakage**: The 384-D content embeddings and 64-D ALS factors are completely separate vector spaces. They are never concatenated, averaged, or projected together; integration occurs solely at score fusion time inside [`HybridRanker`](file:///c:/Users/13ver/Desktop/New%20folder/project/WatcheMan/backend/app/ml/hybrid_ranker.py).

#### Cold-Start Behavior
- **New Users**: When a user has no historical interactions or ALS factors, the ALS generator returns an empty list (`[]`) in $<1$ ms without blocking or triggering synchronous model fitting.
- **Graceful Degradation**: Cold-start users are served high-quality recommendations composed of Content-Based candidates (from onboarding preferences), Popularity candidates, and Freshness candidates.
- **Automatic Ingestion**: Once user interactions cross the threshold, the background worker incorporates the user into the next training iteration.

For full mathematical derivations, hyperparameter specifications, offline evaluation benchmarks, and channel ablation studies, see [ALS Collaborative-Filtering Implementation and Evaluation](file:///c:/Users/13ver/Desktop/New%20folder/project/WatcheMan/docs/als-collaborative-filtering.md) and [Content Filtering and Performance Guide](file:///c:/Users/13ver/Desktop/New%20folder/project/WatcheMan/docs/content-filtering-and-performance.md).

---

### 4. Vector Embeddings & Latent Factor Persistence
All latent representations are persisted in PostgreSQL to ensure instantaneous candidate retrieval without online inference:

| Representation | Dimensions | Model / Algorithm | Storage Table | Index / Lookup Method |
| :--- | :--- | :--- | :--- | :--- |
| **Content Embeddings** | 384 | `BAAI/bge-small-en-v1.5` | `content_embeddings` | `pgvector` IVFFlat / HNSW Cosine Distance |
| **User Taste Vectors** | 384 | Weighted Interaction Centroid | `user_embeddings` | Direct indexed lookup by `user_id` |
| **User ALS Factors** | 64 | Implicit ALS Matrix Factorization | `als_user_factors` | JSON vector / NumPy array by `user_id` |
| **Item ALS Factors** | 64 | Implicit ALS Matrix Factorization | `als_item_factors` | JSON vector / NumPy array by `content_id` |
| **Recommendations** | Top-N Items | HybridRanker Pipeline | `recommendations` | Snapshot persisted per `user_id` |

---

### 5. Distributed Background Processing (Celery Cluster & Celery Beat)
All expensive machine learning routines, offline training, embedding calculations, and external catalog syncs are distributed across isolated Celery workers:

```
Celery Beat (Scheduler)
       │
       │ Periodic cron events
       ▼
  Upstash Redis (Message Broker)
       │
       ├── Queue: `content_based` ──► `content_based_worker`
       │                                ├── Recomputes 384-D BGE user taste embeddings
       │                                └── Generates content-based recommendation updates
       │
       ├── Queue: `als`            ──► `als_worker`
       │                                ├── Builds sparse interaction confidence matrices
       │                                ├── Trains 64-D implicit ALS model
       │                                └── Persists factors to `als_user_factors` / `als_item_factors`
       │
       └── Queue: `default,celery` ──► `celery_worker`
                                        ├── Syncs catalog and poster metadata with TMDB
                                        └── Executes cache invalidation and maintenance tasks
```

#### Dedicated Worker Isolation:
- `content_based_worker` (queue: `content_based`): Handles CPU/GPU-intensive embedding centroid updates and content similarity calculations.
- `als_worker` (queue: `als`): Dedicated memory-isolated worker executing implicit ALS matrix factorization, factor serialization, and model evaluation.
- `celery_worker` (queues: `default,celery`): Manages general async tasks, TMDB ingestion, and orphan cleanup.
- `celery_beat`: Cron scheduler dispatching periodic task triggers every 10–60 minutes.

---

### 6. Redis Caching & Connection Lifecycle
Upstash Redis serves two primary roles:
1. **Celery Message Broker & Result Backend**: Manages task queuing and execution state.
2. **Response Cache**: Caches personalized recommendation lists (1-hour TTL) and OMDb external rating lookups (24-hour TTL).

#### Cache Invalidation & Event Loop Notice:
When a user updates their preferences or explicitly requests a refresh, the backend clears cached keys (`recommendations:user:<id>:*`). 
> [!NOTE]
> In asynchronous Python environments, if an async Redis client is shared across event loop boundaries during task execution, a warning such as `"Event loop is closed"` may be logged during pattern deletion. This represents an internal connection pool cleanup notification rather than a failure of Redis or Celery task execution.

---

## Project Structure

```
WatcheMan/
├── .github/
│   └── workflows/
│       └── ci.yml               # Automated CI for Backend (pytest) and Frontend (lint & build)
├── backend/
│   ├── alembic/                 # Linear database migrations
│   ├── app/
│   │   ├── api/                 # FastAPI modular routers (/api/...)
│   │   ├── core/                # Config, security, timing, telemetry, Redis cache, Celery
│   │   ├── db/                  # Database session and base models
│   │   ├── ml/                  # Recommendation pipeline, embeddings, ALS, hybrid ranker
│   │   ├── models/              # SQLAlchemy schema models (Content, Interaction, Recs)
│   │   ├── repositories/        # Database access layer with explicit relationship loading
│   │   ├── schemas/             # Pydantic request/response validation models
│   │   ├── services/            # Catalog, recommendation, interaction, and TMDB/OMDb services
│   │   └── tasks/               # Celery async tasks (embeddings, ALS, TMDB sync)
│   ├── tests/                   # Hermetic unit and regression tests
│   ├── Dockerfile               # Multi-stage production container definition
│   ├── requirements.txt         # Production Python dependencies
│   └── requirements-dev.txt     # Test dependencies
├── docs/
│   ├── als-collaborative-filtering.md        # ALS implementation, evaluation benchmarks & math
│   └── content-filtering-and-performance.md  # Content filtering & latency audit guide
├── frontend/
│   ├── src/
│   │   ├── components/          # UI cards, modals, navigation, shelves
│   │   ├── features/            # Feature views (Home, Movie, Series, Search, Profile, Recs)
│   │   ├── routes/              # TanStack router page definitions
│   │   ├── services/            # API client services
│   │   └── types/               # TypeScript domain interfaces
│   ├── Dockerfile               # Local Docker Compose container definition
│   └── package.json             # NPM dependencies and scripts
├── scripts/
│   ├── audit_latency.py         # Automated API latency and SQL query benchmark
│   ├── backfill_content_embeddings.py    # Selective embedding maintenance CLI
│   ├── create_catalog_backup.py          # Isolated catalog SQL backup utility
│   ├── ingest_tmdb_catalog.py            # Partitioned TMDB catalog ingestion CLI
│   ├── seed_als_dataset_and_verify.py    # Multi-user synthetic interaction dataset seeder
│   └── verify_ml_data_flow.py            # Live ML health and database report
├── compose.yml                  # Local Docker Compose (API + 3 Workers + Beat + Frontend)
├── render.yaml                  # Render Blueprint definition (FastAPI + Workers + Beat)
├── .env.example                 # Root environment template
└── README.md
```

---

## Environment Configuration

Configuration is cleanly divided between **Backend Secrets** (server-only) and **Public Frontend Variables** (`VITE_*` only).

### Required Environment Variables

| Variable | Scope | Purpose |
| :--- | :--- | :--- |
| `APP_ENV` | Backend | Environment mode (`production` or `development`) |
| `DATABASE_URL` | Backend | Supabase PostgreSQL connection string with pgvector |
| `REDIS_URL` | Backend | Upstash Redis connection string (`rediss://`) |
| `CELERY_BROKER_URL` | Backend | Celery broker URL |
| `CELERY_RESULT_BACKEND` | Backend | Celery result backend |
| `SECRET_KEY` | Backend | Secret key for JWT signing (HS256) |
| `TMDB_API_KEY` | Backend | TMDB v3 API key |
| `OMDB_API_KEY` | Backend | OMDb API key for external ratings |
| `HF_API_TOKEN` | Backend | Hugging Face Inference API token |
| `CORS_ORIGINS` | Backend | Allowed frontend origins (comma-separated) |
| `VITE_API_BASE_URL` | Frontend | Public backend API URL |
| `VITE_TMDB_IMAGE_BASE_URL`| Frontend | TMDB image CDN base URL |

---

## Local Development with Docker Compose

Start the complete stack connected to managed cloud services (Supabase & Upstash):

```bash
# 1. Copy the environment template
cp .env.example .env

# 2. Fill in your API keys in .env

# 3. Build and launch all services
docker compose up --build -d

# 4. Verify running containers
docker compose ps
# -> watchman_frontend              (http://localhost:3000)
# -> watchman_backend               (http://localhost:8000)
# -> watchman_content_based_worker  (queue: content_based)
# -> watchman_als_worker            (queue: als)
# -> watchman_celery_worker         (queues: default, celery)
# -> watchman_celery_beat           (periodic task scheduler)

# 5. Check API health
curl http://localhost:8000/health
```

---

## Testing & Benchmarks

### Automated Test Suite
```bash
# Run tests inside backend container
docker compose run --rm backend python -m pytest -q
```

### Latency Audit Benchmark
Measure end-to-end endpoint performance, database execution times, Redis timing, and SQL query counts:

```bash
python scripts/audit_latency.py
```

---
