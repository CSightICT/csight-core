# ADR-0075: Policy evaluation runs are append-only

- Status: Accepted
- Date: 2026-08-27

## Decision

Re-evaluation creates a new run. The repository exposes no result update, overwrite, or delete;
one successful run appends rule, condition, and effect results once.

## Consequences

Duplicate tasks become no-ops and historical outputs remain available for audit.
