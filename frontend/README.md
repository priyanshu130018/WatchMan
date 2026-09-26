# WatchMan Frontend

Production-grade, cinematic dark-themed frontend for WatchMan — Discover Movies & Web-Series with AI Recommendations.

## Tech Stack

- **Framework**: React 19 + TypeScript (Vite + TanStack Start / Nitro)
- **Routing**: `@tanstack/react-router` (file-based type-safe routing)
- **Data Fetching & Caching**: `@tanstack/react-query` (with 30s background refetching & cache invalidation)
- **State Management**: Zustand (lightweight client session auth store)
- **Icons**: `lucide-react`
- **Styling**: Modern CSS design system tokens with Tailwind CSS, stable 2/3 poster aspect ratios, and responsive 4-column desktop grids.

## Canonical Product Routes

- `/` — Homepage featuring 10 curated sections:
  1. Hero Backdrop Billboard with Trailer launcher and Quick Add/Rate
  2. `{username} must like it (Movies)` / Cold-start Top Picks
  3. `{username} must like it (Web Series)` / Cold-start Top TV Picks
  4. Top 10 Movies
  5. Top 10 Web Series
  6. Trending Movies (week)
  7. Trending Web Series (week)
  8. New Movies (latest releases)
  9. New Web Series (latest releases)
  10. All Movies & Web Series Catalog Rows
- `/movie` — Movies catalog with Genre, Year, and Sort dropdowns, responsive 4-column grid (16 items/page), and accessible pagination.
- `/movie/$id` — Movie details with backdrop hero, trailer modal, 1-10 rating modal, save action, runtime, release date, genre chips, cast & crew carousel, user reviews with edit/delete, and similar movie recommendations.
- `/web-series` — Web series catalog with TV-specific genre filters, year filter, sorting, and pagination.
- `/web-series/$id` — Web series details with seasons & episode count, status, cast carousel, trailer player, ratings, reviews, and similar TV recommendations.
- `/trending` — Unified trending discovery with Content Type (`All`, `Movies`, `Web Series`) and Time Window (`Today`, `This Week`) filters.
- `/recommendation` — Hybrid AI recommendation feed with explanation badges, candidate scores, and instant pipeline refresh action.
- `/search` — Full URL-driven search (`/search?q=...&type=...&genre_id=...&year=...&sort=...&page=...`) with responsive 4-column results and empty states.
- `/saved` (and `/favorites`) — Saved library with type tabs, un-save action, and direct catalog links.
- `/history` — Watch history tracking viewing progress, completion badges, and deletion controls.
- `/profile` — Account profile with username, full name, avatar URL updates, and user library statistics.
- `/settings` — Taste preferences with interactive favorite and disliked genre tags.
- `/login` & `/signup` — Authentication with instant session persistence.
- `/monitor` — Recommendation engine telemetry with pipeline latency, candidate scores, and TMDB health logs.

## Building & Verification

```bash
# In frontend directory:
npm run build     # Compiles production SSR and client bundles cleanly with zero TypeScript errors
npm run dev       # Starts local Vite development server
```
