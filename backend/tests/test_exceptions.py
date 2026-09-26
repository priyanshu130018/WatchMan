"""Comprehensive tests for centralized exception handling and standard error responses."""

from unittest.mock import AsyncMock, patch
import httpx
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.main import app
from app.core.exceptions import (
    AppException,
    AuthenticationException,
    AuthorizationException,
    ConflictException,
    DatabaseException,
    InvalidContentIdException,
    MovieNotFoundException,
    NotFoundException,
    TMDBAuthenticationException,
    TMDBInvalidResponseException,
    TMDBRateLimitedException,
    TMDBTimeoutException,
    TMDBUnavailableException,
    ValidationException,
)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# -----------------------------------------------------------------------------
# 1. Custom Test Routes on Mini App to Validate Handler Translation
# -----------------------------------------------------------------------------

def test_app_exception_handler(client):
    """Test custom AppException is translated to standard error JSON."""
    test_app = FastAPI()
    test_app.exception_handler(AppException)(app.exception_handlers[AppException])

    @test_app.get("/custom-error")
    def trigger_error():
        raise AppException(
            message="Custom failure occurred.",
            code="CUSTOM_FAILURE",
            status_code=418,
            details={"foo": "bar"},
        )

    c = TestClient(test_app)
    response = c.get("/custom-error")
    assert response.status_code == 418
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "CUSTOM_FAILURE"
    assert data["error"]["message"] == "Custom failure occurred."
    assert data["error"]["details"] == {"foo": "bar"}


# -----------------------------------------------------------------------------
# 2. Validation Errors (422 / VALIDATION_ERROR)
# -----------------------------------------------------------------------------

def test_validation_error_format(client):
    """RequestValidationError returns 422 with structured field details."""
    response = client.post("/api/auth/register", json={"email": "not-an-email"})
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "Request validation failed." in data["error"]["message"]
    assert isinstance(data["error"]["details"], list)
    assert len(data["error"]["details"]) > 0
    # Field names should be clean
    fields = [d["field"] for d in data["error"]["details"]]
    assert any("email" in f or "password" in f or "full_name" in f for f in fields)


# -----------------------------------------------------------------------------
# 3. Authentication & Authorization (401 / 403)
# -----------------------------------------------------------------------------

def test_unauthenticated_request_returns_401(client):
    """Protected endpoints return 401 UNAUTHORIZED when no token is supplied."""
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "credentials were not provided" in data["error"]["message"]


def test_invalid_token_returns_401(client):
    """Invalid token returns 401 UNAUTHORIZED."""
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHORIZED"


def test_inactive_or_forbidden_user_returns_403(client):
    """ML operator endpoint without operator email returns 403 FORBIDDEN."""
    # Test with valid token payload for a non-admin email
    with patch("app.core.security.jwt.decode") as mock_jwt:
        import uuid
        test_uid = uuid.uuid4()
        mock_jwt.return_value = {"user_id": str(test_uid)}

        with patch("app.core.security.db.query") if False else patch("sqlalchemy.orm.Session.query") as mock_query:
            from app.database.models.user import User
            mock_user = User(
                id=test_uid,
                email="regular_user@example.com",
                full_name="Regular User",
                password_hash="hashed",
                is_active=True,
            )
            mock_query.return_value.filter.return_value.first.return_value = mock_user

            response = client.post(
                "/api/ml/embeddings/movies/batch",
                headers={"Authorization": "Bearer some.valid.token"},
                json={"limit": 10},
            )
            assert response.status_code == 403
            data = response.json()
            assert data["success"] is False
            assert data["error"]["code"] == "FORBIDDEN"
            assert "ML operator access is required" in data["error"]["message"]


# -----------------------------------------------------------------------------
# 4. Resource Not Found (404)
# -----------------------------------------------------------------------------

