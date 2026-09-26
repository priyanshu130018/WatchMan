"""Unit tests for centralized environment variable validation and secret management."""

import os
import pytest
from app.core.config import ConfigurationError, Settings, get_settings


@pytest.fixture
def valid_env_dict(monkeypatch):
    """A dictionary of completely valid dummy configuration values with isolated os.environ."""
    monkeypatch.setattr(os, "environ", {})
    return {
        "APP_NAME": "WatchManTest",
        "APP_ENV": "testing",
        "APP_DEBUG": "true",
        "APP_VERSION": "1.0.0-test",
        "HOST": "127.0.0.1",
        "PORT": "8000",
        "SECRET_KEY": "fake_test_jwt_secret_value_12345",
        "ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "REFRESH_TOKEN_EXPIRE_DAYS": "30",
        "DATABASE_URL": "postgresql+psycopg://test_user:test_pass@test_host:5432/test_db",
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_ANON_KEY": "fake_supabase_anon_key_abcdef",
        "SUPABASE_SERVICE_ROLE_KEY": "fake_supabase_service_role_key_abcdef",
        "TMDB_API_KEY": "fake_tmdb_api_key_12345",
        "TMDB_BASE_URL": "https://api.themoviedb.org/3",
        "OMDB_API_KEY": "fake_omdb_api_key_12345",
        "OMDB_BASE_URL": "https://www.omdbapi.com/",
        "REDIS_URL": "redis://localhost:6379/0",
        "CELERY_BROKER_URL": "redis://localhost:6379/0",
        "CELERY_RESULT_BACKEND": "redis://localhost:6379/1",
        "CORS_ORIGINS": "http://localhost:5173,http://localhost:3000",
        "FRONTEND_URL": "http://localhost:5173",
        "EMBEDDING_MODEL": "sentence-transformers/all-MiniLM-L6-v2",
        "VECTOR_DIMENSION": "384",
        "ENABLE_PGVECTOR": "true",
        "ML_ADMIN_EMAILS": "admin@example.com,lead@example.com",
        "HF_API_URL": "https://api-inference.huggingface.co/pipeline/feature-extraction",
        "HF_API_TOKEN": "fake_hf_token_12345",
    }


def test_valid_configuration_succeeds(valid_env_dict):
    """Test that a fully specified valid environment loads successfully."""
    s = get_settings(_env_file=None, **valid_env_dict)
    assert s.APP_NAME == "WatchManTest"
    assert s.APP_DEBUG is True
    assert s.PORT == 8000
    assert s.DATABASE_URL == "postgresql+psycopg://test_user:test_pass@test_host:5432/test_db"
    assert s.cors_origins_list == ["http://localhost:5173", "http://localhost:3000"]
    assert s.ml_admin_emails == {"admin@example.com", "lead@example.com"}


def test_missing_required_configuration_fails(valid_env_dict):
    """Test that omitting a required environment variable raises ConfigurationError."""
    del valid_env_dict["TMDB_API_KEY"]
    with pytest.raises(ConfigurationError) as exc_info:
        get_settings(_env_file=None, **valid_env_dict)

    err_msg = str(exc_info.value)
    assert "TMDB_API_KEY" in err_msg
    assert "Missing required environment variables" in err_msg


def test_empty_required_string_fails(valid_env_dict):
    """Test that an empty string value for a required variable raises ConfigurationError."""
    valid_env_dict["SECRET_KEY"] = ""
    with pytest.raises(ConfigurationError) as exc_info:
        get_settings(_env_file=None, **valid_env_dict)

    err_msg = str(exc_info.value)
    assert "SECRET_KEY" in err_msg


def test_whitespace_only_required_string_fails(valid_env_dict):
    """Test that whitespace-only values for required variables raise ConfigurationError."""
    valid_env_dict["SUPABASE_URL"] = "   \t\n  "
    with pytest.raises(ConfigurationError) as exc_info:
        get_settings(_env_file=None, **valid_env_dict)

    err_msg = str(exc_info.value)
    assert "SUPABASE_URL" in err_msg


