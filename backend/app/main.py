import uuid
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logger import logger
from app.db.session import SessionLocal
from app.core.redis import cache
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

from app.api.auth.router import router as auth_router
from app.api.users.router import router as users_router
from app.api.movies.router import router as movie_router
from app.api.web_series.router import router as web_series_router
from app.api.trending.router import router as trending_router
from app.api.search.router import router as search_router
from app.api.ott.router import router as ott_router
from app.api.recommendations.router import router as recommendation_router
from app.api.favorites.router import router as favorites_router
from app.api.ratings.router import router as ratings_router
from app.api.reviews.router import router as reviews_router
from app.api.watch_history.router import router as watch_history_router
from app.api.ml.router import router as ml_router
from app.api.ops.router import router as ops_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Unified movie and web-series discovery and recommendation API",
)

# Security Headers and Request ID tracing middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)

# Configure CORS strictly from validated configuration
origins = settings.cors_origins_list

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Global Centralized Exception Handlers
# -----------------------------------------------------------------------------

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle all typed application domain and infrastructure exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Format Pydantic schema validation failures into standard structured error."""
    details = []
    for error in exc.errors():
        loc = [str(item) for item in error.get("loc", []) if item != "body"]
        field = ".".join(loc) if loc else "body"
        details.append({
            "field": field,
            "reason": error.get("msg", "Invalid value"),
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": details,
            },
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Normalize standard HTTPExceptions into standard API error response format."""
    status_code_to_error_code = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "RESOURCE_CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
        504: "GATEWAY_TIMEOUT",
    }
    error_code = status_code_to_error_code.get(
        exc.status_code,
        "HTTP_ERROR" if exc.status_code < 500 else "INTERNAL_SERVER_ERROR",
    )
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error occurred."
    details = exc.detail if not isinstance(exc.detail, str) else None

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": error_code,
                "message": message,
                "details": details,
            },
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Capture unexpected internal exceptions, log full server-side trace, and return generic 500."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.error(
        f"Unhandled unexpected exception [request_id={request_id}] on {request.method} {request.url.path}: {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred.",
                "details": {
                    "request_id": request_id,
                },
            },
        },
    )


# -----------------------------------------------------------------------------
# Router Registration
# -----------------------------------------------------------------------------

# Register all routers with consistent /api prefix
app.include_router(auth_router)
app.include_router(users_router, prefix="/api")
app.include_router(movie_router, prefix="/api")
app.include_router(web_series_router, prefix="/api")
app.include_router(trending_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(ott_router, prefix="/api")
app.include_router(favorites_router, prefix="/api")
app.include_router(ratings_router, prefix="/api")
app.include_router(reviews_router, prefix="/api")
app.include_router(watch_history_router, prefix="/api")
app.include_router(recommendation_router, prefix="/api")
app.include_router(ml_router, prefix="/api")
app.include_router(ops_router, prefix="/api/ops")


# -----------------------------------------------------------------------------
# Health (Liveness) & Readiness Endpoints
# -----------------------------------------------------------------------------

@app.get("/health")
@app.get("/api/health")
async def health_check():
    """Liveness check endpoint - indicates process is running."""
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
    }


@app.get("/ready")
@app.get("/api/ready")
async def readiness_check():
    """Readiness check endpoint - verifies DB and Redis connectivity."""
    db_healthy = False
    details = {}

    # 1. Check PostgreSQL database connectivity
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_healthy = True
            details["database"] = {"status": "ok", "engine": "postgresql"}
        finally:
            db.close()
    except Exception as e:
        logger.error("Readiness check: PostgreSQL check failed: %s", e)
        details["database"] = {"status": "error", "message": str(e)}

    # 2. Check Redis cache connectivity
    try:
        client = cache.get_client()
        pong = await client.ping()
        if pong:
            details["redis"] = {"status": "ok"}
        else:
            details["redis"] = {"status": "degraded", "message": "Ping failed"}
    except Exception as e:
        logger.warning("Readiness check: Redis check failed: %s", e)
        details["redis"] = {"status": "degraded", "message": str(e)}

    # If DB is down, return 503; if Redis is down, return 200 with degraded state (app can still run)
    is_ready = db_healthy
    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "not_ready",
            "service": settings.APP_NAME,
            "components": details,
        },
    )
