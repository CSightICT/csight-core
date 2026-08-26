# ADR-0062: Append-only asynchronous grounded explanation runs

- Status: Accepted
- Date: 2026-08-27

## Decision

Create a new grounded explanation run, citation pack reference, and transactional outbox event for
each idempotent request. Dispatch only opaque identifiers through RabbitMQ. A thin Celery task claims
the run, calls the provider outside the database transaction, validates, and appends at most one
result.

## Consequences

Duplicate delivery is a no-op and results are never overwritten. Provider and validation failures
are explicit terminal failures with no silent uncited or deterministic fallback.
