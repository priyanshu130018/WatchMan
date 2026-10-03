# WatchMan - Complete URL Structure & Routing Reference

## 1. Frontend Client Routes (TanStack Router)

All frontend routes are declared as file-based routes in `frontend/src/routes/`:

| Route Path | File Path | Auth Required | Purpose |
| :--- | :--- | :---: | :--- |
| `/` | `src/routes/index.tsx` | No | Home landing page with hero banner, personalized rails, trending, and top-rated sections. |
| `/movie` | `src/routes/movie.index.tsx` | No | Full movie catalog browsing with genre, year, language, and sorting filters. |
| `/movie/$id` | `src/routes/movie.$id.tsx` | No | Movie detail view with trailers, cast, crew, ratings, and similar titles. |
| `/web-series` | `src/routes/web-series.index.tsx` | No | Web series / TV show catalog browsing with multi-filter grid. |
| `/web-series/$id` | `src/routes/web-series.$id.tsx` | No | TV show detail view with seasons, episodes, and stream providers. |
| `/trending` | `src/routes/trending.tsx` | No | Combined trending movies and series showcase. |
| `/trending/$id` | `src/routes/trending.$id.tsx` | No | Deep link detail for trending item. |
| `/ott` | `src/routes/ott.tsx` | No | OTT streaming platform title discovery by provider and region. |
| `/search` | `src/routes/search.tsx` | No | Universal search interface across movies and series with live filter controls. |
| `/recommendation` | `src/routes/recommendation.tsx` | Yes | Personalized recommendations feed for authenticated user. |
| `/recommendation/$id` | `src/routes/recommendation.$id.tsx` | No | Deep link detail view from recommendation card. |
| `/saved` | `src/routes/saved.tsx` | Yes | Personal saved watchlist library. |
| `/favorites` | `src/routes/favorites.tsx` | Yes | Route alias redirecting to `/saved`. |
| `/history` | `src/routes/history.tsx` | Yes | Playback tracking and watch history management. |
| `/profile` | `src/routes/profile.tsx` | Yes | User account profile settings and genre preference configuration. |
| `/login` | `src/routes/login.tsx` | No | User authentication and sign-in page. |
| `/signup` | `src/routes/signup.tsx` | No | Account registration page. |
| `/forgot-password` | `src/routes/forgot-password.tsx` | No | Password recovery initiation page. |
| `/reset-password` | `src/routes/reset-password.tsx` | No | Password reset confirmation page. |

---

## 2. Backend REST API Endpoints (`/api/...`)

### A. Authentication (`/api/auth`)
- `POST /api/auth/register` - Create user account
- `POST /api/auth/login` - Authenticate and receive JWT tokens
- `POST /api/auth/refresh` - Rotate refresh token and issue new access token
- `GET /api/auth/me` - Authenticated user details
- `POST /api/auth/logout` - Stateless logout acknowledgment
- `GET /api/auth/health` - Subsystem health probe

### B. Movies (`/api/movies`)
- `GET /api/movies` - Paginated movie catalog
- `POST /api/movies/sync` - Ingest movie from TMDB
- `GET /api/movies/trending` - Trending movies showcase
- `GET /api/movies/top-10` - Top 10 movies rail
- `GET /api/movies/popular` - Popular movies grid
- `GET /api/movies/top-rated` - Top-rated movies grid
- `GET /api/movies/latest` - Latest releases grid
- `GET /api/movies/search` - Search movies via TMDB
- `GET /api/movies/{movie_id}` - Full movie details & external ratings
- `GET /api/movies/{movie_id}/similar` - Similar movies via pgvector / TMDB
- `GET /api/movies/{movie_id}/watch-providers` - Regional streaming availability
- `GET /api/movies/{movie_id}/images` - Movie backdrops and posters
- `GET /api/movies/{movie_id}/tmdb-reviews` - TMDB community reviews

### C. Web Series (`/api/web-series`)
- `GET /api/web-series` - Paginated TV series catalog
- `POST /api/web-series/sync` - Ingest TV show from TMDB
- `GET /api/web-series/trending` - Trending series showcase
- `GET /api/web-series/top-10` - Top 10 series rail
- `GET /api/web-series/popular` - Popular series grid
- `GET /api/web-series/top-rated` - Top-rated series grid
- `GET /api/web-series/latest` - On-the-air series grid
- `GET /api/web-series/search` - Search series via TMDB
- `GET /api/web-series/{tv_id}` - Full series details & external ratings
- `GET /api/web-series/{tv_id}/similar` - Similar series from TMDB
- `GET /api/web-series/{tv_id}/watch-providers` - Regional streaming availability
- `GET /api/web-series/{tv_id}/images` - Series backdrops and posters
- `GET /api/web-series/{tv_id}/tmdb-reviews` - TMDB community reviews

### D. Search & Trending (`/api/search` & `/api/trending`)
- `GET /api/search` - Unified search across movies and web series
- `GET /api/search/movies` - Backward-compatible movie search
- `GET /api/search/tv` - Backward-compatible TV search
- `GET /api/trending` - Combined trending movies & TV shows
- `GET /api/trending/{content_type}/{tmdb_id}` - Trending item detail

