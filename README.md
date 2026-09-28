# WatchMan - Movie & Web Series Discovery & Recommendation Platform

A production-ready, full-stack movie and web-series discovery platform built with React (TypeScript), FastAPI, PostgreSQL (+pgvector), Upstash Redis, and Supabase Auth, powered by a hybrid recommendation engine.

---

## Architecture Overview

```
                      +-----------------------------+
                      |       Vercel (Frontend)     |
                      |  React 19 / TanStack Router |
                      +--------------+--------------+
                                     |
                                     | HTTPS / REST
                                     v
                      +-----------------------------+
                      |     Render (Backend API)    |
                      |        FastAPI Python       |
                      +--------------+--------------+
                                     |
               +---------------------+---------------------+
               |                     |                     |
               v                     v                     v
+-------------------------+ +-----------------+ +-------------------------+
|   Supabase PostgreSQL   | |  Upstash Redis  | |  Render (Celery Worker) |
|  pgvector 384-D vectors | | TLS Broker/Cache| | Background ML & Ingest  |
|  11K+ Catalog Items     | +-----------------+ +-------------------------+
+-------------------------+                                |
                                                           v
                                                +-------------------------+
                                                |   Render (Celery Beat)  |
                                                | Periodic Task Scheduler |
                                                +-------------------------+
```

