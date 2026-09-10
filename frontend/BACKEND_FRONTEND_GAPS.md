# WatchMan integration gaps found during redesign

1. The backend currently authenticates with its own HS256 JWT (`/auth/login` and `/auth/register`). Supabase Auth exists in the backend codebase, but the protected movie/user endpoints use the custom JWT dependency. A final rebuild should make Supabase Auth the canonical issuer and verify Supabase JWTs in FastAPI.
2. There is no backend `/profile` route even though the previous frontend expected one.
3. There is no backend rating route. Rating UI is intentionally not fabricated.
4. `/favorites/` returns favorite records, not movies. The new frontend resolves `movie_id` to movie details.
5. `/watch-history/` returns history records, not movies. The new frontend resolves `movie_id` to movie details.
6. `/recommendations` currently proxies TMDB recommendation endpoints rather than exposing the future personalized hybrid recommender.
7. The backend movie/search responses are TMDB-shaped while pgvector similar results are locally normalized. The new frontend has one normalization adapter for both.
