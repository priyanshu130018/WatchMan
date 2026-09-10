from sqlalchemy.engine import URL
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str
    APP_ENV: str
    APP_DEBUG: bool
    APP_VERSION: str

    HOST: str
    PORT: int

    # Authentication
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Database
    # DATABASE_URL is retained as an override so existing deployments do not
    # break while moving to the split PostgreSQL settings.
    DATABASE_URL_OVERRIDE: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL"),
    )
    POSTGRES_HOST: str = ""
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = ""
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""

    # Optional Supabase
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # TMDB
    TMDB_API_KEY: str
    TMDB_ACCESS_TOKEN: str | None = None

    # Redis
    REDIS_URL: str

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # ML/Embeddings
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    VECTOR_DIMENSION: int = 384
    ENABLE_PGVECTOR: bool = True
    ML_ADMIN_EMAILS: str = ""

    # Frontend
    FRONTEND_URL: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

    @property
    def DATABASE_URL(self) -> str:
        """Return a configured SQLAlchemy URL with safely escaped credentials."""
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
    def ml_admin_emails(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.ML_ADMIN_EMAILS.split(",")
            if email.strip()
        }


settings = Settings()
