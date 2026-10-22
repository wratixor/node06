from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime values. Secrets are supplied by the environment, never defaults."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="NODE06_", extra="ignore")

    environment: str = "development"
    host: str = "127.0.0.1"
    port: int = 8086
    database_url: str | None = None
    build_revision: str = "dev"
    management_origin: str | None = None
    registration_per_hour: int = Field(default=3, ge=1)
    login_per_minute: int = Field(default=10, ge=1)
    account_login_per_minute: int = Field(default=10, ge=1)
    session_hours: int = Field(default=24, ge=1, le=720)
    site_creations_per_hour: int = Field(default=5, ge=1)
    site_renewals_per_hour: int = Field(default=5, ge=1)
    site_verifications_per_minute: int = Field(default=6, ge=1)
    verifier_seconds: float = Field(default=10.0, ge=0.1, le=30)
    verifier_slots: int = Field(default=2, ge=1, le=8)
    claim_max_attempts: int = Field(default=10, ge=1, le=100)


@lru_cache
def get_settings() -> Settings:
    return Settings()
