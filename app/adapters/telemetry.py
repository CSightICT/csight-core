"""OpenTelemetry adapter with an explicit no-export default.

Only this adapter and the composition/interface layers import OpenTelemetry.  Metric
attributes are built here from bounded values so request, tenant, Case, task, and
correlation identifiers can never become metric labels.
"""

from __future__ import annotations

import re
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

from opentelemetry import metrics, trace
from opentelemetry.context import Context
from opentelemetry.sdk.metrics import MeterProvider as SdkMeterProvider
from opentelemetry.sdk.metrics.export import (
    MetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.util.types import AttributeValue

TelemetryExporter = Literal["none", "otlp_http"]

HTTP_METRIC_ATTRIBUTE_KEYS = frozenset(
    {
        "http.request.method",
        "http.route",
        "http.response.status_code_class",
    }
)
TASK_METRIC_ATTRIBUTE_KEYS = frozenset({"celery.task.name", "csight.task.outcome"})

_KNOWN_HTTP_METHODS = frozenset(
    {"CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"}
)
_KNOWN_TASK_NAMES = frozenset(
    {
        "analysis.requested.v1",
        "policy_retrieval.requested.v1",
        "policy_query_build.requested.v2",
        "policy_search.requested.v2",
        "grounded_explanation.requested.v1",
        "policy_evaluation.requested.v1",
        "human_review.requested.v1",
        "case_resolution.requested.v1",
        "external_action.simulation_requested.v1",
    }
)
_KNOWN_TASK_OUTCOMES = frozenset({"error", "reject", "retry", "success"})
_UUID_PATH_SEGMENT = re.compile(
    r"/(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})(?:/|$)"
)


@dataclass(frozen=True, slots=True)
class TelemetryConfiguration:
    """Validated composition input; secrets are already parsed into a mapping."""

    enabled: bool
    service_name: str
    service_version: str
    environment: str
    exporter: TelemetryExporter = "none"
    endpoint: str | None = None
    headers: Mapping[str, str] | None = None
    trace_sample_ratio: float = 1.0
    export_timeout_seconds: float = 5.0
    metric_export_interval_seconds: float = 30.0

    @property
    def external_export_configured(self) -> bool:
        return self.enabled and self.exporter == "otlp_http" and self.endpoint is not None


class TelemetryRuntime:
    """Process-local tracers and meters without mutating global OTel providers."""

    def __init__(
        self,
        *,
        enabled: bool,
        external_export_configured: bool,
        tracer_provider: trace.TracerProvider,
        meter_provider: metrics.MeterProvider,
    ) -> None:
        self.enabled = enabled
        self.external_export_configured = external_export_configured
        self._tracer_provider = tracer_provider
        self._meter_provider = meter_provider
        self._tracer = tracer_provider.get_tracer("csight.telemetry")
        meter = meter_provider.get_meter("csight.telemetry")
        self._http_request_count = meter.create_counter(
            "csight.http.server.request.count",
            unit="{request}",
            description="Completed inbound HTTP requests.",
        )
        self._http_request_duration = meter.create_histogram(
            "csight.http.server.request.duration",
            unit="ms",
            description="Inbound HTTP request duration.",
        )
        self._http_active_requests = meter.create_up_down_counter(
            "csight.http.server.active_requests",
            unit="{request}",
            description="Currently active inbound HTTP requests.",
        )
        self._task_count = meter.create_counter(
            "csight.worker.task.count",
            unit="{task}",
            description="Completed Celery task executions.",
        )
        self._task_duration = meter.create_histogram(
            "csight.worker.task.duration",
            unit="ms",
            description="Celery task execution duration.",
        )

    @contextmanager
    def start_http_span(
        self,
        *,
        method: str,
        carrier: Mapping[str, str],
        correlation_id: str | None,
    ) -> Generator[Span]:
        """Start one server span using only W3C trace-context propagation."""

        normalized_method = normalize_http_method(method)
        parent = _extract_trace_context(carrier)
        with self._tracer.start_as_current_span(
            f"HTTP {normalized_method}",
            context=parent,
            kind=SpanKind.SERVER,
            attributes={"http.request.method": normalized_method},
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            if correlation_id is not None:
                span.set_attribute("csight.correlation_id", correlation_id)
            yield span

    def finish_http_span(
        self,
        span: Span,
        *,
        route: str,
        status_code: int,
        error_type: str | None = None,
    ) -> None:
        normalized_route = normalize_http_route(route)
        span.update_name(f"HTTP {normalized_route}")
        span.set_attribute("http.route", normalized_route)
        span.set_attribute("http.response.status_code", status_code)
        if error_type is not None:
            span.set_attribute("error.type", _safe_error_type(error_type))
        if status_code >= 500 or error_type is not None:
            # Never call record_exception: exception messages and stack traces can
            # contain provider payloads, URLs, credentials, or customer text.
            span.set_status(Status(StatusCode.ERROR))

    def start_http_request(self, *, method: str) -> None:
        self._http_active_requests.add(
            1,
            attributes={"http.request.method": normalize_http_method(method)},
        )

    def finish_http_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        active_attributes = {"http.request.method": normalize_http_method(method)}
        attributes = http_metric_attributes(
            method=method,
            route=route,
            status_code=status_code,
        )
        self._http_active_requests.add(-1, attributes=active_attributes)
        self._http_request_count.add(1, attributes=attributes)
        self._http_request_duration.record(max(0.0, duration_ms), attributes=attributes)

    @contextmanager
    def start_task_span(
        self,
        *,
        task_name: str,
        correlation_id: str | None,
    ) -> Generator[Span]:
        normalized_task = normalize_task_name(task_name)
        with self._tracer.start_as_current_span(
            f"celery {normalized_task}",
            kind=SpanKind.CONSUMER,
            attributes={
                "celery.task.name": normalized_task,
                "messaging.operation.type": "process",
                "messaging.system": "celery",
            },
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            if correlation_id is not None:
                span.set_attribute("csight.correlation_id", correlation_id)
            yield span

    def finish_task_span(self, span: Span, *, outcome: str, error_type: str | None = None) -> None:
        normalized_outcome = normalize_task_outcome(outcome)
        span.set_attribute("csight.task.outcome", normalized_outcome)
        if error_type is not None:
            span.set_attribute("error.type", _safe_error_type(error_type))
        if normalized_outcome == "error":
            span.set_status(Status(StatusCode.ERROR))

    def finish_task(
        self,
        *,
        task_name: str,
        outcome: str,
        duration_ms: float,
    ) -> None:
        attributes = task_metric_attributes(task_name=task_name, outcome=outcome)
        self._task_count.add(1, attributes=attributes)
        self._task_duration.record(max(0.0, duration_ms), attributes=attributes)

    def shutdown(self) -> None:
        """Flush owned SDK providers; no-op providers need no lifecycle work."""

        if isinstance(self._meter_provider, SdkMeterProvider):
            self._meter_provider.shutdown()
        if isinstance(self._tracer_provider, SdkTracerProvider):
            self._tracer_provider.shutdown()


def build_telemetry_runtime(
    configuration: TelemetryConfiguration,
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
) -> TelemetryRuntime:
    """Build a process-local runtime; disabled means no SDK and no network."""

    if not configuration.enabled:
        return TelemetryRuntime(
            enabled=False,
            external_export_configured=False,
            tracer_provider=trace.NoOpTracerProvider(),
            meter_provider=metrics.NoOpMeterProvider(),
        )

    resource = Resource.create(
        {
            "service.name": configuration.service_name,
            "service.version": configuration.service_version,
            "deployment.environment.name": configuration.environment,
        }
    )
    tracer_provider = SdkTracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(configuration.trace_sample_ratio)),
    )
    resolved_span_exporter = span_exporter
    resolved_metric_reader = metric_reader
    if configuration.external_export_configured:
        resolved_span_exporter = resolved_span_exporter or _build_otlp_span_exporter(configuration)
        resolved_metric_reader = resolved_metric_reader or _build_otlp_metric_reader(configuration)
    if resolved_span_exporter is not None:
        processor = (
            SimpleSpanProcessor(resolved_span_exporter)
            if span_exporter is not None
            else BatchSpanProcessor(resolved_span_exporter)
        )
        tracer_provider.add_span_processor(processor)

    metric_readers = (resolved_metric_reader,) if resolved_metric_reader is not None else ()
    meter_provider = SdkMeterProvider(resource=resource, metric_readers=metric_readers)
    return TelemetryRuntime(
        enabled=True,
        external_export_configured=configuration.external_export_configured,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )


def http_metric_attributes(
    *,
    method: str,
    route: str,
    status_code: int,
) -> dict[str, AttributeValue]:
    """Return the complete, low-cardinality HTTP metric label set."""

    return {
        "http.request.method": normalize_http_method(method),
        "http.route": normalize_http_route(route),
        "http.response.status_code_class": _status_code_class(status_code),
    }


def task_metric_attributes(*, task_name: str, outcome: str) -> dict[str, AttributeValue]:
    """Return the complete, low-cardinality task metric label set."""

    return {
        "celery.task.name": normalize_task_name(task_name),
        "csight.task.outcome": normalize_task_outcome(outcome),
    }


def normalize_http_method(method: str) -> str:
    normalized = method.strip().upper()
    return normalized if normalized in _KNOWN_HTTP_METHODS else "OTHER"


def normalize_http_route(route: str) -> str:
    normalized = route.strip()
    if (
        not normalized.startswith("/")
        or len(normalized) > 255
        or "?" in normalized
        or "#" in normalized
        or _UUID_PATH_SEGMENT.search(f"{normalized.rstrip('/')}/") is not None
    ):
        return "unmatched"
    return normalized or "unmatched"


def normalize_task_name(task_name: str) -> str:
    normalized = task_name.strip()
    return normalized if normalized in _KNOWN_TASK_NAMES else "unknown"


def normalize_task_outcome(outcome: str) -> str:
    normalized = outcome.strip().lower()
    return normalized if normalized in _KNOWN_TASK_OUTCOMES else "error"


def _status_code_class(status_code: int) -> str:
    if 100 <= status_code <= 599:
        return f"{status_code // 100}xx"
    return "unknown"


def _safe_error_type(error_type: str) -> str:
    normalized = error_type.strip()
    if not normalized or len(normalized) > 128 or not normalized.replace("_", "").isalnum():
        return "Error"
    return normalized


def _extract_trace_context(carrier: Mapping[str, str]) -> Context:
    # Explicit propagator avoids accepting baggage or vendor-specific arbitrary fields.
    return TraceContextTextMapPropagator().extract(carrier=carrier)


def _build_otlp_span_exporter(configuration: TelemetryConfiguration) -> SpanExporter:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter(
        endpoint=_signal_endpoint(configuration.endpoint, "v1/traces"),
        headers=dict(configuration.headers or {}),
        timeout=configuration.export_timeout_seconds,
    )


def _build_otlp_metric_reader(configuration: TelemetryConfiguration) -> MetricReader:
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

    exporter = OTLPMetricExporter(
        endpoint=_signal_endpoint(configuration.endpoint, "v1/metrics"),
        headers=dict(configuration.headers or {}),
        timeout=configuration.export_timeout_seconds,
    )
    return PeriodicExportingMetricReader(
        exporter,
        export_interval_millis=configuration.metric_export_interval_seconds * 1000,
        export_timeout_millis=configuration.export_timeout_seconds * 1000,
    )


def _signal_endpoint(endpoint: str | None, suffix: str) -> str:
    if endpoint is None:
        raise ValueError("OTLP endpoint is required for external export")
    return f"{endpoint.rstrip('/')}/{suffix}"


__all__ = [
    "HTTP_METRIC_ATTRIBUTE_KEYS",
    "TASK_METRIC_ATTRIBUTE_KEYS",
    "TelemetryConfiguration",
    "TelemetryRuntime",
    "build_telemetry_runtime",
    "http_metric_attributes",
    "normalize_http_route",
    "task_metric_attributes",
]
