# ADR-0106: Opt-in OpenTelemetry for limited-pilot observability

- Status: Accepted
- Date: 2026-08-29

## Context

CSight already emits structured logs with a bounded correlation identifier and exposes a
tenant-scoped, persisted Operations Read API. It did not have process telemetry for HTTP latency or
Celery execution, and the limited-pilot gate already requires observed OpenTelemetry signal
delivery. A missing or unreachable Collector must not cause local development to make network
calls, and telemetry must not weaken the human-final-decision or data-minimization boundaries.

## Decision

- OpenTelemetry is disabled by default and the default exporter is `none`. The only supported
  external transport is an explicitly enabled OTLP/HTTP base endpoint. Constructing readiness does
  not contact that endpoint.
- The OpenTelemetry Python API, SDK, and exporter remain in adapter, interface, and bootstrap code.
  `app/platform` and `app/domains` remain independent of the SDK.
- FastAPI records one inbound server span plus request count, active-request, and duration metrics.
  The span uses the registered route template, never the raw URL path. W3C `traceparent` and
  `tracestate` are the only accepted inbound propagation fields.
- Every registered Celery thin task uses a process-local task base initialized lazily after prefork.
  A task span records only the fixed task contract name, delivery outcome, safe error type, and the
  bounded correlation identifier. Queue payloads remain reference-only and unchanged.
- Logs add current `trace_id` and `span_id`; correlation identifiers remain available in logs and
  spans. Exception messages and stack traces are not recorded into spans because they may contain
  customer text, provider payloads, URLs, or credentials.
- Metric attributes are allowlisted. HTTP metrics contain method, route template, and status class;
  task metrics contain a fixed task name and bounded outcome. Tenant, user, Case, run, Event, task,
  and correlation identifiers are forbidden as metric labels.
- Non-local readiness adds a configuration-only `telemetry_configuration` probe. It passes only when
  telemetry, OTLP/HTTP, and an endpoint are configured. This is not Collector health evidence.
  Limited-pilot qualification separately requires an observed trace-and-metric delivery result.
- The existing Operations Read API remains a persisted database projection. It does not synchronously
  query a Collector or expose process-local counters that would be misleading across API and Worker
  processes.
- Model and policy output remains advisory. Telemetry cannot resolve Human Review, create a final
  Decision, or trigger a real external business action.

## Consequences

- Local and test execution remains network-free unless a test injects in-memory exporters.
- HTTP spans continue an inbound W3C trace. Celery spans are correlated through the durable
  `correlation_id`; full cross-process parent continuation is deferred until a versioned queue/event
  propagation contract is accepted.
- A digest-pinned internal-only qualification stack may verify the HTTP Collector→Prometheus→local
  Alertmanager path without changing the Core demo runtime. The metric pipeline deletes
  SDK-generated `service.instance.id` before Prometheus export so its random UUID cannot become a
  high-cardinality label. This local result does not qualify real Worker-lane export, a pilot-host
  dashboard, or the intended operator paging destination; the pilot remains ineligible until those
  external operational checks are executed and retained as evidence.

## Related decisions

- [ADR-0009](0009-transactional-outbox-and-fenced-analysis-execution.md)
- [ADR-0087](0087-no-automated-execution-of-human-decision.md)
- [ADR-0103](0103-limited-pilot-execution-isolation-and-shadow-mode.md)
- [ADR-0105](0105-postgresql-process-roles-and-tenant-rls.md)