### Production Deployment Target
- **Frontend**: [Vercel](https://vercel.com) (SPA with client-side rewrites and direct route handling)
- **Backend / API**: [Render](https://render.com) (FastAPI Web Service)
- **Celery Worker**: [Render](https://render.com) (Background Worker for ML and catalog sync)
- **Celery Beat**: [Render](https://render.com) (Periodic Scheduler)
- **Database**: [Supabase](https://supabase.com) PostgreSQL with `pgvector`
- **Cache & Message Broker**: [Upstash](https://upstash.com) Redis (`rediss://` TLS)
- **Authentication**: Supabase Auth (JWT validation in FastAPI)
- **Embeddings**: Hugging Face Inference API (`sentence-transformers/all-MiniLM-L6-v2`, 384-D)
- **Catalog Metadata**: TMDB API & OMDb API

---

## Features

- **Authentication-Aware Experience**:
  - Unauthenticated guests see public catalogue, search, and clean login/signup prompts.
  - Authenticated users access *"Recommend for You"*, personal watchlists, watch history, star ratings, and WatchMan decisions.
  - Sticky global search bar is accessible across all public and authenticated routes.
- **Selective & On-Demand Content Embeddings**:
  - Embeddings are generated strategically for initial high-value content (~500 popular movies + ~500 popular TV series) and on-demand when real users interact.
  - Never forces a full 11K-item batch embed. Recommendations continue to work seamlessly when items lack vectors.
- **Hybrid Recommendation Engine**:
  - Blends content vector similarity (pgvector cosine distance), collaborative filtering (ALS latent factors / KNN), catalog popularity, freshness, and personal taste preferences.
  - Transparent explanations and match scores on every card.
  - Sub-second cached delivery via Upstash Redis.
- **Honest Cold-Start Handling**:
  - Guests and new users with zero interactions receive an educational cold-start state with links to explore trending titles. Popular items are never falsely labeled as personalized.
- **WatchMan Decision System**:
  - One-click feedback: *"Must Watch"*, *"Time Pass"*, or *"Skip"*, immediately tuning user taste vectors.

---

## Project Structure

```
WatcheMan/
├── .github/
│   └── workflows/
│       └── ci.yml               # Automated CI for Backend (pytest) and Frontend (lint & build)
├── backend/
│   ├── alembic/                 # Linear database migrations (head: d4e5f6a7b8c9)
│   ├── app/
│   │   ├── api/                 # FastAPI modular routers (/api/...)
│   │   ├── core/                # Config, security, telemetry, Redis cache, Celery app
│   │   ├── db/                  # Database session and base models
│   │   ├── ml/                  # Recommendation pipeline, embeddings, ALS, hybrid ranker
│   │   ├── models/              # SQLAlchemy schema models
│   │   ├── repositories/        # Database access layer
│   │   ├── schemas/             # Pydantic validation models
│   │   ├── services/            # Catalog, recommendation, interaction, and TMDB services
│   │   └── tasks/               # Celery async tasks (embeddings, ALS, TMDB sync, cleanup)
│   ├── tests/                   # 217 hermetic unit and regression tests
│   ├── Dockerfile               # Multi-stage production container definition
│   ├── requirements.txt         # Production Python dependencies
│   ├── requirements-dev.txt     # Test dependencies (pytest, pytest-asyncio)
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/          # Reusable UI cards, modals, navigation, shelves
│   │   ├── features/            # Feature views (Home, Movie, Series, Search, Profile, Recs)
│   │   ├── routes/              # TanStack router page definitions
│   │   ├── services/            # API client services (catalog, auth, watchman, recs)
│   │   └── types/               # TypeScript domain interfaces
│   ├── Dockerfile               # Production container definition
│   ├── vercel.json              # Vercel SPA rewrites configuration
│   ├── package.json             # NPM dependencies and scripts
│   └── .env.example
├── scripts/
│   ├── backfill_content_embeddings.py    # Selective & on-demand embedding maintenance CLI
│   ├── concurrency_test.py               # Performance and load benchmark utility
│   ├── fix_sequences.py                  # PostgreSQL sequence synchronization
│   ├── ingest_tmdb_catalog.py            # Partitioned TMDB catalog ingestion CLI
│   ├── local_test_smoke.sh               # Fast read-only local stack smoke check
│   ├── reset_dev_database.py             # Safe dev reset utility (preserves catalog & schema)
│   ├── verify_homepage_experience.py     # Homepage personalized shelves E2E verification
│   ├── verify_ml_data_flow.py            # ML health, embedding coverage, and database report
│   └── verify_search_filter_experience.py# Live search & filter verification
├── compose.yml                  # Local Docker Compose (API + Worker + Beat + Frontend)
├── render.yaml                  # Render Blueprint definition (FastAPI + Worker + Beat)
├── vercel.json                  # Root Vercel SPA deployment configuration
├── .env.example                 # Root environment template
└── README.md
```

---

## Environment Configuration

Configuration is cleanly divided between **Backend Secrets** (server-only) and **Public Frontend Variables** (`VITE_*` only).

### Required Environment Variables

| Variable | Scope | Purpose | Example |
| :--- | :--- | :--- | :--- |
| `APP_ENV` | Backend | Environment mode | `production` or `development` |
| `DATABASE_URL` | Backend | Supabase PostgreSQL URI | `postgresql+psycopg://user:pass@host:6543/postgres?sslmode=require` |
| `REDIS_URL` | Backend | Upstash Redis connection string | `rediss://default:pass@host.upstash.io:6379` |
| `CELERY_BROKER_URL` | Backend | Celery broker URL | `rediss://default:pass@host.upstash.io:6379` |
| `CELERY_RESULT_BACKEND` | Backend | Celery result backend | `rediss://default:pass@host.upstash.io:6379` |
| `AUTH_PROVIDER` | Backend | Auth provider (`supabase` in prod) | `supabase` |
| `SUPABASE_URL` | Backend/FE | Supabase project URL | `https://your-project.supabase.co` |
| `SUPABASE_ANON_KEY` | Backend | Supabase anonymous key | `sb_anon_...` |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend | Supabase administrative key | `sb_secret_...` |
| `SUPABASE_JWT_SECRET` | Backend | Supabase JWT signing secret | `your-supabase-jwt-secret` |
| `TMDB_API_KEY` | Backend | TMDB v3 API key | `32-char-api-key` |
| `OMDB_API_KEY` | Backend | OMDb API key | `your-omdb-key` |
| `HF_API_URL` | Backend | Hugging Face model endpoint | `https://router.huggingface.co/hf-inference/models` |
| `HF_API_TOKEN` | Backend | Hugging Face token | `hf_...` |
| `CORS_ORIGINS` | Backend | Allowed frontend domains | `https://your-app.vercel.app,http://localhost:3000` |
| `FRONTEND_URL` | Backend | Canonical frontend URL | `https://your-app.vercel.app` |
| `VITE_API_BASE_URL` | Frontend | Public API base endpoint | `https://your-api.onrender.com/api` |
| `VITE_AUTH_PROVIDER` | Frontend | Auth provider | `supabase` |
| `VITE_SUPABASE_URL` | Frontend | Public Supabase URL | `https://your-project.supabase.co` |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Frontend | Public publishable key | `sb_publishable_...` |
| `VITE_TMDB_IMAGE_BASE_URL`| Frontend | TMDB image CDN base | `https://image.tmdb.org/t/p` |

---

## Local Development with Docker Compose

The entire stack runs via Docker Compose pointing to your cloud services (Supabase & Upstash):

```bash
# 1. Copy the consolidated environment template
cp .env.example .env

# 2. Fill in your real API keys in .env

# 3. Build and launch all 4 services
docker compose up --build -d

# 4. Verify running services
docker compose ps
# -> watchman_frontend        (http://localhost:3000)
# -> watchman_backend         (http://localhost:8000)
# -> watchman_celery_worker   (background task runner)
# -> watchman_celery_beat     (periodic task scheduler)

# 5. Run health check
curl http://localhost:8000/health
```

---

## Testing

### Hermetic Backend Test Suite
The backend contains 217 hermetic tests with mock network boundaries:

```bash
# Run tests inside the test container
docker compose run --rm backend_tests python -m pytest -q
# Result: 217 passed in ~39s
```

### Frontend Build & Typecheck
```bash
cd frontend
npm ci
npm run lint
npm run build
```

---

## Pre-Deployment Setup Guide

### 1. Vercel Deployment (Frontend)
1. Import repository on [Vercel](https://vercel.com).
2. Set **Root Directory** to `frontend`.
3. Framework Preset: **Vite** (build command: `npm run build`, output directory: `dist` or `.output/public`).
4. Set Environment Variables in Vercel Project Settings:
   - `VITE_API_BASE_URL`: `https://<your-render-backend>.onrender.com/api`
   - `VITE_AUTH_PROVIDER`: `supabase`
   - `VITE_SUPABASE_URL`: `https://<your-project>.supabase.co`
   - `VITE_SUPABASE_PUBLISHABLE_KEY`: `<your-supabase-publishable-key>`
   - `VITE_TMDB_IMAGE_BASE_URL`: `https://image.tmdb.org/t/p`
5. The included `vercel.json` rewrite rules route direct URL navigations (`/movie/:id`, `/web-series/:id`, `/recommendation`, `/search`) to `/index.html` without 404s.

### 2. Render Deployment (Backend & Celery)
You can deploy using the included `render.yaml` Blueprint or create 3 separate services manually:

1. **API Web Service (`watchman-api`)**:
   - **Root Directory**: `backend`
   - **Environment**: `Python 3.11`
   - **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path**: `/health`
   - **Env Vars**: Fill in database, Redis, TMDB, OMDb, Hugging Face, Supabase, and CORS variables.
2. **Background Worker (`watchman-worker`)**:
   - **Root Directory**: `backend`
   - **Environment**: `Python 3.11`
   - **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start Command**: `celery -A app.core.celery.celery_app worker --loglevel=info`
3. **Periodic Beat Scheduler (`watchman-beat`)**:
   - **Root Directory**: `backend`
   - **Environment**: `Python 3.11`
   - **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start Command**: `celery -A app.core.celery.celery_app beat --loglevel=info`

---

## Operational Scripts

All operational and maintenance scripts are located in `scripts/`:

```bash
# Ingest TMDB catalogue with partitioned discover queries
python scripts/ingest_tmdb_catalog.py --movies --tv --max-pages-per-partition 10

# Selective initial content embedding backfill (Top 500 Movies + Top 500 TV)
python scripts/backfill_content_embeddings.py --popular --limit 1000

# Embed unembedded titles referenced by real user interactions
python scripts/backfill_content_embeddings.py --interacted

# Synchronize PostgreSQL auto-increment sequences
python scripts/fix_sequences.py

# Verify live ML data flow, embedding coverage, and policy status
python scripts/verify_ml_data_flow.py

# Safe dev reset (preserves catalog contents and schema migrations)
python scripts/reset_dev_database.py --runtime-only
```

---

## License

MIT License
