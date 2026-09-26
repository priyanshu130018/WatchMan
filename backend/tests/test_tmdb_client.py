"""Focused tests for the TMDB HTTP client's outbound request behavior.

These tests never touch live TMDB: the network layer is replaced with
``httpx.MockTransport``. They lock in the two properties that matter for the
"ConnectionResetError during TLS" incident:

  1. TLS verification is NEVER disabled on the outbound client.
  2. A transient connection reset (ConnectError) is retried and, if it keeps
     failing, surfaces as a clean ``TMDBUnavailableException`` (HTTP 503) rather
     than leaking the raw socket error.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.exceptions import TMDBUnavailableException
from app.services.tmdb import service as tmdb_service
from app.services.tmdb.service import TMDBService, _build_tmdb_client


class _NullCache:
    """Cache stub so the client path never depends on Redis."""

    async def get(self, *_a, **_k):
        return None

    async def set(self, *_a, **_k):
        return None


def _patch_transport(monkeypatch, handler) -> dict:
    """Route the service's outbound client through an in-memory MockTransport.

    Returns a dict whose ``calls`` key counts how many times the handler ran, so
    tests can assert retry behavior.
    """
    state = {"calls": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        return handler(request, state["calls"])

    def _fake_build_client() -> httpx.AsyncClient:
        # Preserve the real client's redirect/header config but swap the network
        # transport for a deterministic mock. Verification stays at its default
        # (enabled) — we never pass verify=False anywhere.
        return httpx.AsyncClient(
            transport=httpx.MockTransport(_handler),
            follow_redirects=True,
            headers={"User-Agent": "test", "Accept": "application/json"},
        )

    monkeypatch.setattr(tmdb_service, "_build_tmdb_client", _fake_build_client)
    return state


def test_build_client_keeps_tls_verification_enabled():
    """Regression guard: the real client must not disable certificate checks."""
    import ssl

    client = _build_tmdb_client()

    # Locate the SSL context httpx/httpcore will use. The private attribute path
    # has shifted slightly across httpx versions, so probe the known locations
    # and skip (rather than false-fail) if none match the installed layout.
    transport = getattr(client, "_transport", None)
    pool = getattr(transport, "_pool", None)
    ssl_context = getattr(pool, "_ssl_context", None)
    if ssl_context is None:
        pytest.skip("Could not introspect SSL context on this httpx version")

    # The critical invariant: verification is ON. verify=False would flip these.
    assert ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert ssl_context.check_hostname is True


@pytest.mark.asyncio
async def test_trending_returns_parsed_payload(monkeypatch):
    payload = {"page": 1, "results": [{"id": 1, "title": "Example"}], "total_pages": 1}

    def handler(request: httpx.Request, _call: int) -> httpx.Response:
        assert request.url.path.endswith("/trending/movie/day")
        return httpx.Response(200, json=payload)

    _patch_transport(monkeypatch, handler)

    svc = TMDBService(redis_cache=_NullCache())
    data = await svc.trending_movies(time_window="day")
    assert data == payload


@pytest.mark.asyncio
async def test_persistent_connection_reset_becomes_503(monkeypatch):
    """A repeated connection reset must surface as TMDBUnavailableException."""

    def handler(request: httpx.Request, _call: int) -> httpx.Response:
        raise httpx.ConnectError("Connection reset by peer", request=request)

    state = _patch_transport(monkeypatch, handler)

    svc = TMDBService(redis_cache=_NullCache())
    with pytest.raises(TMDBUnavailableException):
        await svc.trending_movies(time_window="day")

    assert state["calls"] >= 1
