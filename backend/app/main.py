from fastapi import FastAPI
from sqlalchemy import text

from app.database.session import engine
from app.api.auth.router import router as auth_router
from app.api.movies import router as movie_router
from app.api.search.router import router as search_router
from app.api.recommendations.router import router as recommendation_router

app = FastAPI(
    title="Rabbit API",
    version="1.0.0"
)

app.include_router(auth_router)
app.include_router(movie_router)
app.include_router(search_router)
app.include_router(recommendation_router)

@app.get("/")
def root():
    return {
        "app": "Rabbit"
    }


@app.get("/health")
async def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    return {
        "database": "connected"
    }