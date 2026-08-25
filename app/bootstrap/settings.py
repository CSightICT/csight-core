"""Environment-backed application settings.

Infrastructure credentials intentionally have no code defaults.  This keeps the
API importable for liveness and test discovery while making readiness fail closed
until a deployment supplies its dependency configuration.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """CSight process configuration loaded from environment variables or ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(default="csight-core-api", min_length=1, validation_alias="APP_NAME")
    app_version: str = Field(default="0.1.0", min_length=1, validation_alias="APP_VERSION")
    environment: str = Field(default="local", min_length=1, validation_alias="ENVIRONMENT")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )
    api_schema_version: str = Field(
        default="1.0", min_length=1, validation_alias="API_SCHEMA_VERSION"
    )

    database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")
    rabbitmq_url: SecretStr | None = Field(default=None, validation_alias="RABBITMQ_URL")

    minio_endpoint: str | None = Field(default=None, validation_alias="MINIO_ENDPOINT")
    minio_access_key: SecretStr | None = Field(default=None, validation_alias="MINIO_ACCESS_KEY")
    minio_secret_key: SecretStr | None = Field(default=None, validation_alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(
        default="csight-evidence", min_length=1, validation_alias="MINIO_BUCKET"
    )
    minio_secure: bool = Field(default=False, validation_alias="MINIO_SECURE")

    llm_provider: str = Field(default="mock", min_length=1, validation_alias="LLM_PROVIDER")
    vision_provider: str = Field(default="mock", min_length=1, validation_alias="VISION_PROVIDER")
    llm_base_url: AnyHttpUrl | None = Field(default=None, validation_alias="LLM_BASE_URL")
    vision_base_url: AnyHttpUrl | None = Field(default=None, validation_alias="VISION_BASE_URL")

    readiness_timeout_seconds: float = Field(
        default=2.0,
        gt=0.0,
        le=30.0,
        validation_alias="READINESS_TIMEOUT_SECONDS",
    )
    database_echo: bool = Field(default=False, validation_alias="DATABASE_ECHO")
    celery_task_max_retries: int = Field(
        default=3, ge=0, le=20, validation_alias="CELERY_TASK_MAX_RETRIES"
    )
    celery_retry_backoff_max_seconds: int = Field(
        default=60,
        ge=1,
        le=3600,
        validation_alias="CELERY_RETRY_BACKOFF_MAX_SECONDS",
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("llm_provider", "vision_provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("minio_endpoint", mode="before")
    @classmethod
    def normalize_minio_endpoint(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().rstrip("/")
            return normalized or None
        return value

    @model_validator(mode="after")
    def validate_related_settings(self) -> Self:
        minio_credentials = (self.minio_access_key, self.minio_secret_key)
        configured_credentials = tuple(
            bool(value and value.get_secret_value()) for value in minio_credentials
        )
        if any(configured_credentials) and not all(configured_credentials):
            raise ValueError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be configured together")
        if any(configured_credentials) and self.minio_endpoint is None:
            raise ValueError("MINIO_ENDPOINT is required when MinIO credentials are configured")
        if self.minio_endpoint is not None and not all(configured_credentials):
            raise ValueError("MinIO credentials are required when MINIO_ENDPOINT is configured")

        if self.llm_provider != "mock" and self.llm_base_url is None:
            raise ValueError("LLM_BASE_URL is required for a non-mock LLM provider")
        if self.vision_provider != "mock" and self.vision_base_url is None:
            raise ValueError("VISION_BASE_URL is required for a non-mock Vision provider")
        return self

    @property
    def database_url_value(self) -> str | None:
        return self.database_url.get_secret_value() if self.database_url is not None else None

    @property
    def rabbitmq_url_value(self) -> str | None:
        return self.rabbitmq_url.get_secret_value() if self.rabbitmq_url is not None else None

    @property
    def minio_access_key_value(self) -> str | None:
        if self.minio_access_key is None:
            return None
        return self.minio_access_key.get_secret_value()

    @property
    def minio_secret_key_value(self) -> str | None:
        if self.minio_secret_key is None:
            return None
        return self.minio_secret_key.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings singleton.

    Tests can call ``get_settings.cache_clear()`` after changing environment
    variables, or inject a ``Settings`` instance into ``create_app`` directly.
    """

    return Settings()
