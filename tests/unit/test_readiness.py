"""Technology-neutral readiness aggregation tests."""

import pytest

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
