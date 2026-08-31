# ADR-0103: Limited-pilot execution isolation and observation-only Shadow mode

- Status: Accepted
- Date: 2026-08-29

## Context

The pilot host has bounded CPU, memory, and optional model capacity. Long model calls must not delay
human review or resolution, and an experimental profile must never participate in a final decision.
Automatic fallback to a different model would also make the evidence chain ambiguous.

## Decision

- Work is routed through three independent lanes: model work at concurrency 1, retrieval work at
  concurrency 2, and policy/human-review/resolution/dry-run work at concurrency 2.
- A process creates each provider client once and reuses its connection pool. Five consecutive
  timeout, 429, or 5xx outcomes open a circuit for 30 seconds; only one probe is admitted after the
  interval. A failed provider is never replaced automatically in the final path.
- Non-terminal model work is limited to four runs globally and four per tenant. Admission uses a
  PostgreSQL advisory transaction lock; an idempotent replay is resolved before quota evaluation.
  Rejected work returns 429 with `Retry-After` and creates no additional run.
- Analysis runs persist an immutable `PRIMARY` or `SHADOW` mode. `SHADOW` is observation-only:
  database triggers and application guards both prohibit policy evaluation, human review,
  resolution, and external-action events from referencing a Shadow run.
- The default retrieval path remains server-fixed to RAW query, HYBRID retrieval, and Top 3. A new
  profile may be activated only after 100 synthetic Shadow comparisons and an explicit version
  switch; existing runs and their version metadata remain unchanged.
- Policy cache identity contains only tenant, index, profile, and content hash. Vision reuse requires
  an exact tenant, evidence digest, model revision, preprocessing version, and threshold-version
  match and records the source result identifier. Inquiry text, inquiry embeddings, provider errors,
  and model responses are not cache material.

## Consequences

- Two slow model calls cannot occupy the decision worker lane, although the target-Mac p95 queue
  objective still requires a measured qualification run.
- Shadow data can be compared without becoming policy or human-decision evidence.
- Hardware-specific model qualification is not transferable; package manifests bind artifact and
  runtime digests, dependency lock, schemas, preprocessing, threshold, device, precision, license,
  SBOM, and qualification results.
- Versioned RabbitMQ dead-letter topology and authenticated replay/cancel are not silently inferred
  from this decision. They require a safe broker migration plus an immutable recovery-operation
  contract and remain a pilot activation gate.

## Related decisions

- [ADR-0009](0009-transactional-outbox-and-fenced-analysis-execution.md)
- [ADR-0011](0011-separate-case-and-analysis-lifecycles.md)
- [ADR-0075](0075-append-only-policy-evaluation-runs.md)
- [ADR-0087](0087-no-automated-execution-of-human-decision.md)
- [ADR-0093](0093-durable-resolution-and-simulation-outboxes.md)
