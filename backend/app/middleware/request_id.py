import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.telemetry import telemetry

logger = logging.getLogger("watchman.request")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that ensures every HTTP request has an X-Request-ID and
    tracks request duration in milliseconds (X-Process-Time-Ms).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response: Response = await call_next(request)
        
        process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = str(process_time_ms)

        # Record metrics in telemetry engine
        telemetry.record_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=process_time_ms,
        )

        # Log structured request telemetry (sanitized, zero secret leakage)
        logger.info(
            "%s %s -> %s (%s ms) [request_id=%s]",
            request.method,
            request.url.path,
            response.status_code,
            process_time_ms,
            request_id,
        )

        return response
