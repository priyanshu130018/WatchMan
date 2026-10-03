"""Precise request and subsystem timing profiler for latency audit."""

from __future__ import annotations

import contextlib
import contextvars
import logging
import time
from dataclasses import dataclass, field
from typing import Generator, Optional

logger = logging.getLogger("watchman.latency_audit")


@dataclass
class RequestTimingContext:
    endpoint: str = ""
    start_time: float = field(default_factory=time.perf_counter)
    total_ms: float = 0.0
    db_ms: float = 0.0
    sql_query_count: int = 0
    sql_queries: list[dict[str, float | str]] = field(default_factory=list)
    redis_ms: float = 0.0
    vector_search_ms: float = 0.0
    candidate_retrieval_ms: float = 0.0
    ranking_ms: float = 0.0
    serialization_ms: float = 0.0
    omdb_ms: float = 0.0
    tmdb_ms: float = 0.0

    def finish(self) -> float:
        self.total_ms = round((time.perf_counter() - self.start_time) * 1000, 2)
        return self.total_ms

    def log_recommendations(self) -> None:
        self.finish()
        msg = (
            f"\n--- [LATENCY AUDIT LOG] ---\n"
            f"endpoint={self.endpoint}\n"
            f"total_ms={self.total_ms:.2f}\n"
            f"db_ms={self.db_ms:.2f}\n"
            f"redis_ms={self.redis_ms:.2f}\n"
            f"vector_search_ms={self.vector_search_ms:.2f}\n"
            f"candidate_retrieval_ms={self.candidate_retrieval_ms:.2f}\n"
            f"ranking_ms={self.ranking_ms:.2f}\n"
            f"serialization_ms={self.serialization_ms:.2f}\n"
            f"sql_query_count={self.sql_query_count}\n"
            f"---------------------------"
        )
        logger.info(msg)
        print(msg, flush=True)

    def log_movies(self) -> None:
        self.finish()
        msg = (
            f"\n--- [LATENCY AUDIT LOG] ---\n"
            f"endpoint={self.endpoint}\n"
            f"total_ms={self.total_ms:.2f}\n"
            f"db_ms={self.db_ms:.2f}\n"
            f"sql_query_count={self.sql_query_count}\n"
            f"serialization_ms={self.serialization_ms:.2f}\n"
            f"---------------------------"
        )
        logger.info(msg)
        print(msg, flush=True)

    def log_movie_detail(self) -> None:
        self.finish()
        msg = (
            f"\n--- [LATENCY AUDIT LOG] ---\n"
            f"endpoint={self.endpoint}\n"
            f"total_ms={self.total_ms:.2f}\n"
            f"db_ms={self.db_ms:.2f}\n"
            f"redis_ms={self.redis_ms:.2f}\n"
            f"omdb_ms={self.omdb_ms:.2f}\n"
            f"tmdb_ms={self.tmdb_ms:.2f}\n"
            f"sql_query_count={self.sql_query_count}\n"
            f"serialization_ms={self.serialization_ms:.2f}\n"
            f"---------------------------"
        )
        logger.info(msg)
        print(msg, flush=True)


_timing_ctx: contextvars.ContextVar[Optional[RequestTimingContext]] = contextvars.ContextVar(
    "_timing_ctx", default=None
)


def get_current_timing_ctx() -> Optional[RequestTimingContext]:
    return _timing_ctx.get()


def start_timing_ctx(endpoint: str) -> RequestTimingContext:
    ctx = RequestTimingContext(endpoint=endpoint)
    _timing_ctx.set(ctx)
    return ctx


@contextlib.contextmanager
def track_timing_ctx(endpoint: str) -> Generator[RequestTimingContext, None, None]:
    ctx = RequestTimingContext(endpoint=endpoint)
    token = _timing_ctx.set(ctx)
    try:
        yield ctx
    finally:
        ctx.finish()
        _timing_ctx.reset(token)


@contextlib.contextmanager
def time_block(metric_name: str) -> Generator[None, None, None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        ctx = get_current_timing_ctx()
        if ctx:
            current = getattr(ctx, metric_name, 0.0)
            setattr(ctx, metric_name, current + elapsed_ms)
