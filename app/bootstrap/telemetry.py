"""Composition helpers for the process-local OpenTelemetry adapter."""

from __future__ import annotations

from dataclasses import dataclass
from os import getpid

from app.adapters.telemetry import (
    TelemetryConfiguration,
    TelemetryRuntime,
    build_telemetry_runtime,
)
from app.bootstrap.settings import Settings, get_settings


def build_process_telemetry(settings: Settings) -> TelemetryRuntime:
    """Build telemetry without setting global providers or contacting a collector."""

    return build_telemetry_runtime(
        TelemetryConfiguration(
            enabled=settings.otel_enabled,
            service_name=settings.otel_service_name_value,
            service_version=settings.app_version,
            environment=settings.environment,
            exporter=settings.otel_exporter,
            endpoint=settings.otel_exporter_otlp_endpoint_value,
            headers=settings.otel_exporter_otlp_headers_value,
            trace_sample_ratio=settings.otel_trace_sample_ratio,
            export_timeout_seconds=settings.otel_export_timeout_seconds,
            metric_export_interval_seconds=settings.otel_metric_export_interval_seconds,
        )
    )


@dataclass(slots=True)
class _RuntimeCacheEntry:
    settings: Settings
    runtime: TelemetryRuntime


_PROCESS_RUNTIME_CACHE: dict[int, _RuntimeCacheEntry] = {}


def get_process_telemetry(settings: Settings | None = None) -> TelemetryRuntime:
    """Lazily initialize after Celery prefork and reuse within one child process."""

    resolved_settings = settings or get_settings()
    pid = getpid()
    existing = _PROCESS_RUNTIME_CACHE.get(pid)
    if existing is not None and existing.settings is resolved_settings:
        return existing.runtime
    runtime = build_process_telemetry(resolved_settings)
    _PROCESS_RUNTIME_CACHE[pid] = _RuntimeCacheEntry(
        settings=resolved_settings,
        runtime=runtime,
    )
    return runtime


def reset_process_telemetry_cache() -> None:
    """Test seam that also flushes any locally owned providers."""

    entries = tuple(_PROCESS_RUNTIME_CACHE.values())
    _PROCESS_RUNTIME_CACHE.clear()
    for entry in entries:
        entry.runtime.shutdown()


__all__ = [
    "build_process_telemetry",
    "get_process_telemetry",
    "reset_process_telemetry_cache",
]