def test_movie_not_found(client):
    """TMDB 404 response translates to 404 MOVIE_NOT_FOUND."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = httpx.Response(
            status_code=404,
            content=b'{"status_code": 34, "status_message": "The resource you requested could not be found."}',
            request=httpx.Request("GET", "https://api.themoviedb.org/3/movie/9999999"),
        )
        mock_get.return_value = mock_response

        response = client.get("/api/movies/9999999")
        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "MOVIE_NOT_FOUND"
        assert "9999999" in data["error"]["message"]


def test_operator_endpoints_reject_anonymous(client):
    """Security regression: operational/diagnostic endpoints must not be public.

    ``/api/ops/metrics`` and ``/api/ops/status`` expose internal telemetry and
    infrastructure diagnostics and are operator-gated. Anonymous callers must be
    rejected (401) rather than served the data.
    """
    for path in (
        "/api/ops/metrics",
        "/api/ops/status",
    ):
        resp = client.get(path)
        assert resp.status_code == 401, f"{path} should require auth, got {resp.status_code}"


# -----------------------------------------------------------------------------
# 5. Resource Conflict (409)
# -----------------------------------------------------------------------------

def test_duplicate_user_register_conflict(client):
    """Duplicate email registration returns 409 USER_ALREADY_EXISTS."""
    with patch("sqlalchemy.orm.Session.query") as mock_query:
        from app.database.models.user import User
        mock_user = User(
            id="00000000-0000-0000-0000-000000000001",
            email="existing@example.com",
            full_name="Existing User",
            password_hash="hashed",
            is_active=True,
        )
        mock_query.return_value.filter.return_value.first.return_value = mock_user

        response = client.post(
            "/api/auth/register",
            json={
                "email": "existing@example.com",
                "password": "strongPassword123!",
                "full_name": "Existing User",
            },
        )
        assert response.status_code == 409
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "USER_ALREADY_EXISTS"
        assert "already registered" in data["error"]["message"]


# -----------------------------------------------------------------------------
# 6. TMDB Specific Errors
# -----------------------------------------------------------------------------

def test_tmdb_timeout_error(client):
    """TMDB timeout returns 503 TMDB_TIMEOUT."""
    with patch("httpx.AsyncClient.get", side_effect=httpx.ReadTimeout("Timeout connecting to TMDB")):
        response = client.get("/api/movies/popular")
        assert response.status_code == 503
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "TMDB_TIMEOUT"
        assert "Timed out" in data["error"]["message"]


def test_tmdb_connection_unavailable_error(client):
    """TMDB network connection error returns 503 TMDB_UNAVAILABLE."""
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused")):
        response = client.get("/api/movies/trending")
        assert response.status_code == 503
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "TMDB_UNAVAILABLE"


def test_tmdb_rate_limited_error(client):
    """TMDB 429 returns 429 TMDB_RATE_LIMITED."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = httpx.Response(
            status_code=429,
            content=b'{"status_code": 25, "status_message": "Your request count is over the allowed limit."}',
            request=httpx.Request("GET", "https://api.themoviedb.org/3/movie/popular"),
        )
        mock_get.return_value = mock_response

        response = client.get("/api/movies/popular")
        assert response.status_code == 429
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "TMDB_RATE_LIMITED"


def test_tmdb_authentication_error(client):
    """TMDB 401 returns 502 TMDB_AUTHENTICATION_ERROR without exposing API keys."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = httpx.Response(
            status_code=401,
            content=b'{"status_code": 7, "status_message": "Invalid API key"}',
            request=httpx.Request("GET", "https://api.themoviedb.org/3/movie/popular"),
        )
        mock_get.return_value = mock_response

        response = client.get("/api/movies/popular")
        assert response.status_code == 502
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "TMDB_AUTHENTICATION_ERROR"
        assert "Invalid API key" not in data["error"]["message"]


def test_tmdb_invalid_json_response(client):
    """TMDB unparseable response returns 502 TMDB_INVALID_RESPONSE."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = httpx.Response(
            status_code=200,
            content=b'<html><body>Cloudflare Error</body></html>',
            request=httpx.Request("GET", "https://api.themoviedb.org/3/movie/popular"),
        )
        mock_get.return_value = mock_response

        response = client.get("/api/movies/popular")
        assert response.status_code == 502
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "TMDB_INVALID_RESPONSE"


# -----------------------------------------------------------------------------
# 7. Unexpected Exception & Secret Leakage Prevention (500)
# -----------------------------------------------------------------------------

def test_unexpected_exception_handler(client):
    """Unexpected exception returns 500 INTERNAL_SERVER_ERROR without exposing tracebacks or secrets."""
    test_app = FastAPI()
    test_app.exception_handler(Exception)(app.exception_handlers[Exception])

    @test_app.get("/broken")
    def broken_route():
        secret = "SUPER_SECRET_DATABASE_PASSWORD_XYZ123"
        raise RuntimeError(f"Database connection broke with secret {secret}")

    c = TestClient(test_app, raise_server_exceptions=False)
    response = c.get("/broken")
    assert response.status_code == 500
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert data["error"]["message"] == "An unexpected error occurred."
    assert "request_id" in data["error"]["details"]

    # Verify secret and traceback are NOT leaked to client
    text = response.text
    assert "SUPER_SECRET_DATABASE_PASSWORD_XYZ123" not in text
    assert "Traceback" not in text
    assert "RuntimeError" not in text


# -----------------------------------------------------------------------------
# 8. Empty Search Results vs Exceptions
# -----------------------------------------------------------------------------

def test_empty_search_results_remains_success(client):
    """Valid search with zero matches returns 200 with empty list, NOT an error."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = httpx.Response(
            status_code=200,
            json={
                "page": 1,
                "results": [],
                "total_pages": 0,
                "total_results": 0,
            },
            request=httpx.Request("GET", "https://api.themoviedb.org/3/search/movie"),
        )
        mock_get.return_value = mock_response

        response = client.get("/api/search/movies?query=xyznonexistentmovie12345")
        assert response.status_code == 200
        data = response.json()
        assert data.get("results") == []
