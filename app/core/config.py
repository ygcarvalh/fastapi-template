from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRET_KEY = "change-me-in-production-to-a-random-32-byte-string"
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str | None = None
    # pool_size + max_overflow, multiplied by the number of worker processes,
    # must stay under PostgreSQL's max_connections.
    db_pool_size: Annotated[int, Field(gt=0)] = 5
    db_max_overflow: Annotated[int, Field(gt=0)] = 10
    db_pool_recycle: Annotated[int, Field(gt=0)] = 1800
    secret_key: Annotated[str, Field(min_length=MIN_SECRET_KEY_LENGTH)]
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    impersonation_token_expire_minutes: int = 30

    docs_enabled: bool = True
    cors_origins: str = ""
    max_request_body_bytes: Annotated[int, Field(gt=0)] = 8 * 1024 * 1024
    hsts_enabled: bool = False
    rate_limit_storage_uri: str = ""
    login_rate_limit: str = "10/minute"
    register_rate_limit: str = "5/minute"
    mail_rate_limit: str = "5/hour"

    service_name: str = "fastapi-template"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    log_file: str | None = None
    metrics_enabled: bool = True
    tracing_enabled: bool = True
    otlp_endpoint: str = ""
    request_log_excluded_paths: str = "/health,/health/ready,/metrics"
    request_log_persist_enabled: bool = True
    feature_flags: str = "items,request-log,audit-log"
    audit_log_retention_days: int = 365
    request_log_retention_days: int = 30
    jobs_enabled: bool = True
    jobs_startup_delay_seconds: Annotated[int, Field(ge=0)] = 30
    idempotency_enabled: bool = True
    idempotency_retention_hours: Annotated[int, Field(gt=0)] = 24
    idempotency_in_flight_timeout_seconds: Annotated[int, Field(gt=0)] = 60

    app_base_url: str = "http://localhost:4200"
    storage_root: str = "var/uploads"
    max_attachment_bytes: Annotated[int, Field(gt=0)] = 5 * 1024 * 1024
    attachment_content_types: str = (
        "image/png,image/jpeg,image/webp,application/pdf,text/plain"
    )
    mail_backend: Literal["log", "smtp"] = "log"
    mail_from: str = "no-reply@example.com"
    smtp_host: str = "localhost"
    smtp_port: Annotated[int, Field(gt=0, le=65535)] = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    email_verification_expire_hours: Annotated[int, Field(gt=0)] = 48
    mail_resend_cooldown_seconds: Annotated[int, Field(ge=0)] = 60
    password_reset_expire_minutes: Annotated[int, Field(gt=0)] = 60
    require_verified_email: bool = False
    demo_data_enabled: bool = False

    @property
    def attachment_type_set(self) -> frozenset[str]:
        return frozenset(
            entry.strip()
            for entry in self.attachment_content_types.split(",")
            if entry.strip()
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @field_validator("cors_origins")
    @classmethod
    def reject_wildcard_origin(cls, value: str) -> str:
        if "*" in value:
            raise ValueError(
                "CORS_ORIGINS takes named origins only; '*' would let any site "
                "call the API with a stolen token"
            )
        return value

    @model_validator(mode="after")
    def refuse_an_upload_ceiling_the_body_limit_would_cut(self) -> "Settings":
        if self.max_attachment_bytes > self.max_request_body_bytes:
            raise ValueError(
                "MAX_ATTACHMENT_BYTES is above MAX_REQUEST_BODY_BYTES, so an upload "
                "the attachment limit allows would be refused as a body that is too "
                "large. Raise MAX_REQUEST_BODY_BYTES above it."
            )
        return self

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
