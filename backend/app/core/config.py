from typing import Any
from sqlalchemy.engine import URL
from pydantic import AliasChoices, Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """Raised when application configuration is missing, incomplete, or invalid."""
    pass


class Settings(BaseSettings):
    # Application
    APP_NAME: str
    APP_ENV: str
    APP_DEBUG: bool
    APP_VERSION: str
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security / Authentication (Local JWT path)
    SECRET_KEY: str = "watchman-local-dev-secret-key-minimum-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    # Strategy A: Full connection URL
    DATABASE_URL_OVERRIDE: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL"),
    )
    # Strategy B: Split PostgreSQL connection parameters
    POSTGRES_HOST: str | None = None
    POSTGRES_PORT: int | None = None
    POSTGRES_DB: str | None = None
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None

    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # Authentication provider selection.
    #   "supabase" -> production: validate Supabase Auth access tokens only.
    #   "local"    -> development: use this service's own HS256 JWT + bcrypt.
    # Defaults to "local" so local dev keeps working; production is REQUIRED to
    # set "supabase" (enforced in the validator below, which also forbids
    # localhost infra in production).
    AUTH_PROVIDER: str = "local"
    # Shared Supabase JWT secret (symmetric HS256 tokens). Required when
    # AUTH_PROVIDER=supabase and the project signs tokens with the shared secret.
    SUPABASE_JWT_SECRET: str | None = None
    # Expected audience claim on Supabase access tokens.
    SUPABASE_JWT_AUD: str = "authenticated"

    # TMDB
    TMDB_API_KEY: str
    TMDB_BASE_URL: str = "https://api.themoviedb.org/3"

    # OMDb (IMDb / Rotten Tomatoes / Metacritic ratings)
    OMDB_API_KEY: str
    OMDB_BASE_URL: str = "https://www.omdbapi.com/"

    # Redis & Celery
    REDIS_URL: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # CORS & Frontend
    CORS_ORIGINS: str
    FRONTEND_URL: str

    # ML & Embeddings
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    VECTOR_DIMENSION: int = 384
    ENABLE_PGVECTOR: bool = True
    ML_ADMIN_EMAILS: str = "admin@watchman.io"

    # HuggingFace Inference API (remote embeddings)
    HF_API_URL: str = "https://router.huggingface.co/hf-inference/models"
    HF_API_TOKEN: str

    # Selective content embedding strategy
    INITIAL_POPULAR_MOVIE_EMBED_LIMIT: int = 500
    INITIAL_POPULAR_TV_EMBED_LIMIT: int = 500
    ENABLE_INTERACTION_EMBEDDING: bool = True
    ENABLE_SEARCH_EMBEDDING: bool = False
    SEARCH_EMBED_THRESHOLD: int = 3

    # ---- Hybrid recommendation tuning ----------------------------------
    # These are ALGORITHM hyperparameters (not secrets), so they carry safe,
    # documented defaults and can be overridden in .env. See
    # docs/RECOMMENDATION_ARCHITECTURE.md for the meaning of each.
    #
    # Hybrid blend weights (final_score = sum(weight_i * signal_i)).
    REC_WEIGHT_CONTENT: float = 0.40
    REC_WEIGHT_COLLABORATIVE: float = 0.30
    REC_WEIGHT_POPULARITY: float = 0.15
    REC_WEIGHT_FRESHNESS: float = 0.10
    REC_WEIGHT_PREFERENCE: float = 0.05

    # ALS / matrix-factorization hyperparameters (collaborative branch).
    ALS_FACTORS: int = 64
    ALS_REGULARIZATION: float = 0.05
    ALS_ALPHA: float = 40.0
    ALS_ITERATIONS: int = 15
    ALS_SEED: int = 42
    ALS_MIN_USERS: int = 3
    ALS_MIN_ITEMS: int = 3
    ALS_MIN_INTERACTIONS: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def validate_non_empty_strings(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Strip strings and reject empty or whitespace-only strings for required string fields
        cleaned = {}
        for key, value in data.items():
            if isinstance(value, str):
                trimmed = value.strip()
                # Empty string is treated as None / unset
                cleaned[key] = trimmed if trimmed else None
            else:
                cleaned[key] = value
        return cleaned

    @model_validator(mode="after")
    def validate_database_and_cors_configuration(self) -> "Settings":
        # Validate Database configuration
        has_url_override = bool(self.DATABASE_URL_OVERRIDE and self.DATABASE_URL_OVERRIDE.strip())
        split_vars = [
            ("POSTGRES_HOST", self.POSTGRES_HOST),
            ("POSTGRES_PORT", self.POSTGRES_PORT),
            ("POSTGRES_DB", self.POSTGRES_DB),
            ("POSTGRES_USER", self.POSTGRES_USER),
            ("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD),
        ]
        has_all_split = all(v is not None for _, v in split_vars)
        has_any_split = any(v is not None for _, v in split_vars)

        if not has_url_override and not has_all_split:
            if has_any_split:
                missing_split = [k for k, v in split_vars if v is None]
                raise ValueError(
                    f"Incomplete PostgreSQL configuration. Missing: {', '.join(missing_split)}. "
                    f"Provide either DATABASE_URL or all of POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD."
                )
            raise ValueError(
                "Database configuration is missing. Provide either DATABASE_URL or all of "
                "POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD."
            )

        # Validate CORS
        if not self.cors_origins_list:
            raise ValueError("CORS_ORIGINS must contain at least one valid origin URL.")
        if "*" in self.cors_origins_list:
            raise ValueError(
                "Wildcard '*' in CORS_ORIGINS is not permitted with authenticated credentials."
            )

        # ---- Production hardening ------------------------------------------
        # In production the runtime path MUST be Supabase Auth + hosted infra.
        # Never allow a silent fallback to local auth or localhost services.
        if self.APP_ENV.strip().lower() in ("production", "prod"):
            if self.AUTH_PROVIDER.strip().lower() != "supabase":
                raise ValueError(
                    "In production APP_ENV, AUTH_PROVIDER must be 'supabase' "
                    "(local JWT/bcrypt auth is not permitted in production)."
                )
            if not (self.SUPABASE_JWT_SECRET and self.SUPABASE_JWT_SECRET.strip()):
                raise ValueError(
                    "SUPABASE_JWT_SECRET is required when AUTH_PROVIDER=supabase "
                    "in production so access tokens can be validated."
                )
            self._reject_localhost("DATABASE_URL", self.DATABASE_URL)
            self._reject_localhost("REDIS_URL", self.REDIS_URL)
            self._reject_localhost("CELERY_BROKER_URL", self.CELERY_BROKER_URL)
            self._reject_localhost("CELERY_RESULT_BACKEND", self.CELERY_RESULT_BACKEND)

        return self

    @staticmethod
    def _reject_localhost(name: str, value: str | None) -> None:
        """Fail fast if a production connection string points at local infra."""
        if not value:
            return
        lowered = value.lower()
        for needle in (
            "localhost",
            "127.0.0.1",
            "::1",
            "@db:",
            "@redis:",
            "@postgres:",
            "//db:",
            "//redis:",
            "//postgres:",
        ):
            if needle in lowered:
                raise ValueError(
                    f"{name} points at local/Docker infrastructure ('{needle}') "
                    f"which is not allowed in production. Use Supabase/Upstash hosts."
                )

    @property
    def DATABASE_URL(self) -> str:
        """Return configured SQLAlchemy URL. Strategy A (DATABASE_URL) takes precedence."""
        if self.DATABASE_URL_OVERRIDE and self.DATABASE_URL_OVERRIDE.strip():
            return self.DATABASE_URL_OVERRIDE.strip()
        return URL.create(
            "postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        ).render_as_string(hide_password=False)

    @property
    def cors_origins_list(self) -> list[str]:
        origins = [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]
        if hasattr(self, "FRONTEND_URL") and self.FRONTEND_URL and self.FRONTEND_URL.strip():
            fe = self.FRONTEND_URL.strip()
            if fe not in origins:
                origins.append(fe)
        return origins

    @property
    def ml_admin_emails(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.ML_ADMIN_EMAILS.split(",")
            if email.strip()
        }

    @property
    def recommendation_weights(self) -> dict[str, float]:
        """Hybrid blend weights for the ranker. Keys match HybridRanker."""
        return {
            "content": self.REC_WEIGHT_CONTENT,
            "collaborative": self.REC_WEIGHT_COLLABORATIVE,
            "popularity": self.REC_WEIGHT_POPULARITY,
            "freshness": self.REC_WEIGHT_FRESHNESS,
            "preference": self.REC_WEIGHT_PREFERENCE,
        }

    @property
    def als_params(self) -> dict[str, float | int]:
        """ALS hyperparameters + training guards."""
        return {
            "factors": self.ALS_FACTORS,
            "regularization": self.ALS_REGULARIZATION,
            "alpha": self.ALS_ALPHA,
            "iterations": self.ALS_ITERATIONS,
            "seed": self.ALS_SEED,
            "min_users": self.ALS_MIN_USERS,
            "min_items": self.ALS_MIN_ITEMS,
            "min_interactions": self.ALS_MIN_INTERACTIONS,
        }


def format_validation_error(err: ValidationError) -> str:
    """Format Pydantic ValidationError into a safe, informative message without secret values."""
    missing_fields = []
    invalid_fields = []

    for error in err.errors():
        loc = ".".join(str(l) for l in error.get("loc", []))
        error_type = error.get("type", "")
        msg = error.get("msg", "")

        if error_type in ("missing", "value_error.missing") or "Field required" in msg:
            missing_fields.append(loc)
        else:
            invalid_fields.append(f"'{loc}': {msg}")

    lines = ["Application configuration failed:"]
    if missing_fields:
        lines.append(f"Missing required environment variables: {', '.join(sorted(set(missing_fields)))}")
    if invalid_fields:
        lines.append(f"Invalid environment configuration: {'; '.join(invalid_fields)}")

    return "\n".join(lines)


def get_settings(_env_file: str | None = ".env", **kwargs: Any) -> Settings:
    """Instantiate and validate Settings, raising ConfigurationError on failure."""
    try:
        return Settings(_env_file=_env_file, **kwargs)
    except ValidationError as e:
        raise ConfigurationError(format_validation_error(e)) from None
    except Exception as e:
        raise ConfigurationError(f"Configuration initialization error: {e}") from None


settings = get_settings()
