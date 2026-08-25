"""Technology-neutral readiness probe contract."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class ProbeStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """A deliberately non-sensitive dependency status."""

    name: str
    status: ProbeStatus

    @property
    def ready(self) -> bool:
        return self.status is ProbeStatus.OK


@runtime_checkable
class DependencyProbe(Protocol):
    """Port implemented by each infrastructure-specific health probe."""

    @property
    def name(self) -> str: ...

    def check(self) -> bool:
        """Return whether the dependency can serve requests right now."""
        ...


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    results: tuple[ProbeResult, ...]

    @property
    def ready(self) -> bool:
        return bool(self.results) and all(result.ready for result in self.results)

    def as_status_map(self) -> dict[str, ProbeStatus]:
        return {result.name: result.status for result in self.results}


class ReadinessService:
    """Runs all mandatory dependency probes without leaking failure details."""

    def __init__(self, probes: tuple[DependencyProbe, ...]) -> None:
        names = tuple(probe.name for probe in probes)
        if len(names) != len(set(names)):
            raise ValueError("readiness probe names must be unique")
        self._probes = probes

    def check(self) -> ReadinessReport:
        results: list[ProbeResult] = []
        for probe in self._probes:
            try:
                is_ready = probe.check()
            except Exception:  # A probe failure must degrade readiness, never crash the API.
                is_ready = False
            status = ProbeStatus.OK if is_ready else ProbeStatus.UNAVAILABLE
            results.append(ProbeResult(name=probe.name, status=status))
        return ReadinessReport(results=tuple(results))
