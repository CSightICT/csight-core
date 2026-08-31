# ADR-0102: Sensitive Case payloads move through an additive lifecycle boundary

- Status: Accepted
- Date: 2026-08-29

## Context

The Case aggregate currently stores customer prose beside operational state. Rebuilding the mature
append-only schema is higher risk than introducing a restricted boundary incrementally. Evidence
uploads also need request-level idempotency and a security gate before real customer images are
accepted.

## Decision

The first migration is an expand phase:

- `case_sensitive_payloads` stores customer prose, its non-reversible SHA-256 digest, an explicit
  retention-policy version, expiry, and purge state;
- `data_lifecycle_events` records PII-free append-only create, migration, reconciliation, and purge
  events;
- Case creation dual-writes the existing compatibility column and the restricted payload in one
  transaction;
- Case reads prefer the restricted payload while the compatibility column remains for one release;
- existing rows are backfilled without changing Case identity or history; and
- Evidence upload keys are unique within `(tenant_id, case_id, idempotency_key)`, and a replay with
  a different digest fails closed.

Production composition has no implicit retention default. It also refuses to accept Evidence
unless metadata-stripping re-encoding and a configured ClamAV adapter are enabled. Local and test
profiles may use network-free inspection or sanitization with an explicit non-production scanner.

The legacy Case column is not removed or purged in this phase. Contract migration is permitted only
after dual-write parity, backfill completeness, rollback, and read-path verification have passed in
the target environment. Purge jobs must not claim erasure while the compatibility copy exists.

## Follow-up

[ADR-0108](0108-retention-purge-and-evidence-reconciliation.md) defines the guarded follow-up
migration. It retains the legacy column for response compatibility but removes expired prose from
both copies atomically, replaces the legacy value with a fixed PII-free tombstone, eliminates
operational fallback, and blocks upgrade when backfill or dual-write parity is incomplete. Full
legacy-column removal remains deferred.

## Consequences

- The change is additive and rollback-safe; existing Case IDs and append-only workflow records are
  preserved.
- Retention is customer onboarding configuration, not application guesswork.
- EXIF orientation is applied before metadata-free re-encoding, and both inbound and normalized
  bytes are malware-scanned before private object storage.
- The current release establishes the lifecycle boundary but does not yet claim that expired legacy
  prose has been erased.
- Learning assets continue to exclude raw inquiry text and direct identifiers.

## Related decisions

- [ADR-0004](0004-tenant-isolation-and-access-control.md)
- [ADR-0006](0006-private-evidence-storage.md)
- [ADR-0014](0014-analysis-evidence-snapshot.md)
