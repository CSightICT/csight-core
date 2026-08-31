"""Network-free OpenTelemetry adapter and interface contracts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from celery import Celery
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, MetricsData
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.util.types import AttributeValue
from structlog.typing import WrappedLogger

from app.adapters.telemetry import (
    HTTP_METRIC_ATTRIBUTE_KEYS,
    TASK_METRIC_ATTRIBUTE_KEYS,
    TelemetryConfiguration,
    TelemetryRuntime,
    build_telemetry_runtime,
    http_metric_attributes,
    task_metric_attributes,
)
from app.bootstrap.logging import add_trace_context
from app.bootstrap.settings import Settings
from app.bootstrap.telemetry import build_process_telemetry
from app.interface.workers import telemetry as worker_telemetry_module
from app.interface.workers.telemetry import TelemetryTask
from app.main import create_app

pytestmark = pytest.mark.unit


def _runtime() -> tuple[TelemetryRuntime, InMemorySpanExporter, InMemoryMetricReader]:
    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    runtime = build_telemetry_runtime(
        TelemetryConfiguration(
            enabled=True,
            service_name="csight-test",
            service_version="test",
            environment="test",
        ),
        span_exporter=span_exporter,
        metric_reader=metric_reader,
    )
    return runtime, span_exporter, metric_reader


def _metric_attributes(
    data: MetricsData,
    *,
    instrument_name: str,
) -> tuple[Mapping[str, AttributeValue], ...]:
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == instrument_name:
                    return tuple(
                        cast(Mapping[str, AttributeValue], point.attributes or {})
                        for point in metric.data.data_points
                    )
    return ()


def test_default_runtime_uses_no_sdk_exporter_or_external_endpoint() -> None:
    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    runtime = build_process_telemetry(settings)

    assert settings.otel_enabled is False
    assert settings.otel_exporter == "none"
    assert settings.otel_exporter_otlp_endpoint_value is None
    assert runtime.enabled is False
    assert runtime.external_export_configured is False


def test_production_configuration_requires_opt_in_otlp_and_keeps_headers_secret() -> None:
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        environment="production",
        otel_enabled=True,
        otel_exporter="otlp_http",
        otel_exporter_otlp_endpoint="https://collector.example/",
        otel_exporter_otlp_headers="Authorization=pilot-secret,X-Scope=csight",
    )

    assert settings.otel_is_configured is True
    assert settings.otel_configuration_missing == ()
    assert settings.otel_exporter_otlp_endpoint_value == "https://collector.example"
    assert settings.otel_exporter_otlp_headers_value == {
        "Authorization": "pilot-secret",
        "X-Scope": "csight",
    }
    assert "pilot-secret" not in repr(settings)


def test_http_middleware_emits_correlated_route_span_and_low_cardinality_metrics() -> None:
    runtime, span_exporter, metric_reader = _runtime()
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        environment="test",
        otel_enabled=True,
    )
    trace_id = "1234567890abcdef1234567890abcdef"
    parent_span_id = "1234567890abcdef"

    with TestClient(create_app(settings, telemetry_runtime=runtime)) as client:
        response = client.get(
            "/health/live",
            headers={
                "X-Correlation-ID": "pilot-correlation",
                "traceparent": f"00-{trace_id}-{parent_span_id}-01",
            },
        )
        metrics_data = metric_reader.get_metrics_data()

        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"] == "pilot-correlation"
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.context is not None
        assert format(span.context.trace_id, "032x") == trace_id
        assert span.parent is not None
        assert format(span.parent.span_id, "016x") == parent_span_id
        assert span.name == "HTTP /health/live"
        assert span.attributes is not None
        assert span.attributes["http.route"] == "/health/live"
        assert span.attributes["csight.correlation_id"] == "pilot-correlation"
        assert "tenant_id" not in span.attributes
        assert "case_id" not in span.attributes

        assert metrics_data is not None
        request_points = _metric_attributes(
            metrics_data,
            instrument_name="csight.http.server.request.count",
        )
        assert request_points == (
            {
                "http.request.method": "GET",
                "http.route": "/health/live",
                "http.response.status_code_class": "2xx",
            },
        )
        for attributes in request_points:
            assert set(attributes) <= HTTP_METRIC_ATTRIBUTE_KEYS
            assert "pilot-correlation" not in attributes.values()


def test_metric_attribute_builders_collapse_identifiers_and_unbounded_values() -> None:
    identifier = str(uuid4())

    http_attributes = http_metric_attributes(
        method="UNBOUNDED-METHOD",
        route=f"/api/v1/cases/{identifier}",
        status_code=200,
    )
    task_attributes = task_metric_attributes(
        task_name=f"customer-generated-{identifier}",
        outcome=f"customer-generated-{identifier}",
    )

    assert set(http_attributes) == HTTP_METRIC_ATTRIBUTE_KEYS
    assert http_attributes == {
        "http.request.method": "OTHER",
        "http.route": "unmatched",
        "http.response.status_code_class": "2xx",
    }
    assert set(task_attributes) == TASK_METRIC_ATTRIBUTE_KEYS
    assert task_attributes == {
        "celery.task.name": "unknown",
        "csight.task.outcome": "error",
    }
    assert identifier not in http_attributes.values()
    assert identifier not in task_attributes.values()


def test_celery_task_base_emits_consumer_span_and_task_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, span_exporter, metric_reader = _runtime()
    monkeypatch.setattr(worker_telemetry_module, "get_process_telemetry", lambda: runtime)
    celery = Celery("telemetry-test", task_cls=TelemetryTask)

    @celery.task(name="analysis.requested.v1")  # pyright: ignore[reportUntypedFunctionDecorator]
    def task(payload: dict[str, object]) -> dict[str, object]:
        return payload

    result = task.apply(  # pyright: ignore[reportFunctionMemberAccess]
        args=({"correlation_id": "worker-correlation"},),
        throw=True,
    ).get()
    metrics_data = metric_reader.get_metrics_data()

    assert result == {"correlation_id": "worker-correlation"}
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "celery analysis.requested.v1"
    assert span.attributes is not None
    assert span.attributes["csight.correlation_id"] == "worker-correlation"
    assert span.attributes["csight.task.outcome"] == "success"
    assert "tenant_id" not in span.attributes
    assert "case_id" not in span.attributes
    assert metrics_data is not None
    task_points = _metric_attributes(
        metrics_data,
        instrument_name="csight.worker.task.count",
    )
    assert task_points == (
        {
            "celery.task.name": "analysis.requested.v1",
            "csight.task.outcome": "success",
        },
    )
    assert set(task_points[0]) == TASK_METRIC_ATTRIBUTE_KEYS


def test_log_processor_adds_current_trace_and_span_identifiers() -> None:
    runtime, _span_exporter, _metric_reader = _runtime()

    with runtime.start_task_span(
        task_name="analysis.requested.v1",
        correlation_id="log-correlation",
    ):
        event = add_trace_context(
            cast(WrappedLogger, object()),
            "info",
            {"event": "safe"},
        )

    assert len(cast(str, event["trace_id"])) == 32
    assert len(cast(str, event["span_id"])) == 16


def test_span_error_records_only_safe_type_not_exception_message_or_stack() -> None:
    runtime, span_exporter, _metric_reader = _runtime()

    with (
        pytest.raises(RuntimeError, match="customer-private-text"),
        runtime.start_task_span(
            task_name="analysis.requested.v1",
            correlation_id="error-correlation",
        ) as span,
    ):
        runtime.finish_task_span(
            span,
            outcome="error",
            error_type="RuntimeError",
        )
        raise RuntimeError("customer-private-text")

    finished = span_exporter.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].events == ()
    assert finished[0].attributes is not None
    assert finished[0].attributes["error.type"] == "RuntimeError"
    assert "customer-private-text" not in repr(finished[0].attributes)


@pytest.mark.contract
def test_domain_and_platform_sources_do_not_import_opentelemetry_sdk() -> None:
    root = Path(__file__).resolve().parents[2] / "app"
    violations = []
    for boundary in (root / "domains", root / "platform"):
        if not boundary.exists():
            continue
        for source in boundary.rglob("*.py"):
            if "opentelemetry" in source.read_text(encoding="utf-8"):
                violations.append(str(source.relative_to(root)))

    assert violations == []
