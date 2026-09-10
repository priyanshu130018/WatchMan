from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.auth.router import router as auth_router
from app.api.movies.router import router as movie_router
from app.api.search.router import router as search_router
from app.api.recommendations.router import router as recommendation_router
from app.api.favorites.router import router as favorites_router
from app.api.watch_history.router import router as watch_history_router
from app.api.ml.router import router as ml_router
from app.api.ratings.router import router as ratings_router

app = FastAPI(
    title="WatchMan API",
    version="1.0.0",
    description="Movie discovery and recommendation API"
)

# Configure CORS
origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()] or [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers with consistent /api prefix
# Auth router already has /api/auth prefix
app.include_router(auth_router)

# Other routers - add /api prefix
app.include_router(movie_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(favorites_router, prefix="/api")
app.include_router(watch_history_router, prefix="/api")
app.include_router(ratings_router, prefix="/api")
app.include_router(recommendation_router, prefix="/api")
app.include_router(ml_router, prefix="/api")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "WatchMan API"}

