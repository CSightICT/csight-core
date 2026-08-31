"""Sprint 1 composition remains fail-closed without opening network connections."""

import pytest
from pydantic import SecretStr

from app.bootstrap.settings import Settings
from app.bootstrap.sprint1 import (
    Sprint1ConfigurationError,
    build_sprint1_services,
    sprint1_is_configured,
)
from app.interface.http.services import Sprint1ServiceContainer

pytestmark = pytest.mark.unit


def test_sprint1_composition_refuses_missing_secrets() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert sprint1_is_configured(settings) is False
    with pytest.raises(Sprint1ConfigurationError, match="DATABASE_URL"):
        build_sprint1_services(settings)


def test_sprint1_composition_builds_without_connecting_to_dependencies() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=SecretStr("postgresql+psycopg://user:secret@invalid:5432/csight"),
        jwt_secret_key=SecretStr("local-test-jwt-secret-with-at-least-32-bytes"),
        minio_endpoint="minio.invalid:9000",
        minio_presigned_endpoint="objects.invalid:443",
        minio_access_key=SecretStr("access"),
        minio_secret_key=SecretStr("secret"),
        minio_presigned_secure=True,
    )

    services = build_sprint1_services(settings)

    assert sprint1_is_configured(settings) is True
    assert isinstance(services, Sprint1ServiceContainer)


def test_production_composition_requires_reencoding_and_clamav() -> None:
    base = {
        "environment": "production",
        "database_url": SecretStr("postgresql+psycopg://user:secret@invalid:5432/csight"),
        "jwt_secret_key": SecretStr("local-test-jwt-secret-with-at-least-32-bytes"),
        "minio_endpoint": "minio.invalid:9000",
        "minio_presigned_endpoint": "objects.invalid:443",
        "minio_access_key": SecretStr("access"),
        "minio_secret_key": SecretStr("secret"),
        "sensitive_payload_retention_policy_version": "customer/90d",
        "sensitive_payload_retention_days": 90,
    }
    unsafe = Settings(_env_file=None, **base)  # pyright: ignore[reportCallIssue]

    assert sprint1_is_configured(unsafe) is False
    with pytest.raises(Sprint1ConfigurationError, match="EVIDENCE_IMAGE_SANITIZATION"):
        build_sprint1_services(unsafe)

    safe = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        **base,
        evidence_image_sanitization_enabled=True,
        evidence_malware_scanner="clamav",
        clamav_host="scanner.internal",
    )

    assert sprint1_is_configured(safe) is True
    assert isinstance(build_sprint1_services(safe), Sprint1ServiceContainer)
