"""Public health, readiness, system-info, and error envelope contracts."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.bootstrap.settings import Settings
from app.interface.http.dependencies import provide_readiness_service
from app.main import create_app
from app.ports.readiness import ReadinessService

pytestmark = pytest.mark.contract


class StaticProbe:
    def __init__(self, name: str, ready: bool) -> None:
        self.name = name
        self._ready = ready

    def check(self) -> bool:
        return self._ready


def _readiness(*, rabbitmq_ready: bool = True) -> ReadinessService:
    return ReadinessService(
        probes=(
            StaticProbe("postgresql", True),
            StaticProbe("rabbitmq", rabbitmq_ready),
            StaticProbe("minio", True),
        )
    )


def test_live_does_not_call_external_dependencies() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    application = create_app(settings)
    application.dependency_overrides[provide_readiness_service] = lambda: _readiness()

    response = TestClient(application).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "csight-core-api"}


def test_ready_returns_200_when_every_dependency_is_available() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    application = create_app(settings)
    application.dependency_overrides[provide_readiness_service] = lambda: _readiness()

    response = TestClient(application).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "csight-core-api",
        "dependencies": {"postgresql": "ok", "rabbitmq": "ok", "minio": "ok"},
    }


def test_ready_fails_closed_when_dependency_configuration_is_absent() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        database_url=None,
        rabbitmq_url=None,
        minio_endpoint=None,
        minio_access_key=None,
        minio_secret_key=None,
    )

    response = TestClient(create_app(settings)).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["dependencies"] == {
        "postgresql": "unavailable",
        "rabbitmq": "unavailable",
        "minio": "unavailable",
    }


def test_ready_returns_sanitized_503_when_a_dependency_is_down() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    application = create_app(settings)
    application.dependency_overrides[provide_readiness_service] = lambda: _readiness(
        rabbitmq_ready=False
    )

    response = TestClient(application).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["dependencies"]["rabbitmq"] == "unavailable"
    assert "url" not in response.text.lower()
    assert "password" not in response.text.lower()


def test_system_info_exposes_only_non_sensitive_settings() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        app_name="csight-test-api",
        app_version="9.8.7",
        environment="test",
        api_schema_version="1.0",
        database_url=SecretStr("postgresql+psycopg://secret-user:secret-pass@database:5432/csight"),
        rabbitmq_url=SecretStr("amqp://secret-user:secret-pass@rabbitmq:5672//"),
        minio_endpoint="minio:9000",
        minio_access_key=SecretStr("secret-access"),
        minio_secret_key=SecretStr("secret-key"),
    )

    response = TestClient(create_app(settings)).get("/api/v1/system/info")

    assert response.status_code == 200
    assert response.json() == {
        "service": "csight-test-api",
        "version": "9.8.7",
        "environment": "test",
        "api_schema_version": "1.0",
    }
    assert "secret" not in response.text


def test_http_errors_use_the_standard_envelope_and_correlation_id() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    response = TestClient(create_app(settings)).get(
        "/does-not-exist", headers={"X-Correlation-ID": "corr-test"}
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "HTTP_404",
            "message": "Not Found",
            "details": {},
            "correlation_id": "corr-test",
        }
    }
