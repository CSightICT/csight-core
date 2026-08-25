"""Settings validation and secret-handling tests."""

import pytest
from pydantic import SecretStr, ValidationError

from app.bootstrap.settings import Settings

pytestmark = pytest.mark.unit


def test_defaults_use_mock_providers_without_infrastructure_secrets() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.llm_provider == "mock"
    assert settings.vision_provider == "mock"
    assert settings.database_url is None
    assert settings.rabbitmq_url is None
    assert settings.jwt_secret_key is None
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_access_token_expire_minutes == 30
    assert settings.development_seed_enabled is False
    assert settings.development_seed_admin_password is None
    assert settings.development_seed_reviewer_password is None
    assert settings.development_seed_quality_viewer_password is None
    assert settings.minio_access_key is None
    assert settings.minio_secret_key is None
    assert settings.minio_region == "us-east-1"
    assert settings.minio_presigned_endpoint_value is None
    assert settings.minio_presigned_secure_value is False
    assert settings.signed_url_ttl_seconds == 900
    assert settings.max_upload_bytes == 10 * 1024 * 1024
    assert settings.allowed_image_mime_types == {"image/jpeg", "image/png", "image/webp"}
    assert settings.allowed_image_extensions == {"jpg", "jpeg", "png", "webp"}
    assert settings.max_image_pixels == 40_000_000


def test_settings_normalize_environment_values_and_hide_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "warning")
    monkeypatch.setenv("LLM_PROVIDER", " MOCK ")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:password@db:5432/csight")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.log_level == "WARNING"
    assert settings.llm_provider == "mock"
    assert settings.database_url_value is not None
    assert "user:password" not in repr(settings)


def test_jwt_settings_normalize_and_hide_secret() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        jwt_secret_key=SecretStr("a-random-local-secret-with-at-least-32-bytes"),
        jwt_algorithm="hs256",
        jwt_issuer=" csight-test ",
        jwt_audience=" csight-clients ",
    )

    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_issuer == "csight-test"
    assert settings.jwt_audience == "csight-clients"
    assert settings.jwt_secret_key_value == "a-random-local-secret-with-at-least-32-bytes"
    assert "a-random-local-secret" not in repr(settings)


def test_short_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            jwt_secret_key=SecretStr("too-short"),
        )


def test_development_seed_passwords_are_redacted() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        development_seed_admin_password=SecretStr("a" * 16),
        development_seed_reviewer_password=SecretStr("r" * 16),
        development_seed_quality_viewer_password=SecretStr("q" * 16),
    )

    rendered = repr(settings)
    assert "a" * 16 not in rendered
    assert "r" * 16 not in rendered
    assert "q" * 16 not in rendered


def test_partial_minio_credentials_are_rejected() -> None:
    with pytest.raises(ValidationError, match="configured together"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            minio_endpoint="minio:9000",
            minio_access_key=SecretStr("access-only"),
        )


def test_presigned_endpoint_can_differ_from_internal_endpoint() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        minio_endpoint=" minio:9000/ ",
        minio_presigned_endpoint=" evidence.example.test:443/ ",
        minio_access_key=SecretStr("access"),
        minio_secret_key=SecretStr("secret"),
        minio_secure=False,
        minio_presigned_secure=True,
    )

    assert settings.minio_endpoint == "minio:9000"
    assert settings.minio_presigned_endpoint_value == "evidence.example.test:443"
    assert settings.minio_presigned_secure_value is True


def test_presigned_endpoint_requires_internal_minio_configuration() -> None:
    with pytest.raises(ValidationError, match="MINIO_ENDPOINT"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            minio_presigned_endpoint="evidence.example.test:443",
        )


def test_minio_endpoint_rejects_url_schemes() -> None:
    with pytest.raises(ValidationError, match="without a scheme"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            minio_endpoint="http://minio:9000",
            minio_access_key=SecretStr("access"),
            minio_secret_key=SecretStr("secret"),
        )


def test_upload_limits_are_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            max_upload_bytes=0,
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            max_image_pixels=178_956_971,
        )


def test_image_allowlists_are_normalized_and_reject_unsupported_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOWED_IMAGE_MIME_TYPES", " IMAGE/PNG ")
    monkeypatch.setenv("ALLOWED_IMAGE_EXTENSIONS", " .PNG ")
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.allowed_image_mime_types == {"image/png"}
    assert settings.allowed_image_extensions == {"png"}
    with pytest.raises(ValidationError, match="JPEG, PNG, and WebP"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            allowed_image_mime_types="image/svg+xml",
        )


def test_non_mock_provider_requires_base_url() -> None:
    with pytest.raises(ValidationError, match="LLM_BASE_URL"):
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            llm_provider="vllm",
        )
