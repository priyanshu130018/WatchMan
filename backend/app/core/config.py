from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str
    APP_ENV: str
    APP_DEBUG: bool
    APP_VERSION: str

    HOST: str
    PORT: int

    DATABASE_URL: str

    TMDB_API_KEY: str
    TMDB_ACCESS_TOKEN: str | None = None

    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str

    REDIS_URL: str

    CORS_ORIGINS: str

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()