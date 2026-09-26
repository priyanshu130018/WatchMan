import time
import logging
from fastapi import Request
from app.core.exceptions import RateLimitException
from app.core.redis import cache

logger = logging.getLogger(__name__)

# Simple in-memory fallback
_local_rate_limit_store: dict[str, list[float]] = {}


def check_rate_limit(
    key: str,
    max_requests: int = 60,
    window_seconds: int = 60,
) -> bool:
    """
    Check if a key has exceeded rate limits using in-memory / cache sliding window.
    """
    now = time.time()
    history = _local_rate_limit_store.get(key, [])
    history = [t for t in history if t > now - window_seconds]
    history.append(now)
    _local_rate_limit_store[key] = history

    return len(history) <= max_requests


def rate_limit_dependency(max_requests: int = 60, window_seconds: int = 60):
    """FastAPI dependency to enforce rate limits per client IP."""
    async def _dependency(request: Request):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        key = f"{client_ip}:{path}"

        if not check_rate_limit(key, max_requests=max_requests, window_seconds=window_seconds):
            raise RateLimitException(
                message="Rate limit exceeded. Please try again later.",
                details={"retry_after_seconds": window_seconds},
            )

    return _dependency
