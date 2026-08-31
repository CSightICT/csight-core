"""Environment-backed application settings.

Infrastructure credentials intentionally have no code defaults.  This keeps the
API importable for liveness and test discovery while making readiness fail closed
until a deployment supplies its dependency configuration.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.platform.tenant import Role

_SUPPORTED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_SUPPORTED_IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp"})


class OidcGroupTargetSettings(BaseModel):
    """Configuration-only admission mapping; local DB roles remain authoritative."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    tenant_slug: str = Field(pattern=r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    allowed_roles: frozenset[Role] = Field(min_length=1)


class SignedIntakeSourceSettings(BaseModel):
    """One deployment-owned integration identity and verification key."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
    tenant_id: UUID
    actor_user_id: UUID
    provenance: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,191}$")
    public_key_file: Path


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
    otel_enabled: bool = Field(default=False, validation_alias="OTEL_ENABLED")
    otel_service_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        validation_alias="OTEL_SERVICE_NAME",
    )
    otel_exporter: Literal["none", "otlp_http"] = Field(
        default="none",
        validation_alias="OTEL_EXPORTER",
    )
    otel_exporter_otlp_endpoint: AnyHttpUrl | None = Field(
        default=None,
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    otel_exporter_otlp_headers: SecretStr | None = Field(
        default=None,
        validation_alias="OTEL_EXPORTER_OTLP_HEADERS",
    )
    otel_trace_sample_ratio: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        validation_alias="OTEL_TRACE_SAMPLE_RATIO",
    )
    otel_export_timeout_seconds: float = Field(
        default=5.0,
        gt=0.0,
        le=30.0,
        validation_alias="OTEL_EXPORT_TIMEOUT_SECONDS",
    )
    otel_metric_export_interval_seconds: float = Field(
        default=30.0,
        ge=5.0,
        le=300.0,
        validation_alias="OTEL_METRIC_EXPORT_INTERVAL_SECONDS",
    )
    api_schema_version: str = Field(
        default="1.0", min_length=1, validation_alias="API_SCHEMA_VERSION"
    )

    database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")
    database_password_file: Path | None = Field(
        default=None,
        validation_alias="DATABASE_PASSWORD_FILE",
    )
    database_runtime_role: Literal["legacy_owner", "api", "worker", "dispatcher", "migration"] = (
        Field(default="legacy_owner", validation_alias="DATABASE_RUNTIME_ROLE")
    )
    database_rls_required: bool = Field(
        default=False,
        validation_alias="DATABASE_RLS_REQUIRED",
    )
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
    legacy_password_auth_enabled: bool | None = Field(
        default=None,
        validation_alias="LEGACY_PASSWORD_AUTH_ENABLED",
    )

    oidc_enabled: bool = Field(default=False, validation_alias="OIDC_ENABLED")
    oidc_provider_key: str = Field(
        default="enterprise",
        min_length=1,
        max_length=64,
        validation_alias="OIDC_PROVIDER_KEY",
    )
    oidc_issuer: AnyHttpUrl | None = Field(default=None, validation_alias="OIDC_ISSUER")
    oidc_client_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
        validation_alias="OIDC_CLIENT_ID",
    )
    oidc_client_secret: SecretStr | None = Field(
        default=None,
        validation_alias="OIDC_CLIENT_SECRET",
    )
    oidc_authorization_endpoint: AnyHttpUrl | None = Field(
        default=None,
        validation_alias="OIDC_AUTHORIZATION_ENDPOINT",
    )
    oidc_token_endpoint: AnyHttpUrl | None = Field(
        default=None,
        validation_alias="OIDC_TOKEN_ENDPOINT",
    )
    oidc_jwks_uri: AnyHttpUrl | None = Field(default=None, validation_alias="OIDC_JWKS_URI")
    oidc_redirect_uri: AnyHttpUrl | None = Field(
        default=None,
        validation_alias="OIDC_REDIRECT_URI",
    )
    oidc_scopes: Annotated[tuple[str, ...], NoDecode] = Field(
        default=("openid", "email", "profile"),
        validation_alias="OIDC_SCOPES",
    )
    oidc_allowed_algorithms: Annotated[tuple[str, ...], NoDecode] = Field(
        default=("RS256",),
        validation_alias="OIDC_ALLOWED_ALGORITHMS",
    )
    oidc_groups_claim: str = Field(
        default="groups",
        min_length=1,
        max_length=255,
        validation_alias="OIDC_GROUPS_CLAIM",
    )
    oidc_group_mappings: dict[str, OidcGroupTargetSettings] = Field(
        default_factory=dict,
        validation_alias="OIDC_GROUP_MAPPINGS",
    )
    oidc_return_path_allowlist: Annotated[tuple[str, ...], NoDecode] = Field(
        default=("/cases", "/reviews"),
        validation_alias="OIDC_RETURN_PATH_ALLOWLIST",
    )
    oidc_connect_timeout_seconds: float = Field(
        default=3.0,
        gt=0,
        le=30,
        validation_alias="OIDC_CONNECT_TIMEOUT_SECONDS",
    )
    oidc_read_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=60,
        validation_alias="OIDC_READ_TIMEOUT_SECONDS",
    )
    oidc_max_response_bytes: int = Field(
        default=1024 * 1024,
        ge=1024,
        le=4 * 1024 * 1024,
        validation_alias="OIDC_MAX_RESPONSE_BYTES",
    )
    oidc_jwks_cache_seconds: int = Field(
        default=300,
        ge=1,
        le=86400,
        validation_alias="OIDC_JWKS_CACHE_SECONDS",
    )
    oidc_clock_skew_seconds: int = Field(
        default=30,
        ge=0,
        le=300,
        validation_alias="OIDC_CLOCK_SKEW_SECONDS",
    )
    oidc_tls_verify: bool = Field(default=True, validation_alias="OIDC_TLS_VERIFY")
    oidc_allow_insecure_http: bool = Field(
        default=False,
        validation_alias="OIDC_ALLOW_INSECURE_HTTP",
    )
    oidc_session_absolute_timeout_seconds: int = Field(
        default=8 * 60 * 60,
        ge=1,
        le=8 * 60 * 60,
        validation_alias="OIDC_SESSION_ABSOLUTE_TIMEOUT_SECONDS",
    )
    oidc_session_idle_timeout_seconds: int = Field(
        default=30 * 60,
        ge=1,
        le=30 * 60,
        validation_alias="OIDC_SESSION_IDLE_TIMEOUT_SECONDS",
    )
    oidc_session_expiry_warning_seconds: int = Field(
        default=5 * 60,
        ge=1,
        le=29 * 60,
        validation_alias="OIDC_SESSION_EXPIRY_WARNING_SECONDS",
    )
    oidc_cookie_name: str = Field(
        default="csight_session",
        pattern=r"^[A-Za-z0-9_-]{1,64}$",
        validation_alias="OIDC_COOKIE_NAME",
    )
    oidc_cookie_secure: bool = Field(default=True, validation_alias="OIDC_COOKIE_SECURE")
    oidc_cookie_same_site: Literal["lax", "strict"] = Field(
        default="lax",
        validation_alias="OIDC_COOKIE_SAME_SITE",
    )

    signed_intake_enabled: bool = Field(
        default=False,
        validation_alias="SIGNED_INTAKE_ENABLED",
    )
    signed_intake_sources: dict[str, SignedIntakeSourceSettings] = Field(
        default_factory=dict,
        validation_alias="SIGNED_INTAKE_SOURCES",
    )
    signed_intake_max_body_bytes: int = Field(
        default=128 * 1024,
        ge=1024,
        le=1024 * 1024,
        validation_alias="SIGNED_INTAKE_MAX_BODY_BYTES",
    )
    signed_intake_clock_skew_seconds: int = Field(
        default=300,
        ge=0,
        le=300,
        validation_alias="SIGNED_INTAKE_CLOCK_SKEW_SECONDS",
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
    evidence_image_sanitization_enabled: bool = Field(
        default=False,
        validation_alias="EVIDENCE_IMAGE_SANITIZATION_ENABLED",
    )
    evidence_malware_scanner: Literal["disabled", "clamav"] = Field(
        default="disabled",
        validation_alias="EVIDENCE_MALWARE_SCANNER",
    )
    clamav_host: str | None = Field(default=None, validation_alias="CLAMAV_HOST")
    clamav_port: int = Field(default=3310, ge=1, le=65535, validation_alias="CLAMAV_PORT")
    clamav_timeout_seconds: float = Field(
        default=10.0,
        gt=0.0,
        le=120.0,
        validation_alias="CLAMAV_TIMEOUT_SECONDS",
    )
    sensitive_payload_retention_policy_version: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        validation_alias="SENSITIVE_PAYLOAD_RETENTION_POLICY_VERSION",
    )
    sensitive_payload_retention_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
        validation_alias="SENSITIVE_PAYLOAD_RETENTION_DAYS",
    )
    privacy_lifecycle_automation_enabled: bool = Field(
        default=False,
        validation_alias="PRIVACY_LIFECYCLE_AUTOMATION_ENABLED",
    )
    privacy_lifecycle_tenant_id: UUID | None = Field(
        default=None,
        validation_alias="PRIVACY_LIFECYCLE_TENANT_ID",
    )
    privacy_lifecycle_interval_seconds: int = Field(
        default=3600,
        ge=60,
        le=86_400,
        validation_alias="PRIVACY_LIFECYCLE_INTERVAL_SECONDS",
    )
    privacy_lifecycle_batch_size: int = Field(
        default=500,
        ge=1,
        le=5000,
        validation_alias="PRIVACY_LIFECYCLE_BATCH_SIZE",
    )
    privacy_lifecycle_max_batches_per_sweep: int = Field(
        default=20,
        ge=1,
        le=100,
        validation_alias="PRIVACY_LIFECYCLE_MAX_BATCHES_PER_SWEEP",
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
    model_release_enforcement: bool = Field(
        default=False,
        validation_alias="MODEL_RELEASE_ENFORCEMENT",
    )
    model_route_enforcement: bool = Field(
        default=False,
        validation_alias="MODEL_ROUTE_ENFORCEMENT",
    )
    model_route_deployment_id: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$",
        validation_alias="MODEL_ROUTE_DEPLOYMENT_ID",
    )
    model_release_signing_public_key_file: Path | None = Field(
        default=None,
        validation_alias="MODEL_RELEASE_SIGNING_PUBLIC_KEY_FILE",
    )
    model_release_signing_key_id: str | None = Field(
        default=None,
        min_length=3,
        max_length=128,
        validation_alias="MODEL_RELEASE_SIGNING_KEY_ID",
    )
    llm_artifact_content_digest: str | None = Field(
        default=None,
        validation_alias="LLM_ARTIFACT_CONTENT_DIGEST",
    )
    llm_runtime_image_digest: str | None = Field(
        default=None,
        validation_alias="LLM_RUNTIME_IMAGE_DIGEST",
    )
    llm_dependency_lock_digest: str | None = Field(
        default=None,
        validation_alias="LLM_DEPENDENCY_LOCK_DIGEST",
    )
    llm_sbom_digest: str | None = Field(
        default=None,
        validation_alias="LLM_SBOM_DIGEST",
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
    provider_circuit_failure_threshold: int = Field(
        default=5,
        ge=1,
        le=100,
        validation_alias="PROVIDER_CIRCUIT_FAILURE_THRESHOLD",
    )
    provider_circuit_open_seconds: float = Field(
        default=30.0,
        gt=0.0,
        le=3600.0,
        validation_alias="PROVIDER_CIRCUIT_OPEN_SECONDS",
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

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator(
        "otel_service_name",
        "otel_exporter_otlp_endpoint",
        "otel_exporter_otlp_headers",
        mode="before",
    )
    @classmethod
    def normalize_optional_otel_value(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("otel_exporter", mode="before")
    @classmethod
    def normalize_otel_exporter(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator(
        "oidc_client_id",
        "oidc_client_secret",
        "oidc_issuer",
        "oidc_authorization_endpoint",
        "oidc_token_endpoint",
        "oidc_jwks_uri",
        "oidc_redirect_uri",
        mode="before",
    )
    @classmethod
    def normalize_optional_oidc_value(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("oidc_provider_key", "oidc_groups_claim", mode="before")
    @classmethod
    def normalize_required_oidc_value(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("oidc_scopes", "oidc_return_path_allowlist", mode="before")
    @classmethod
    def normalize_oidc_csv_tuple(cls, value: object) -> object:
        return _normalized_csv_tuple(value, uppercase=False)

    @field_validator("oidc_allowed_algorithms", mode="before")
    @classmethod
    def normalize_oidc_algorithms(cls, value: object) -> object:
        return _normalized_csv_tuple(value, uppercase=True)

    @field_validator("sensitive_payload_retention_policy_version", mode="before")
    @classmethod
    def normalize_optional_retention_policy_version(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("privacy_lifecycle_tenant_id", mode="before")
    @classmethod
    def normalize_optional_privacy_lifecycle_tenant_id(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("llm_provider", "vision_provider", "evidence_malware_scanner", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("clamav_host", mode="before")
    @classmethod
    def normalize_clamav_host(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
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
        "model_release_signing_key_id",
        "llm_artifact_content_digest",
        "llm_runtime_image_digest",
        "llm_dependency_lock_digest",
        "llm_sbom_digest",
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
        if self.otel_exporter_otlp_headers is not None:
            _parse_otel_headers(self.otel_exporter_otlp_headers.get_secret_value())
        if self.database_rls_required and self.database_runtime_role not in {
            "api",
            "worker",
            "dispatcher",
        }:
            raise ValueError(
                "DATABASE_RLS_REQUIRED requires an api, worker, or dispatcher runtime role"
            )
        if self.database_password_file is not None:
            _ = self.database_url_value
        if self.database_rls_required:
            database_url = self.database_url_value
            if database_url is None or not database_url.startswith("postgresql"):
                raise ValueError("DATABASE_RLS_REQUIRED requires a PostgreSQL DATABASE_URL")
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

        retention_values = (
            self.sensitive_payload_retention_policy_version,
            self.sensitive_payload_retention_days,
        )
        if any(value is not None for value in retention_values) and not all(
            value is not None for value in retention_values
        ):
            raise ValueError(
                "SENSITIVE_PAYLOAD_RETENTION_POLICY_VERSION and "
                "SENSITIVE_PAYLOAD_RETENTION_DAYS must be configured together"
            )
        if self.privacy_lifecycle_automation_enabled:
            if self.privacy_lifecycle_tenant_id is None:
                raise ValueError(
                    "PRIVACY_LIFECYCLE_TENANT_ID is required when retention automation is enabled"
                )
            if not all(value is not None for value in retention_values):
                raise ValueError(
                    "Retention automation requires an explicit "
                    "SENSITIVE_PAYLOAD_RETENTION_POLICY_VERSION and "
                    "SENSITIVE_PAYLOAD_RETENTION_DAYS"
                )
            if self.database_url_value is None:
                raise ValueError("Retention automation requires DATABASE_URL")
            if self.environment not in {"local", "test"} and (
                not self.database_rls_required or self.database_runtime_role != "api"
            ):
                raise ValueError(
                    "Non-local retention automation requires the RLS-enforced API database role"
                )

        if self.jwt_secret_key is not None:
            secret = self.jwt_secret_key.get_secret_value()
            if len(secret.encode("utf-8")) < 32:
                raise ValueError("JWT_SECRET_KEY must contain at least 32 bytes")

        if self.environment not in {"local", "test"} and self.legacy_password_enabled:
            raise ValueError(
                "LEGACY_PASSWORD_AUTH_ENABLED must be false outside local/test environments"
            )

        if self.environment not in {"local", "test"} and self.oidc_allow_insecure_http:
            raise ValueError(
                "OIDC_ALLOW_INSECURE_HTTP may only be enabled in local/test environments"
            )

        if "openid" not in self.oidc_scopes:
            raise ValueError("OIDC_SCOPES must include openid")
        supported_oidc_algorithms = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
        if any(
            algorithm not in supported_oidc_algorithms for algorithm in self.oidc_allowed_algorithms
        ):
            raise ValueError("OIDC_ALLOWED_ALGORITHMS contains an unsupported algorithm")
        if (
            self.oidc_session_idle_timeout_seconds > self.oidc_session_absolute_timeout_seconds
            or self.oidc_session_expiry_warning_seconds >= self.oidc_session_idle_timeout_seconds
        ):
            raise ValueError(
                "OIDC session idle and warning windows must fit within the absolute timeout"
            )
        if any(
            not group or group != group.strip() or len(group) > 512
            for group in self.oidc_group_mappings
        ):
            raise ValueError("OIDC_GROUP_MAPPINGS keys must be bounded non-blank values")
        if self.oidc_redirect_uri is not None:
            redirect = urlsplit(str(self.oidc_redirect_uri))
            if redirect.path != "/auth/oidc/callback" or redirect.query or redirect.fragment:
                raise ValueError("OIDC_REDIRECT_URI must target /auth/oidc/callback exactly")

        if any(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}", key_id) is None
            for key_id in self.signed_intake_sources
        ):
            raise ValueError("SIGNED_INTAKE_SOURCES contains an invalid key identifier")
        source_ids = [source.source_id for source in self.signed_intake_sources.values()]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("SIGNED_INTAKE_SOURCES source_id values must be unique")
        if self.signed_intake_enabled:
            if self.database_url_value is None or not self.signed_intake_sources:
                raise ValueError(
                    "SIGNED_INTAKE_ENABLED requires DATABASE_URL and SIGNED_INTAKE_SOURCES"
                )
            if not all(value is not None for value in retention_values):
                raise ValueError(
                    "SIGNED_INTAKE_ENABLED requires an explicit sensitive payload retention policy"
                )
            if self.environment not in {"local", "test"} and (
                not self.database_rls_required or self.database_runtime_role != "api"
            ):
                raise ValueError(
                    "Non-local signed intake requires the RLS-enforced API database role"
                )

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
        if self.evidence_malware_scanner == "clamav" and self.clamav_host is None:
            raise ValueError("CLAMAV_HOST is required when EVIDENCE_MALWARE_SCANNER=clamav")

        if self.llm_provider in {"vllm", "mlx"} and self.llm_base_url is None:
            raise ValueError("LLM_BASE_URL is required for a remote HTTP LLM provider")
        release_key_values = (
            self.model_release_signing_public_key_file,
            self.model_release_signing_key_id,
        )
        if any(value is not None for value in release_key_values) and not all(
            value is not None for value in release_key_values
        ):
            raise ValueError(
                "MODEL_RELEASE_SIGNING_PUBLIC_KEY_FILE and MODEL_RELEASE_SIGNING_KEY_ID "
                "must be configured together"
            )
        if (
            self.llm_provider == "vllm"
            and self.environment not in {"local", "test"}
            and not self.model_release_enforcement
        ):
            raise ValueError("Non-local vLLM requires MODEL_RELEASE_ENFORCEMENT=true")
        if self.model_release_enforcement:
            required_release_identity = (
                self.database_url_value,
                self.model_release_signing_public_key_file,
                self.model_release_signing_key_id,
                self.llm_model_revision,
                self.llm_artifact_content_digest,
                self.llm_runtime_image_digest,
                self.llm_dependency_lock_digest,
                self.llm_sbom_digest,
            )
            if self.llm_provider != "vllm" or not all(required_release_identity):
                raise ValueError(
                    "MODEL_RELEASE_ENFORCEMENT requires vLLM, PostgreSQL, a signing key, "
                    "an exact model revision, and all runtime content digests"
                )
            if not str(self.database_url_value).startswith("postgresql"):
                raise ValueError("MODEL_RELEASE_ENFORCEMENT requires PostgreSQL")
            if self.llm_model_revision is None or not _is_lower_hex(self.llm_model_revision, 40):
                raise ValueError("LLM_MODEL_REVISION must be an exact 40-character commit hash")
            for digest in (
                self.llm_artifact_content_digest,
                self.llm_runtime_image_digest,
                self.llm_dependency_lock_digest,
                self.llm_sbom_digest,
            ):
                if digest is None or not _is_sha256_digest(digest):
                    raise ValueError("Model release digests must use sha256:<64 lowercase hex>")
        if self.model_route_deployment_id is not None and not self.model_route_enforcement:
            raise ValueError(
                "MODEL_ROUTE_DEPLOYMENT_ID may only be set when MODEL_ROUTE_ENFORCEMENT=true"
            )
        if self.model_route_enforcement:
            if not self.model_release_enforcement:
                raise ValueError("MODEL_ROUTE_ENFORCEMENT requires MODEL_RELEASE_ENFORCEMENT=true")
            if self.database_runtime_role not in {"api", "worker"}:
                raise ValueError("MODEL_ROUTE_ENFORCEMENT requires the API or Worker database role")
            if self.environment not in {"local", "test"} and not self.database_rls_required:
                raise ValueError(
                    "Non-local MODEL_ROUTE_ENFORCEMENT requires DATABASE_RLS_REQUIRED=true"
                )
            if self.database_runtime_role == "worker" and self.model_route_deployment_id is None:
                raise ValueError(
                    "Worker MODEL_ROUTE_ENFORCEMENT requires MODEL_ROUTE_DEPLOYMENT_ID"
                )
            if self.database_runtime_role == "api" and self.model_route_deployment_id is not None:
                raise ValueError("The API process must not receive MODEL_ROUTE_DEPLOYMENT_ID")
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
        if self.database_url is None:
            if self.database_password_file is not None:
                raise ValueError("DATABASE_PASSWORD_FILE requires DATABASE_URL")
            return None

        database_url = self.database_url.get_secret_value()
        if self.database_password_file is None:
            return database_url

        parsed_url = make_url(database_url)
        if parsed_url.password is not None:
            raise ValueError(
                "DATABASE_URL must omit its password when DATABASE_PASSWORD_FILE is configured"
            )
        try:
            password = self.database_password_file.read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as exc:
            raise ValueError("DATABASE_PASSWORD_FILE cannot be read") from exc
        if not password or "\n" in password or "\r" in password:
            raise ValueError("DATABASE_PASSWORD_FILE must contain exactly one non-empty line")
        if len(password.encode("utf-8")) > 4096:
            raise ValueError("DATABASE_PASSWORD_FILE exceeds the 4096-byte limit")
        return parsed_url.set(password=password).render_as_string(hide_password=False)

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
    def legacy_password_enabled(self) -> bool:
        if self.legacy_password_auth_enabled is not None:
            return self.legacy_password_auth_enabled
        return self.environment in {"local", "test"}

    @property
    def oidc_client_secret_value(self) -> str | None:
        if self.oidc_client_secret is None:
            return None
        return self.oidc_client_secret.get_secret_value()

    @property
    def oidc_configuration_missing(self) -> tuple[str, ...]:
        candidates: list[tuple[str, object | None]] = [
            ("OIDC_ENABLED=true", self.oidc_enabled or None),
            ("DATABASE_URL", self.database_url_value),
            ("OIDC_ISSUER", self.oidc_issuer),
            ("OIDC_CLIENT_ID", self.oidc_client_id),
            ("OIDC_AUTHORIZATION_ENDPOINT", self.oidc_authorization_endpoint),
            ("OIDC_TOKEN_ENDPOINT", self.oidc_token_endpoint),
            ("OIDC_JWKS_URI", self.oidc_jwks_uri),
            ("OIDC_REDIRECT_URI", self.oidc_redirect_uri),
            ("OIDC_GROUP_MAPPINGS", self.oidc_group_mappings or None),
        ]
        if self.environment not in {"local", "test"}:
            candidates.extend(
                (
                    ("OIDC_TLS_VERIFY=true", self.oidc_tls_verify or None),
                    ("OIDC_COOKIE_SECURE=true", self.oidc_cookie_secure or None),
                )
            )
        configured_urls = (
            self.oidc_issuer,
            self.oidc_authorization_endpoint,
            self.oidc_token_endpoint,
            self.oidc_jwks_uri,
            self.oidc_redirect_uri,
        )
        if any(url is not None and url.scheme != "https" for url in configured_urls) and not (
            self.environment in {"local", "test"} and self.oidc_allow_insecure_http
        ):
            candidates.append(("OIDC_HTTPS_ENDPOINTS", None))
        return tuple(name for name, value in candidates if not value)

    @property
    def oidc_is_configured(self) -> bool:
        return not self.oidc_configuration_missing

    @property
    def signed_intake_configuration_missing(self) -> tuple[str, ...]:
        candidates: list[tuple[str, object | None]] = [
            ("SIGNED_INTAKE_ENABLED=true", self.signed_intake_enabled or None),
            ("DATABASE_URL", self.database_url_value),
            ("SIGNED_INTAKE_SOURCES", self.signed_intake_sources or None),
            (
                "SENSITIVE_PAYLOAD_RETENTION_POLICY_VERSION",
                self.sensitive_payload_retention_policy_version_value,
            ),
            (
                "SENSITIVE_PAYLOAD_RETENTION_DAYS",
                self.sensitive_payload_retention_days_value,
            ),
        ]
        return tuple(name for name, value in candidates if not value)

    @property
    def signed_intake_is_configured(self) -> bool:
        return not self.signed_intake_configuration_missing

    @property
    def otel_service_name_value(self) -> str:
        return self.otel_service_name or self.app_name

    @property
    def otel_exporter_otlp_endpoint_value(self) -> str | None:
        if self.otel_exporter_otlp_endpoint is None:
            return None
        return str(self.otel_exporter_otlp_endpoint).rstrip("/")

    @property
    def otel_exporter_otlp_headers_value(self) -> dict[str, str]:
        if self.otel_exporter_otlp_headers is None:
            return {}
        return _parse_otel_headers(self.otel_exporter_otlp_headers.get_secret_value())

    @property
    def otel_configuration_missing(self) -> tuple[str, ...]:
        candidates = (
            ("OTEL_ENABLED=true", self.otel_enabled),
            ("OTEL_EXPORTER=otlp_http", self.otel_exporter == "otlp_http"),
            ("OTEL_EXPORTER_OTLP_ENDPOINT", self.otel_exporter_otlp_endpoint),
        )
        return tuple(name for name, value in candidates if not value)

    @property
    def otel_is_configured(self) -> bool:
        return not self.otel_configuration_missing

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

    @property
    def sensitive_payload_retention_policy_version_value(self) -> str | None:
        if self.sensitive_payload_retention_policy_version is not None:
            return self.sensitive_payload_retention_policy_version
        if self.environment in {"local", "test"}:
            return "development/30d"
        return None

    @property
    def sensitive_payload_retention_days_value(self) -> int | None:
        if self.sensitive_payload_retention_days is not None:
            return self.sensitive_payload_retention_days
        if self.environment in {"local", "test"}:
            return 30
        return None


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


def _parse_otel_headers(value: str) -> dict[str, str]:
    """Parse bounded comma-separated OTLP headers without ever logging the input."""

    parsed: dict[str, str] = {}
    for candidate in value.split(","):
        key, separator, header_value = candidate.partition("=")
        normalized_key = key.strip()
        normalized_value = header_value.strip()
        if (
            not separator
            or not normalized_key
            or not normalized_value
            or len(normalized_key) > 128
            or len(normalized_value) > 2048
            or not normalized_key.replace("-", "").replace("_", "").isalnum()
            or "\n" in normalized_value
            or "\r" in normalized_value
        ):
            raise ValueError("OTEL_EXPORTER_OTLP_HEADERS contains an invalid header")
        if normalized_key.casefold() in {key.casefold() for key in parsed}:
            raise ValueError("OTEL_EXPORTER_OTLP_HEADERS contains a duplicate header")
        parsed[normalized_key] = normalized_value
    if not parsed:
        raise ValueError("OTEL_EXPORTER_OTLP_HEADERS must not be empty")
    return parsed


def _normalized_csv_tuple(value: object, *, uppercase: bool) -> tuple[str, ...]:
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, (list, tuple)):
        candidates = value
    else:
        return value  # type: ignore[return-value]
    normalized = tuple(
        str(candidate).strip().upper() if uppercase else str(candidate).strip()
        for candidate in candidates
        if str(candidate).strip()
    )
    if not normalized or len(normalized) != len(set(normalized)):
        raise ValueError("OIDC list settings must be non-empty and unique")
    return normalized


def _is_lower_hex(value: str, length: int) -> bool:
    return len(value) == length and all(character in "0123456789abcdef" for character in value)


def _is_sha256_digest(value: str) -> bool:
    prefix, separator, digest = value.partition(":")
    return separator == ":" and prefix == "sha256" and _is_lower_hex(digest, 64)
