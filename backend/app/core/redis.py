"""Redis client and caching service with non-blocking graceful degradation."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.timing import get_current_timing_ctx

logger = logging.getLogger(__name__)


class RedisCache:
    """Async Redis cache manager with automatic JSON serialization and graceful degradation."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or settings.REDIS_URL
        self._client: aioredis.Redis | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def get_client(self) -> aioredis.Redis:
        """Get or initialize the underlying async Redis client."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._client is None or (current_loop is not None and self._loop is not current_loop):
            self._loop = current_loop
            self._client = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
        return self._client

    async def get(self, key: str) -> Any | None:
        """Retrieve a cached item by key, deserializing from JSON."""
        t0 = time.perf_counter()
        try:
            client = self.get_client()
            raw_data = await client.get(key)
            if raw_data is None:
                return None
            return json.loads(raw_data)
        except (json.JSONDecodeError, ValueError):
            return raw_data
        except Exception as e:
            logger.warning("Redis GET failed for key '%s': %s (degrading gracefully)", key, e)
            return None
        finally:
            elapsed = (time.perf_counter() - t0) * 1000
            ctx = get_current_timing_ctx()
            if ctx:
                ctx.redis_ms += elapsed

    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Cache an item by key, serializing to JSON, with optional TTL in seconds."""
        t0 = time.perf_counter()
        try:
            client = self.get_client()
            serialized = json.dumps(value, default=str)
            await client.set(key, serialized, ex=ttl)
            return True
        except Exception as e:
            logger.warning("Redis SET failed for key '%s': %s (degrading gracefully)", key, e)
            return False
        finally:
            elapsed = (time.perf_counter() - t0) * 1000
            ctx = get_current_timing_ctx()
            if ctx:
                ctx.redis_ms += elapsed

    async def delete(self, key: str) -> bool:
        """Remove a cached key."""
        t0 = time.perf_counter()
        try:
            client = self.get_client()
            await client.delete(key)
            return True
        except Exception as e:
            logger.warning("Redis DELETE failed for key '%s': %s (degrading gracefully)", key, e)
            return False
        finally:
            elapsed = (time.perf_counter() - t0) * 1000
            ctx = get_current_timing_ctx()
            if ctx:
                ctx.redis_ms += elapsed

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern."""
        t0 = time.perf_counter()
        try:
            client = self.get_client()
            keys = []
            async for k in client.scan_iter(match=pattern):
                keys.append(k)
            if keys:
                return await client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning("Redis DELETE pattern '%s' failed: %s (degrading gracefully)", pattern, e)
            return 0
        finally:
            elapsed = (time.perf_counter() - t0) * 1000
            ctx = get_current_timing_ctx()
            if ctx:
                ctx.redis_ms += elapsed

    async def close(self) -> None:
        """Close the Redis connection pool."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None


# Global default cache singleton
cache = RedisCache()

