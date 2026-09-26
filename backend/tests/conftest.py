"""Pytest shared fixtures and database test environment setup."""

import os
import pytest

# Ensure standard test environment variables are present before importing app modules
_TEST_ENV_DEFAULTS = {
    "APP_NAME": "WatchMan API",
    "APP_ENV": "test",
    "APP_DEBUG": "false",
    "APP_VERSION": "1.0.0",
    "HOST": "0.0.0.0",
    "PORT": "8000",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "watchman_test",
    "POSTGRES_USER": "watchman",
    "POSTGRES_PASSWORD": "ci_test_password",
    "DATABASE_URL": "sqlite:///:memory:",
    "SECRET_KEY": "ci_testing_secret_key_minimum_thirty_two_characters_long",
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "15",
    "REFRESH_TOKEN_EXPIRE_DAYS": "7",
    "TMDB_API_KEY": "ci_test_tmdb_api_key_000000000000",
    "TMDB_BASE_URL": "https://api.themoviedb.org/3",
    "OMDB_API_KEY": "ci_test_omdb_api_key",
    "OMDB_BASE_URL": "https://www.omdbapi.com/",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/1",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/2",
    "SUPABASE_URL": "https://ci-test.supabase.co",
    "SUPABASE_ANON_KEY": "ci_anon_key",
    "SUPABASE_SERVICE_ROLE_KEY": "ci_service_role_key",
    # Auth provider defaults to local for the test suite; Supabase-specific tests
    # override AUTH_PROVIDER / SUPABASE_JWT_SECRET explicitly.
    "AUTH_PROVIDER": "local",
    "SUPABASE_JWT_SECRET": "ci_test_supabase_jwt_secret_minimum_thirty_two_chars",
    "SUPABASE_JWT_AUD": "authenticated",
    "CORS_ORIGINS": "http://localhost:3000,http://localhost:8000",
    "ENABLE_PGVECTOR": "false",
    "EMBEDDING_MODEL": "all-MiniLM-L6-v2",
    "VECTOR_DIMENSION": "384",
    "ML_ADMIN_EMAILS": "admin@watchman.local",
    "HF_API_URL": "https://api-inference.huggingface.co/pipeline/feature-extraction",
    "HF_API_TOKEN": "ci_test_hf_token",
    "FRONTEND_URL": "http://localhost:3000",
}

for key, val in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(key, val)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture
def test_engine():
    """Create function-scoped in-memory SQLite engine with StaticPool for strict test isolation."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    """Function-scoped database session using the test engine."""
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def override_db_dependency(test_engine):
    """Automatically override FastAPI get_db dependency with test database session for each test."""
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def _get_test_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_test_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def mock_sentence_encoder(monkeypatch):
    """Hermetic offline test double for SentenceEncoder._request."""
    import math
    from app.ml.embeddings.sentence_encoder import SentenceEncoder

    unit_val = 1.0 / math.sqrt(384)
    unit_vec = [unit_val] * 384

    def _mock_request(self, inputs):
        if isinstance(inputs, str):
            return unit_vec
        return [unit_vec for _ in inputs]

    monkeypatch.setattr(SentenceEncoder, "_request", _mock_request)

