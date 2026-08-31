# Operations Read API

## Purpose and boundary

The operations read API gives one authenticated tenant administrator a bounded view of durable
workflow health. It is read-only, emits `Cache-Control: no-store`, and never performs queue replay,
cancellation, refund, payment, notification, or any other business side effect.

The endpoints are:

- `GET /api/v1/operations/overview`
- `GET /api/v1/operations/failures?lookback_hours=24`

Both endpoints require the `ADMIN` role. The current principal's tenant is the only tenant accepted
by the application service; no tenant selector is exposed over HTTP. `lookback_hours` is bounded to
1–168 hours and the default stalled threshold is five minutes.

## Bounded response dimensions

`overview` always returns seven named queue dimensions and seven processing dimensions:

1. analysis dispatch / analysis;
2. policy retrieval;
3. grounded explanation;
4. policy evaluation;
5. human review;
6. case resolution; and
7. action simulation.

Queue rows expose backlog, pending, processing, published-but-unconsumed, failed, retry, stalled,
oldest-backlog age, and last healthy time. Processing rows expose backlog, running, retry,
partial-success, failed, stalled, oldest-backlog age, and last healthy time. Absent activity is a
zero-valued catalog row rather than a newly invented label.

Active-version rows expose only bounded component names plus model, prompt, policy, threshold, and
index version metadata already persisted by the workflow. The `source` field distinguishes an
actual active record from the latest immutable run snapshot or latest successful result. The list
is deterministically capped at 64 rows. It must not be interpreted as deployment proof when the
source is `latest_run_snapshot` or `latest_succeeded_result`.

`failures` returns the same seven component dimensions and, for each component, aggregate failed,
partial-success, retry, and currently stalled signal counts. It includes at most three normalized
failure codes per component. Provider messages, exception text, raw inputs, outputs, inquiry text,
object keys, tenant IDs, case IDs, run IDs, and event IDs are never returned.

The PostgreSQL adapter executes one aggregate statement per endpoint. This bounds query round trips
and avoids loading workflow ORM objects into application memory. Counts are operational signals:
one workflow condition and one delivery condition may both be counted because they represent
separate remediation surfaces.

## Replay and cancellation blocker

Replay and cancellation are intentionally not implemented. Accepted ADR-0011 prohibits reviving a
terminal analysis run and requires reanalysis to create a new immutable run; ADR-0075 applies the
same append-only rule to policy evaluation. The durable outboxes in ADR-0093 are fenced by event
identity and preserve terminal delivery failure records. The current application has no accepted,
cross-workflow operator contract that defines all of the following:

- which terminal states are eligible and which actor role may request the operation;
- a new immutable operation/event identity and idempotency key;
- whether replay creates a new analysis/retrieval/evaluation/resolution/simulation run;
- how a queued or claimed item is fenced without mutating historical result or attempt rows;
- how cancel races with a worker that already owns a live claim; and
- the append-only audit event, reason-code vocabulary, and downstream side-effect boundary.

Adding a generic `replay` or `cancel` endpoint before that contract exists could overwrite history,
duplicate a business action, or make a terminal record appear mutable. An accepted ADR plus
workflow-specific application commands, persistence invariants, and race tests are required before
either mutation is exposed.

## Composition wiring

The feature is isolated so shared composition files can be wired in one controlled change:

1. Build `OperationsServiceContainer` with
   `app.bootstrap.operations.build_operations_services(settings)` when a database is configured.
2. Store it at `application.state.operations_services`.
3. Include `app.interface.http.routers.operations.router` in the FastAPI application and, if the
   router package maintains public exports, export it there.

The feature-specific provider lives in `app.interface.http.operations_services`; no shared
permission enum or common dependency-provider change is required. Authorization is enforced again
inside both application services, so directly calling a use case cannot bypass the admin check.
