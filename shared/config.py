"""Application configuration loaded from environment variables.

Secrets and connection details come from the environment (docker-compose,
Container Apps secrets). Graph credentials themselves are NOT stored here — they
live encrypted in the ``app_config`` table and are entered via the admin UI.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---------------------------------------------------------
    # Async SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@db:5432/copilot
    database_url: str = Field(
        default="postgresql+psycopg://copilot:copilot@db:5432/copilot",
        alias="DATABASE_URL",
    )

    # --- Security ---------------------------------------------------------
    # Signs session/JWT tokens for the password gate.
    secret_key: str = Field(default="dev-insecure-change-me", alias="SECRET_KEY")
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt the Graph client secret.
    fernet_key: str = Field(default="", alias="FERNET_KEY")
    access_token_expire_minutes: int = Field(
        default=60 * 12, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )

    # Optional first-run admin bootstrap (created only if no users exist).
    admin_username: str | None = Field(default=None, alias="ADMIN_USERNAME")
    admin_password: str | None = Field(default=None, alias="ADMIN_PASSWORD")

    # --- App --------------------------------------------------------------
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    # Directory holding the built frontend bundle (served by the API in prod).
    frontend_dist: str = Field(default="frontend/dist", alias="FRONTEND_DIST")

    # --- Ingest tuning ----------------------------------------------------
    ingest_concurrency: int = Field(default=15, alias="INGEST_CONCURRENCY")
    default_backfill_days: int = Field(default=30, alias="DEFAULT_BACKFILL_DAYS")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
