"""Centralized typed exception hierarchy for WatchMan.

All domain, service, and infrastructure layers raise typed subclasses of
AppException. These are translated into standard API error responses by the
global FastAPI exception handlers in app.main.
"""

from typing import Any


class AppException(Exception):
    """Base application exception supporting structured machine-readable errors."""

    status_code: int = 500
    code: str = "INTERNAL_SERVER_ERROR"
    message: str = "An unexpected internal server error occurred."

    def __init__(
        self,
        message: str | None = None,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Format as standard API error response body."""
        return {
            "success": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }


# -----------------------------------------------------------------------------
# Validation & Input Exceptions (422 / 400)
# -----------------------------------------------------------------------------

class ValidationException(AppException):
    """Raised when incoming request payload or parameter fails validation."""

    status_code = 422
    code = "VALIDATION_ERROR"
    message = "Request validation failed."


class InvalidContentIdException(ValidationException):
    code = "INVALID_CONTENT_ID"
    message = "The provided content identifier is invalid."


# -----------------------------------------------------------------------------
# Authentication & Authorization Exceptions (401 / 403)
# -----------------------------------------------------------------------------

class AuthenticationException(AppException):
    """Raised when authentication credentials are missing, invalid, or expired."""

    status_code = 401
    code = "UNAUTHORIZED"
    message = "Authentication credentials were not provided or are invalid."


class AuthorizationException(AppException):
    """Raised when an authenticated user lacks required permissions."""

    status_code = 403
    code = "FORBIDDEN"
    message = "You do not have permission to perform this action."


# -----------------------------------------------------------------------------
# Resource Not Found Exceptions (404)
# -----------------------------------------------------------------------------

class NotFoundException(AppException):
    """Raised when a requested resource does not exist."""

    status_code = 404
    code = "NOT_FOUND"
    message = "The requested resource was not found."


class MovieNotFoundException(NotFoundException):
    code = "MOVIE_NOT_FOUND"
    message = "Movie with the requested ID was not found."


class TVShowNotFoundException(NotFoundException):
    code = "TV_SHOW_NOT_FOUND"
    message = "TV show with the requested ID was not found."


class ContentNotFoundException(NotFoundException):
    code = "CONTENT_NOT_FOUND"
    message = "Content with the requested ID was not found."


class UserNotFoundException(NotFoundException):
    code = "USER_NOT_FOUND"
    message = "User with the requested ID was not found."


class FavoriteNotFoundException(NotFoundException):
    code = "FAVORITE_NOT_FOUND"
    message = "Favorite entry not found."


class WatchHistoryNotFoundException(NotFoundException):
    code = "WATCH_HISTORY_NOT_FOUND"
    message = "Watch history entry not found."


class NoResultsFoundException(NotFoundException):
    """Raised when an upstream feed/search returns zero items."""

    code = "NO_RESULTS_FOUND"
    message = "No matching content was found for this request."


# -----------------------------------------------------------------------------
# Conflict Exceptions (409)
# -----------------------------------------------------------------------------

class ConflictException(AppException):
    """Raised when a resource state conflicts with the requested operation."""

    status_code = 409
    code = "RESOURCE_CONFLICT"
    message = "A resource with the specified identifier already exists."


class UserAlreadyExistsException(ConflictException):
    code = "USER_ALREADY_EXISTS"
    message = "A user with this email address already exists."


# -----------------------------------------------------------------------------
# External Service & TMDB Exceptions (502 / 503 / 429)
# -----------------------------------------------------------------------------

class ExternalServiceException(AppException):
    """Raised when an upstream external service returns an error."""

    status_code = 502
    code = "EXTERNAL_SERVICE_ERROR"
    message = "An error occurred communicating with an external service."


class TMDBException(ExternalServiceException):
    """Base exception for TMDB API communication failures."""

    status_code = 502
    code = "TMDB_ERROR"
    message = "TMDB service encountered an error."


class TMDBTimeoutException(TMDBException):
    status_code = 503
    code = "TMDB_TIMEOUT"
    message = "Timed out while waiting for TMDB service."


class TMDBUnavailableException(TMDBException):
    status_code = 503
    code = "TMDB_UNAVAILABLE"
    message = "TMDB service is currently unreachable or unavailable."


class TMDBRateLimitedException(TMDBException):
    status_code = 429
    code = "TMDB_RATE_LIMITED"
    message = "TMDB API rate limit exceeded. Please retry shortly."


class TMDBAuthenticationException(TMDBException):
    status_code = 502
    code = "TMDB_AUTHENTICATION_ERROR"
    message = "Failed to authenticate with TMDB API."


class TMDBInvalidResponseException(TMDBException):
    status_code = 502
    code = "TMDB_INVALID_RESPONSE"
    message = "TMDB returned an invalid or unparseable response."


# -----------------------------------------------------------------------------
# Infrastructure & Domain Exceptions (500)
# -----------------------------------------------------------------------------

class DatabaseException(AppException):
    """Raised when a database query or connection fails unexpectedly."""

    status_code = 500
    code = "DATABASE_ERROR"
    message = "A database error occurred."


class CacheException(AppException):
    """Raised when a cache backend operation fails unexpectedly."""

    status_code = 500
    code = "CACHE_ERROR"
    message = "A cache operation failed."


class RecommendationException(AppException):
    """Raised when a recommendation scoring or ranking pipeline fails."""

    status_code = 500
    code = "RECOMMENDATION_ERROR"
    message = "An error occurred in the recommendation engine."


class SearchException(AppException):
    """Raised when a search query fails execution."""

    status_code = 500
    code = "SEARCH_ERROR"
    message = "An error occurred during search execution."


class ConfigurationException(AppException):
    """Raised when application configuration is invalid or missing."""

    status_code = 500
    code = "CONFIGURATION_ERROR"
    message = "Application configuration error."
