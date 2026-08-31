"""Technology-neutral readiness aggregation tests."""

import pytest

from app.bootstrap.dependencies import build_readiness_service
from app.bootstrap.settings import Settings
from app.ports.readiness import ProbeStatus, ReadinessService

pytestmark = pytest.mark.unit


class StaticProbe:
    def __init__(self, name: str, result: bool | Exception) -> None:
        self.name = name
        self._result = result

    def check(self) -> bool:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_readiness_requires_every_probe() -> None:
    service = ReadinessService(
        probes=(
            StaticProbe("postgresql", True),
            StaticProbe("rabbitmq", False),
            StaticProbe("minio", True),
        )
    )

    report = service.check()

    assert report.ready is False
    assert report.as_status_map() == {
        "postgresql": ProbeStatus.OK,
        "rabbitmq": ProbeStatus.UNAVAILABLE,
        "minio": ProbeStatus.OK,
    }


def test_probe_exception_is_sanitized_to_unavailable() -> None:
    report = ReadinessService(
        probes=(StaticProbe("postgresql", RuntimeError("contains-sensitive-detail")),)
    ).check()

    assert report.ready is False
    assert report.as_status_map() == {"postgresql": ProbeStatus.UNAVAILABLE}


def test_production_readiness_requires_oidc_and_telemetry_configuration() -> None:
    production = build_readiness_service(
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            environment="production",
        )
    ).check()
    local = build_readiness_service(
        Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    ).check()
    telemetry_configured = build_readiness_service(
        Settings(
            _env_file=None,  # pyright: ignore[reportCallIssue]
            environment="production",
            otel_enabled=True,
            otel_exporter="otlp_http",
            otel_exporter_otlp_endpoint="https://collector.example",
        )
    ).check()

    assert production.as_status_map()["oidc_configuration"] is ProbeStatus.UNAVAILABLE
    assert production.as_status_map()["telemetry_configuration"] is ProbeStatus.UNAVAILABLE
    assert "oidc_configuration" not in local.as_status_map()
    assert "telemetry_configuration" not in local.as_status_map()
    assert telemetry_configured.as_status_map()["telemetry_configuration"] is ProbeStatus.OK
