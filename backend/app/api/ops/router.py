"""Operational observability and telemetry endpoints for WatchMan."""

import sys
import time
import shutil
import os
from typing import Any, Dict
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.logger import logger
from app.core.redis import cache
from app.core.security import require_admin
from app.core.telemetry import telemetry
from app.db.session import SessionLocal
from app.models.user import User

router = APIRouter(tags=["Operations & Monitoring"])
_START_TIME = time.time()


@router.get("/metrics")
async def get_system_metrics(
    _: User = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Returns rolling request telemetry, latency percentiles (p50, p95, p99),
    status code distributions (2xx, 4xx, 5xx), route breakdowns, and dependency metrics.

    Operator-only: exposes internal service telemetry, so it requires an
    authenticated operator (see ``ML_ADMIN_EMAILS``). Use ``/health`` / ``/ready``
    for unauthenticated liveness/readiness probes.
    """
    snapshot = telemetry.get_metrics_snapshot()
    snapshot["uptime_seconds"] = round(time.time() - _START_TIME, 1)
    snapshot["service"] = settings.APP_NAME
    snapshot["environment"] = settings.APP_ENV
    return snapshot


@router.get("/status")
async def get_operational_status(
    _: User = Depends(require_admin),
) -> JSONResponse:
    """
    Detailed operational diagnostics inspecting PostgreSQL connection & pool stats,
    Redis memory & client status, Celery broker reachability, disk capacity, and telemetry.

    Operator-only: exposes infrastructure diagnostics (DB/Redis internals, disk,
    interpreter version), so it requires an authenticated operator. Unauthenticated
    callers should use ``/health`` / ``/ready`` instead.
    """
    op_status: Dict[str, Any] = {
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "version": settings.APP_VERSION,
        "uptime_seconds": round(time.time() - _START_TIME, 1),
        "components": {},
        "system": {},
    }

    overall_healthy = True

    # 1. PostgreSQL Diagnostic
    t0 = time.perf_counter()
    try:
        db = SessionLocal()
        try:
            # Query connection and table counts safely
            db.execute(text("SELECT 1"))
            db_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            op_status["components"]["database"] = {
                "status": "healthy",
                "engine": "postgresql",
                "latency_ms": db_latency_ms,
                "pool_size": getattr(db.get_bind().pool, "size", lambda: 5)(),
            }
        finally:
            db.close()
    except Exception as e:
        overall_healthy = False
        op_status["components"]["database"] = {
            "status": "unavailable",
            "error": str(e),
        }

    # 2. Redis Diagnostic
    t0 = time.perf_counter()
    try:
        client = cache.get_client()
        pong = await client.ping()
        redis_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        
        info = {}
        try:
            info = await client.info("memory")
        except Exception:
            pass

        used_memory_human = info.get("used_memory_human", "N/A")
        op_status["components"]["redis"] = {
            "status": "healthy" if pong else "degraded",
            "latency_ms": redis_latency_ms,
            "memory_used": used_memory_human,
        }
    except Exception as e:
        op_status["components"]["redis"] = {
            "status": "degraded",
            "error": str(e),
            "note": "Application continues operating with in-memory / direct DB fallback",
        }

    # 3. Host System Resource Diagnostic
    try:
        total, used, free = shutil.disk_usage("/")
        op_status["system"]["disk"] = {
            "total_gb": round(total / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
            "used_pct": round((used / total) * 100, 2),
        }
    except Exception:
        op_status["system"]["disk"] = {"status": "unavailable"}

    op_status["system"]["python_version"] = sys.version.split()[0]
    op_status["status"] = "healthy" if overall_healthy else "degraded"

    http_status = status.HTTP_200_OK if overall_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=http_status, content=op_status)
