# WatchMan Frontend

Clean replacement frontend for WatchMan.

## Stack
- React 19 + TypeScript
- TanStack Router
- TanStack Query
- Axios
- Supabase JS client
- Tailwind CSS
- Lucide icons

## API integration
Set `VITE_API_BASE_URL` to the FastAPI `/api` base, for example `http://localhost:8000/api`.

The current backend exposes custom JWT authentication. The UI therefore uses the current `/auth/login`, `/auth/register`, and `/auth/me` contract so the existing API can be exercised. The final backend rebuild should replace this auth bridge with canonical Supabase Auth JWT verification, after which the frontend session adapter can pass the Supabase access token directly.

Favorites and watch history endpoints currently return IDs/records rather than expanded movie objects. The frontend deliberately resolves those movie IDs through the movie detail endpoint instead of inventing a response shape.
