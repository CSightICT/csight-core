"""Environment-backed application settings.

Infrastructure credentials intentionally have no code defaults.  This keeps the
API importable for liveness and test discovery while making readiness fail closed
until a deployment supplies its dependency configuration.
"""

from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_SUPPORTED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_SUPPORTED_IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp"})


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

    jwt_secret_key: SecretStr | None = Field(default=None, validation_alias="JWT_SECRET_KEY")
    jwt_algorithm: Literal["HS256"] = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    jwt_issuer: str = Field(
        default="csight-core", min_length=1, max_length=255, validation_alias="JWT_ISSUER"
    )
    jwt_audience: str = Field(
        default="csight-api", min_length=1, max_length=255, validation_alias="JWT_AUDIENCE"
    )
    jwt_access_token_expire_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,
        validation_alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    )

    development_seed_enabled: bool = Field(
        default=False,
        validation_alias="DEVELOPMENT_SEED_ENABLED",
    )
    development_seed_admin_password: SecretStr | None = Field(
        default=None,
        validation_alias="DEVELOPMENT_SEED_ADMIN_PASSWORD",
    )
    development_seed_reviewer_password: SecretStr | None = Field(
        default=None,
        validation_alias="DEVELOPMENT_SEED_REVIEWER_PASSWORD",
    )
    development_seed_quality_viewer_password: SecretStr | None = Field(
        default=None,
        validation_alias="DEVELOPMENT_SEED_QUALITY_VIEWER_PASSWORD",
    )

    minio_endpoint: str | None = Field(default=None, validation_alias="MINIO_ENDPOINT")
    minio_presigned_endpoint: str | None = Field(
        default=None, validation_alias="MINIO_PRESIGNED_ENDPOINT"
    )
    minio_access_key: SecretStr | None = Field(default=None, validation_alias="MINIO_ACCESS_KEY")
    minio_secret_key: SecretStr | None = Field(default=None, validation_alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(
        default="csight-evidence", min_length=1, max_length=63, validation_alias="MINIO_BUCKET"
    )
    minio_region: str = Field(
        default="us-east-1", min_length=1, max_length=255, validation_alias="MINIO_REGION"
    )
    minio_secure: bool = Field(default=False, validation_alias="MINIO_SECURE")
    minio_presigned_secure: bool | None = Field(
        default=None, validation_alias="MINIO_PRESIGNED_SECURE"
    )
    signed_url_ttl_seconds: int = Field(
        default=900,
        ge=1,
        le=604800,
        validation_alias="SIGNED_URL_TTL_SECONDS",
    )

    max_upload_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1,
        le=100 * 1024 * 1024,
        validation_alias="MAX_UPLOAD_BYTES",
    )
    allowed_image_mime_types: Annotated[frozenset[str], NoDecode] = Field(
        default=_SUPPORTED_IMAGE_MIME_TYPES,
        validation_alias="ALLOWED_IMAGE_MIME_TYPES",
    )
    allowed_image_extensions: Annotated[frozenset[str], NoDecode] = Field(
        default=_SUPPORTED_IMAGE_EXTENSIONS,
        validation_alias="ALLOWED_IMAGE_EXTENSIONS",
    )
    max_image_pixels: int = Field(
        default=40_000_000,
        ge=1,
        le=178_956_970,
        validation_alias="MAX_IMAGE_PIXELS",
    )

    llm_provider: Literal["mock", "vllm", "mlx"] = Field(
        default="mock",
        validation_alias="LLM_PROVIDER",
    )
    vision_provider: Literal["mock", "remote"] = Field(
        default="mock", validation_alias="VISION_PROVIDER"
    )
    vision_mock_mode: Literal[
        "success_single_defect",
        "success_multiple_defects",
        "no_defect",
        "low_quality_image",
        "empty_detections",
        "timeout",
        "transient_error",
        "permanent_error",
        "invalid_schema",
        "invalid_geometry",
        "binary_candidate",
        "binary_below_threshold",
    ] = Field(default="success_single_defect", validation_alias="VISION_MOCK_MODE")
    vision_task: Literal[
        "QUALITY_CHECK",
        "DEFECT_DETECTION",
        "QUALITY_AND_DEFECT_DETECTION",
        "ANY_DEFECT_CLASSIFICATION",
    ] = Field(
        default="QUALITY_AND_DEFECT_DETECTION",
        validation_alias="VISION_TASK",
    )
    vision_assessment_expected_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        validation_alias="VISION_ASSESSMENT_EXPECTED_THRESHOLD",
    )
    llm_base_url: AnyHttpUrl | None = Field(default=None, validation_alias="LLM_BASE_URL")
    llm_api_key: SecretStr | None = Field(default=None, validation_alias="LLM_API_KEY")
    llm_model_id: str = Field(
        default="csight-mock-llm",
        min_length=1,
        max_length=255,
        validation_alias="LLM_MODEL_ID",
    )
    llm_model_version: str = Field(
        default="0.1.0",
        min_length=1,
        max_length=100,
        validation_alias="LLM_MODEL_VERSION",
    )
    llm_model_revision: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        validation_alias="LLM_MODEL_REVISION",
    )
    llm_connect_timeout_seconds: float = Field(
        default=5.0,
        gt=0.0,
        le=60.0,
        validation_alias="LLM_CONNECT_TIMEOUT_SECONDS",
    )
    llm_read_timeout_seconds: float = Field(
        default=120.0,
        gt=0.0,
        le=900.0,
        validation_alias="LLM_READ_TIMEOUT_SECONDS",
    )
    llm_max_output_tokens: int = Field(
        default=1024,
        ge=1,
        le=32768,
        validation_alias="LLM_MAX_OUTPUT_TOKENS",
    )
    llm_max_output_chars: int = Field(
        default=20_000,
        ge=256,
        le=1_000_000,
        validation_alias="LLM_MAX_OUTPUT_CHARS",
    )
    llm_max_input_chars: int = Field(
        default=20_000,
        ge=1,
        le=1_000_000,
        validation_alias="LLM_MAX_INPUT_CHARS",
    )
    llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        validation_alias="LLM_TEMPERATURE",
    )
    llm_tls_verify: bool = Field(default=True, validation_alias="LLM_TLS_VERIFY")
    vision_base_url: AnyHttpUrl | None = Field(default=None, validation_alias="VISION_BASE_URL")
    vision_api_key: SecretStr | None = Field(default=None, validation_alias="VISION_API_KEY")
    vision_model_id: str = Field(
        default="csight-mock-vision",
        min_length=1,
        max_length=255,
        validation_alias="VISION_MODEL_ID",
    )
    vision_model_version: str = Field(
        default="0.1.0",
        min_length=1,
        max_length=100,
        validation_alias="VISION_MODEL_VERSION",
    )
    vision_model_revision: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        validation_alias="VISION_MODEL_REVISION",
    )
    vision_connect_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=60,
        validation_alias="VISION_CONNECT_TIMEOUT_SECONDS",
    )
    vision_read_timeout_seconds: float = Field(
        default=120.0,
        gt=0,
        le=900,
        validation_alias="VISION_READ_TIMEOUT_SECONDS",
    )
    vision_max_image_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1,
        le=100 * 1024 * 1024,
        validation_alias="VISION_MAX_IMAGE_BYTES",
    )
    vision_tls_verify: bool = Field(default=True, validation_alias="VISION_TLS_VERIFY")
    embedding_base_url: AnyHttpUrl | None = Field(
        default=None, validation_alias="EMBEDDING_BASE_URL"
    )
    embedding_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        le=300.0,
        validation_alias="EMBEDDING_TIMEOUT_SECONDS",
    )
    reranker_base_url: AnyHttpUrl | None = Field(default=None, validation_alias="RERANKER_BASE_URL")
    reranker_timeout_seconds: float = Field(
        default=120.0,
        gt=0.0,
        le=900.0,
        validation_alias="RERANKER_TIMEOUT_SECONDS",
    )

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
    analysis_task_soft_time_limit_seconds: int = Field(
        default=150,
        ge=1,
        le=3600,
        validation_alias="ANALYSIS_TASK_SOFT_TIME_LIMIT_SECONDS",
    )
    analysis_task_hard_time_limit_seconds: int = Field(
        default=180,
        ge=2,
        le=7200,
        validation_alias="ANALYSIS_TASK_HARD_TIME_LIMIT_SECONDS",
    )
    analysis_stage_lease_seconds: int = Field(
        default=300,
        ge=3,
        le=86400,
        validation_alias="ANALYSIS_STAGE_LEASE_SECONDS",
    )
    analysis_outbox_poll_interval_seconds: float = Field(
        default=1.0,
        gt=0.0,
        le=60.0,
        validation_alias="ANALYSIS_OUTBOX_POLL_INTERVAL_SECONDS",
    )
    analysis_outbox_batch_size: int = Field(
        default=100,
        ge=1,
        le=1000,
        validation_alias="ANALYSIS_OUTBOX_BATCH_SIZE",
    )
    analysis_outbox_claim_seconds: int = Field(
        default=30,
        ge=1,
        le=3600,
        validation_alias="ANALYSIS_OUTBOX_CLAIM_SECONDS",
    )
    analysis_outbox_max_attempts: int = Field(
        default=10,
        ge=1,
        le=100,
        validation_alias="ANALYSIS_OUTBOX_MAX_ATTEMPTS",
    )
    analysis_outbox_retry_base_seconds: float = Field(
        default=1.0,
        gt=0.0,
        le=3600.0,
        validation_alias="ANALYSIS_OUTBOX_RETRY_BASE_SECONDS",
    )
    analysis_outbox_retry_max_seconds: float = Field(
        default=60.0,
        gt=0.0,
        le=86400.0,
        validation_alias="ANALYSIS_OUTBOX_RETRY_MAX_SECONDS",
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

    @field_validator("vision_task", mode="before")
    @classmethod
    def normalize_vision_task(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("vision_assessment_expected_threshold", mode="before")
    @classmethod
    def normalize_optional_threshold(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "llm_model_id",
        "llm_model_version",
        "vision_model_id",
        "vision_model_version",
        mode="before",
    )
    @classmethod
    def normalize_required_llm_identity(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator(
        "llm_model_revision",
        "llm_api_key",
        "vision_model_revision",
        "vision_api_key",
        mode="before",
    )
    @classmethod
    def normalize_optional_llm_identity(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("jwt_algorithm", mode="before")
    @classmethod
    def normalize_jwt_algorithm(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("jwt_issuer", "jwt_audience", "minio_region", mode="before")
    @classmethod
    def normalize_named_setting(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("allowed_image_mime_types", mode="before")
    @classmethod
    def normalize_allowed_image_mime_types(cls, value: object) -> object:
        normalized = _normalized_csv_values(value, strip_dot=False)
        unsupported = normalized - _SUPPORTED_IMAGE_MIME_TYPES
        if unsupported:
            raise ValueError("Only JPEG, PNG, and WebP MIME types are supported")
        return normalized

    @field_validator("allowed_image_extensions", mode="before")
    @classmethod
    def normalize_allowed_image_extensions(cls, value: object) -> object:
        normalized = _normalized_csv_values(value, strip_dot=True)
        unsupported = normalized - _SUPPORTED_IMAGE_EXTENSIONS
        if unsupported:
            raise ValueError("Only jpg, jpeg, png, and webp extensions are supported")
        return normalized

    @field_validator("minio_endpoint", "minio_presigned_endpoint", mode="before")
    @classmethod
    def normalize_minio_endpoint(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().rstrip("/")
            if "://" in normalized:
                raise ValueError(
                    "MinIO endpoints must be configured as host[:port] without a scheme"
                )
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
        if self.minio_presigned_endpoint is not None and self.minio_endpoint is None:
            raise ValueError(
                "MINIO_ENDPOINT is required when MINIO_PRESIGNED_ENDPOINT is configured"
            )

        if self.jwt_secret_key is not None:
            secret = self.jwt_secret_key.get_secret_value()
            if len(secret.encode("utf-8")) < 32:
                raise ValueError("JWT_SECRET_KEY must contain at least 32 bytes")

        configured_formats = {
            "jpeg": "image/jpeg" in self.allowed_image_mime_types
            and bool({"jpg", "jpeg"} & self.allowed_image_extensions),
            "png": "image/png" in self.allowed_image_mime_types
            and "png" in self.allowed_image_extensions,
            "webp": "image/webp" in self.allowed_image_mime_types
            and "webp" in self.allowed_image_extensions,
        }
        if not any(configured_formats.values()):
            raise ValueError(
                "ALLOWED_IMAGE_MIME_TYPES and ALLOWED_IMAGE_EXTENSIONS must share a format"
            )

        if self.llm_provider in {"vllm", "mlx"} and self.llm_base_url is None:
            raise ValueError("LLM_BASE_URL is required for a remote HTTP LLM provider")
        if self.vision_provider != "mock" and self.vision_base_url is None:
            raise ValueError("VISION_BASE_URL is required for a non-mock Vision provider")
        binary_mock = self.vision_provider == "mock" and self.vision_mock_mode in {
            "binary_candidate",
            "binary_below_threshold",
        }
        any_defect_task = self.vision_task == "ANY_DEFECT_CLASSIFICATION"
        if self.vision_provider == "mock" and binary_mock is not any_defect_task:
            raise ValueError(
                "VISION_MOCK_MODE and VISION_TASK must describe the same Vision contract"
            )
        binary_remote = self.vision_provider == "remote" and any_defect_task
        if (binary_mock or binary_remote) and self.vision_assessment_expected_threshold is None:
            raise ValueError(
                "VISION_ASSESSMENT_EXPECTED_THRESHOLD is required for any-defect assessment"
            )
        if not (
            self.analysis_stage_lease_seconds
            > self.analysis_task_hard_time_limit_seconds
            > self.analysis_task_soft_time_limit_seconds
        ):
            raise ValueError(
                "ANALYSIS_STAGE_LEASE_SECONDS must be greater than "
                "ANALYSIS_TASK_HARD_TIME_LIMIT_SECONDS, which must be greater than "
                "ANALYSIS_TASK_SOFT_TIME_LIMIT_SECONDS"
            )
        if self.analysis_outbox_retry_max_seconds < self.analysis_outbox_retry_base_seconds:
            raise ValueError(
                "ANALYSIS_OUTBOX_RETRY_MAX_SECONDS must be greater than or equal to "
                "ANALYSIS_OUTBOX_RETRY_BASE_SECONDS"
            )
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

    @property
    def jwt_secret_key_value(self) -> str | None:
        if self.jwt_secret_key is None:
            return None
        return self.jwt_secret_key.get_secret_value()

    @property
    def llm_api_key_value(self) -> str | None:
        if self.llm_api_key is None:
            return None
        return self.llm_api_key.get_secret_value()

    @property
    def llm_base_url_value(self) -> str | None:
        if self.llm_base_url is None:
            return None
        return str(self.llm_base_url).rstrip("/")

    @property
    def vision_api_key_value(self) -> str | None:
        if self.vision_api_key is None:
            return None
        return self.vision_api_key.get_secret_value()

    @property
    def vision_base_url_value(self) -> str | None:
        if self.vision_base_url is None:
            return None
        return str(self.vision_base_url).rstrip("/")

    @property
    def minio_presigned_endpoint_value(self) -> str | None:
        return self.minio_presigned_endpoint or self.minio_endpoint

    @property
    def minio_presigned_secure_value(self) -> bool:
        if self.minio_presigned_secure is None:
            return self.minio_secure
        return self.minio_presigned_secure


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process settings singleton.

    Tests can call ``get_settings.cache_clear()`` after changing environment
    variables, or inject a ``Settings`` instance into ``create_app`` directly.
    """

    return Settings()


def _normalized_csv_values(value: object, *, strip_dot: bool) -> frozenset[str]:
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, (set, frozenset, list, tuple)):
        candidates = value
    else:
        return value  # type: ignore[return-value]
    normalized = frozenset(
        str(candidate).strip().lower().lstrip("." if strip_dot else "")
        for candidate in candidates
        if str(candidate).strip()
    )
    if not normalized:
        raise ValueError("At least one allowed image value is required")
    return normalized
