from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime values. Secrets are supplied by the environment, never defaults."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="NODE06_", extra="ignore")

    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8086
    database_url: str | None = None
    build_revision: str = "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
