# WatchMan - Movie & Web Series Discovery & Recommendation Platform

A production-ready, full-stack movie and web-series discovery platform built with React (TypeScript), FastAPI, PostgreSQL (+pgvector), Upstash Redis, and Celery, powered by a hybrid recommendation engine.

---

## High-Level Architecture

```
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
          |    PostgreSQL      |  |   Upstash Redis   |  |   Celery Worker    |
          | (Supabase+pgvector)|  | (Cache & Broker)  |  | (Async Background) |
          +--------------------+  +---------+---------+  +---------+----------+
                     ^                      ^                      ^
                     |                      |                      |
                     |                      +----------------------+
                     |                                             |
                     |            +-------------------+            |
                     +------------+    Celery Beat    +------------+
                                  | (Periodic Worker) |
                                  +-------------------+
```

### Component Roles & Responsibilities
- **React Frontend**: Single-page application rendering the catalog browsing interface, search bar, personalized shelves, movie detail views, and user feedback controls (*Must Watch*, *Time Pass*, *Skip*).
- **FastAPI Backend**: High-performance asynchronous REST API handling authentication, catalog filtering, paginated content delivery, and recommendation requests.
- **PostgreSQL (Supabase)**: Relational database storing the primary content catalog (11K+ items), user profiles, ratings, saved content, watch history, WatchMan decisions, and vector embeddings using the `pgvector` extension.
- **Upstash Redis**: In-memory data store used as a TLS-encrypted Celery message broker and a sub-second response cache for personalized recommendations and external metadata.
- **Celery Worker & Celery Beat**: Distributed background processing system responsible for periodically refreshing stale user embeddings, computing offline ALS collaborative factors, and syncing catalog metadata without blocking user-facing API endpoints.

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
WatchMan uses an asynchronous, multi-channel hybrid recommendation architecture:

```
User Interactions (Rate, Save, Watch, Decision)
                     |
                     v
             PostgreSQL Tables
                     |
                     v
   Asynchronous Celery Worker Refresh
                     |
                     v
        `user_embeddings` Table
                     |
                     v
    Multi-Channel Candidate Generation
   (Content-Based, ALS Collaborative, Popularity, Freshness)
                     |
                     v
         Hybrid Scoring & Ranking
   (Preference Matching + Diversity Guards)
                     |
                     v
    Persisted Recommendations / Redis Cache
                     |
                     v
            FastAPI GET Response
                     |
                     v
               React Frontend
```

- **Asynchronous Taste Vector Generation**: User embeddings are generated in the background by Celery workers. Normal `GET /api/recommendations` requests read the precomputed vector from the `user_embeddings` table and **never** calculate or write embeddings synchronously.
- **Deterministic Delivery**: Recommendation responses are cached in Redis and backed by persistent database snapshots in the `recommendations` table.

For an in-depth breakdown of candidate generation, seen-content filtering, and performance optimizations, see [Content Filtering and Performance Guide](file:///c:/Users/13ver/Desktop/New%20folder/project/WatcheMan/docs/content-filtering-and-performance.md).

---

### 4. Vector Embeddings
WatchMan employs dense semantic vectors to understand content themes and user preferences:

- **Model**: `BAAI/bge-small-en-v1.5`
- **Vector Dimension**: 384 dimensions
- **Content Embeddings**: Computed from title, overview, tagline, genres, cast, and crew. Stored in the `content_embeddings` table with an indexed `pgvector` column.
- **User Embeddings**: Mathematical summary of a user's positive interactions (high star ratings, watchlist saves, completed watch history, and *"Must Watch"* decisions). Stored in the `user_embeddings` table.
- **Similarity Search**: Content-based candidates are retrieved using native `pgvector` cosine distance queries:
  $$\text{Cosine Similarity}(\vec{u}, \vec{c}) = \frac{\vec{u} \cdot \vec{c}}{\|\vec{u}\|_2 \|\vec{c}\|_2}$$

---

### 5. Background Processing (Celery & Celery Beat)
All expensive ML computations, embedding generation, and catalog sync routines are offloaded to background workers:

```
Celery Beat (Scheduler)
       |
       | Periodic Trigger (Every 10 minutes)
       v
  Upstash Redis (Task Queue)
       |
       v
Celery Worker Process
       |
       +---> `refresh_changed_user_embeddings`: Recomputes taste vectors for active users
       +---> `train_als_model`: Retrains collaborative matrix factorization
       +---> `sync_catalog`: Pulls fresh updates from TMDB
       |
       v
Updates `user_embeddings` in PostgreSQL
```

#### What Happens When a User Interacts:
1. When a user rates, saves, watches, or classifies a movie (*Must Watch*, *Time Pass*, *Skip*), the interaction is recorded immediately in PostgreSQL.
2. The user's taste vector is flagged as stale.
3. On the next worker run (scheduled every 10 minutes or triggered via event), Celery loads the latest interaction weights and updates the user's 384-D vector in `user_embeddings`.
4. Subsequent recommendation requests immediately benefit from the refreshed taste profile.

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
│   └── content-filtering-and-performance.md  # Deep dive into filtering & latency audit
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
│   ├── ingest_tmdb_catalog.py            # Partitioned TMDB catalog ingestion CLI
│   └── verify_ml_data_flow.py            # Live ML health and database report
├── compose.yml                  # Local Docker Compose (API + Worker + Beat + Frontend)
├── render.yaml                  # Render Blueprint definition (FastAPI + Worker + Beat)
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

# 3. Build and launch all 4 services
docker compose up --build -d

# 4. Verify running containers
docker compose ps
# -> watchman_frontend        (http://localhost:3000)
# -> watchman_backend         (http://localhost:8000)
# -> watchman_celery_worker   (background task runner)
# -> watchman_celery_beat     (periodic task scheduler)

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

## License

MIT License
