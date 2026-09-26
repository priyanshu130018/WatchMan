# WatchMan - Movie Discovery & Recommendation Platform

A full-stack movie discovery and recommendation application built with React/TypeScript, FastAPI, and PostgreSQL with ML-powered recommendations.

## Features

- **User Authentication**: Secure JWT-based authentication with password hashing
- **Movie Discovery**: Browse trending, popular, top-rated, and latest movies
- **Search**: Full-text movie search powered by TMDB API
- **Favorites**: Save and manage favorite movies
- **Watch History**: Track watched movies and progress
- **Recommendations**: Live hybrid recommendations using content similarity, collaborative activity, and popularity fallback
- **User Profiles**: Customizable user profiles with preferences
- **Responsive UI**: Modern interface built with React and Tailwind CSS

## Tech Stack

### Frontend
- React 19 with TypeScript
- Vite - Fast build tool
- TanStack Router - Advanced routing
- TanStack Query - Data fetching
- Zustand - State management
- Tailwind CSS - Styling

### Backend
- FastAPI - Python web framework
- PostgreSQL with pgvector - Database and vector similarity search
- Supabase - Managed Postgres / project services
- SQLAlchemy + Alembic - ORM and migrations
- Redis - Caching of frequent TMDB/recommendation responses
- Celery (worker + beat) - Background recommendation & catalog jobs
- JWT - Authentication
- HuggingFace Inference API - Remote sentence-transformer embeddings (`sentence-transformers/all-MiniLM-L6-v2`, 384-dim). Embeddings are generated via API call rather than a local torch model, keeping the image small.

## Quick Start with Docker

1. Clone repository and setup env:
   ```bash
   git clone https://github.com/priyanshu130018/Watcher.git
   cd WatcheMan
   cp backend/.env.example backend/.env
   ```

2. Add your TMDB API key to `backend/.env`:
   ```bash
   TMDB_API_KEY=your_key_here
   ```

3. Start all services:
   ```bash
   docker-compose up --build
   ```

4. Access the app:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## Local Development Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your configuration
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## API Endpoints

### Auth
- `POST /api/auth/register` - Register
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Current user
- `POST /api/auth/logout` - Logout

### Movies
- `GET /api/movies/trending` - Trending movies
- `GET /api/movies/popular` - Popular movies
- `GET /api/movies/{movie_id}` - Movie details
- `GET /api/movies/{movie_id}/similar` - Similar movies

### Ratings
- `GET /api/ratings/` - Current user's ratings
- `PUT /api/ratings/{movie_id}` - Create or update a 1–5 rating

### Search
- `GET /api/search/movies?query=...` - Search

### Favorites (Protected)
- `GET /api/favorites` - List favorites
- `POST /api/favorites` - Add favorite
- `DELETE /api/favorites/{movie_id}` - Remove favorite

### Watch History (Protected)
- `GET /api/watch-history` - List history
- `POST /api/watch-history` - Add to history
- `PUT /api/watch-history/{id}` - Update progress
- `DELETE /api/watch-history/{id}` - Delete

### Personalized recommendations (Protected)
- `GET /api/recommendations/personalized?limit=20` - Hybrid ranking from favorites, viewing progress, ratings, and peer activity

## Authentication

Uses JWT tokens. After login, include token in requests:
```
Authorization: Bearer <token>
```

## Environment Configuration

### Backend (.env)
```env
POSTGRES_HOST=localhost
POSTGRES_DB=watchman_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password
SECRET_KEY=your-secret-key
TMDB_API_KEY=your-tmdb-key
TMDB_BASE_URL=https://api.themoviedb.org/3
OMDB_API_KEY=your-omdb-key
OMDB_BASE_URL=https://www.omdbapi.com/
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
VECTOR_DIMENSION=384
ENABLE_PGVECTOR=true
ML_ADMIN_EMAILS=admin@example.com
# HuggingFace Inference API (remote embeddings) - create a free token at
# https://huggingface.co/settings/tokens
HF_API_URL=https://api-inference.huggingface.co/pipeline/feature-extraction
HF_API_TOKEN=your-hf-token
```

All backend settings are loaded from `.env` via `app/core/config.py` with **no default values** — a missing required variable raises a `ConfigurationError` at startup (fail-fast). See `.env.example` for the full list.

The frontend refreshes catalog and personalized queries every 30 seconds while open. Favoriting or rating a title immediately invalidates the personalized query, so the next recommendation fetch reflects the new signal.

### Frontend (.env)
```env
VITE_API_BASE_URL=http://localhost:8000/api
```

## Security

- Passwords hashed with bcrypt
- JWT tokens for stateless auth
- User data isolation - users only see their own data
- All protected routes verify authentication
- Secrets never committed to git

## Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Revert
alembic downgrade -1
```

## Project Structure

```
WatcheMan/
├── frontend/          # React application
│   ├── src/
│   │   ├── api/      # API client
│   │   ├── components/
│   │   ├── routes/   # Pages
│   │   ├── store/    # Zustand stores
│   │   └── types/    # TypeScript types
│   ├── Dockerfile
│   └── package.json
│
├── backend/          # FastAPI application
│   ├── app/
│   │   ├── api/      # Route handlers
│   │   ├── core/     # Config, security
│   │   ├── database/ # Models, migrations
│   │   ├── ml/       # Recommendations
│   │   └── main.py   # App setup
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
│
└── docker-compose.yml
```

## Testing

Backend:
```bash
pytest backend/tests/
```

Frontend:
```bash
npm run build
npm run lint
```

## Troubleshooting

**Port in use:**
```bash
# Linux/Mac
lsof -i :8000

# Windows
netstat -ano | findstr :8000
```

**Database connection error:**
- Ensure PostgreSQL is running
- Check POSTGRES_HOST, PORT, credentials
- Run `alembic upgrade head`

**Docker issues:**
```bash
docker-compose down
docker-compose up --build --no-cache
```

## License

MIT License

## Support

Open an issue on GitHub for support.
