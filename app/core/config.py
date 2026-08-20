from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRET_KEY = "change-me-in-production-to-a-random-32-byte-string"
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str | None = None
    secret_key: Annotated[str, Field(min_length=MIN_SECRET_KEY_LENGTH)]
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    docs_enabled: bool = True
    hsts_enabled: bool = False
    login_rate_limit: str = "10/minute"
    register_rate_limit: str = "5/minute"

    service_name: str = "fastapi-template"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    log_file: str | None = None
    request_log_excluded_paths: str = "/health,/health/ready,/metrics"

    @field_validator("secret_key")
    @classmethod
    def reject_placeholder_secret_key(cls, value: str) -> str:
        if value == PLACEHOLDER_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY is still the .env.example placeholder; "
                "generate a real one with: openssl rand -hex 32"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