### E. OTT Streaming Discovery (`/api/ott`)
- `GET /api/ott/regions` - List supported ISO-3166-1 regions
- `GET /api/ott/providers` - List streaming services in region
- `GET /api/ott/{content_type}` - Discover titles by streaming provider

### F. Recommendations (`/api/recommendations`)
- `GET /api/recommendations` - Personalized hybrid recommendations
- `POST /api/recommendations/refresh` - Force cache flush & recompute
- `GET /api/recommendations/personalized` - Live hybrid candidate stream
- `GET /api/recommendations/home` - Unified homepage shelves
- `GET /api/recommendations/must-like` - "You Must Like" shelf
- `GET /api/recommendations/watched-liked` - "You Already Watched & Liked" shelf
- `GET /api/recommendations/continue-watching` - "Continue Watching" shelf
- `GET /api/recommendations/{content_type}/{tmdb_id}` - Item vector similarity

### G. User Interactions & Feedback
- `GET /api/saved` & `GET /api/saved/paginated` - List user saved watchlist
- `POST /api/saved` - Add item to watchlist
- `DELETE /api/saved/{content_type}/{tmdb_id}` & `DELETE /api/saved/{content_id}` - Remove from watchlist
- `GET /api/ratings` & `GET /api/ratings/paginated` - List user ratings
- `GET /api/ratings/{content_type}/{tmdb_id}` - Get rating for title
- `POST /api/ratings` & `PUT /api/ratings/{content_type}/{tmdb_id}` - Upsert rating
- `DELETE /api/ratings/{content_type}/{tmdb_id}` - Delete rating
- `GET /api/watch-history` & `GET /api/watch-history/paginated` - List watch history
- `POST /api/watch-history` & `PUT /api/watch-history/{history_id}` - Log/update progress
- `DELETE /api/watch-history/{history_id}` - Delete history record
- `GET /api/content/{content_id}/watchman` - Get dynamic 0-100 WatchMan score
- `PUT /api/content/{content_id}/watchman` - Persist decision (`must_watch`, `time_pass`, `skip`)
- `GET /api/reviews/{content_type}/{tmdb_id}` - List community reviews
- `POST /api/reviews` & `PUT /api/reviews/{review_id}` - Create/update review
- `DELETE /api/reviews/{review_id}` - Delete review
- `GET /api/users/me/profile` & `PUT /api/users/me/profile` - Profile details
- `GET /api/users/me/preferences` & `PUT /api/users/me/preferences` - Genre preferences

### H. Infrastructure, Health & Operations
- `GET /health` & `GET /api/health` - Process liveness check
- `GET /ready` & `GET /api/ready` - PostgreSQL & Redis readiness check
- `GET /api/ops/metrics` - Latency percentiles & route telemetry (Operator-only)
- `GET /api/ops/status` - Database pool & Redis memory diagnostics (Operator-only)
- `POST /api/ml/embeddings/movies/batch` - Batch generate missing BGE vectors (Operator-only)
- `POST /api/ml/embeddings/movies/{movie_id}` - Single item vector generation (Operator-only)

---

## 3. URL Parameter Taxonomy

| Parameter | Type | Valid Values / Constraints | Used In |
| :--- | :--- | :--- | :--- |
| `page` | Query (int) | $\ge 1$, default $1$ | All paginated listing endpoints |
| `limit` / `page_size` | Query (int) | $1 \dots 100$, default $18$ or $20$ | All paginated listing endpoints |
| `sort` | Query (str) | `popularity_desc`, `popularity_asc`, `vote_average_desc`, `release_date_desc`, `title_asc` | Catalog & search endpoints |
| `year` | Query (int) | $1900 \dots 2030$ | Catalog & search filters |
| `genre_id` / `genre` | Query (int) | Integer matching `genres.tmdb_id` | Catalog & search filters |
| `language` | Query (str) | ISO-639-1 code (e.g. `en`, `hi`, `ko`, `es`) | Catalog & search filters |
| `collection` | Query (str) | `popular` | Catalog listing (caps set to top 100) |
| `time_window` | Query (str) | `day`, `week` | Trending endpoints |
| `region` | Query (str) | 2-letter uppercase ISO-3166-1 (e.g. `IN`, `US`, `GB`) | OTT & watch-provider endpoints |
| `force_refresh` | Query (bool) | `true`, `false` | Recommendation endpoints |

---

## 4. External Services & CDN Endpoints

The backend connects securely to external services without leaking API credentials to the client:
- **TMDB API**: `https://api.themoviedb.org/3/` (Catalog metadata, images, streaming availability via JustWatch).
- **TMDB Image CDN**: `https://image.tmdb.org/t/p/{size}/` (High-resolution backdrops, posters, and profile images).
- **OMDb API**: `https://www.omdbapi.com/` (IMDb, Rotten Tomatoes, and Metacritic rating enrichment).
- **YouTube**: `https://www.youtube.com/watch?v={key}` (Official trailer playback).