def test_database_strategy_a_url_override(valid_env_dict):
    """Test that Strategy A (direct DATABASE_URL) succeeds without split postgres variables."""
    for key in ["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]:
        valid_env_dict.pop(key, None)

    valid_env_dict["DATABASE_URL"] = "postgresql+psycopg://override_user:override_pass@dbhost:5432/overridedb"
    s = get_settings(_env_file=None, **valid_env_dict)
    assert s.DATABASE_URL == "postgresql+psycopg://override_user:override_pass@dbhost:5432/overridedb"


def test_database_strategy_b_split_variables(valid_env_dict):
    """Test that Strategy B (split POSTGRES_* variables) builds the database URL properly."""
    valid_env_dict.pop("DATABASE_URL", None)
    valid_env_dict.pop("POSTGRES_URL", None)

    valid_env_dict["POSTGRES_HOST"] = "custom_host"
    valid_env_dict["POSTGRES_PORT"] = 5432
    valid_env_dict["POSTGRES_DB"] = "custom_db"
    valid_env_dict["POSTGRES_USER"] = "custom_user"
    valid_env_dict["POSTGRES_PASSWORD"] = "custom_pass"

    s = get_settings(_env_file=None, **valid_env_dict)
    assert s.DATABASE_URL == "postgresql+psycopg://custom_user:custom_pass@custom_host:5432/custom_db"


def test_database_strategy_b_incomplete_fails(valid_env_dict):
    """Test that providing partial split PostgreSQL variables fails validation."""
    valid_env_dict.pop("DATABASE_URL", None)
    valid_env_dict.pop("POSTGRES_URL", None)

    # Missing POSTGRES_PASSWORD and POSTGRES_USER
    valid_env_dict["POSTGRES_HOST"] = "custom_host"
    valid_env_dict["POSTGRES_PORT"] = 5432
    valid_env_dict["POSTGRES_DB"] = "custom_db"

    with pytest.raises(ConfigurationError) as exc_info:
        get_settings(_env_file=None, **valid_env_dict)

    err_msg = str(exc_info.value)
    assert "Incomplete PostgreSQL configuration" in err_msg
    assert "POSTGRES_USER" in err_msg
    assert "POSTGRES_PASSWORD" in err_msg


def test_missing_all_database_configuration_fails(valid_env_dict):
    """Test that omitting both Strategy A and Strategy B database configuration fails."""
    valid_env_dict.pop("DATABASE_URL", None)
    valid_env_dict.pop("POSTGRES_URL", None)
    for key in ["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]:
        valid_env_dict.pop(key, None)

    with pytest.raises(ConfigurationError) as exc_info:
        get_settings(_env_file=None, **valid_env_dict)

    err_msg = str(exc_info.value)
    assert "Database configuration is missing" in err_msg


def test_invalid_integer_configuration_fails(valid_env_dict):
    """Test that an invalid integer value raises ConfigurationError."""
    valid_env_dict["PORT"] = "not_a_valid_integer"
    with pytest.raises(ConfigurationError) as exc_info:
        get_settings(_env_file=None, **valid_env_dict)

    err_msg = str(exc_info.value)
    assert "PORT" in err_msg


def test_invalid_boolean_configuration_fails(valid_env_dict):
    """Test that an invalid boolean value raises ConfigurationError."""
    valid_env_dict["APP_DEBUG"] = "invalid_bool_string"
    with pytest.raises(ConfigurationError) as exc_info:
        get_settings(_env_file=None, **valid_env_dict)

    err_msg = str(exc_info.value)
    assert "APP_DEBUG" in err_msg


def test_configuration_error_does_not_expose_secret_values(valid_env_dict):
    """Test that ConfigurationError messages never leak secret values."""
    secret_value = "super_top_secret_jwt_key_that_must_not_appear_in_error_logs_9999"
    valid_env_dict["SECRET_KEY"] = secret_value
    valid_env_dict["PORT"] = "invalid_port"

    with pytest.raises(ConfigurationError) as exc_info:
        get_settings(_env_file=None, **valid_env_dict)

    err_msg = str(exc_info.value)
    assert secret_value not in err_msg
    assert "PORT" in err_msg


# --------------------------------------------------------------------------- #
# Production hardening: Supabase-only auth + no localhost/Docker infrastructure.
# These guard the constraint that production must NEVER silently fall back to
# local auth or local/Docker Postgres/Redis.
# --------------------------------------------------------------------------- #

@pytest.fixture
def prod_env_dict(valid_env_dict):
    """A valid production environment: Supabase auth + hosted (non-local) infra."""
    valid_env_dict["APP_ENV"] = "production"
    valid_env_dict["AUTH_PROVIDER"] = "supabase"
    valid_env_dict["SUPABASE_JWT_SECRET"] = "prod_supabase_jwt_secret_minimum_thirty_two_chars"
    valid_env_dict["DATABASE_URL"] = (
        "postgresql+psycopg://postgres.ref:pw@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"
    )
    valid_env_dict["REDIS_URL"] = "rediss://default:pw@fake-name.upstash.io:6379"
    valid_env_dict["CELERY_BROKER_URL"] = "rediss://default:pw@fake-name.upstash.io:6379"
    valid_env_dict["CELERY_RESULT_BACKEND"] = "rediss://default:pw@fake-name.upstash.io:6379"
    return valid_env_dict


def test_production_supabase_config_succeeds(prod_env_dict):
    """A well-formed production config (Supabase auth + hosted infra) loads."""
    s = get_settings(_env_file=None, **prod_env_dict)
    assert s.APP_ENV == "production"
    assert s.AUTH_PROVIDER == "supabase"


def test_production_rejects_local_auth_provider(prod_env_dict):
    """Production must refuse AUTH_PROVIDER=local (no local JWT/bcrypt in prod)."""
    prod_env_dict["AUTH_PROVIDER"] = "local"
    with pytest.raises(ConfigurationError) as exc_info:
        get_settings(_env_file=None, **prod_env_dict)
    assert "AUTH_PROVIDER must be 'supabase'" in str(exc_info.value)


def test_production_requires_supabase_jwt_secret(prod_env_dict):
    """Production Supabase auth requires a JWT secret to validate tokens."""
    prod_env_dict["SUPABASE_JWT_SECRET"] = ""
    with pytest.raises(ConfigurationError) as exc_info:
        get_settings(_env_file=None, **prod_env_dict)
    assert "SUPABASE_JWT_SECRET is required" in str(exc_info.value)


def test_production_rejects_localhost_database_url(prod_env_dict):
    """Production must refuse a localhost DATABASE_URL (no local Postgres)."""
    prod_env_dict["DATABASE_URL"] = "postgresql+psycopg://u:p@localhost:5432/watchman"
    with pytest.raises(ConfigurationError) as exc_info:
        get_settings(_env_file=None, **prod_env_dict)
    assert "local/Docker infrastructure" in str(exc_info.value)


def test_production_rejects_docker_service_host(prod_env_dict):
    """Production must refuse a Docker service-name host like @db: (no Docker Postgres)."""
    prod_env_dict["DATABASE_URL"] = "postgresql+psycopg://u:p@db:5432/watchman"
    with pytest.raises(ConfigurationError) as exc_info:
        get_settings(_env_file=None, **prod_env_dict)
    assert "local/Docker infrastructure" in str(exc_info.value)


def test_production_rejects_localhost_redis(prod_env_dict):
    """Production must refuse a localhost REDIS_URL (no local/Docker Redis)."""
    prod_env_dict["REDIS_URL"] = "redis://localhost:6379/0"
    with pytest.raises(ConfigurationError) as exc_info:
        get_settings(_env_file=None, **prod_env_dict)
    assert "local/Docker infrastructure" in str(exc_info.value)


def test_development_allows_local_auth_and_localhost(valid_env_dict):
    """Non-production env keeps the local dev path (local auth + localhost infra)."""
    valid_env_dict["APP_ENV"] = "development"
    valid_env_dict["AUTH_PROVIDER"] = "local"
    valid_env_dict["REDIS_URL"] = "redis://localhost:6379/0"
    s = get_settings(_env_file=None, **valid_env_dict)
    assert s.AUTH_PROVIDER == "local"
