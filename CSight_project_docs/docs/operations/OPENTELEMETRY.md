# Limited-pilot OpenTelemetry activation and evidence runbook

This runbook activates an already implemented exporter contract. A repository-owned isolated stack
qualifies the HTTP signal path with a local receiver; it is not the pilot deployment and does not
claim that an operator paging destination currently exists. Local and test defaults make no
telemetry network calls.

## 1. Configuration

Keep the default local values:

```dotenv
OTEL_ENABLED=false
OTEL_EXPORTER=none
OTEL_EXPORTER_OTLP_ENDPOINT=
```

For a limited-pilot deployment, inject all of the following through deployment configuration:

```dotenv
OTEL_ENABLED=true
OTEL_SERVICE_NAME=csight-core
OTEL_EXPORTER=otlp_http
OTEL_EXPORTER_OTLP_ENDPOINT=https://collector.example
OTEL_TRACE_SAMPLE_RATIO=1.0
OTEL_EXPORT_TIMEOUT_SECONDS=5
OTEL_METRIC_EXPORT_INTERVAL_SECONDS=30
```

`OTEL_EXPORTER_OTLP_ENDPOINT` is a base endpoint; Core appends `/v1/traces` and `/v1/metrics`.
Optional `OTEL_EXPORTER_OTLP_HEADERS` uses comma-separated `header=value` pairs. Treat every value as
a secret: do not print it, store it in a committed `.env`, or attach it to qualification evidence.

## 2. Implemented signals

Inbound HTTP spans accept only W3C trace context and use route templates. HTTP metrics are:

- `csight.http.server.request.count`
- `csight.http.server.request.duration` in milliseconds
- `csight.http.server.active_requests`

Celery task spans and metrics cover the seven versioned task contracts. Task metrics are:

- `csight.worker.task.count`
- `csight.worker.task.duration` in milliseconds

Metric labels are intentionally limited to HTTP method, route template, HTTP status class, fixed task
name, and bounded task outcome. Never add tenant, user, Case, run, Event, task, or correlation IDs as
metric labels. Correlation IDs belong only in structured logs and spans.

The qualification Collector deletes SDK-generated `service.instance.id` from the metric resource
before Prometheus export. Without that processor, the Prometheus translation exposes a random UUID
as `exported_instance`, which violates the low-cardinality storage boundary even though application
instrument attributes are safe.

## 3. Readiness semantics

In non-local environments, `/health/ready` includes `telemetry_configuration`. It checks configuration
only and performs no synchronous Collector request. A `200` therefore proves that the application is
configured to export; it does not prove ingestion, storage, dashboard queries, or alert delivery.

The Operations Read API remains database-only. Do not add a synchronous Collector dependency to an
operator request path. Collector and alert health belong in the external monitoring control plane.

## 4. Pilot evidence procedure

Before a limited pilot can be eligible, retain PII-free evidence that:

1. one request with a known correlation identifier produced an HTTP span and count/duration metrics;
2. one task in each Worker lane produced a consumer span and count/duration metrics;
3. the same correlation identifier can locate related safe logs and spans;
4. no metric label contains a UUID or any tenant, Case, user, run, Event, task, or correlation ID;
5. exporter outage and recovery do not fail an HTTP request or alter durable task outcomes;
6. the Collector/backend receives both traces and metrics for the configured service/resource;
7. an alert rule is triggered, delivered to the intended receiver, acknowledged, and closed.

Record the observed result in the limited-pilot evidence manifest. Setting
`otel_signal_delivery_passed=true` or `operations_alert_delivery_passed=true` without the retained
external evidence is invalid.

### Isolated local qualification

Run this without changing the Core demo stack:

```bash
make qualify-observability
```

The command starts a separate internal-only Docker network with digest-pinned Collector,
Prometheus, Alertmanager, a CSight HTTP emitter, and a bounded local webhook receiver. It exposes no
host ports and always removes its containers, network, and volumes. It verifies:

1. a known W3C trace and bounded correlation identifier reach the Collector;
2. the CSight HTTP request counter is queryable from Prometheus;
3. stored labels contain no UUID or tenant/Case/user/run/Event/task/correlation identifier;
4. Alertmanager delivers and receives a `200` acknowledgement for firing and resolved states;
5. the CSight HTTP endpoint remains `200` while the Collector is stopped;
6. trace, metric, and alert delivery resume after the Collector restarts.

PII-free evidence is written under
`local-data/observability-qualification/latest/qualification_report.json`. The raw stack is local
qualification evidence only: `external_notification_sent=false` and
`operator_paging_destination_qualified=false` remain fail-closed.

## 5. Current qualification state

- SDK, OTLP/HTTP exporter, safe configuration default: implemented and unit-tested.
- HTTP and Celery spans/metrics with low-cardinality labels: implemented and in-memory tested.
- Configuration-only readiness and pilot runtime gate: implemented and unit-tested.
- Isolated HTTP Collector ingestion and Prometheus metric query: **PASS** on 2026-08-30.
- Isolated local firing/resolved alert delivery, acknowledgement, outage, and recovery: **PASS** on
  2026-08-30.
- Real Worker task export for all three lanes: **NOT_RUN**.
- Pilot-host dashboard p50/p95 query validation: **NOT_RUN**.
- Intended operator paging destination delivery and human acknowledgement: **NOT_RUN**.

Until the remaining `NOT_RUN` items are executed, do not set either release-manifest telemetry gate
to true. The limited-pilot release remains blocked even when the isolated qualification passes.
